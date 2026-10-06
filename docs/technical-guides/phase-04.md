# Phase 4 · 발행 확인·반환·영속성의 세 경계

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

발행 함수의 반환, Broker 확인, Queue에 전달됨, Consumer 업무 완료를 서로 구분합니다. 신뢰성은 성공 표시 하나를 추가하는 문제가 아니라 어디까지 확인했는지 기록하는 설계입니다.

## 전체 흐름

Producer 발행 → Broker Confirm / NACK → mandatory Return 여부 → durable Queue + persistent → Consumer 업무 / ACK

## 용어

- **Confirm**: Broker가 발행자에게 보내는 확인입니다. Consumer가 보내는 ACK와 별개입니다.
- **mandatory / Return**: 라우팅할 Queue가 없을 때 발행자에게 반환하도록 요청하는 옵션과 반환 응답입니다.
- **Durable / Persistent**: Durable은 Queue의 수명 설정, persistent는 메시지 저장 의도입니다. 서로 다른 설정입니다.
- **Unknown outcome**: 연결 단절로 결과를 확인하지 못한 상태입니다. 미확인은 발행 실패와 동일하지 않습니다.

## 신뢰성 요구를 질문으로 나누기

Confirm은 발행 측 확인이며 업무 결과를 보장하지 않습니다. mandatory는 unroutable을 감지하기 위한 별도 설정입니다. Broker가 unroutable 메시지를 처리했다는 확인과 해당 메시지의 Return을 함께 받을 수 있습니다.

따라서 UI는 confirmed, returned, 처리 결과를 각각 표시해야 합니다. Return이 있었다면 연결된 Queue에 전달됐다는 의미로 성공을 표시하면 안 됩니다.

## Pika BlockingConnection에서 결과 분류

confirm_delivery를 켜면 basic_publish가 확인을 기다리는 방식으로 동작합니다. mandatory 발행의 라우팅 실패는 UnroutableError, Broker NACK는 NackError로 처리할 수 있습니다. 설치 버전의 예외·연결 동작을 확인합니다.

연결 오류·timeout은 경우에 따라 발행 전 실패인지 발행 후 확인 유실인지 구분하기 어렵습니다. 아래 교육 예시는 보수적으로 UNKNOWN으로 분류합니다. 자동으로 다시 보내면 중복 발행될 수 있어 업무 키와 이력이 필요합니다.

## 재시작 실험에서 무엇을 증명할까요?

durable Queue와 delivery_mode=2 메시지를 전용 Broker에 남긴 뒤 정상 재시작하고 내용을 확인합니다. 임시 Queue와 다른 이름을 사용해 속성 충돌을 피합니다. 동일 이름 Queue를 다른 durable 설정으로 선언하면 채널 오류가 날 수 있습니다.

정상 재시작 통과는 전원 손실·디스크 손실·다중 노드 장애까지 보장하는 결과가 아닙니다. 테스트가 확인한 장애 범위를 기록하고 사용자 진행 중인 실험 Broker는 임의 중단하지 않습니다.

## 설계 예시 · 발행 결과를 분리해서 반환

```python
import pika

def publish_checked(ch, exchange, key, body):
    ch.confirm_delivery()
    try:
        ch.basic_publish(
            exchange=exchange, routing_key=key, body=body,
            mandatory=True,
            properties=pika.BasicProperties(delivery_mode=2),
        )
    except pika.exceptions.UnroutableError:
        return {"outcome": "RETURNED", "routed": False}
    except pika.exceptions.NackError:
        return {"outcome": "NACKED"}
    except pika.exceptions.AMQPError:
        return {"outcome": "UNKNOWN", "retry_automatically": False}
    return {"outcome": "CONFIRMED", "consumer_done": False}
```

- ch는 같은 스레드에서 소유하는 연결된 channel이며 Exchange·Queue·Binding은 사전에 선언해야 합니다.
- CONFIRMED의 consumer_done=False는 결과를 섞지 않기 위한 표시입니다. 실제 업무 결과는 별도 기록으로 확인합니다.
- 이 코드는 핵심 분류 예시입니다. API timeout, 오류 이전 성공 여부, message_id·관측 이벤트와 shutdown 처리는 실제 구현에서 더해져야 합니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 정상 Binding으로 mandatory 발행 | Confirm과 Queue 수신 각각 확인 | 발행 측 확인과 전달 대상은 다른 사실입니다. |
| Binding 없는 key로 mandatory 발행 | Return 관측 | Consumer가 꺼진 상태와 라우팅 실패를 구분합니다. |
| 전용 Broker의 정상 재시작 | 선언된 durable/persistent 데이터 비교 | 확인한 재시작 범위를 기록합니다. |

## 주의할 오해

- Timeout 뒤 무조건 새 Message ID로 재발행하면 중복 업무를 만들 수 있습니다.
- 실제 Broker의 확인을 받지 않고 기본값 confirmed=True를 표시하면 안 됩니다.

## 설명해 보기

- Confirm을 받아도 업무가 끝나지 않은 이유는 무엇인가요?
- 발행 후 확인 응답만 유실되면 재시도를 어떻게 결정해야 할까요?

## 참고 자료

- [RabbitMQ Confirm / ACK](https://www.rabbitmq.com/docs/confirms)
- [Pika 발행 확인 API](https://pika.readthedocs.io/en/stable/examples/blocking_delivery_confirmations.html)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
