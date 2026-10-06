# Phase 0 · 환경 준비와 연결 코드

학습 목표: 브라우저·API·RabbitMQ의 실행 위치를 이해하고, 환경변수가 연결 설정과 인증으로 이어지는 과정을 설명합니다.

## 1. 먼저 열 파일과 라이브러리

| 파일 | 역할 | 도구·라이브러리 |
|---|---|---|
| [docker-compose.yml](../../docker-compose.yml) | 서비스·포트·volume·시작 조건 | Docker Compose |
| [backend/Dockerfile](../../backend/Dockerfile) | Python 의존성 설치와 API 실행 | Docker, pip, Uvicorn |
| [frontend/Dockerfile](../../frontend/Dockerfile) | Vue 빌드 후 정적 파일 제공 | Node, npm, Vite, Nginx |
| [scripts/init_env.py](../../scripts/init_env.py) | 로컬 비밀 생성·패키징 호출 | secrets, pathlib, subprocess |
| [scripts/package_lab.py](../../scripts/package_lab.py) | 소스·문서 ZIP 작성 | pathlib, zipfile |
| [config.py](../../backend/app/config.py) | 환경변수 → Settings | os, dataclasses |
| [main.py](../../backend/app/main.py) | 앱 시작·인증·상태 조회 | FastAPI, HTTPX, Pydantic |
| [App.vue](../../frontend/src/App.vue) / [lab.ts](../../frontend/src/lab.ts) | 연결 입력·실제 요청 | Vue, browser fetch |

`init_env.py`와 `package_lab.py`는 현재 최상위 코드를 순서대로 실행하는 스크립트입니다. 별도의 `init_env()` 함수나 `main()` 함수가 있다고 가정하지 않습니다.

## 2. 실행 흐름

```text
python scripts/init_env.py
  → 프로젝트 루트 경로 계산
  → .env를 새 파일 모드(x)로 열기
  → 비밀번호·토큰을 secrets로 생성하고 파일에 저장
  → data 폴더 준비
  → package_lab.py를 별도 Python으로 실행

docker compose up --build
  → .env 값을 Compose가 읽음
  → RabbitMQ 시작 / healthcheck
  → API 이미지 빌드 → Uvicorn 실행
  → Vue 빌드 → Nginx 실행
  → PC에서 localhost:5173 화면 접속
```

`.env`가 있으면 FileExistsError를 처리하고 기존 값을 유지합니다. `subprocess.run(..., check=True)`는 패키징이 실패하면 성공한 척하지 않고 오류를 발생시킵니다. 비밀 값은 출력하지 않습니다.

## 3. 호스트와 포트의 뜻

| 접속하는 프로그램 | 대상 주소 | 의미 |
|---|---|---|
| 브라우저 | localhost:5173 | PC에 공개된 Nginx 화면 |
| 브라우저 | localhost:8000 | PC에 공개된 FastAPI |
| API 컨테이너 | rabbitmq:5672 | Compose 내부 DNS로 찾은 Broker의 AMQP |
| API 컨테이너 | rabbitmq:15672 | Broker Management HTTP API |
| 브라우저 | localhost:15672 | PC에서 보는 RabbitMQ 관리 화면 |

컨테이너 내부의 localhost는 해당 컨테이너 자신입니다. API에서 localhost:5672를 쓰면 RabbitMQ 컨테이너에 접속하는 것이 아닙니다.

`rabbit-data`는 Broker 저장용 volume, `./data:/lab/data`는 API 업무·이벤트 파일을 PC에 남기는 bind mount입니다. 프런트는 빌드 시 소스를 복사하므로 파일 수정이 실행 중인 Nginx에 자동 반영되는 hot reload 구조가 아닙니다.

## 4. 설정 객체의 로직

`Settings`는 `@dataclass(frozen=True)`로 정의됩니다. `os.getenv()`의 값을 기본 필드로 읽고 모듈 마지막의 `settings = Settings()`가 객체를 만듭니다.

```text
.env
 → Compose의 environment
 → API 프로세스 환경변수
 → config.py import / Settings 생성
 → main.py, messaging.py, consumer.py가 settings 참조
```

앱이 `.env`를 직접 파싱하지는 않습니다. `frozen=True`는 객체 필드 재할당을 제한합니다. 환경변수를 나중에 바꿔도 이미 생성한 설정 객체가 자동 갱신되지 않으므로 프로세스 재시작이 필요합니다.

## 5. 공통 함수의 입력과 출력

| 함수 | 입력 | 출력·효과 |
|---|---|---|
| `lifespan(app)` | FastAPI 앱 | 시작 시 필수 설정 검사, 종료 시 Consumer/실험 연결 정리 |
| `authorize(x_lab_token)` | HTTP X-Lab-Token | 일치하면 통과, 아니면 HTTP 401 |
| `health()` | 없음 | API 실행 응답, broker_checked=False |
| `queue_stats(queue=None)` | Queue 이름 또는 기본 hello | name/ready/unacked/consumers, 미수집 시 503 |
| `snapshot()` | 토큰 검증된 GET | Broker 지표 + Consumer 상태 + 앱 이벤트 + 수집 시각 |
| `connect()` / App.vue | gateway·token 화면 상태 | 실제 상태 요청 성공 후 mode=live, connected=true |
| `request<T>()` / lab.ts | base, token, path, 선택 body | fetch JSON, 실패 시 Error, 요청 timeout 10초 |

`lifespan()`의 yield 앞은 시작 처리, 뒤는 종료 처리입니다. `health()`는 Broker 확인을 하지 않으므로 API 실행 응답만으로 RabbitMQ 접속 성공을 판단하면 안 됩니다.

## 6. 실제 연결 버튼의 호출 순서

```text
App.vue.connect()
 → 토큰이 비어 있는지 검사
 → HTTP/HTTPS 주소 형식·Origin 제약 검사
 → request(gateway, token, snapshotPath())
 → GET /snapshot 또는 /experiments/snapshot
 → authorize()
 → Broker와 현재 실험 상태 확인
 → 화면 snapshot·mode·connected 업데이트
```

Phase 3 연결 초기 확인에는 공통 `/snapshot`을 사용하고, 활성화된 PhaseThree의 `read()`가 `/routing/snapshot`을 따로 조회합니다.

`request()`는 body가 없으면 GET, 있으면 JSON POST를 사용합니다. `AbortSignal.timeout()`은 브라우저 대기 제한이며 서버 작업을 되돌리는 기능은 아닙니다. `generation`을 대조해 모드/단계 전환 전에 시작한 요청의 응답을 새 화면에 적용하지 않습니다.

토큰은 메모리에서 유지합니다. Gateway 주소·학습 체크·노트는 localStorage에 저장하지만 토큰·Broker 비밀번호는 저장하지 않습니다. CORS와 토큰 인증은 별개입니다.

## 7. Queue 지표를 얻는 로직

`queue_stats()`는 먼저 실습 Queue를 선언합니다. 따라서 없는 Queue를 생성할 수 있지만 메시지를 꺼내지는 않습니다. 그다음 HTTPX로 `/api/queues/{vhost}/{queue}`를 요청합니다. `urllib.parse.quote(..., safe='')`는 vhost나 Queue 이름을 URL 경로에 맞게 인코딩합니다.

새 Queue 지표가 아직 없으면 최대 6회 확인하며 사이에 0.3초 기다립니다. 필수 필드가 없거나 HTTP 요청이 실패하면 503입니다. 데이터 없음이 Ready 0으로 바뀌지 않습니다.

## 8. 읽기 실험과 확인 문제

1. Compose에서 외부 포트와 내부 포트를 표시하세요. API의 `RABBIT_HOST`가 rabbitmq인 이유를 설명하세요.
2. `health()`의 응답과 `snapshot()`의 응답을 비교하세요. 어느 쪽이 Broker를 확인하나요?
3. 토큰 검사를 하는 함수와 RabbitMQ 계정 인증을 하는 코드를 각각 찾으세요.
4. package_lab.py의 files 목록에서 `.env`, data, .git이 포함되지 않는 이유를 확인하세요.
5. 실행 중인 프런트에 소스를 바꾸기만 하면 반영되지 않는 이유를 Dockerfile에서 찾으세요.

다음 문서: [Phase 1 · 발행·수신·ACK](phase1.md).
