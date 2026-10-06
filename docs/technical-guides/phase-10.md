# Phase 10 · Celery Retry·ACK·Worker 종료를 구분

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

Task Framework에도 장애 위치별 결과가 있습니다. Worker 실행 자식이 죽은 상황, 전체 연결이 닫힌 상황, Task가 스스로 Retry를 요청한 상황을 같은 실패로 묶지 않습니다.

## 전체 흐름

Task Queue 분기 → Worker 실행 → early / late ACK 정책 → retry 또는 worker-lost → Task 이력 + 업무 결과 비교

## 용어

- **early / late ACK**: 실행 이전 확인과 실행 이후 확인 정책입니다. 실제 실패/종료 처리는 추가 설정 영향을 받습니다.
- **self.retry**: Celery가 다음 Task 시도를 발행하는 동작입니다. Broker가 ACK 없는 전달을 되돌리는 것과 다릅니다.
- **task_reject_on_worker_lost**: 실행 자식의 갑작스러운 종료 시 requeue 동작에 영향을 주는 설정입니다. 반복 실패 Task는 무한 재실행을 주의합니다.
- **Routing / Events**: Task를 특정 Queue로 보내는 설정과 Worker가 보내는 실행 관측 이벤트입니다. 이벤트 수집에도 중단·누락이 가능합니다.

## ACK 시점만으로 설명이 끝나지 않습니다

early ACK이면 실행 중 전체 Worker가 사라졌을 때 Broker는 이미 확인된 작업을 다시 줄 수 없습니다. late ACK는 실행 후 확인을 목표로 하지만 실행 자식이 사라지는 경우에도 무조건 requeue되는 것은 아닙니다.

task_reject_on_worker_lost, 실패/timeout ACK 정책, 전체 Worker와 자식 종료 여부를 따로 기록해야 합니다. 같은 설정 이름의 의미도 설치 Celery 버전 문서와 실제 장애 실험으로 확인합니다.

## Retry가 유지하는 것과 새로 생기는 것

self.retry는 같은 Task ID의 추가 실행 요청을 만들 수 있습니다. 시도 기록에는 retries·새 attempt_id·Worker·시각을 포함해 하나의 Task가 몇 번 실행됐는지 구분합니다.

Task가 retry_count를 늘린 것과 Broker redelivered는 서로 다른 축입니다. 영구 실패를 무조건 autoretry하지 않고 특정 일시 예외만 bounded retry합니다. 중복 가능한 업무는 Phase 6의 보호를 사용합니다.

## 관측 결과를 대조하기

Celery Event Collector가 Worker 이벤트를 받아 저장하고 Task 화면을 갱신합니다. 수집기가 죽으면 이벤트가 빠질 수 있어 이벤트 없음이 실행 없음이라는 증거가 아닙니다. Broker 지표·Result Backend·업무 DB도 대조합니다.

설정 변경은 실행 프로필로 기록하고 해당 Worker를 재시작하여 적용을 확인합니다. 전체 Broker를 종료하지 않고 제어기가 소유한 고정 Worker만 장애 대상으로 선택합니다.

## 설계 예시 · Queue 분리와 제한된 Retry

```python
# app은 Phase 9에서 구성한 Celery 앱
app.conf.task_routes = {"lab.flaky": {"queue": "phase10.slow"}}

@app.task(bind=True, name="lab.flaky", max_retries=3,
          acks_late=True, reject_on_worker_lost=True)
def flaky(self, failures_before_success=2):
    if self.request.retries < failures_before_success:
        delay = min(2 ** self.request.retries, 30)
        raise self.retry(exc=ConnectionError("학습용 일시 오류"), countdown=delay)
    return {"attempt_number": self.request.retries + 1, "status": "ok"}
```

- 이 코드는 실제 외부 호출 대신 학습용 실패를 만듭니다. failures_before_success=2이면 세 번째 실행에서 성공합니다.
- max_retries는 추가 재시도 한도입니다. reject_on_worker_lost=True는 모든 업무에 무조건 권장하는 기본값이 아니라 비교할 실험 프로필입니다.
- 실제 구성은 ACK-on-failure/timeout, prefetch, concurrency, serializer 등 다른 설정도 저장해 종료 결과를 재현해야 합니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 일시 실패를 self.retry로 2번 반복 | Task ID의 시도 3개 | 추가 Task 발행 Retry를 관찰합니다. |
| late ACK 자식 프로세스 강제 종료 | 설정별 requeue 결과 비교 | 자식 종료와 전체 Worker 연결 종료를 분리합니다. |
| Event Collector만 중단 | 업무 진행 여부 별도 대조 | 관측 중단과 실행 중단은 다릅니다. |

## 주의할 오해

- task_reject_on_worker_lost를 켠 poison task는 계속 Worker를 잃는 반복을 만들 수 있습니다. 격리·상한이 필요합니다.
- revoke나 warm shutdown은 실행 자식 강제 종료와 같은 장애가 아닙니다. 실제 방식과 시점을 기록합니다.

## 설명해 보기

- Celery Retry와 RabbitMQ 재전달을 어떤 필드로 구분하나요?
- late ACK를 켰는데도 특정 자식 종료에서 재실행되지 않을 수 있는 이유는 무엇인가요?

## 참고 자료

- [Celery ACK 관련 설정](https://docs.celeryq.dev/en/stable/userguide/configuration.html)
- [Celery Retry](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [Celery Task Routing](https://docs.celeryq.dev/en/stable/userguide/routing.html)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
