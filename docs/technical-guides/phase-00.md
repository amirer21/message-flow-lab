# Phase 0 · 실습 환경과 통신 경계

현재 프로젝트 구현의 핵심 코드를 발췌합니다. 파일의 주변 선언·imports·연결은 생략될 수 있으므로 전체 파일과 함께 읽으세요.

처음에는 설치 명령보다 “어떤 프로그램이 어디에서 실행되고 누구와 통신하는가”를 이해합니다. 브라우저, Python API, RabbitMQ는 서로 다른 프로세스이며 각자 다른 접속 주소와 책임을 갖습니다.

## 전체 흐름

브라우저 · localhost:5173 → HTTP / 실습 토큰 → FastAPI · localhost:8000 → AMQP 5672 → RabbitMQ · lab vhost

## 용어

- **Container**: 이미지에 담긴 프로그램을 실행하는 분리된 환경입니다. 이미지 다운로드와 컨테이너 실행은 서로 다른 단계입니다.
- **Compose service**: RabbitMQ·API·화면을 서비스 이름과 설정으로 묶은 실행 정의입니다.
- **Port / host**: 포트는 서버의 입구 번호, host는 서버 위치입니다. localhost는 그 코드를 실행하는 환경 자신을 가리킵니다.
- **vhost**: 한 RabbitMQ 안에서 Queue·Exchange를 분리하는 논리 공간입니다. 현재 실습은 lab을 사용합니다.
- **Volume**: 컨테이너를 교체해도 유지할 데이터를 별도로 보관합니다. 컨테이너 삭제와 데이터 볼륨 삭제는 다릅니다.

## 왜 Gateway를 거칠까요?

브라우저는 HTTP로 버튼 요청을 보냅니다. Gateway는 토큰과 입력을 확인하고 Pika로 RabbitMQ에 연결합니다. 이 구조에서 Broker 계정은 서버 환경변수에 있고, 브라우저에는 RabbitMQ 비밀번호를 주지 않습니다.

localhost:5173은 화면, localhost:8000은 API, localhost:15672는 RabbitMQ 관리 화면입니다. 메시지 전송은 AMQP 5672를 사용합니다. 관리 화면이 열린다는 사실만으로 발행·소비가 성공한 것은 아닙니다.

## Docker 안과 밖에서 주소가 달라지는 이유

API 컨테이너 안의 localhost는 API 컨테이너 자신입니다. RabbitMQ 서비스에 접속할 때는 Compose 네트워크의 서비스 이름 rabbitmq를 사용합니다. PC의 브라우저에서는 PC에 공개한 localhost 포트로 접속합니다.

healthcheck는 실행 준비 상태를 확인합니다. depends_on의 service_healthy는 시작 순서를 도와주지만 이후 장애나 업무 성공을 자동으로 해결하지 않습니다. /health와 실제 Broker 연결 확인을 따로 관찰합니다.

## 환경변수와 인증

.env는 로컬 설정 파일입니다. Docker가 값을 API와 Broker에 전달하고 Python settings가 읽습니다. LAB_TOKEN은 API 실습 요청을 허용하는 값이며 RabbitMQ 계정 비밀번호와 다릅니다. 토큰을 코드나 GitHub에 넣지 않습니다.

CORS는 브라우저가 어느 출처의 화면에서 API를 호출할 수 있는지 제한합니다. CORS 허용과 토큰 인증은 별개입니다. 게시된 HTTPS 화면에서 HTTP 로컬 Gateway를 바로 연결하기 어려우므로 로컬 실습 화면을 사용합니다.

## 실제 코드 · AMQP 연결의 생명주기

출처: [backend/app/messaging.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/messaging.py)

```python
@contextmanager
def connection():
    """AMQP 연결을 열고 with 블록 종료 시 닫는다. 접속값은 서버 환경변수에서 읽는다."""
    params = pika.ConnectionParameters(
        host=settings.rabbit_host, port=settings.rabbit_port,
        virtual_host=settings.rabbit_vhost,
        credentials=pika.PlainCredentials(settings.rabbit_user, settings.rabbit_password),
        heartbeat=30, blocked_connection_timeout=5, socket_timeout=3,
        stack_timeout=5, connection_attempts=1,
    )
    conn = pika.BlockingConnection(params)
    try:
        yield conn
    finally:
        if conn.is_open:
            conn.close()
```

- ConnectionParameters는 host·vhost·계정과 연결 timeout을 묶습니다. 실제 값은 settings에서 읽습니다.
- BlockingConnection이 TCP/AMQP 연결을 엽니다. channel은 이 연결 위에서 만들며 발행·ACK 같은 명령을 전달합니다.
- yield 이후 호출자가 작업하고 finally에서 열린 연결을 닫습니다. heartbeat는 연결 생존 확인이며 업무 완료 확인은 아닙니다.

## 실제 코드 · 실습 API 토큰 확인

출처: [backend/app/main.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/main.py)

```python
def authorize(x_lab_token: str = Header(default="")):
    if not settings.lab_token or not secrets.compare_digest(x_lab_token.encode(), settings.lab_token.encode()):
        raise HTTPException(status_code=401, detail="실습 토큰이 일치하지 않습니다.")
```

- FastAPI Header가 X-Lab-Token을 읽고 compare_digest로 서버 설정값과 비교합니다.
- 토큰 불일치는 HTTP 401입니다. 각 실습 API에도 이 검사를 연결해야 인증 없는 메시지 조작을 막을 수 있습니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 관리 화면 15672 접속 | Queue와 연결 상태를 관찰 | AMQP 메시지 요청과 관리용 HTTP는 다른 통신입니다. |
| 실제 연결에 잘못된 LAB_TOKEN 입력 | 인증 오류 표시 | 화면 접근이 허용돼도 실험 요청은 별도로 인증합니다. |
| API 환경의 RABBIT_HOST 확인 | 컨테이너에서는 rabbitmq | localhost의 의미가 실행 위치에 따라 달라집니다. |

## 주의할 오해

- 기존 볼륨을 남긴 채 .env만 바꾸면 기존 Broker 계정이 자동 변경되는 것은 아닙니다.
- docker compose down -v는 데이터 볼륨까지 지우므로 평상시 종료 명령으로 쓰지 않습니다.

## 설명해 보기

- 브라우저가 RabbitMQ에 직접 연결하지 않는 이유를 설명할 수 있나요?
- API 컨테이너에서 localhost:5672로 접속하면 왜 대상이 달라질까요?

## 참고 자료

- [프로젝트 실행 구조](https://github.com/amirer21/message-flow-lab/blob/main/docker-compose.yml)
- [프로젝트 접속 설정](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/config.py)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
