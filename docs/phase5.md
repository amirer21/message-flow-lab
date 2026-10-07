# Phase 5 · 실패, Retry, DLQ

## 학습 질문

다시 처리할 실패와 격리할 실패는 어떻게 나눌까?

## 예상과 관찰

| 시나리오 | 동작 | 예상 결과 |
|---|---|---|
| transient_2x | retry_count < 2이면 실패, ≥ 2이면 성공 | 시도 3회, 성공 1회 |
| permanent | 항상 영구 실패 | 즉시 DLQ 격리, 재시도 없음 |
| retry_exceed | 항상 일시 실패 | 3회 재시도 후 DLQ |

## 토폴로지

```
phase5.{uid}.work (direct, durable)
  └─ phase5.{uid}.work.q (durable, binding key="job")

phase5.{uid}.retry (direct, durable)
  └─ phase5.{uid}.retry.q (durable, TTL=5000ms, DLX→work exchange)

phase5.{uid}.dead (direct, durable)
  └─ phase5.{uid}.dead.q (durable, binding key="job")
```

## 핵심 개념

### Retry vs Requeue

- **Requeue** (`basic_nack(requeue=True)`): 메시지를 Queue 앞에 즉시 돌려놓음. 횟수 제한 없음, CPU/네트워크 낭비.
- **Retry Queue**: 별도 Queue에 TTL을 설정하여 대기 시간 확보. 헤더로 횟수 추적 및 제한.

### DLQ (Dead Letter Queue)

재시도할 수 없는 메시지를 격리하는 Queue. 영구 실패(잘못된 형식, 누락 필드)와 재시도 한도 초과 메시지가 저장됨. 수동 분석 후 재발행 또는 폐기.

### TTL + DLX

retry.q에 `x-message-ttl=5000`을 설정하면 메시지가 5초 후 만료됨. `x-dead-letter-exchange`로 지정한 work exchange로 자동 이동.

## 처리 흐름

1. work.q에서 메시지 소비
2. 시나리오와 retry_count로 판정 (success / retry / dlq)
3. retry: retry exchange에 새 메시지 발행 (retry_count+1) → 원본 ACK
4. dlq: dead exchange에 발행 → 원본 ACK
5. success: 업무 기록 → 원본 ACK

## 완료 기준

- [ ] Retry와 즉시 Requeue의 차이를 설명한다.
- [ ] 영구 실패와 일시 실패를 분류하는 기준을 설명한다.
- [ ] 무한 재전달을 방지하는 방법을 확인했다.
- [ ] DLQ에 격리된 메시지의 활용 방법을 설명한다.

## 관찰할 때 기억하세요

즉시 Requeue를 반복하면 실패 메시지가 자원을 계속 차지할 수 있습니다. TTL이 있는 별도 retry Queue로 대기 시간을 두고 재시도 횟수를 제한합니다. DLQ의 메시지는 자동 복구 대상이 아니라 분석 후 수동 처리합니다.
