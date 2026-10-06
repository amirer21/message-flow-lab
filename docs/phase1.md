# Phase 1 · 첫 메시지 보내기와 용어 설명

## ACK란 무엇인가요?

ACK는 Acknowledgement의 줄임말로 ‘확인 응답’입니다. Consumer가 Broker에 “이 전달은 완료로 처리해도 됩니다”라고 알려 줍니다. Broker가 ACK를 반영하면 해당 Queue의 메시지를 더 이상 재전달을 위해 보관하지 않습니다.

편지로 생각하면 Queue는 편지함, Consumer는 편지를 꺼내 읽는 사람, ACK는 읽었다는 확인입니다. 메시지를 받는 것과 ACK를 보내는 것은 별개입니다.

이 실습에서는 본문을 확인하고 버튼으로 수동 ACK를 보냅니다. 실제 업무 처리는 실행하지 않습니다. 업무에서는 처리 완료 후 ACK하도록 구현해야 하며, ACK 자체가 DB 저장·결제 성공을 자동 검증하지는 않습니다.

## 숫자가 변하는 순서

| 동작 | 관찰 | 의미 |
|---|---|---|
| Consumer 없이 3개 발행 | Ready 3 / Unacked 0 | 전달 대기 3개 |
| Consumer 시작 | Ready 2 / Unacked 1 | 하나를 받았지만 확인 전 |
| ACK 한 번 | 다음 메시지 전달 가능 | Prefetch 1이므로 다음 한 개를 받음 |
| 세 메시지 모두 ACK | Ready 0 / Unacked 0 | 전달·확인 대기 없음 |

Consumer가 계속 실행 중이면 ACK 직후 다음 메시지가 전달되어 Unacked가 다시 1일 수 있습니다. 실제 관리 지표 수집에는 지연이 있습니다. ACK 전 Consumer 연결이 닫히면 해당 메시지는 다시 전달될 수 있도록 Queue에 돌아갑니다.

화면의 ACK 전송 숫자는 앱의 전송 기록이며 Broker 반영 시각과 구분합니다. Consumer ACK와 Producer가 받는 Publisher Confirm도 서로 다른 확인입니다. [RabbitMQ 공식 설명](https://www.rabbitmq.com/docs/confirms)을 참고하세요.

## 실습의 전체 흐름

```text
Vue 화면의 발행 버튼
  → FastAPI Gateway의 Python Producer
  → Pika / AMQP로 RabbitMQ에 발행
  → 기본 Exchange → hello Queue
  → Python Consumer가 한 개 수신
  → 본문 확인 후 ACK 버튼
  → Gateway를 거쳐 Consumer가 Broker에 ACK 전송
```

예시 모드에서는 위 흐름을 브라우저에서 계산합니다. 실제 연결 모드에서 Docker의 Python API·RabbitMQ와 통신합니다.

## 용어 설명

### 메시지가 이동하는 흐름

| 용어 | 쉬운 설명 |
|---|---|
| MQ · Message Queue | 프로그램 사이에서 메시지를 잠시 보관하고 전달하는 방식입니다. 보내는 프로그램과 받는 프로그램이 동시에 실행되지 않아도 일을 이어갈 수 있습니다. |
| Message · 메시지 | 프로그램 사이에 전달하는 데이터 한 묶음입니다. 이 실습에서는 입력한 hello 한 개가 메시지 한 개입니다. |
| Payload · 본문 | 메시지 안에 담긴 실제 내용입니다. 편지로 비유하면 봉투 안의 글에 해당합니다. |
| Producer · 생산자 | 메시지를 만들어 보내는 프로그램입니다. 발행 버튼을 누르면 Gateway의 Python 코드가 Producer 역할을 합니다. |
| Publish · 발행 | Producer가 메시지를 Broker에 보내는 동작입니다. 발행 요청을 보냈다는 기록만으로 수신이나 업무 완료를 확정할 수는 없습니다. |
| Broker · 중개 서버 | 메시지를 받아 Queue에 보관하고 Consumer에게 전달하는 서버입니다. 이 실습의 Broker 소프트웨어는 RabbitMQ입니다. |
| Exchange · 분배 창구 | Broker 안에서 메시지를 어느 Queue로 보낼지 결정합니다. Phase 1은 기본 Exchange를 통해 이름이 hello인 Queue로 보냅니다. |
| Routing Key · 전달 기준 | Exchange가 Queue를 고를 때 사용하는 값입니다. Phase 1은 hello라는 Queue 이름을 Routing Key로 사용합니다. 자세한 분기는 Phase 3에서 배웁니다. |
| Queue · 대기열 | 전달할 메시지를 보관하는 공간입니다. 편지함처럼 Consumer가 잠시 없어도 메시지가 기다릴 수 있습니다. 이 실습의 Queue 이름은 hello입니다. |
| Consumer · 소비자 | Queue에서 메시지를 받아 확인하거나 처리하는 프로그램입니다. 시작 버튼으로 연결하고, 멈춤 버튼으로 연결을 종료합니다. |

### ACK와 화면의 숫자 읽기

| 용어 | 쉬운 설명 |
|---|---|
| ACK · Acknowledgement | Consumer가 Broker에 보내는 전달 완료 확인입니다. Broker가 ACK를 반영하면 해당 Queue의 메시지는 더 이상 재전달을 위해 보관되지 않습니다. |
| Manual ACK · 수동 확인 | 메시지를 받자마자 자동 확인하지 않고, Consumer가 명시적으로 ACK를 보내는 방식입니다. 여기서는 본문을 읽고 ACK 버튼을 눌러 시점을 직접 관찰합니다. |
| Ready · 전달 대기 | 아직 Consumer에게 전달하지 않은 메시지 수입니다. 메시지 3개를 보내고 Consumer를 시작하지 않으면 Ready는 3입니다. |
| Unacked · 확인 대기 | Consumer에게 전달했지만 Broker가 아직 ACK를 받지 않은 메시지 수입니다. 단순히 업무가 실행 중이라는 뜻은 아닙니다. |
| Prefetch 1 · 한 개씩 확인 | 이 Consumer가 ACK하지 않은 메시지를 최대 한 개 받도록 설정합니다. 현재 메시지를 ACK해야 다음 메시지를 받으므로 변화를 한 개씩 볼 수 있습니다. |
| Message ID · 메시지 번호 | 논리적인 메시지를 구분하는 번호입니다. 같은 메시지가 다시 전달되면 이 번호로 같은 메시지인지 비교합니다. |
| Attempt ID · 전달 시도 번호 | 한 번의 전달을 구분하는 실습용 번호입니다. 같은 메시지가 재전달되면 새 번호가 생기며, 이전 전달의 ACK로 다음 전달을 잘못 확인하지 않도록 사용합니다. |
| Redelivery · 재전달 | ACK하지 않은 메시지가 연결 종료 등으로 다시 전달되는 것입니다. 같은 메시지를 받았다고 업무가 처음 실행되는 것은 아니므로 Phase 2에서 중복 처리를 실험합니다. |
| ACK 전송 · ACK_SENT | 앱이 ACK 호출을 보낸 기록입니다. Broker가 반영한 정확한 시각이나 실제 업무 성공을 자동으로 증명하지는 않습니다. Queue 지표도 함께 확인합니다. |
| Publisher Confirm · 발행 확인 | Broker가 Producer에게 보내는 발행 확인입니다. Consumer가 보내는 ACK와 방향·목적이 다릅니다. Phase 1에서는 사용하지 않으며 Phase 4에서 배웁니다. |

### 이 실습을 실행하는 도구

| 용어 | 쉬운 설명 |
|---|---|
| RabbitMQ | 메시지를 보관하고 전달하는 Broker 소프트웨어입니다. 관리 화면에서는 Queue의 상태를 볼 수 있습니다. |
| Python · Pika | Python은 Producer와 Consumer를 작성하는 언어입니다. Pika는 그 Python 코드가 RabbitMQ와 메시지·ACK를 주고받게 해 주는 라이브러리입니다. |
| AMQP · 메시지 통신 규칙 | Producer·Consumer와 RabbitMQ가 메시지를 주고받는 약속입니다. 이 실습에서는 AMQP 0-9-1을 사용하며 접속 포트는 5672입니다. |
| Gateway · FastAPI · API | 브라우저의 발행·시작·ACK 요청을 받아 Python 코드로 실행하는 연결 창구입니다. FastAPI로 만들었고 로컬 주소는 localhost:8000입니다. 브라우저가 RabbitMQ에 직접 접속하는 구조는 아닙니다. |
| Vue · 대시보드 | 버튼·숫자·메시지 내용을 보여 주는 웹 화면을 만드는 도구입니다. 로컬 화면은 localhost:5173에서 열립니다. |
| Docker · Container · Compose | 컨테이너는 프로그램을 실행하는 분리된 환경입니다. Docker가 실행하고 Compose가 RabbitMQ·Gateway·화면을 한 번에 구성합니다. |
| Management · 관리 화면 | RabbitMQ의 Queue와 연결 상태를 살펴보는 화면입니다. 포트 15672를 사용하며, 메시지를 주고받는 AMQP 포트 5672와 역할이 다릅니다. |
| LAB_TOKEN · 실습 토큰 | Gateway의 실험 요청을 허용할지 확인하는 비밀 값입니다. 실제 연결 화면에 입력하며 RabbitMQ 관리 화면의 비밀번호와는 별개입니다. |
| 예시 모드 · 실제 연결 | 예시 모드는 브라우저에서 설명용 상황을 계산합니다. 실제 연결은 Docker 환경의 API와 RabbitMQ를 사용합니다. 예시 숫자는 실제 Broker의 관측값이 아닙니다. |

