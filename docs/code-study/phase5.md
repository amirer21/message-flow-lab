# Phase 5 · 실패·Retry·DLQ 코드

학습 목표: 일시 실패와 영구 실패를 분류하고, TTL 기반 재시도 Queue와 DLQ 토폴로지의 동작을 코드로 설명합니다.

## 1. 읽을 파일과 라이브러리

| 파일 | 주요 코드 | 라이브러리 |
|---|---|---|
| [PhaseFive.vue](../../frontend/src/PhaseFive.vue) | run, process, tick 폴링, 시나리오 선택 | Vue, fetch 요청 helper |
| [retry.ts](../../frontend/src/retry.ts) | DemoRetry, decide, tick, TTL 시뮬레이션 | TypeScript |
| [retry.py](../../backend/app/retry.py) | RetryLab, _decide, process, 토폴로지 | FastAPI, Pydantic, Pika, Queue, Future, Thread |
| [main.py](../../backend/app/main.py) | include_router, lifespan shutdown | 공통 인증과 종료 연결 |
| [test_retry.py](../../backend/tests/test_retry.py) | 시나리오별 판정, 교환기 라우팅, ACK 검증 | unittest, mock, TestClient |
| [smoke_phase5.py](../../scripts/smoke_phase5.py) | 실제 TTL 대기, 3가지 시나리오 검증 | HTTPX |

## 2. 토폴로지

```
phase5.{uid}.work (direct, durable)
  └─ phase5.{uid}.work.q (durable, binding key="job")

phase5.{uid}.retry (direct, durable)
  └─ phase5.{uid}.retry.q (durable, TTL=5000ms, DLX→work exchange, DLR key="job")

phase5.{uid}.dead (direct, durable)
  └─ phase5.{uid}.dead.q (durable, binding key="job")
```

retry.q의 `x-message-ttl`은 5000ms입니다. 만료되면 RabbitMQ의 DLX 기능이 메시지를 work exchange로 재라우팅합니다. `x-dead-letter-routing-key`가 "job"이므로 work.q로 돌아갑니다.

## 3. 요청 모델과 API

| 경로 | 요청·모델 | 동작 |
|---|---|---|
| GET /retry/snapshot | 토큰 | 현재 토폴로지·Queue Ready·이벤트 조회 |
| POST /retry/setup | 빈 body | 이전 토폴로지 삭제 후 새 실험 |
| POST /retry/publish | RetryPublishRequest(body, scenario) | work.q에 메시지 발행 |
| POST /retry/process | 빈 body | work.q에서 1개 소비 → 시나리오별 판정 |

## 4. 처리 의사결정 (`_decide`)

| 시나리오 | retry_count 조건 | 결과 |
|---|---|---|
| `transient_2x` | < 2 | retry |
| `transient_2x` | ≥ 2 | success |
| `permanent` | 무관 | dlq (항상) |
| `retry_exceed` | < MAX_RETRIES(3) | retry |
| `retry_exceed` | ≥ MAX_RETRIES(3) | dlq |

## 5. process() 흐름

1. `basic_get(work.q)` → 메시지 1개 가져오기
2. headers에서 `x-retry-count`, `x-scenario` 읽기
3. `x-death` 헤더 존재 시 `RETRY_RETURNED` 이벤트 기록 (DLX 경유 증거)
4. `_decide(scenario, retry_count)` 호출
5. 결과에 따라:
   - **success**: `PROCESSING_SUCCEEDED` 기록 → 원본 ACK
   - **retry**: retry exchange에 새 메시지 발행 (retry_count+1) → Confirm → 원본 ACK
   - **dlq**: dead exchange에 메시지 발행 → Confirm → 원본 ACK

원본 메시지는 어떤 결과든 항상 ACK됩니다. Retry 시 새 메시지를 발행하고 원본을 ACK하므로, 그 사이 장애가 발생하면 메시지가 중복될 수 있습니다.

## 6. 이벤트 타입

| 이벤트 | 의미 |
|---|---|
| `TOPOLOGY_CREATED` | 새 실험 시작 |
| `PUBLISH_SENT` | 발행 요청 전송 |
| `PUBLISH_CONFIRMED` | Broker Confirm ACK |
| `PROCESSING_STARTED` | work.q에서 메시지 소비 시작 |
| `PROCESSING_FAILED` | 시나리오에 의한 처리 실패 |
| `PROCESSING_SUCCEEDED` | 처리 성공 |
| `RETRY_SCHEDULED` | retry exchange에 재발행 완료 |
| `RETRY_RETURNED` | DLX 경유로 work.q에 복귀 감지 (x-death 헤더) |
| `DLQ_STORED` | dead exchange에 격리 완료 |
| `ACK_SENT` | 원본 메시지 ACK |

## 7. 브라우저 예시 (DemoRetry)

`retry.ts`의 `DemoRetry`는 실제 Broker 없이 동작합니다. `tick()` 메서드가 2초마다 호출되어 retry queue의 메시지 중 enqueued_at + 5000ms가 지난 것을 work queue로 이동합니다.

## 8. 학습 문제

1. `basic_nack(requeue=True)`와 별도 retry Queue의 차이는 무엇인가?
2. retry exchange에 발행 후 원본 ACK 전에 장애가 발생하면 어떤 상태가 되는가?
3. DLQ에 격리된 메시지를 어떻게 활용할 수 있는가?
4. TTL이 정확히 5000ms 후에 만료된다고 보장할 수 있는가?
5. MAX_RETRIES를 늘리면 항상 더 안전한가?
