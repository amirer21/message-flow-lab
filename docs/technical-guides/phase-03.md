# Phase 3 · Exchange·Binding으로 전달 대상 결정

현재 프로젝트 구현의 핵심 코드를 발췌합니다. 파일의 주변 선언·imports·연결은 생략될 수 있으므로 전체 파일과 함께 읽으세요.

Queue가 메시지를 골라 가져오는 구조가 아니라 Producer의 발행 대상을 Exchange와 Binding으로 연결합니다. 같은 메시지가 여러 Queue에 복사되는 경우와 한 Queue에서 여러 Worker가 나누어 받는 경우를 구분합니다.

## 전체 흐름

Producer + Routing Key → Exchange의 종류 → Binding 규칙 비교 → Queue A / B / C → Queue별 실제 수신

## 용어

- **Binding**: Exchange와 Queue를 연결하는 규칙입니다. 연결할 때 Binding Key를 지정합니다.
- **Direct**: Routing Key가 Binding Key와 정확히 같은 Queue로 전달합니다. 같은 key로 연결된 여러 Queue에도 복사됩니다.
- **Fanout**: Routing Key를 기준으로 고르지 않고 연결된 모든 Queue에 복사합니다.
- **Topic**: 점으로 나눈 단어를 비교합니다. *는 한 단어, #는 0개 이상입니다.
- **Exclusive Queue**: 소유 연결에 종속된 임시 Queue입니다. 현재 Phase 3은 API 연결 종료 시 사라집니다.

## 세 가지 종류를 코드로 읽기

Direct에서 A/C의 Binding이 error이면 error 메시지는 A/C에 각각 생깁니다. Fanout에서는 A/B/C 모두 받습니다. Topic의 order.*는 order.created와 일치하지만 order.created.eu와는 일치하지 않습니다.

order.#는 order와 order.created.eu도 받을 수 있습니다. 이 판단은 Broker가 실행합니다. 브라우저의 topicMatches는 설명용 예상 계산이며 실제 수신 관측으로 기록하지 않습니다.

## 복사와 경쟁 소비의 차이

Fanout으로 세 Queue에 복사하면 각 Queue가 독립적으로 확인합니다. A가 ACK해도 B의 복사본은 남을 수 있습니다. 반면 한 Queue를 Worker 세 개가 소비하면 각 전달을 나누어 처리하는 경쟁 소비입니다.

Message ID가 같아도 Queue가 다르면 다른 복사본입니다. 이벤트에 Queue를 함께 기록해야 세 전달을 하나의 이벤트로 잘못 합치지 않습니다.

## Binding 변경과 실제 수신

Binding은 앞으로 발행될 메시지의 길을 바꿉니다. 이미 Queue에 저장된 메시지를 새 Queue로 이동시키지 않습니다. 현재 UI의 수신 버튼은 basic_get으로 Queue별 최대 한 개를 꺼내고 ACK합니다.

최신 메시지보다 이전 메시지가 먼저 수신될 수 있으므로 Message ID를 대조합니다. 미수신만으로 발행 실패나 유실을 확정하지 않습니다. 새 실험은 이 단계의 임시 토폴로지를 삭제·재생성합니다.

## 실제 코드 · 임시 Exchange와 Binding 생성

출처: [backend/app/routing.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/routing.py)

```python
self._kind = kind
self._exchange = f"phase3.{uuid4().hex}"
channel.exchange_declare(exchange=self._exchange, exchange_type=kind, auto_delete=True)
self._queues = []
for index, binding in enumerate(bindings):
    label = "abc"[index]
    name = f"{self._exchange}.{label}"
    channel.queue_declare(queue=name, exclusive=True, auto_delete=True)
    channel.queue_bind(queue=name, exchange=self._exchange, routing_key=binding)
    self._queues.append({"id": label, "name": name, "binding": binding})
self._records.clear()
self._received = []
self._last_publish = None
self.record("TOPOLOGY_CREATED", exchange_type=kind)
```

- uuid가 실험 자원 이름을 구분합니다. exchange_type이 실제 Broker의 Routing 방식을 정합니다.
- Queue별 queue_bind가 binding을 연결합니다. exclusive=True이므로 영속성 실험에 재사용하면 안 됩니다.
- 첫 부분은 기존 토폴로지를 지운 후의 생성 구간입니다. kind·bindings·channel은 같은 메서드의 인자입니다.

## 실제 코드 · Queue에서 실제 복사본 수신

출처: [backend/app/routing.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/routing.py)

```python
elif command == "receive":
    self._received = []
    for queue in self._queues:
        method, properties, body = channel.basic_get(queue=queue["name"], auto_ack=False)
        if method is None:
            continue
        envelope = json.loads(body)
        item = {"queue_id": queue["id"], "message_id": properties.message_id,
                "body": envelope["body"], "routing_key": method.routing_key,
                "prediction": envelope.get("prediction", []), "redelivered": method.redelivered}
        self.record("DELIVERED", **item)
        channel.basic_ack(delivery_tag=method.delivery_tag)
        self.record("ACK_SENT", properties.message_id, queue_id=queue["id"])
        self._received.append(item)
```

- basic_get은 지표 조회가 아니라 소비입니다. 메시지가 없으면 method=None입니다.
- body·message_id·routing_key·queue_id를 실제 응답에서 읽고 같은 channel로 ACK합니다. 사용자의 prediction은 정답을 결정하지 않습니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| Direct에 error 발행 | A/C 수신 | 같은 Binding Key로 연결한 두 Queue가 일치합니다. |
| Topic에 order.created.eu 발행 | 기본 # Queue C만 수신 | order.*는 한 단어만 추가로 허용합니다. |
| 메시지 발행 후 Binding 변경 | 기존 복사본은 원래 Queue에 남음 | Routing은 발행 시점에 적용됩니다. |

## 주의할 오해

- Binding이 없는 메시지의 미수신을 Consumer 처리 완료로 해석하지 않습니다.
- 현재 임시 Queue는 API 연결 종료 시 삭제됩니다. Broker 영속성과 별개의 실험입니다.

## 설명해 보기

- Fanout 3개 Queue와 한 Queue의 3개 Worker는 어떻게 다를까요?
- order.#와 order.*가 order에 대해 다른 결과를 내는 이유는 무엇인가요?

## 참고 자료

- [프로젝트 Routing 코드](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/routing.py)
- [RabbitMQ Topic 튜토리얼](https://www.rabbitmq.com/tutorials/tutorial-five-python)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
