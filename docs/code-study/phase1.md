# Phase 1 · 발행·수신·Manual ACK 코드

학습 목표: 입력 본문이 AMQP 메시지로 바뀌는 과정과 ACK 전후의 상태 변화를 실제 함수 순서로 설명합니다.

## 1. 읽을 파일과 라이브러리

| 파일 | 주요 코드 | 라이브러리 |
|---|---|---|
| [App.vue](../../frontend/src/App.vue) | action, refresh, snapshotPath | Vue |
| [lab.ts](../../frontend/src/lab.ts) | request, DemoLab | fetch, crypto.randomUUID |
| [main.py](../../backend/app/main.py) | post_message, start_consumer, ack, stop_consumer, snapshot | FastAPI, Pydantic, HTTPX |
| [messaging.py](../../backend/app/messaging.py) | connection, declare, publish | Pika, json, uuid, contextlib |
| [consumer.py](../../backend/app/consumer.py) | ConsumerSession | threading, queue, Future, Pika |
| [events.py](../../backend/app/events.py) | EventStore.record/view | deque, Lock, JSONL |

Phase 1의 Queue는 `hello`입니다. 코드에서 `settings.queue`가 그 이름을 제공합니다.

## 2. 발행 함수: 입력에서 메시지까지

| 함수 | 입력 | 출력·변화 |
|---|---|---|
| `action('publish', count)` | 화면 payload·개수 | POST 후 snapshot 재조회 |
| `post_message(request)` | PublishRequest(body, count) | 검증 후 publish 결과 반환 |
| `connection()` | settings | Pika 연결을 yield, 종료 시 close |
| `declare(channel, queue)` | channel·선택 Queue | durable Queue 선언 |
| `publish(body, count, queue)` | 본문·1~3개·기본 hello | message_ids, PUBLISH_SENT, publisher_confirmed=False |
| `events.record(...)` | 종류·메시지 ID·metadata | 메모리/JSONL 이벤트, 세션 카운터 |

실제 호출 순서:

```text
발행 버튼 → App.action('publish', 3)
 → request('/rabbit/messages', {body: 'hello', count: 3})
 → authorize() → Pydantic 검사 → post_message()
 → publish('hello', 3)
 → connection() → channel() → declare()
 → UUID 생성 / JSON bytes / basic_publish() × 3
 → PUBLISH_SENT 이벤트 × 3
 → {message_ids, status, publisher_confirmed: false}
 → App이 /snapshot 재조회 → Ready·이벤트 화면 갱신
```

`publish()`는 count가 1이면 입력 본문 그대로, 2~3이면 본문 뒤에 1, 2, 3을 붙입니다. 각 메시지는 다른 UUID를 가집니다.

전송 데이터는 다음과 같이 나뉩니다. ID 값은 이해를 위한 기호입니다.

```text
HTTP 요청: {"body": "hello", "count": 3}
AMQP 본문: UTF-8 bytes로 인코딩한 {"body": "hello 1"}
AMQP 속성: message_id=M1, correlation_id=M1,
           content_type=application/json, delivery_mode=2
Exchange: "" / Routing Key: "hello"
```

기본 Exchange가 Queue 이름과 같은 Routing Key로 전달합니다. durable Queue와 persistent 메시지는 사용하지만 Confirm은 없으므로 발행 응답을 처리 완료로 읽지 않습니다.

## 3. Consumer의 주요 함수와 상태

| 함수 | 언제 호출되나? | 처리 |
|---|---|---|
| `ConsumerSession.start()` | 시작 버튼 | 전용 Thread 실행, ready Event 대기, 실패 검사 |
| `_run()` | 새 Thread 안 | 연결·채널·Queue 준비, Prefetch 1, 소비 등록, 이벤트/명령 처리 |
| `_received(channel, method, properties, body)` | Pika 실제 전달 callback | 본문 해석, 새 attempt_id, pending·delivery_tag 저장, DELIVERED 기록 |
| `view()` | 상태 조회 | Lock으로 pending과 active 상태 복사 |
| `command(kind, attempt_id)` | HTTP ACK/멈춤 요청 | 내부 Queue에 명령/Future 넣고 결과 대기 |
| `_ack(channel, attempt_id)` | 소유 Thread의 ack 명령 | 현재 시도 대조, basic_ack, pending 비움, ACK_SENT |
| `shutdown()` | 종료 요청·앱 종료 | stop 요청 후 Thread join |

주요 메모리 필드:

- `_pending`: 화면에서 확인/ACK할 현재 전달. message_id, attempt_id, body, redelivered 포함.
- `_delivery_tag`: Pika가 준 channel 범위의 전달 번호.
- `_active`: Consumer 실행 여부. `_ready`: 시작 결과를 호출 측에 알리는 Event.
- `_commands`: **Python 내부** 명령 Queue. RabbitMQ의 hello Queue가 아님.

`_received()`는 JSON 객체의 body 문자열을 읽고, 일반 텍스트면 가능한 원문을 유지합니다. 메시지 속성에 ID가 없으면 앱이 UUID를 만들기 때문에 외부 Producer의 ID 없는 재전달을 안정된 논리 ID로 비교하는 데는 한계가 있습니다. 프로젝트 Producer는 message_id를 넣습니다.

## 4. 전달과 ACK의 데이터 흐름

```text
RabbitMQ hello → Pika callback _received()
 → pending={message_id:M1, attempt_id:A1, body:'hello 1', redelivered:false}
 → _delivery_tag=T1
 → /snapshot → 화면에서 M1/A1 표시

ACK 버튼 → POST /consumer/ack {attempt_id:A1}
 → main.ack() → consumer.command('ack', A1)
 → _commands → 소유 Thread → _ack(channel, A1)
 → A1 == 현재 pending.attempt_id 확인
 → basic_ack(delivery_tag=T1)
 → pending=None / delivery_tag=None / ACK_SENT
 → Broker가 ACK 반영 → Prefetch 공간 확보 → 다음 메시지 전달
```

HTTP 요청 스레드가 channel을 직접 조작하지 않습니다. `Future.result(timeout=7)`은 소유 스레드 처리 결과를 기다립니다. timeout은 작업 미실행 증거가 아니므로 현재 전달을 확인하고 판단합니다.

## 5. 상태 변화 예측

다른 Producer/Consumer 없는 조건입니다. 실제 Management 지표에는 수집 지연이 있습니다.

| 시점 | Ready | Unacked | pending |
|---|---|---|---|
| Consumer 없이 3개 발행 | 3 | 0 | 없음 |
| Consumer 시작·첫 전달 | 2 | 1 | M1/A1 |
| M1 ACK 반영 후 M2 전달 | 1 | 1 | M2/A2 |
| M2 ACK 반영 후 M3 전달 | 0 | 1 | M3/A3 |
| M3 ACK 반영 | 0 | 0 | 없음 |

`pending`을 비운 순간과 Broker 지표 변경 사이에는 시간 차이가 있습니다. ACK 후 다음 전달이 즉시 올 수 있으므로 Unacked가 항상 잠깐 0으로 화면에 보인다고 기대하지 않습니다.

## 6. 멈춤·stale ACK·실패 처리

- stop 명령은 `conn.close()`를 호출하고 미확인 메시지에 ACK하지 않습니다. Broker가 연결 종료를 감지한 뒤 재전달 가능 상태가 됩니다.
- 이전 A1을 M2/A2에 ACK하면 `_ack()`가 ValueError, HTTP 409를 반환합니다. Broker ACK를 보내기 전에 비교하므로 M2를 잘못 확인하지 않습니다.
- basic_ack 자체가 실패하면 pending을 비우기 전에 예외가 나므로 성공 상태를 만들지 않습니다.
- Consumer 실행 실패/종료 시 대기 Future에 예외를 전달합니다. FastAPI 오류는 503 또는 409로 바뀝니다.
- `EventStore.record()`의 로그 쓰기 실패가 이미 수행한 메시징 작업을 반복하게 만들지는 않습니다. 대신 저장 오류를 로그로 남깁니다.

## 7. 예시 모델은 같은 흐름을 어떻게 표현하는가?

`DemoLab.publish()`는 메모리 messages 배열에 넣고 `deliver()`를 호출합니다. Consumer가 활성이고 pending이 없으면 `shift()`로 하나를 꺼내 pending으로 만듭니다. `ack()`는 시도 ID를 검사한 뒤 pending을 비우고 다음 deliver()를 실행합니다.

`stop()`은 ACK 전 pending을 배열 앞에 넣고 redelivered=true로 표시합니다. 예시는 Management 수집 지연·네트워크·Broker 종료 감지까지 재현하지 않습니다. 실제 코드의 판단 원칙을 설명하는 모델입니다.

## 8. 함수와 함께 하는 실험

1. 코드에서 Prefetch 1과 auto_ack=False를 찾고, 3개 발행 뒤 pending이 한 개인 이유를 설명하세요.
2. `_received()`에 전달된 body와 최종 pending.body를 비교하세요. JSON decoding이 필요한 이유는 무엇인가요?
3. ACK 전 멈춤 후 재시작하면 message_id/attempt_id/redelivered 중 어떤 값이 바뀔지 예측하세요.
4. `test_stale_ack_cannot_acknowledge_next_delivery` 검증을 읽어 시도 ID 검사 위치를 확인하세요.
5. `scripts/smoke.py`의 실제 지표 확인과 예시 모델 검증의 차이를 설명하세요.

다음 문서: [Phase 2 · 종료·재전달·업무 중복](phase2.md).
