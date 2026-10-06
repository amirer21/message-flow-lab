# Phase 8 · Kombu의 추상화와 남는 책임

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

Pika로 배운 Broker 개념을 Kombu의 Connection·Exchange·Queue·Producer·Consumer 객체로 다시 표현합니다. 코드가 줄어들어도 ACK, 재전달, 멱등 업무 설계의 책임은 남습니다.

## 전체 흐름

Connection → Exchange + Queue 객체 → Producer.publish → Consumer callback → message.ack

## 용어

- **Connection / Transport**: 서버 연결과 메시징 구현을 추상화합니다. transport마다 지원 보장이 같다고 가정하지 않습니다.
- **Entity 선언**: Exchange·Queue 객체로 이름·종류·Binding·durable 속성을 기술합니다.
- **Serializer / accept**: 발행 데이터 직렬화와 소비 허용 형식입니다. JSON만 허용하는 방향으로 제한합니다.
- **message.ack()**: Kombu 메시지 객체의 확인 동작입니다. 업무 완료를 판단하는 코드는 여전히 직접 필요합니다.

## Pika 코드와 대응시키기

Pika의 queue_declare/queue_bind가 Kombu Queue 객체 선언으로, basic_publish가 Producer.publish로, basic_ack가 message.ack로 대응합니다. 연결·메시지·토폴로지 객체를 조합해 코드의 반복을 줄입니다.

아래는 RabbitMQ AMQP transport의 학습용 send-once/consume-once 예시입니다. BROKER_URL은 컨테이너 환경변수에서 읽고 코드에 실제 비밀번호를 넣지 않습니다.

## 선언과 소비의 생명주기

Producer의 declare=[queue]가 토폴로지를 준비한 뒤 발행합니다. Consumer는 callbacks를 등록하고 drain_events로 전달 이벤트를 처리합니다. callback 안의 message.ack가 전달을 확인합니다.

context manager는 연결·소비 자원의 수명을 정리합니다. 본문을 print한 예시가 실제 DB 업무를 완료했다고 뜻하지는 않습니다. 예외·연결 복구·timeout은 실제 Worker에서 추가해야 합니다.

## 공정한 라이브러리 비교

같은 Queue 속성, payload, ACK 정책과 장애 위치로 Pika와 Kombu를 비교해야 라이브러리 차이를 볼 수 있습니다. 단순 정상 발행만 비교하면 신뢰성 동작이 빠집니다.

publish retry 옵션을 켜면 연결 실패 시 재발행 가능성과 중복을 이해해야 합니다. Confirm 설정과 mandatory 처리는 사용 transport·버전 문서를 확인하고 실제 Broker로 검증합니다.

## 설계 예시 · Kombu로 한 번 발행하고 소비

```python
import os
from kombu import Connection, Exchange, Queue, Producer, Consumer

exchange = Exchange("phase8.jobs", type="direct", durable=True)
queue = Queue("phase8.jobs.q", exchange=exchange, routing_key="job", durable=True)

def received(body, message):
    print("수신 본문:", body)
    message.ack()

with Connection(os.environ["BROKER_URL"]) as conn:
    Producer(conn).publish(
        {"body": "hello"}, exchange=exchange, routing_key="job",
        serializer="json", declare=[queue], delivery_mode=2,
    )
    with Consumer(conn, queues=[queue], callbacks=[received],
                  accept=["json"], prefetch_count=1):
        conn.drain_events(timeout=10)
```

- 이 예시는 Kombu 설치·BROKER_URL·실행 가능한 RabbitMQ가 필요합니다. 현재 실습 이미지에는 Kombu가 추가돼 있지 않습니다.
- drain_events는 한 이벤트를 기다립니다. 계속 실행하는 Worker에는 종료 신호·timeout 처리·반복 루프가 필요합니다.
- 발행 코드에 Confirm 보장을 추가했다고 간주하지 않습니다. 목적은 객체와 Pika 동작의 대응을 읽는 것입니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| Pika와 같은 데이터 발행·수동 ACK | 내용과 Queue 결과 비교 | 사용 API는 달라도 Broker 개념은 이어집니다. |
| ACK 전에 Consumer 종료 | 재전달 확인 | 추상화가 재전달 책임을 제거하지 않습니다. |
| JSON 외 입력 | 허용 포맷 제한 확인 | 임의 객체 역직렬화를 열지 않습니다. |

## 주의할 오해

- Kombu API를 Celery Task API와 같은 것으로 부르지 않습니다. Celery는 Kombu 위에 Task 기능을 더합니다.
- transport를 바꿔도 RabbitMQ의 Confirm·Routing 동작이 그대로라고 가정하지 않습니다.

## 설명해 보기

- Kombu Queue 객체가 Pika의 어떤 명령들을 감싸나요?
- message.ack()를 언제 호출해야 하는 책임은 누가 갖나요?

## 참고 자료

- [Kombu Consumers](https://docs.celeryq.dev/projects/kombu/en/stable/userguide/consumers.html)
- [Kombu Producers](https://docs.celeryq.dev/projects/kombu/en/stable/userguide/producers.html)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
