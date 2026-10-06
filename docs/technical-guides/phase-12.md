# Phase 12 · Outbox로 DB와 발행 사이의 중단 복구

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

DB 저장과 RabbitMQ 발행은 하나의 DB transaction으로 묶이지 않습니다. Outbox는 “보낼 이벤트”도 업무와 같은 DB에 commit하고 Relay가 나중에 발행하도록 만들어 미발행 상태를 복구할 수 있게 합니다.

## 전체 흐름

업무 + outbox 같은 commit → Relay가 미발행 row claim → 네트워크 발행 / Confirm → published 표시 → 멱등 Consumer 업무 commit

## 용어

- **Dual write**: DB 변경과 메시지 발행을 서로 다른 시스템에 수행하는 두 작업입니다. 사이에 실패할 수 있습니다.
- **Outbox / Relay**: Outbox는 아직 발행할 이벤트의 DB 테이블, Relay는 이를 읽어 Broker에 보내는 프로세스입니다.
- **Lease / SKIP LOCKED**: 처리 소유 기간과 잠긴 행을 건너뛰는 DB 방식입니다. 여러 Relay의 경쟁과 중단 회수를 설계합니다.
- **At-least-once 영향**: 발행 확인 후 DB 표시 전에 죽으면 재발행할 수 있습니다. 소비 업무의 멱등 보호를 함께 씁니다.

## 어떤 유실 경로를 바꿀까요?

업무 DB commit 후 바로 메시지를 보내는 구조에서는 발행 전 종료하면 DB 업무만 남고 이벤트가 사라질 수 있습니다. Outbox row를 업무와 같은 transaction으로 저장하면 발행 의도가 DB에 남아 Relay가 다시 찾을 수 있습니다.

반대로 발행을 먼저 하고 DB를 저장하면 발행된 이벤트가 rollback된 업무를 가리킬 수 있습니다. commit된 outbox만 발행하는 경로로 이 문제를 피합니다. 업무와 Outbox가 서로 다른 DB면 같은 단일 transaction으로 보호할 수 없습니다.

## Relay의 claim과 네트워크 작업

FOR UPDATE SKIP LOCKED로 미발행 row를 고르고 짧은 transaction에서 lease를 갱신한 뒤 commit합니다. 네트워크 발행은 이 transaction 밖에서 하여 오래 DB lock을 붙잡지 않습니다.

Lease는 영원한 잠금이 아닙니다. Relay가 죽으면 만료 후 다른 Relay가 회수합니다. lease 기간, 재시도 backoff, 늦게 살아난 이전 Relay의 완료 표시 방지와 안정된 event_id가 필요합니다.

## Outbox가 중복 발행을 없애지는 않습니다

Broker가 Confirm했지만 Relay가 published 표시 전에 죽으면 같은 outbox를 다시 발행할 수 있습니다. 항상 같은 event_id/업무 키를 사용하고 Phase 6 Consumer가 중복 업무를 막아야 합니다.

검증은 Broker 중단 중 commit 성공·Outbox 적체, 복구 후 전송, Confirm 후 표시 전 Relay 종료로 나눕니다. 이벤트는 시각과 source를 기록하며 Broker 내부 Routing 시각을 만들어 내지 않습니다.

## 설계 예시 · Outbox와 claim SQL

```sql
CREATE TABLE outbox (
    event_id UUID PRIMARY KEY,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    lease_owner UUID,
    lease_until TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 짧은 transaction에서 한 건 claim. %s는 DB 드라이버 인자입니다.
WITH candidate AS (
    SELECT event_id FROM outbox
    WHERE published_at IS NULL AND next_attempt_at <= now()
      AND (lease_until IS NULL OR lease_until < now())
    ORDER BY created_at
    LIMIT 1 FOR UPDATE SKIP LOCKED
)
UPDATE outbox o SET lease_owner = %s,
    lease_until = now() + interval '30 seconds'
FROM candidate c WHERE o.event_id = c.event_id
RETURNING o.event_id, o.payload;
```

- 업무 테이블 변경과 최초 outbox INSERT는 별도의 하나의 transaction으로 함께 commit해야 합니다. 이 코드에는 업무 테이블이 생략됐습니다.
- claim SQL을 Psycopg conn.execute로 실행하고 lease_owner에 이번 claim의 새 UUID를 전달합니다. 반환 row가 없으면 현재 할 일이 없습니다.

## 설계 예시 · Confirm 후 소유권 확인하여 완료 표시

```python
import json
import pika

def send_claimed(conn, ch, event_id, payload, claim_token):
    # claim transaction은 이미 commit된 상태. ch는 Confirm 모드.
    ch.basic_publish(
        exchange="phase12.events", routing_key="job", mandatory=True,
        body=json.dumps(payload).encode("utf-8"),
        properties=pika.BasicProperties(
            message_id=str(event_id), delivery_mode=2,
            content_type="application/json",
        ),
    )
    with conn.transaction():
        conn.execute(
            "UPDATE outbox SET published_at = now(), lease_until = NULL "
            "WHERE event_id = %s AND lease_owner = %s "
            "AND lease_until > now() AND published_at IS NULL",
            (event_id, claim_token),
        )
```

- ch.confirm_delivery()와 토폴로지가 사전에 준비돼야 합니다. 발행 오류가 나면 완료 UPDATE를 실행하지 않습니다.
- 발행 성공과 UPDATE 사이가 중복 가능 지점입니다. lease가 만료되어 UPDATE가 0행이면 다시 발행될 수 있어 Consumer 멱등성이 필수입니다.
- 실제 Relay에는 bounded backoff, 실패 이유·attempts·영구 격리, 주기 polling, lease 회수, 인덱스·종료 처리와 payload 검증이 더 필요합니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 전용 Broker 중단 중 업무 저장 | 업무와 미발행 Outbox가 함께 남음 | 발행 의도가 DB에 영속화됩니다. |
| Broker 복구 | 적체 감소·Consumer 효과 대조 | 단순 발행 수가 아니라 업무 결과까지 확인합니다. |
| Confirm 후 UPDATE 전 Relay 종료 | 동일 이벤트 재발행, 업무 효과 1회 | Relay 중복 가능성과 멱등 Consumer를 함께 검증합니다. |

## 주의할 오해

- Outbox를 exactly-once 발행 기능이라고 설명하지 않습니다.
- Relay가 선택한 row를 먼저 published로 바꾸고 나중에 발행하면 장애 시 복구할 미발행 이벤트를 숨깁니다.

## 설명해 보기

- 업무와 Outbox를 같은 transaction에 넣는 이유는 무엇인가요?
- 네트워크 작업을 DB row lock 안에서 오래 실행하면 어떤 문제가 생기나요?

## 참고 자료

- [PostgreSQL SKIP LOCKED](https://www.postgresql.org/docs/current/sql-select.html)
- [프로젝트 Outbox 설계안](https://github.com/amirer21/message-flow-lab/blob/main/docs/remaining-development-plan.md)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
