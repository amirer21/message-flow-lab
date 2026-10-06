# Phase 9 · Celery Task의 요청·실행·결과 분리

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

Celery는 함수를 Task로 등록하고, 실행 요청을 메시지로 보내고, Worker가 실행한 결과를 따로 조회하는 Framework입니다. RabbitMQ가 Python 함수를 실행하는 것은 아닙니다.

## 전체 흐름

HTTP 요청 → apply_async → Task ID → RabbitMQ Task Queue → Celery Worker 실행 → Result Backend 조회

## 용어

- **Task / Task ID**: 실행할 함수 정의와 그 실행 요청의 식별자입니다. HTTP 요청의 즉시 결과 대신 Task ID를 받을 수 있습니다.
- **Worker**: 등록된 Task 이름을 실제 Python 함수에 연결해 실행하는 프로세스입니다.
- **Broker / Result Backend**: Broker는 실행 요청을 전달하고 Result Backend는 상태·결과를 저장합니다. 서로 다른 역할입니다.
- **PENDING**: 아직 상태가 없다는 뜻일 수 있습니다. 미실행 외에 모르는 ID나 만료된 결과도 포함할 수 있습니다.

## 일반 메시지와 Task 프로토콜

Celery 메시지는 Task 이름·인자·Task ID 등의 표준 형식을 사용합니다. Phase 1의 {body: hello}를 그대로 Celery Queue에 넣으면 같은 Task 요청이 되는 것이 아닙니다. apply_async 또는 delay로 Celery가 메시지를 작성하게 합니다.

Worker에는 발행한 이름의 Task가 등록돼 있어야 합니다. API에 임의 Task 이름·코드를 받아 실행하는 기능을 열지 않고, 학습용 함수와 입력 범위를 고정합니다.

## 비동기 요청을 HTTP에서 활용하기

API는 발행 요청 후 Task ID를 반환하고 브라우저는 별도 상태 조회를 합니다. FastAPI 요청 안에서 긴 AsyncResult.get을 호출하면 그 요청이 기다리게 돼 분리의 장점을 잃습니다.

Task 본문은 Worker에서 실행됩니다. Result Backend가 없거나 결과 무시 설정이면 완료 결과 조회가 제한됩니다. 결과 보관 TTL이 만료돼도 업무 DB 효과가 사라지는 것은 아닙니다.

## 실행 환경과 결과 모델

아래는 Redis Result Backend를 선택하는 설계 예시입니다. 현재 Compose에는 이 서비스와 Celery Worker가 추가돼 있지 않습니다. PostgreSQL 업무 DB와 결과 저장소는 목적을 구분해 설계합니다.

Windows PC에서는 현재처럼 Linux 컨테이너에서 Worker를 실행합니다. serializer와 accept_content를 JSON으로 제한하고 Task 시작 관측, 성공·오류·만료 표시를 분리합니다.

## 설계 예시 · tasks.py와 비동기 발행

```python
import os
from celery import Celery

app = Celery("messageflow", broker=os.environ["BROKER_URL"],
             backend=os.environ["RESULT_BACKEND"])
app.conf.update(task_serializer="json", result_serializer="json",
                accept_content=["json"], task_track_started=True)

@app.task(name="lab.add")
def add(x: int, y: int):
    return x + y

# API에서 호출합니다. add 본문을 여기서 실행하지 않습니다.
def submit_add(x, y):
    job = add.apply_async(args=[x, y], queue="phase9.tasks")
    return {"task_id": job.id}

def lookup(task_id):
    job = app.AsyncResult(task_id)
    return {"state": job.state,
            "result": job.result if job.successful() else None}
```

- BROKER_URL은 RabbitMQ AMQP 주소, RESULT_BACKEND는 설계한 결과 저장소 주소입니다. 실제 값은 환경변수에서 주입합니다.
- job.id로 후속 요청을 연결합니다. PENDING을 단순 대기나 실패로 확정하지 않습니다. 성공일 때만 숫자 결과를 반환합니다.
- 실제 API에는 입력·Task ID 인증/소유권, 오류 응답, 결과 만료 처리도 필요합니다. 예시는 Task 역할을 읽는 핵심 부분입니다.

## 설계 예시 · Linux 컨테이너 안의 Worker 실행

```shell
celery -A tasks worker --loglevel=INFO --queues=phase9.tasks --concurrency=1
```

- tasks.py와 의존성·환경변수가 준비된 Worker 컨테이너 안에서 실행하는 명령입니다. 현재 호스트에서 그대로 실행하는 실습 명령은 아닙니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| Worker 정지 중 Task 발행 | Task Queue에 대기 | API 발행과 함수 실행 시점이 분리됩니다. |
| Worker 시작 | 결과 5 조회 가능 | add(2, 3)을 Worker가 실행하고 결과 저장소에 반영합니다. |
| 모르는 Task ID 조회 | PENDING 등 알 수 없음 상태 | 진행 중인 실제 Task가 있다는 증거는 아닙니다. |

## 주의할 오해

- Task result를 비즈니스 원장처럼 쓰지 않습니다. 결과 만료와 업무 데이터 영속성은 별개입니다.
- Task ID만 알고 아무 사용자 결과를 조회할 수 있게 만들지 않습니다. 접근 범위를 설계합니다.

## 설명해 보기

- Broker와 Result Backend가 각각 중단되면 어떤 기능이 달라질까요?
- delay 호출과 Python 함수 직접 호출은 어디에서 실행되는지가 어떻게 다른가요?

## 참고 자료

- [Celery Task 호출](https://docs.celeryq.dev/en/stable/userguide/calling.html)
- [Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
