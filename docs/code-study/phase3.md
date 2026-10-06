# Phase 3 · Exchange·Binding·Routing 코드

학습 목표: Queue 예측과 실제 Broker 라우팅을 구분하고, 임시 토폴로지·Queue별 복사·수신/ACK 흐름을 설명합니다.

## 1. 읽을 파일과 라이브러리

| 파일 | 주요 코드 | 라이브러리 |
|---|---|---|
| [PhaseThree.vue](../../frontend/src/PhaseThree.vue) | choose, sync, read, run, rules | Vue, fetch 요청 helper |
| [routing.ts](../../frontend/src/routing.ts) | RoutingSnapshot, topicMatches, RoutingDemo | TypeScript, Map, crypto |
| [routing.py](../../backend/app/routing.py) | Router, 요청 모델, RoutingLab | FastAPI, Pydantic, Pika, Queue, Future, Thread |
| [main.py](../../backend/app/main.py) | include_router, lifespan | 공통 인증과 종료 연결 |
| [test_routing.py](../../backend/tests/test_routing.py) | 실제 수신·예측 분리, 입력·인증 검증 | unittest, mock, TestClient |
| [smoke_phase3.py](../../scripts/smoke_phase3.py) | 실제 Routing 비교 | HTTPX |

Queue A/B/C는 고정 학습 라벨이고 실제 이름은 `phase3.<uuid>.a/b/c`입니다. 새 실험마다 UUID가 바뀝니다.

## 2. 요청 모델과 API

| 경로 | 요청·모델 | 동작 |
|---|---|---|
| GET /routing/snapshot | 토큰 | 현재 토폴로지·Ready·관측값 조회 |
| POST /routing/setup | SetupRequest(exchange_type, bindings) | 현재 임시 Queue 삭제 후 새 실험 |
| POST /routing/bindings | 같은 SetupRequest | 기존 Exchange의 Binding만 변경 |
| POST /routing/messages | RoutingPublishRequest(body, routing_key, prediction) | 실제 발행 |
| POST /routing/receive | 빈 body | 각 Queue 최대 한 개 수신 후 ACK |

SetupRequest는 Direct/Fanout/Topic과 Binding **정확히 3개**를 받습니다. validator는 UTF-8 바이트 길이를 검사합니다. 한글의 글자 수와 AMQP key 바이트 수는 다를 수 있습니다. Publish 요청의 prediction은 a/b/c 라벨 목록이며, 사용자 예측을 저장하는 필드입니다.

`main.py`는 `app.include_router(..., dependencies=[Depends(authorize)])`로 모든 Routing 경로에 토큰 검사를 적용합니다. 경로 함수는 `perform(command, payload)`를 호출하고, perform은 lab.call로 넘깁니다. 상태 충돌은 409, 연결/시간 초과는 503입니다.

## 3. RoutingLab의 함수

| 함수 | 입력 | 출력·효과 |
|---|---|---|
| `call(command, payload)` | snapshot/setup/bindings/publish/receive | 필요 시 소유 Thread 시작, 명령/Future 전달, 결과 대기 |
| `_run()` | 내부 명령 Queue | Pika 연결·기본 Direct 준비, 이벤트·명령 처리, 종료 |
| `setup(channel, kind, bindings)` | 소유 channel·종류·3 Binding | UUID Exchange·exclusive Queue 선언, 관측 상태 초기화 |
| `handle(channel, command, payload)` | 현재 명령 | 각 동작 실행 후 snapshot 반환 |
| `snapshot(channel)` | 소유 channel | passive Queue count, events, last_received, last_publish |
| `record(kind, message_id, **metadata)` | 관측 데이터 | 최근 200개 deque에 추가 |
| `shutdown()` | 없음 | end 명령, 연결 close, Thread join |
| `topic_matches(binding, routing_key)` | 패턴·key | 설명/검증용 bool. 실제 Broker 라우팅에 사용하지 않음 |

`call()`의 Python 명령 Queue와 RabbitMQ A/B/C는 서로 다릅니다. Thread는 channel을 소유하고 command 처리를 직렬화합니다. 첫 실제 snapshot에도 연결/토폴로지 준비가 필요하므로 **처음에는 자원이 생성**됩니다. 이후 snapshot은 메시지를 소비하지 않습니다.

## 4. 새 실험의 데이터 흐름

```text
Exchange 선택 → choose(kind): 화면 입력 기본값만 변경
 → '선택한 종류로 새 실험' → run('setup')
 → POST {exchange_type:'topic', bindings:['order.*','*.completed','#']}
 → Router setup() → perform('setup') → lab.call()
 → 소유 Thread → handle() → setup()
 → 이전 임시 Queue 삭제
 → 새 UUID Exchange 선언
 → Queue A/B/C 선언 → queue_bind 각각 수행
 → 이벤트·수신·최신 발행 상태 초기화
 → snapshot 반환 → Vue data 갱신
```

choose()만 호출하면 Broker 종류는 바뀌지 않습니다. data.exchange_type이 현재 실험, kind는 화면의 선택값입니다. 둘이 다르면 발행을 막고 새 실험 적용을 안내합니다.

Exchange는 auto_delete, Queue는 exclusive+auto_delete입니다. Queue들은 소유 연결 종료 시 삭제됩니다. setup은 이 단계의 대기 메시지를 삭제하므로 진행 중인 결과를 보존하려면 먼저 기록하세요. Phase 1/2 Queue는 건드리지 않습니다.

## 5. 발행: 사용자 예측과 Broker 판단

```text
run('messages')
 → {body:'order-test', routing_key:'order.created', prediction:['a','c']}
 → POST /routing/messages
 → handle('publish')
 → message_id=M1 생성
 → JSON envelope={body:'order-test', prediction:['a','c']}
 → basic_publish(exchange=실제 UUID, routing_key='order.created', body=bytes)
 → last_publish={message_id:M1, routing_key, prediction, publisher_confirmed:false}
 → PUBLISH_SENT 기록
 → Broker가 종류+Binding으로 실제 Queue 선택
```

prediction을 잘못 골라도 실제 Queue는 달라지지 않습니다. Broker는 envelope 안의 prediction을 읽어 라우팅하지 않습니다. Confirm 없이 발행하므로 최신 발행 기록은 Broker 수락·업무 완료를 확정하는 상태가 아닙니다.

기본 Binding으로 예상할 수 있는 결과:

| 종류 | A / B / C Binding | key | 실제 수신 대상 |
|---|---|---|---|
| Direct | error / info / error | error | A/C |
| Fanout | 무시 / 무시 / 무시 | anything | A/B/C |
| Topic | order.* / *.completed / # | order.created | A/C |
| Topic | order.* / *.completed / # | payment.completed | B/C |
| Topic | order.* / *.completed / # | order.created.eu | C |

이는 현재 고정된 실험 조건에서 확인한 라우팅입니다. 화면 미수신만으로 유실·발행 실패를 단정하지 않습니다.

## 6. 수신·ACK: 실제 결과의 출처

`run('receive')`는 POST `/routing/receive`를 호출합니다. 서버는 A/B/C 순서로 `basic_get(queue=..., auto_ack=False)`를 수행합니다.

```text
Queue A에서 basic_get → 전달 있음
 → properties.message_id / method.routing_key / body에서 복사본 정보 생성
 → DELIVERED 기록
 → basic_ack(method.delivery_tag)
 → ACK_SENT 기록
 → last_received에 복사본 추가

Queue B/C에서도 각각 최대 한 번
 → snapshot() → Ready count와 관측값 반환
```

같은 logical M1의 Fanout 복사본이 A/B/C에서 관측될 수 있습니다. basic_get의 delivery_tag는 수신 channel의 번호이고 메시지 ID와 다릅니다. 이 단계는 수신·ACK를 하나의 버튼 안에서 수행하며 Phase 1/2처럼 사람의 ACK를 기다리는 pending 상태가 없습니다.

`snapshot()`은 `queue_declare(passive=True).method.message_count`로 각 Ready를 조회합니다. exclusive Queue의 소유 channel에서 수행합니다. 일반 GET은 basic_get을 사용하지 않습니다.

`last_received`는 **마지막 수신 버튼의 결과**입니다. 다음 receive에서 비워 새 결과를 채웁니다. 전 기간 모든 수신 목록은 아닙니다. 오래된 메시지가 먼저 올 수 있으므로 최신 last_publish.message_id와 복사본 ID를 대조해야 합니다.

## 7. snapshot 데이터의 의미

```text
exchange_type: 현재 적용된 종류
exchange: 실제 UUID Exchange 이름
queues: [{id, name, binding, ready}, ...]
events: 최근 관측 이벤트, 최신 순
last_received: [{queue_id, message_id, body, routing_key, prediction, redelivered}, ...]
last_publish: {message_id, routing_key, prediction, publisher_confirmed:false} 또는 null
collected_at: 이 응답을 수집한 UTC 시각
```

Queue별 copied message를 하나의 수신 객체로 덮어쓰면 Fanout 학습 정보가 사라집니다. last_received는 Queue 라벨을 포함한 목록입니다. Phase 3 이벤트는 RoutingLab의 메모리 deque이며 공통 EventStore의 JSONL 이력과 별개입니다. API 재시작 후 복원되지 않습니다.

## 8. Binding 변경 로직

`handle('bindings')`는 요청 종류와 현재 종류가 다르면 ValueError를 발생시킵니다. 같은 종류에서 변경된 Queue만 old Binding을 unbind하고 new Binding을 bind합니다. 새 Exchange를 만드는 setup과 다릅니다.

```text
old Binding=error → M1 발행 → Queue A에 M1 보관
Binding을 new로 변경
 → 기존 M1은 Queue A에 그대로 있음
 → 이후 error 메시지는 새 Binding 기준으로 판단
 → receive하면 기존 M1을 먼저 받을 수 있음
```

Binding 변경은 앞으로 발행할 메시지의 전달 조건입니다. 이미 Queue에 들어간 메시지의 이동 규칙이 아닙니다.

## 9. Topic 계산 함수의 로직

Python topic_matches와 TypeScript topicMatches는 Binding/key를 `.`로 나눈 단어 배열을 비교합니다. 상태 `(i, j)`는 패턴의 i번째와 key의 j번째 비교 위치입니다.

- 패턴 끝이면 key도 끝이어야 match.
- 일반 단어는 정확히 같을 때 다음 단어로 이동.
- `*`는 key의 한 단어를 사용하고 둘 다 한 칸 이동.
- `#`는 0개 사용해 다음 패턴으로 이동하거나, 한 단어를 사용하고 같은 # 위치에서 비교 계속.
- Python `lru_cache`, TypeScript `Map`이 같은 `(i,j)`의 중복 계산을 줄입니다.

예를 들어 `order.#`와 `order`는 #가 0개 단어를 사용해 일치합니다. `order.*`와 `order.created.eu`는 *가 한 단어만 사용하므로 불일치합니다.

이 함수는 설명·예시·검증용입니다. 실제 handle('publish')는 이 함수로 Queue를 고르지 않고 Broker에 발행합니다.

## 10. Vue와 예시 모델

| 코드 | 역할 |
|---|---|
| `choose(next)` | 선택 종류·입력 기본 Binding/key 초기화 |
| `sync(snapshot)` | 서버 현재 종류·Binding을 입력 폼에 맞춤 |
| `read(syncForm)` | 활성 실제 모드에서 snapshot 조회; 필요하면 폼 동기화 |
| `run(action)` | 입력 검사, 예시 함수 또는 실제 POST 실행 |
| `rules` computed | 현재 입력으로 설명용 예상 Queue 계산 |
| watch + timer | 모드/활성 변경 및 2초 관측, generation으로 이전 응답 제외 |
| `RoutingDemo.setup/bind/publish/receive/snapshot` | 메모리 A/B/C에 예시 복사본 저장·수신 계산 |

정기 read는 폼을 매번 덮어쓰지 않으므로 작성 중 Binding을 보존합니다. 버튼 mutation과 관측 요청은 busy로 조절합니다. 연결 실패는 마지막 수집값을 유지하고 disconnect 이벤트로 공통 연결 상태를 변경합니다.

예시 publish는 종류와 topicMatches로 메모리 배열에 복사하고 receive는 각 배열 shift로 최대 한 개를 꺼냅니다. 실제 네트워크·Broker 확인과는 별개입니다.

## 11. 함수와 함께 하는 실험

1. Direct에서 A/C 모두 error이면 M1은 몇 Queue에서 관측될지 예측하세요.
2. prediction을 B로 선택하고 error를 발행하면 실제 결과가 왜 B가 아닌지 코드에서 찾으세요.
3. M1, M2를 같은 key로 연속 발행한 뒤 한 번 receive하면 어떤 ID가 last_received에 있는지 예측하세요.
4. Binding 변경과 setup 중 어느 동작이 기존 대기 메시지를 삭제하는지 찾으세요.
5. `order.#`와 `order`, `order.*`와 `order.created.eu`를 `(i,j)` 순서로 비교하세요.
6. `test_receipts_are_actual_queue_copies_independent_of_prediction`이 검증하는 경계를 설명하세요.

실제 smoke_phase3.py는 현재 임시 토폴로지를 초기화합니다. 사용자 진행 중인 실험과 함께 실행하지 마세요. 다음 실제 개발 단계는 [Phase 4 계획](../remaining-development-plan.md)이며 Confirm·Return을 다룹니다.
