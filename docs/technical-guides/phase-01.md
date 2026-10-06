# Phase 1 · 발행·전달·수동 ACK의 상태 전이

현재 프로젝트 구현의 핵심 코드를 발췌합니다. 파일의 주변 선언·imports·연결은 생략될 수 있으므로 전체 파일과 함께 읽으세요.

Producer와 Consumer를 분리하면 Consumer가 꺼져 있어도 메시지를 먼저 보관할 수 있습니다. 이 단계는 “받았다”와 “완료로 확인했다”를 구분해 Queue의 숫자를 읽는 연습입니다.

## 전체 흐름

Producer 발행 → 기본 Exchange → hello Queue · Ready → Consumer 전달 · Unacked → ACK → 다음 전달

## 용어

- **Producer / publish**: 메시지를 만드는 역할과 Broker에 보내는 동작입니다. 이 프로젝트에서는 Gateway가 Producer 코드를 실행합니다.
- **Queue / Ready**: Queue는 전달 대기 공간이고 Ready는 아직 전달하지 않은 메시지 수입니다.
- **Consumer / Unacked**: Consumer는 메시지를 받는 프로그램입니다. Unacked는 전달됐지만 Broker가 확인을 받지 않은 메시지 수입니다.
- **ACK / delivery_tag**: ACK는 Consumer의 전달 완료 응답입니다. delivery_tag는 해당 channel에서 전달을 식별하며 같은 channel에서 ACK해야 합니다.
- **Prefetch 1**: 이 Consumer가 ACK하지 않은 메시지를 한 개까지만 받는 설정입니다. ACK 후 다음 전달을 관찰할 수 있습니다.

## 발행은 어떤 데이터로 이루어질까요?

입력한 본문은 JSON으로 감싼 뒤 UTF-8 bytes로 보내고 message_id를 붙입니다. 기본 Exchange의 이름은 빈 문자열입니다. Routing Key에 hello를 넣어 같은 이름의 Queue로 전달하도록 합니다.

현재 Queue는 durable이고 메시지에는 delivery_mode=2가 있습니다. 하지만 Phase 1은 Publisher Confirm을 사용하지 않습니다. basic_publish 호출이 끝났다는 사실을 발행 요청 전송으로 기록하며 소비 완료나 발행 확인으로 부르지 않습니다.

## 전달만으로 메시지를 없애지 않는 이유

auto_ack=False이므로 Broker가 전달한 뒤 ACK를 기다립니다. 본문이 화면에 나타나도 메시지는 Unacked 상태입니다. Queue 안에 Ready만 있는 상태와 Consumer가 이미 받은 상태는 다릅니다.

세 개를 발행하면 Ready 3 / Unacked 0입니다. Consumer를 시작하면 Ready 2 / Unacked 1이 됩니다. 첫 ACK 후 다음 메시지가 바로 전달될 수 있어 Unacked가 계속 1처럼 보일 수 있습니다. 마지막 ACK 이후 두 숫자가 0이 됩니다.

## 브라우저 ACK 요청과 Pika 스레드

브라우저는 현재 attempt_id를 포함해 Gateway에 ACK를 요청합니다. API 스레드가 Pika channel을 직접 조작하지 않고 Python Queue로 명령을 전달합니다. channel을 소유한 Consumer 스레드가 실제 basic_ack를 호출합니다.

attempt_id 대조는 오래된 버튼 요청이 다음 메시지를 ACK하는 문제를 막습니다. Message ID는 논리 메시지, Attempt ID는 전달 시도입니다. 이 단계의 확인은 본문 확인 실습이며 실제 결제·DB 업무 처리는 하지 않습니다.

## 실제 코드 · Producer 발행

출처: [backend/app/messaging.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/messaging.py)

```python
def publish(body: str, count: int, queue=None):
    """기본 Exchange로 발행한다. 호출 반환은 소비 완료나 Confirm 수신을 뜻하지 않는다."""
    queue = queue or settings.queue
    message_ids = []
    with connection() as conn:
        channel = conn.channel()
        declare(channel, queue)
        for index in range(count):
            message_id = str(uuid4())
            text = body if count == 1 else f"{body} {index + 1}"
            channel.basic_publish(
                exchange="", routing_key=queue,
                body=json.dumps({"body": text}, ensure_ascii=False).encode("utf-8"),
                properties=pika.BasicProperties(
                    message_id=message_id, correlation_id=message_id,
                    content_type="application/json", delivery_mode=2,
                ),
            )
            events.record("PUBLISH_SENT", message_id, worker="producer-lab", body=text, exchange="", routing_key=queue, queue=queue)
            message_ids.append(message_id)
    # Phase 1 intentionally does not claim publisher-confirm guarantees.
    return {"message_ids": message_ids, "status": "PUBLISH_SENT", "publisher_confirmed": False}
```

- declare는 durable Queue를 준비합니다. count만큼 UUID를 만들고 본문과 properties를 발행합니다.
- exchange=""와 routing_key=queue가 기본 Exchange의 전달 규칙을 사용합니다. properties는 본문 밖의 메시지 메타데이터입니다.
- 반환값 publisher_confirmed=False와 PUBLISH_SENT가 현재 관측 범위를 보여 줍니다.

## 실제 코드 · 현재 전달만 ACK

출처: [backend/app/consumer.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/consumer.py)

```python
def _ack(self, channel, attempt_id):
    # 이전 버튼 요청이 다음 전달을 ACK하지 않도록 현재 시도를 먼저 대조한다.
    with self._lock:
        pending = self._pending
        tag = self._delivery_tag
    if not pending or pending["attempt_id"] != attempt_id:
        raise ValueError("현재 전달과 일치하지 않는 ACK입니다.")
    channel.basic_ack(delivery_tag=tag)
    with self._lock:
        self._pending = None
        self._delivery_tag = None
    events.record("ACK_SENT", pending["message_id"], attempt_id=attempt_id, worker="consumer-lab")
```

- 현재 pending과 delivery_tag를 읽고 요청 attempt_id를 대조합니다. 일치하지 않으면 완료 처리하지 않습니다.
- basic_ack는 이 전달의 tag를 사용합니다. 그 뒤 앱의 pending을 비우고 ACK_SENT를 기록합니다.
- 이 이벤트는 호출 기록입니다. Broker 반영 확인과 업무 완료는 별도이며 실제 Queue 지표도 봅니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| Consumer 없이 3개 발행 | Ready 3 / Unacked 0 | Broker가 전달 전 데이터를 보관합니다. |
| Consumer 시작 후 ACK 없이 대기 | Ready 2 / Unacked 1 | Prefetch 1이 추가 전달을 제한합니다. |
| 세 메시지 차례로 ACK | Ready 0 / Unacked 0 | 수신과 확인을 모두 끝냅니다. |

## 주의할 오해

- Ready 0만 보고 업무 성공을 결론 내리지 않습니다. Unacked나 업무 결과가 남을 수 있습니다.
- ACK를 보내는 코드와 업무를 처리하는 코드는 별개입니다. 실제 업무에서는 처리 완료를 판단한 뒤 ACK해야 합니다.

## 설명해 보기

- 첫 ACK 후 Unacked가 다시 1인 이유는 무엇인가요?
- auto_ack=True로 바꾸면 Consumer 종료 시 어떤 보호가 달라질까요?

## 참고 자료

- [RabbitMQ Work Queues](https://www.rabbitmq.com/tutorials/tutorial-two-python)
- [프로젝트 Consumer](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/consumer.py)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
