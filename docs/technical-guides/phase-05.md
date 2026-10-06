# Phase 5 · 제한된 Retry와 DLQ의 역할

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

실패를 모두 재시도하면 한 메시지가 계속 자원을 차지할 수 있습니다. 다시 실행하면 해결될 실패와 입력 자체가 잘못된 실패를 분류하고, 시도 횟수와 대기를 제한합니다.

## 전체 흐름

작업 Queue → 일시 실패 → Confirm된 Retry 발행 → TTL 대기 → 작업 Queue → 한도 초과 → DLQ

## 용어

- **NACK / reject**: Consumer가 전달을 완료하지 못했다고 알리는 동작입니다. requeue 옵션에 따라 되돌리거나 DLX로 이동할 수 있습니다.
- **Retry / Requeue**: Retry는 새 시도·횟수·대기 정책, requeue는 전달을 Queue로 돌리는 Broker 동작입니다.
- **TTL / DLX / DLQ**: TTL은 대기 데이터의 만료 설정, DLX는 만료·거절된 메시지를 분배하는 Exchange, DLQ는 최종 격리 Queue입니다.
- **retry_count / x-death**: 앱의 시도 헤더와 Broker의 dead-letter 이력입니다. 같은 의미로 무작정 합산하지 않습니다.

## 실패를 분류하는 기준

네트워크 일시 오류는 잠시 뒤 다시 시도할 수 있습니다. 필수 필드 누락은 같은 입력을 반복해도 해결되지 않으므로 바로 격리할 수 있습니다. 최대 추가 재시도 3회라면 최초 실행을 포함해 최대 4회라는 기준도 명시합니다.

backoff는 시간이 지나며 대기를 늘리는 정책입니다. 무제한 immediate requeue는 poison message가 실패를 빠르게 반복하는 상황을 만들 수 있습니다. DLQ는 문제를 자동 해결하지 않고 조사 가능한 곳에 격리합니다.

## TTL + Dead Letter 경로

예시 토폴로지는 work Exchange/Queue, retry Exchange/Queue, dead Exchange/Queue로 나눕니다. retry Queue에 5초 TTL과 작업 Exchange로 돌아오는 DLX를 지정합니다. TTL이 지나면 재시도할 메시지를 작업 Queue로 다시 전달합니다.

TTL은 정확한 예약 실행 시각을 보장하는 스케줄러가 아닙니다. 메시지 크기·적체·Queue 종류·Broker 상태에 따라 관측 시간이 달라집니다. production에서는 변경 가능한 Broker policy와 DLX 전달 안전성도 검토합니다.

## 재발행과 원본 ACK 사이의 순서

앱이 retry_count를 늘려 새 메시지를 발행한다면 발행 확인 후 원본 ACK를 보냅니다. 새 발행이 실패했는데 원본을 ACK하면 두 위치 모두에서 사라질 수 있습니다.

반대로 새 발행 확인 뒤 원본 ACK 전 종료하면 원본이 재전달되며 Retry 복사본도 남을 수 있습니다. 멱등성 없이는 중복 업무가 생길 수 있으므로 Phase 6과 연결합니다.

## 설계 예시 · Retry Queue의 TTL/DLX 토폴로지

```python
# ch는 연결된 Pika channel
ch.exchange_declare(exchange="phase5.work", exchange_type="direct", durable=True)
ch.exchange_declare(exchange="phase5.retry", exchange_type="direct", durable=True)
ch.exchange_declare(exchange="phase5.dead", exchange_type="direct", durable=True)
ch.queue_declare(queue="phase5.work.q", durable=True)
ch.queue_bind(queue="phase5.work.q", exchange="phase5.work", routing_key="job")
ch.queue_declare(queue="phase5.retry.q", durable=True, arguments={
    "x-message-ttl": 5000,
    "x-dead-letter-exchange": "phase5.work",
    "x-dead-letter-routing-key": "job",
})
ch.queue_bind(queue="phase5.retry.q", exchange="phase5.retry", routing_key="job")
ch.queue_declare(queue="phase5.dead.q", durable=True)
ch.queue_bind(queue="phase5.dead.q", exchange="phase5.dead", routing_key="job")
```

- 이 선언은 메시지의 길만 만듭니다. 실패 분류·Retry 재발행·원본 ACK 코드는 별도로 구현합니다.
- 추가 시도 횟수는 앱 헤더로 관리하고 한도 초과 시 phase5.dead로 발행합니다. 선언만으로 제한이 생기지는 않습니다.
- 교육용 고정 arguments 예시입니다. 기존 Queue의 arguments 변경은 속성 충돌이 생길 수 있어 새 자원 또는 migration/policy가 필요합니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 일시 실패 2회 후 성공 | 시도 3회, 성공 효과 1회 | 최초 실행과 재시도 횟수를 구분합니다. |
| 입력 영구 오류 | 즉시 최종 DLQ | 같은 입력 반복은 해결되지 않습니다. |
| 재발행 확인 후 원본 ACK 전 종료 | 중복 후보 관측 | 두 메시지 작업 사이에 원자성이 없습니다. |

## 주의할 오해

- DLQ를 화면에서 보려고 basic_get하면 실제로 소비합니다. 일반 목록은 저장한 이력으로 조회합니다.
- DLX를 사용한다고 모든 Queue에서 장애 중 이동 유실 가능성이 없어지는 것은 아닙니다. Queue 종류와 정책을 확인합니다.

## 설명해 보기

- max_retries=3을 총 3회 실행과 구분해서 설명할 수 있나요?
- Retry 메시지 발행을 확인하기 전에 원본을 ACK하면 어떤 위험이 있나요?

## 참고 자료

- [RabbitMQ DLX](https://www.rabbitmq.com/docs/dlx)
- [RabbitMQ TTL](https://www.rabbitmq.com/docs/ttl)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
