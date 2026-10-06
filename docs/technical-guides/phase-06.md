# Phase 6 · DB 트랜잭션으로 업무 효과를 한 번만

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

같은 메시지가 다시 와도 업무 결과를 한 번만 반영하는 것이 멱등성입니다. 메시지의 중복 수신을 없애려 하기보다, DB가 업무 중복을 판정하고 변경을 한 묶음으로 commit하도록 설계합니다.

## 전체 흐름

idempotency_key 읽기 → 고유 키 INSERT → 같은 트랜잭션의 업무 변경 → DB commit → 그 뒤 Consumer ACK

## 용어

- **Idempotency key**: 논리 업무를 식별하는 안정된 키입니다. 전송 UUID와 같아야 하는 것은 아닙니다. 같은 주문 처리에는 같은 업무 키를 사용합니다.
- **Unique constraint**: DB가 동시 실행에서도 같은 키를 둘 이상 저장하지 못하게 하는 제약입니다.
- **Transaction**: 여러 DB 변경을 모두 commit하거나 모두 rollback하는 경계입니다.
- **Consumer scope**: 같은 이벤트를 서로 다른 목적의 Consumer가 처리할 수 있도록 중복 판정 범위를 분리하는 값입니다.

## 메모리 set이나 SELECT로 충분하지 않은 이유

처리한 키를 메모리 set에 넣으면 프로세스 재시작 시 잊습니다. SELECT로 먼저 조회한 뒤 업무를 처리하면 Worker A/B가 동시에 “없다”고 보고 둘 다 처리할 수 있습니다.

PostgreSQL 고유 제약과 INSERT ... ON CONFLICT DO NOTHING ... RETURNING으로 한 실행만 처리 권한을 얻습니다. 키 기록과 업무 변경은 같은 트랜잭션에 있어야 합니다.

## DB commit과 ACK의 순서

업무가 rollback되면 처리 키도 rollback해야 다음 시도가 업무를 다시 수행할 수 있습니다. commit 전에 ACK하면 DB 오류 시 메시지만 완료 처리될 수 있습니다.

commit 후 ACK 전에 죽으면 재전달됩니다. 이번에는 처리 키가 이미 있으므로 업무를 반복하지 않고 ACK할 수 있습니다. 이 방식은 같은 DB 안의 업무 효과를 보호하며 외부 이메일·결제를 자동으로 원자 처리하지는 않습니다.

## 데이터 모델과 관측

processed_commands에는 consumer_scope와 idempotency_key의 복합 고유 키를 둡니다. business_effects에는 실제 학습용 업무 결과를 저장합니다. 이력에는 run_id·message_id·attempt_id를 함께 남겨 재전달과 업무 중복 방어를 구분합니다.

아래 예시는 Psycopg 3 connection·channel을 이미 준비했다고 가정합니다. transaction context를 벗어나야 commit이 완료되므로 ACK는 with 블록 바깥입니다.

## 설계 예시 · 고유 제약과 같은 트랜잭션의 업무 기록

```sql
CREATE TABLE processed_commands (
    consumer_scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    PRIMARY KEY (consumer_scope, idempotency_key)
);
CREATE TABLE business_effects (
    consumer_scope TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    amount INTEGER NOT NULL
);
```

- 먼저 migration으로 테이블을 만듭니다. 업무와 처리 키가 별도 DB에 있으면 이 단일 트랜잭션 예시를 그대로 적용할 수 없습니다.

## 설계 예시 · commit 이후 ACK

```python
def handle_job(conn, ch, delivery_tag, key, amount):
    with conn.transaction():
        row = conn.execute(
            "INSERT INTO processed_commands VALUES (%s, %s) "
            "ON CONFLICT DO NOTHING RETURNING idempotency_key",
            ("billing-demo", key),
        ).fetchone()
        if row is not None:
            conn.execute(
                "INSERT INTO business_effects VALUES (%s, %s, %s)",
                ("billing-demo", key, amount),
            )
    ch.basic_ack(delivery_tag=delivery_tag)
```

- row가 있는 실행만 처음 처리한 권한을 얻어 업무를 반영합니다. 충돌한 실행은 기존 업무가 commit된 후 중복으로 판정됩니다.
- 두 INSERT는 같은 transaction입니다. 업무 INSERT가 예외이면 키 INSERT도 rollback하고 ACK하지 않습니다.
- conn은 유효한 Psycopg 3 connection으로 외부 transaction이 없는 상태를 가정합니다. 실제 Worker의 retry·연결 복구·오류 분류는 별도입니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 같은 업무 키를 두 Worker가 동시에 처리 | 업무 효과 1개 | DB 고유 제약이 경쟁을 판정합니다. |
| 업무 INSERT 직전에 오류 | 키·업무 모두 rollback | 재전달이 정상 작업을 이어갈 수 있습니다. |
| commit 후 ACK 전 종료 | 재전달되지만 효과는 1개 | 영속 처리 키가 중복을 방어합니다. |

## 주의할 오해

- 먼저 processed를 commit하고 나중에 업무를 변경하면 장애 시 영원히 미처리 상태가 될 수 있습니다.
- Message ID를 매 발행 새로 생성하면 같은 업무 재요청 판정에는 안정된 별도 업무 키가 필요합니다.

## 설명해 보기

- SELECT 후 INSERT와 고유 제약 경쟁 처리는 어떻게 다른가요?
- 이 설계가 외부 이메일 전송까지 한 번만 보장하지 못하는 이유는 무엇인가요?

## 참고 자료

- [PostgreSQL ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html)
- [PostgreSQL 트랜잭션 격리](https://www.postgresql.org/docs/current/transaction-iso.html)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
