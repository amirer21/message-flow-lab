# Phase 11 · Pyro5 RPC와 MQ 호출 방식 비교

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

RPC는 원격 객체를 로컬 함수처럼 호출하고 보통 응답을 기다립니다. MQ Task 요청은 먼저 Queue에 넣고 나중에 결과를 확인할 수 있습니다. 동일 계산으로 대기·장애 결과를 비교합니다.

## 전체 흐름

Gateway 요청 → Pyro Proxy → Daemon → Calculator 함수 실행 → RPC 응답 / timeout → Celery 방식과 비교

## 용어

- **RPC**: Remote Procedure Call: 다른 프로세스의 함수를 네트워크를 통해 호출하는 방식입니다.
- **Proxy / Daemon**: Proxy는 원격 객체를 호출하는 클라이언트, Daemon은 객체를 등록하고 요청을 처리하는 서버입니다.
- **URI / Name Server**: URI는 원격 객체 주소입니다. Name Server는 이름에서 URI를 찾게 하는 선택 서비스입니다.
- **Timeout**: 호출자가 얼마나 기다릴지 제한합니다. 서버 실행을 자동 취소하거나 미실행을 증명하지 않습니다.

## 호출이 실제로 이동하는 위치

브라우저는 HTTP로 Gateway에 요청하고 Gateway의 Python 코드가 Pyro5 Proxy를 사용합니다. Pyro5 Daemon 안의 Calculator가 함수를 실행하고 결과를 반환합니다. 브라우저가 Pyro wire protocol에 직접 연결하는 구조는 아닙니다.

expose는 호출할 메서드를 공개합니다. 입력으로 임의 URI·객체·메서드 이름을 받아 서버에 연결시키지 않고, 전용 서비스의 계산 메서드만 허용합니다. 아래는 Compose 내부 직접 URI 연결 예시입니다.

## 장애 때 달라지는 경험

RPC 서비스가 정지해 있으면 연결·호출이 실패할 수 있습니다. MQ에서는 Worker가 없어도 Broker가 정상이라면 요청을 Queue에 남길 수 있습니다. 하지만 Broker가 중단되면 MQ 발행도 실패할 수 있습니다.

RPC timeout이 나더라도 서버가 계산이나 업무를 이미 진행했을 수 있습니다. 같은 요청을 다시 호출하면 중복 효과가 생길 수 있어 멱등 업무 키가 필요합니다.

## 비교 범위를 정확히 정하기

동일한 순수 합산 add(2, 3)으로 정상 결과와 대기를 비교하고, 서비스 정지·느린 계산·호출 중 단절의 조건을 하나씩 바꿉니다. 시간초과 후 서버 로그나 결과 기록을 다시 확인합니다.

MQ도 request/reply를 구현할 수 있고 Pyro도 다양한 호출 방식을 지원합니다. RPC는 항상 동기만 가능하고 MQ는 절대 응답을 못 받는다고 설명하지 않고, 이번에 선택한 실행 모델을 비교합니다.

## 설계 예시 · Calculator 서버

```python
import Pyro5.api

@Pyro5.api.expose
class Calculator:
    def add(self, x, y):
        return x + y

with Pyro5.api.Daemon(host="0.0.0.0", port=9090) as daemon:
    uri = daemon.register(Calculator(), objectId="calculator")
    print(uri)
    daemon.requestLoop()
```

- 0.0.0.0은 컨테이너 내부 접속용 설계입니다. 호스트 포트를 외부에 공개하는 설정은 별도이며 현재 Compose에는 Pyro 서비스가 없습니다.

## 설계 예시 · Gateway의 원격 호출

```python
import Pyro5.api
import Pyro5.errors

def rpc_add(x, y):
    with Pyro5.api.Proxy("PYRO:calculator@pyro-service:9090") as proxy:
        proxy._pyroTimeout = 3
        try:
            return {"result": proxy.add(x, y)}
        except Pyro5.errors.TimeoutError:
            return {"outcome": "TIMEOUT", "server_cancelled": False}
```

- pyro-service는 앞으로 추가할 Compose 서비스 이름입니다. 같은 네트워크 안의 Gateway에서 호출한다고 가정합니다.
- timeout은 응답 대기를 끝낸 것입니다. server_cancelled=False는 자동 취소를 관측하지 않았음을 표시합니다.
- 실제 Gateway에는 접속 오류·허용 입력·관측 이력·동시성·HTTP 오류 정책을 더해야 합니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| RPC와 Celery로 같은 합산 요청 | 정상 결과 일치 | 호출 모델과 계산 로직을 분리합니다. |
| RPC 서비스 / Celery Worker 정지 | 호출 실패 / Task 대기 비교 | 현재 시점에 필요한 서버가 다릅니다. |
| timeout보다 오래 실행하는 함수 | 호출자는 먼저 종료될 수 있음 | 서버의 계속 실행 여부를 별도로 관측합니다. |

## 주의할 오해

- 네트워크 timeout을 서버 작업 rollback이나 취소로 처리하면 안 됩니다.
- Pyro5와 Pika는 이름이 비슷해도 RPC와 AMQP 클라이언트라는 서로 다른 라이브러리입니다.

## 설명해 보기

- RPC timeout 후 같은 주문을 다시 요청하면 어떤 업무 키가 필요할까요?
- Worker가 없어도 MQ 요청을 남길 수 있으려면 어떤 서비스는 살아 있어야 하나요?

## 참고 자료

- [Pyro5 Clients](https://pyro5.readthedocs.io/en/latest/clientcode.html)
- [Pyro5 Servers](https://pyro5.readthedocs.io/en/latest/servercode.html)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
