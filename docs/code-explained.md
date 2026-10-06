# MessageFlow Lab · 도구와 코드 해설

작성일: 2026-10-06 · 기준: Phase 0–3 / v0.3.0

각 단계의 함수 호출 순서·입출력·데이터 흐름을 상세히 읽으려면 [Phase별 코드 학습 안내](phase-code-study.md)를 함께 보세요.

이 문서는 현재 프로젝트의 코드가 어떤 역할을 하는지 읽는 학습 안내입니다. **실제 구현 코드**와 **향후 도입을 이해하기 위한 예시**를 구분합니다. 도입 계획은 [남은 단계 개발 계획서](remaining-development-plan.md)를 참고하세요.

## 1. RabbitMQ, Pika, Celery, Pyro5는 어떻게 다른가?

| 이름 | 종류와 역할 | 현재 사용 여부 | 이 프로젝트의 위치 |
|---|---|---|---|
| RabbitMQ | 메시지를 보관하고 Queue로 전달하는 서버(Broker) | 사용 중 | `docker-compose.yml`의 rabbitmq 서비스 |
| Pika | Python이 RabbitMQ와 AMQP 0-9-1로 통신하는 클라이언트 라이브러리 | 사용 중, 1.3.2 | `backend/app/messaging.py`, `consumer.py`, `routing.py` |
| Kombu | Connection·Exchange·Queue 등 메시징 개념을 추상화하는 Python 라이브러리 | 미도입 | Phase 8 예정 |
| Celery | Task 등록·발행·Worker 실행·Retry·결과 조회를 제공하는 작업 프레임워크 | 미도입 | Phase 9–10 예정 |
| Pyro5 | Python 객체의 메서드를 다른 프로세스/컴퓨터에서 호출하는 RPC 라이브러리 | 미도입 | Phase 11 예정 |
| PostgreSQL | 업무 데이터·멱등 처리·이벤트·Outbox를 저장할 관계형 DB | 미도입 | Phase 6, 12 예정 |

**Pika와 Pyro5는 이름이 비슷하지만 별개입니다.** 현재 메시지 발행·소비 코드는 Pika를 사용합니다. RabbitMQ 자체는 Python 라이브러리가 아니라 Docker에서 실행되는 별도 서버입니다.

Celery가 RabbitMQ를 Broker로 사용하도록 구성할 수 있지만 현재의 Pika Consumer가 Celery Worker인 것은 아닙니다. Pyro5 원격 호출도 RabbitMQ의 Queue에 메시지를 넣는 동작과 다릅니다.

## 2. 나머지 라이브러리와 도구

| 도구 | 무엇을 하는가? | 확인할 파일 |
|---|---|---|
| FastAPI | 화면의 HTTP 요청을 받아 Python 함수에 연결 | `backend/app/main.py` |
| Uvicorn | FastAPI 앱을 실행하는 ASGI 서버 | `backend/Dockerfile`의 CMD |
| Pydantic | 메시지 길이·개수·종류 등 요청 데이터 검증 | `main.py`, `routing.py`의 BaseModel |
| HTTPX | API가 RabbitMQ Management HTTP API를 조회, smoke 코드가 실습 API 호출 | `main.py`, `scripts/smoke*.py` |
| Vue 3 | 선택된 Phase·모드·관측값에 맞춰 화면 갱신 | `frontend/src/App.vue`, `PhaseTwo.vue`, `PhaseThree.vue` |
| TypeScript | 화면 데이터의 구조와 함수 입력을 검사 | `frontend/src/types.ts`, `routing.ts` |
| Vite | 개발 서버와 배포용 프런트 빌드 | `vite.config.ts`, `package.json` |
| vue-tsc | Vue 템플릿을 포함한 타입 검사 | `package.json`의 build 스크립트 |
| lucide-vue-next | 버튼·제목 아이콘 | Vue 컴포넌트의 import |
| Nginx | 빌드된 HTML·JS·CSS와 실습 ZIP 제공 | `frontend/Dockerfile`의 최종 단계 |
| Docker / Compose | 서비스를 격리 실행하고 연결·포트·볼륨·시작 조건 정의 | `docker-compose.yml` |
| WSL 2 | 이 Windows PC에서 Docker Linux 환경을 실행하는 기반 | 프로젝트 코드 밖의 실행 환경 |
| Git / GitHub | 소스 변경 이력과 공개 저장소 | 저장소 전체 |
| Sites | 정적 학습 화면 게시 | `.openai/hosting.json`, `dist/` |
| unittest / Node test runner | Python 동작과 브라우저 예시 모델 검증 | `backend/tests/`, `frontend/tests/` |

Python의 `json`, `uuid`, `threading`, `queue`, `concurrent.futures`, `subprocess`, `pathlib`, `os`, `secrets`, `contextlib`는 **표준 라이브러리**입니다. pip로 각각 설치하는 외부 패키지가 아닙니다.

외부 Python 의존성의 고정 버전은 [requirements.txt](../backend/requirements.txt), 프런트 의존성 선언과 실제 설치 버전은 [package.json](../package.json)과 `package-lock.json`에서 확인합니다. 공식 사이트의 stable 문서는 설치 버전보다 최신일 수 있습니다.

## 3. 전체 동작 흐름

```mermaid
flowchart LR
  UI[Vue 학습 화면] -->|HTTP + 실습 토큰| API[FastAPI Gateway]
  API -->|Pika / AMQP 5672| MQ[RabbitMQ]
  API -->|HTTP Management 15672| MQ
  MQ -->|메시지 전달| C[Python Consumer]
  C -->|ACK| MQ
  C -->|Phase 2 업무 반영| F[JSONL 파일]
  API -->|관측 snapshot| UI
```

화면은 RabbitMQ 비밀번호로 Broker에 직접 접속하지 않습니다. HTTP로 Gateway를 호출하고, Gateway가 서버의 접속 정보를 이용해 Broker와 통신합니다. Management 포트는 지표·관리용이며 메시지 AMQP 연결과 구분합니다.

예시 모드에서는 이 경로 대신 브라우저의 `DemoLab` 또는 `RoutingDemo`가 메모리에서 상태를 계산합니다. 예시 화면의 메시지는 실제 RabbitMQ Queue에 들어가지 않습니다.

## 4. 코드 읽는 순서

1. [docker-compose.yml](../docker-compose.yml): 어떤 서버가 실행되는지 확인.
2. [config.py](../backend/app/config.py): 환경변수가 Python 설정으로 바뀌는 과정.
3. [messaging.py](../backend/app/messaging.py): RabbitMQ 연결·Queue 선언·발행.
4. [consumer.py](../backend/app/consumer.py): 전달받기·ACK·Consumer 종료.
5. [main.py](../backend/app/main.py): 화면의 버튼이 위 동작을 호출하는 경로.
6. [lab.ts](../frontend/src/lab.ts), [App.vue](../frontend/src/App.vue): 예시 모델과 실제 HTTP 요청의 차이.
7. [phase2_worker.py](../backend/app/phase2_worker.py), [experiments.py](../backend/app/experiments.py), [effects.py](../backend/app/effects.py): 프로세스 종료·중복 효과.
8. [routing.py](../backend/app/routing.py), [routing.ts](../frontend/src/routing.ts), [PhaseThree.vue](../frontend/src/PhaseThree.vue): Exchange별 실제 전달과 예시 계산.
9. `backend/tests/`, `frontend/tests/`, `scripts/smoke*.py`: 코드가 지켜야 하는 동작.

## 5. Docker Compose 코드

실제 설정의 일부:

```yaml
rabbitmq:
  image: rabbitmq:4.2-management
  ports:
    - "127.0.0.1:5672:5672"
    - "127.0.0.1:15672:15672"
  volumes:
    - rabbit-data:/var/lib/rabbitmq
```

- `image`: RabbitMQ와 관리 기능이 들어 있는 이미지를 실행합니다.
- `127.0.0.1:5672:5672`: PC의 로컬 주소에서 AMQP 포트에 접속하도록 합니다.
- `15672`: 브라우저 관리 화면과 Management API 포트입니다.
- `rabbit-data`: 컨테이너가 교체돼도 Broker 데이터를 유지하는 Docker volume입니다. 임시 Queue까지 영속화한다는 의미는 아닙니다.

API의 `RABBIT_HOST: rabbitmq`는 Compose 내부 DNS 이름입니다. 컨테이너 안의 `localhost`는 그 컨테이너 자신이므로 다른 RabbitMQ 컨테이너를 가리키지 않습니다. 반대로 브라우저에서 Gateway에 연결할 때는 PC에 공개된 `http://localhost:8000`을 사용합니다.

`depends_on`과 `condition: service_healthy`는 초기 시작 시 Broker의 healthcheck를 기다립니다. 이후 발생하는 모든 연결 장애를 자동 해결하는 기능은 아닙니다.

프런트 Dockerfile은 Node에서 `npm ci`와 빌드를 수행한 다음 결과 `dist/`만 Nginx 이미지로 옮깁니다. 실행 중인 로컬 5173 화면은 이 Nginx가 제공합니다. `npm run dev`로 띄우는 Vite 개발 서버와 실행 방식은 다릅니다.

## 6. 환경변수와 접속 코드

[config.py](../backend/app/config.py)의 예:

```python
rabbit_host: str = os.getenv("RABBIT_HOST", "localhost")
rabbit_vhost: str = os.getenv("RABBIT_VHOST", "lab")
lab_token: str = os.getenv("LAB_TOKEN", "")
```

`os.getenv()`는 프로세스의 환경변수를 읽습니다. 이 앱이 `.env` 파일을 직접 파싱하는 것은 아닙니다. Compose가 `.env`를 읽고 필요한 값을 컨테이너 환경변수로 전달합니다. 설정 객체는 모듈 import 시 생성되므로 값을 바꿨다면 실행 프로세스도 다시 시작해야 합니다.

[init_env.py](../scripts/init_env.py)는 `secrets.token_urlsafe()`로 로컬 비밀번호와 실습 토큰을 생성합니다. 파일을 `"x"` 모드로 열기 때문에 이미 존재하는 `.env`를 덮어쓰지 않습니다. `.env`는 Git과 실습 ZIP에서 제외됩니다.

[messaging.py](../backend/app/messaging.py)의 실제 연결:

```python
params = pika.ConnectionParameters(
    host=settings.rabbit_host, port=settings.rabbit_port,
    virtual_host=settings.rabbit_vhost,
    credentials=pika.PlainCredentials(settings.rabbit_user, settings.rabbit_password),
    heartbeat=30, blocked_connection_timeout=5, socket_timeout=3,
    stack_timeout=5, connection_attempts=1,
)
conn = pika.BlockingConnection(params)
```

`virtual_host`는 Broker 안의 논리적 격리 공간입니다. `BlockingConnection`은 동기식 API로 연결합니다. heartbeat와 timeout은 연결 확인·대기 제한을 위한 설정이며, 메시지 처리 성공을 보장하거나 자동으로 재발행하는 설정은 아닙니다. `PlainCredentials`는 계정 인증이며 암호화 설정 자체는 아닙니다. 현재 구성은 로컬 실습용입니다.

`connection()`에 붙은 `@contextmanager`와 `yield` 덕분에 `with connection() as conn:` 형태로 사용하고, `finally`에서 열린 연결을 닫습니다.

## 7. Phase 1 · 메시지 발행 코드

[messaging.py](../backend/app/messaging.py)의 실제 핵심:

```python
channel.queue_declare(queue=queue, durable=True)
channel.basic_publish(
    exchange="", routing_key=queue,
    body=json.dumps({"body": text}, ensure_ascii=False).encode("utf-8"),
    properties=pika.BasicProperties(
        message_id=message_id, correlation_id=message_id,
        content_type="application/json", delivery_mode=2,
    ),
)
```

`channel`은 하나의 연결 안에서 AMQP 작업을 수행하는 논리 통로입니다. Queue 선언은 같은 속성의 Queue가 있으면 재사용합니다. 이미 있는 Queue를 다른 속성으로 선언하면 오류가 날 수 있습니다.

`exchange=""`는 RabbitMQ의 기본 Exchange입니다. Queue 이름을 Routing Key로 사용하기 때문에 Queue에 직접 넣는 것처럼 보이지만 Exchange를 통한 전달입니다. JSON 문자열을 UTF-8 bytes로 바꿔 메시지 본문으로 전송합니다.

`message_id`는 논리 메시지 식별자이고 `correlation_id`는 요청·응답 등을 연관 지을 때 쓰는 속성입니다. 현재는 두 값이 같고 별도 request/reply 기능은 없습니다. `delivery_mode=2`는 persistent 메시지 속성, `durable=True`는 Queue 속성입니다. **현재 코드는 이 두 설정을 이미 사용하지만 Publisher Confirm을 사용하지 않습니다.** 반환값의 `publisher_confirmed=False`를 읽어야 하는 이유입니다.

따라서 `PUBLISH_SENT`는 발행 호출이 반환됐다는 앱 기록입니다. Consumer 업무 완료가 아니며, 이 코드만으로 모든 장애에서 안전한 전달을 주장하지 않습니다. Phase 4에서 Confirm·Return·재시작 실험을 추가합니다.

## 8. Phase 1 · Consumer, Prefetch와 ACK

[consumer.py](../backend/app/consumer.py)의 실제 설정:

```python
channel.basic_qos(prefetch_count=1)
channel.basic_consume(
    queue=settings.queue,
    on_message_callback=self._received,
    auto_ack=False,
)
```

`prefetch_count=1`은 이 Consumer에 ACK되지 않은 전달이 하나 있는 동안 추가 전달을 제한합니다. `auto_ack=False`이므로 수신 즉시 자동 ACK하지 않습니다. `self._received`는 실제 메시지가 전달되면 Pika가 호출하는 함수입니다.

이 함수는 `properties.message_id`, `method.redelivered`, 본문을 읽고 매 전달마다 새로운 `attempt_id`를 만듭니다. 예를 들어 같은 메시지가 재전달되면 Message ID는 같지만 Attempt ID는 달라집니다. `method.delivery_tag`는 **현재 channel의 전달 식별자**이므로 다른 channel에서 ACK하는 ID로 사용하지 않습니다.

ACK 버튼의 실제 핵심:

```python
if not pending or pending["attempt_id"] != attempt_id:
    raise ValueError("현재 전달과 일치하지 않는 ACK입니다.")
channel.basic_ack(delivery_tag=tag)
```

전달 시도를 먼저 비교하기 때문에 이전 메시지의 버튼을 늦게 눌러 다음 메시지를 ACK하는 일을 막습니다. ACK 호출 뒤 현재 `pending`을 비우고 `ACK_SENT` 이벤트를 기록합니다. 이 시각은 앱의 호출 시각이며 Broker 내부 반영 시각과 같다고 단정하지 않습니다.

Consumer 종료는 `conn.close()`이며 ACK를 대신 보내지 않습니다. Broker가 연결 종료를 감지하면 미확인 전달이 다시 Queue로 돌아갈 수 있습니다.

## 9. 왜 Thread, Queue, Future가 있는가?

FastAPI 요청을 처리하는 스레드와 Pika 연결을 소유한 스레드는 다를 수 있습니다. 현재 `ConsumerSession`은 명령을 Python `queue.Queue`에 넣고, Pika 스레드가 꺼내 실행합니다. `Future`는 그 명령의 결과나 예외를 요청 함수에 전달합니다.

```text
HTTP ACK 요청 → command("ack", attempt_id)
             → Python Queue에 명령 + Future 저장
             → Pika 스레드가 _ack() 실행
             → Future 결과 → HTTP 응답
```

여기서 Python `queue.Queue`는 프로세스 내부의 스레드 간 명령 통로이며 **RabbitMQ Queue와 다릅니다**. DB나 Broker의 영속 메시지 저장소가 아닙니다. `Lock`은 공유 상태 읽기·변경이 겹치는 것을 조절합니다.

Pika 작업은 연결을 소유한 스레드에서 실행해야 합니다. 공식적으로 제공하는 다른 방식은 `add_callback_threadsafe()`이지만 현재 프로젝트는 명령 Queue를 소유 스레드가 처리하는 구조입니다. [Pika 연결 문서](https://pika.readthedocs.io/en/stable/modules/adapters/blocking.html)

`conn.process_data_events()`는 Broker 프레임·heartbeat·콜백을 처리하도록 합니다. 직접 실행용 [consumer.py](../workers/pika_worker/consumer.py)는 작업 지연을 `conn.sleep(args.seconds)`로 표현해 연결 처리가 멈추는 것을 줄입니다.

## 10. FastAPI와 Pydantic 코드

[main.py](../backend/app/main.py)의 실제 API:

```python
class PublishRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4096)
    count: int = Field(default=1, ge=1, le=3)

@app.post("/rabbit/messages", dependencies=[Depends(authorize)])
def post_message(request: PublishRequest):
    if not request.body.strip():
        raise HTTPException(status_code=422, detail="빈 메시지는 발행할 수 없습니다.")
    return publish(request.body, request.count)
```

`@app.post`는 HTTP 경로를 함수에 연결합니다. `BaseModel`과 `Field`는 JSON의 타입·범위를 검사합니다. 길이가 1 이상이어도 공백만 있을 수 있으므로 `strip()`으로 추가 검사합니다. `Depends(authorize)`는 함수 실행 전 실습 토큰을 확인합니다.

`authorize()`는 `X-Lab-Token`을 읽고 `secrets.compare_digest()`로 비교합니다. RabbitMQ 계정 인증과 HTTP 실습 토큰 인증은 서로 다른 경계입니다. CORS는 브라우저의 허용 Origin을 설정하며 토큰 인증을 대신하지 않습니다.

| HTTP 상태 | 이 프로젝트에서 읽는 의미 |
|---|---|
| 401 | 실습 토큰이 없거나 일치하지 않음 |
| 422 | 입력 타입·범위·필수 ID 등의 검증 실패 |
| 409 | 현재 실험 상태와 맞지 않는 동작, stale ACK 등 |
| 503 | Broker/API 실험 동작의 결과를 확인할 수 없음 |

실패 응답을 받은 발행을 자동 재시도하지 않습니다. 응답을 받기 전에 이미 메시지가 전송됐을 가능성을 고려합니다.

## 11. Queue 숫자와 이벤트는 어디에서 오는가?

[main.py](../backend/app/main.py)의 `queue_stats()`는 HTTPX로 RabbitMQ Management API의 `/api/queues/{vhost}/{queue}`를 조회합니다. 새 Queue의 지표가 아직 수집되지 않았으면 잠깐 기다리고, 수집할 수 없는 값을 임의로 0으로 만들지 않습니다.

[events.py](../backend/app/events.py)의 `EventStore`는 앱이 관측한 `PUBLISH_SENT`, `DELIVERED`, `ACK_SENT` 등을 메모리 deque에 보관하고 JSONL에도 추가합니다. 세션 카운터는 API 재시작 시 초기화되지만 Broker Queue의 메시지는 별개로 남을 수 있습니다. 현재 API는 이 JSONL을 다시 읽어 전체 세션 이력을 복원하지 않습니다.

GET `/rabbit/messages`는 이 관측 이벤트를 조회합니다. RabbitMQ Queue에서 메시지를 꺼내 확인하는 동작이 아닙니다. Phase 3의 명시적 POST `/routing/receive`는 실제 소비 동작입니다.

## 12. Phase 2 · 실제 프로세스를 종료하는 이유

[experiments.py](../backend/app/experiments.py)는 다음 고정 명령으로 자식 Python 프로세스를 만듭니다.

```python
[sys.executable, "-u", "-m", "app.phase2_worker"]
```

`sys.executable`은 현재 Python 실행 파일, `-u`는 출력 버퍼링 최소화, `-m`은 모듈 실행입니다. 자식의 실제 소스는 **`backend/app/phase2_worker.py`**입니다. stdin으로 `process/ack/stop` JSON 명령을 보내고 stdout으로 이벤트·응답을 받습니다. 이는 로컬 프로세스 IPC이며 RabbitMQ 메시지나 Pyro RPC가 아닙니다.

`crash()`는 제어기가 만든 자식을 `kill()`합니다. Linux 컨테이너에서는 SIGKILL이며 API·RabbitMQ를 종료하지 않습니다. 예시 모드의 상태 변경과 달리 연결이 갑자기 끊기는 실제 장애를 관찰합니다.

[phase2_worker.py](../backend/app/phase2_worker.py)의 순서:

```python
effect = append_effect(pending["message_id"], pending["attempt_id"])
pending["processed"] = True
# 이후 사용자가 ACK 명령을 보냈을 때만 실행
channel.basic_ack(delivery_tag=tag)
```

업무 반영과 ACK가 분리돼 있습니다. ACK 전에 죽으면 같은 메시지가 다시 전달되고, 새 시도에서 업무를 다시 반영할 수 있습니다. 같은 시도의 두 번 클릭을 막는 `processed`와, 재전달까지 막는 업무 멱등성은 다릅니다.

[effects.py](../backend/app/effects.py)는 JSONL에 업무 기록을 append하고 `flush()`·`os.fsync()`를 호출합니다. 디스크 기록 후 종료 실험을 위한 학습용 효과이며 실제 결제나 DB 트랜잭션은 아닙니다. Message ID별 중복 제거를 하지 않는 것이 Phase 2의 의도입니다.

## 13. Phase 3 · 실제 Routing과 설명용 계산

[routing.py](../backend/app/routing.py)의 토폴로지 선언 핵심:

```python
channel.exchange_declare(exchange=self._exchange, exchange_type=kind, auto_delete=True)
channel.queue_declare(queue=name, exclusive=True, auto_delete=True)
channel.queue_bind(queue=name, exchange=self._exchange, routing_key=binding)
```

Exchange 종류는 `direct/fanout/topic` 중 하나입니다. 전용 연결이 UUID 이름의 Queue A/B/C를 소유합니다. `exclusive=True`이므로 연결 종료 시 임시 Queue가 사라집니다. 새 실험은 이 단계의 기존 Queue와 대기 메시지를 삭제하고 다른 UUID로 생성합니다.

실제 발행의 `routing_key`와 Binding을 비교해 Queue를 고르는 주체는 **RabbitMQ**입니다. 사용자 예측 `prediction`은 본문에 저장하지만 Broker의 Routing을 제어하지 않습니다.

수신은 `basic_get(auto_ack=False)`으로 Queue마다 최대 한 개를 받은 뒤 같은 channel에서 ACK합니다. `last_received`에는 실제 받은 복사본만 들어갑니다. Ready는 passive queue_declare의 message_count에서 얻습니다. 메시지를 꺼내지 않고 Queue 개수를 확인하는 조회입니다.

Python `topic_matches()`와 TypeScript `topicMatches()`는 `*`/`#` 규칙을 설명·검증하는 계산 코드입니다. TypeScript `RoutingDemo`는 예시 Queue를 계산하지만 실제 Broker 라우팅의 대체 구현으로 사용하지 않습니다. 규칙 계산과 실제 수신 기록을 화면에서 구분합니다.

## 14. Vue 코드와 예시/실제 모드

Vue의 `ref()`는 변경 가능한 화면 상태, `computed()`는 상태에서 계산한 값입니다. 예를 들어 선택된 Phase가 바뀌면 제목·질문·완료 기준이 다시 계산됩니다. `watch()`는 모드·활성 화면·접속값 변경에 반응합니다.

`App.vue`는 단계 선택과 공통 연결을 담당합니다. `PhaseTwo.vue`는 부모가 전달한 snapshot과 버튼 이벤트를 사용하고, `PhaseThree.vue`는 활성화된 동안 `/routing/snapshot`을 직접 주기적으로 조회합니다.

[lab.ts](../frontend/src/lab.ts)의 `request()`는 `fetch()`로 토큰 헤더를 보내고, body가 없으면 GET, 있으면 JSON POST를 수행합니다. `AbortSignal.timeout(10000)`은 브라우저 요청 대기 제한입니다. timeout이 서버 업무를 취소했다는 의미는 아닙니다.

`generation` 값은 단계·모드 전환 전에 시작한 요청의 응답을 새 화면에 적용하지 않기 위한 비교값입니다. 토큰은 메모리에서 사용하며 localStorage에 저장하지 않습니다. 학습 체크·노트·Gateway 주소는 기기별로 저장합니다.

## 15. Celery 코드는 앞으로 무엇이 달라지는가?

**다음 코드는 설명용 예시입니다. 현재 프로젝트의 설치 패키지나 실행 서비스가 아닙니다.** Phase 9에서는 별도 Celery 앱·Worker·결과 저장소를 구성합니다.

```python
from celery import Celery

app = Celery("messageflow", broker=broker_url, backend=result_backend_url)

@app.task
def add(a, b):
    return a + b

# Worker가 따로 실행 중이어야 비동기 요청을 처리합니다.
result = add.delay(2, 3)
task_id = result.id
```

`broker_url`과 `result_backend_url`은 실제 비밀을 하드코딩하지 않고 설정에서 주입할 값입니다. `@app.task`는 Task 등록, `delay()`는 실행 요청 발행, 별도 Worker는 함수 실행, backend는 결과 저장을 맡습니다. Gateway는 Task ID를 반환하고 나중에 결과를 조회하도록 구현할 예정입니다. [Celery 시작 안내](https://docs.celeryq.dev/en/stable/getting-started/first-steps-with-celery.html)

일반 `add(2, 3)` 호출과 `add.delay(2, 3)`는 실행 위치·응답 방식이 다릅니다. Celery Task의 메시지 형식도 현재 Pika의 `{"body": ...}`와 다르므로 기존 Producer를 Celery Queue에 연결하는 것으로 전환되지 않습니다.

Phase 10에서 early/late ACK·retry·worker-lost 정책을 별도로 실험합니다. Celery를 도입해도 업무 중복 가능성이 자동으로 없어지는 것은 아닙니다.

## 16. Pyro5 코드는 앞으로 무엇이 달라지는가?

**다음은 서버/클라이언트 역할을 보여 주는 설명용 예시입니다. 현재 프로젝트에서 실행·검증한 코드가 아닙니다.** Phase 11은 Pyro5와 Celery로 같은 계산을 비교합니다.

서버 측:

```python
import Pyro5.api

@Pyro5.api.expose
class Calculator:
    def add(self, a, b):
        return a + b

with Pyro5.api.Daemon() as daemon:
    uri = daemon.register(Calculator)
    print(uri)  # 학습 예시. 실제 앱은 설정/서비스 발견 방식으로 전달합니다.
    daemon.requestLoop()
```

클라이언트 측:

```python
import Pyro5.api

with Pyro5.api.Proxy(service_uri) as calculator:
    calculator._pyroTimeout = 3
    answer = calculator.add(2, 3)
```

`expose`는 원격 공개 메서드, `Daemon`은 요청을 받는 서버, `Proxy`는 원격 객체를 호출하는 클라이언트입니다. `service_uri`는 서버 등록 결과로 설정할 실제 URI입니다. Name Server 없이 직접 URI를 쓰는 구성을 먼저 고려합니다. [Pyro5 예제](https://pyro5.readthedocs.io/en/latest/intro.html)

이 동기 호출은 응답을 기다립니다. timeout이나 연결 오류가 났다고 서버가 실행하지 않았다고 확정할 수 없습니다. 향후 화면은 브라우저 → FastAPI → Pyro5 서비스 경로를 사용합니다. Pyro5 호출을 브라우저에서 직접 실행하지 않습니다.

## 17. 코드와 실험을 연결해서 읽기

| 직접 확인할 현상 | 함께 읽을 코드 | 관찰할 값 |
|---|---|---|
| Consumer 없이 3개 발행 | `messaging.publish()` | Ready 3, PUBLISH_SENT 3 |
| Consumer 시작 | `ConsumerSession._run()`, `_received()` | Ready 2, Unacked 1, attempt_id |
| ACK 한 번 | `_ack()` | 현재 pending 해제, 다음 전달 |
| 오래된 ACK | `_ack()`의 attempt_id 비교 | 409, 새 전달이 잘못 ACK되지 않음 |
| 업무 반영 후 ACK 전 종료 | `phase2_worker.main()`, `ExperimentConsumer.crash()` | 같은 Message ID, 새 attempt_id, redelivered |
| 재전달 업무 재반영 | `append_effect()`, `read_effects()` | 동일 메시지 업무 횟수 2 |
| Fanout 발행·수신 | `RoutingLab.handle()` | A/B/C의 같은 Message ID |
| Binding 변경 후 수신 | `RoutingLab.handle()`의 bindings/receive | 기존 대기 메시지 유지 |
| 예시 모드 조작 | `DemoLab`, `RoutingDemo` | 실제 Broker가 아닌 메모리 상태 |

실제 실험 실행은 [검증 기록](verification.md), 각 단계 안내는 [Phase 2](phase2.md), [Phase 3](phase3.md)를 참고하세요. 읽기만으로는 Queue를 변경하지 않습니다. smoke 스크립트나 화면 버튼은 실제 발행·소비·종료를 수행하므로 해당 문서의 영향 범위를 먼저 확인합니다.

## 18. 이해도 점검

1. 왜 RabbitMQ 서버와 Pika Python 코드가 둘 다 필요한가?
2. `exchange=""`와 `routing_key="hello"`는 어떤 경로로 전달되는가?
3. `durable=True`, `delivery_mode=2`, Publisher Confirm은 각각 무엇인가?
4. `message_id`, `attempt_id`, `delivery_tag`를 하나의 ID로 합치면 어떤 문제가 생기는가?
5. Python `queue.Queue`와 RabbitMQ Queue는 무엇이 다른가?
6. 업무 파일 저장 뒤 ACK 전에 종료하면 왜 업무가 중복될 수 있는가?
7. 예측 계산과 실제 Queue 수신을 왜 구분하는가?
8. Celery `delay()`와 Pyro5 Proxy 호출은 호출자의 대기 방식이 어떻게 다른가?

이 질문의 답을 현재 코드와 실험 기록에서 찾은 뒤 Phase 4로 진행하면 발행 확인·Return·장애 처리의 차이를 이해하기 쉽습니다.
