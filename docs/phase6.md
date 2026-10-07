# Phase 6 · 멱등성 (Idempotency)

## 학습 질문

같은 요청이 두 번 와도 결과를 한 번만 반영할까?

## 예상과 관찰

| 시나리오 | 동작 | 예상 결과 |
|---|---|---|
| normal | 메시지 1건 발행 → 처리 | 업무 효과 1건 기록 |
| duplicate | 같은 키로 2건 발행 → 각각 처리 | 업무 효과 여전히 1건 |
| crash_after_commit | DB commit 후 ACK 전 장애 → 재전달 | 업무 효과 중복 없음 |

## 토폴로지

```
phase6.{uid}.work (direct, durable)
  └─ phase6.{uid}.work.q (durable, binding key="job")

SQLite DB (data/idempotency.db)
  ├─ processed_commands (consumer_scope, idempotency_key) ← UNIQUE
  └─ business_effects (id, consumer_scope, idempotency_key, amount, created_at)
```

## 핵심 개념

### Idempotency Key

각 메시지에 포함된 고유 식별자. 같은 키의 메시지가 여러 번 처리되어도 업무 효과를 한 번만 반영하기 위한 기준값.

### Unique Constraint

`processed_commands` 테이블의 `(consumer_scope, idempotency_key)` 복합 기본키. `INSERT OR IGNORE`로 삽입을 시도하면 이미 존재하는 키는 무시됨.

### Transaction

중복 검사(`INSERT OR IGNORE`)와 업무 효과 기록(`INSERT INTO business_effects`)을 하나의 트랜잭션으로 묶어 원자성을 보장. 두 작업이 모두 성공하거나 모두 실패함.

### Commit-then-ACK

DB에 먼저 커밋한 뒤 RabbitMQ에 ACK를 보내는 순서. 커밋 후 ACK 전에 장애가 발생하면 메시지가 재전달되지만, unique constraint가 중복 효과를 방어함.

## 처리 흐름

1. work.q에서 메시지 소비 (auto_ack=False)
2. DB 트랜잭션 시작
3. `INSERT OR IGNORE INTO processed_commands` 실행
4. 새 행이 생성되면 `INSERT INTO business_effects` 실행
5. 트랜잭션 커밋
6. RabbitMQ ACK 전송

## 완료 기준

- [ ] 중복 수신에도 업무 효과가 한 번만 발생함을 확인했다.
- [ ] DB unique constraint로 중복을 방지하는 원리를 설명한다.
- [ ] Commit 후 ACK 전 장애에서 재전달 메시지의 중복 방어를 확인했다.
- [ ] 메시지를 한 번만 받는 보장과 업무 효과를 한 번만 반영하는 설계의 차이를 설명한다.

## 관찰할 때 기억하세요

Exactly-once delivery는 분산 시스템에서 사실상 불가능합니다. 대신 at-least-once delivery + idempotent processing으로 exactly-once semantics를 달성합니다. 메시지를 한 번만 받는 보장과 업무 효과를 한 번만 반영하는 설계는 구분해야 합니다.
