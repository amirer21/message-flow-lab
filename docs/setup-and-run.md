# 실습 환경 구축 및 실행 가이드

이 문서는 저장소를 처음 내려받은 PC에서 MessageFlow Lab을 실행하고 실제 RabbitMQ 메시지를 확인하는 절차입니다. 현재 실습 기능은 Phase 0–4이며 Phase 5–12는 후속 학습 범위입니다. 명령은 별도 안내가 없으면 **저장소 루트 폴더**에서 Windows PowerShell로 실행합니다.

## 1. 준비 도구

| 도구 | 용도 |
|---|---|
| Git | 코드 다운로드와 업데이트 |
| Python 3.12 이상 | `.env` 생성 스크립트 실행 |
| Docker Desktop와 Docker Compose | RabbitMQ, Python API, 웹 화면 실행 |
| 웹 브라우저 | 실습 화면과 RabbitMQ 관리 화면 접속 |

Windows에서는 Docker Desktop의 WSL 2 기반 Linux 컨테이너 환경을 준비하고 Docker Desktop을 실행합니다. 아래 명령이 동작해야 다음 단계로 진행할 수 있습니다.

```powershell
git --version
python --version
docker --version
docker compose version
docker info
```

`docker info`가 서버 연결 오류를 반환하면 Docker Desktop 시작과 Linux 컨테이너 설정을 먼저 확인합니다. `python`이 없고 Python Launcher가 있다면 이 문서의 호스트 Python 명령을 `py -3`으로 바꿔 실행할 수 있습니다. 컨테이너 내부의 `python` 명령은 그대로 사용합니다.

기본 실습에서는 호스트에 Node.js, Pika, FastAPI를 설치할 필요가 없습니다. API는 `python:3.12-slim`, 화면 빌드는 `node:22-alpine`, Broker는 `rabbitmq:4.2-management`를 사용합니다. 최초 실행에는 이미지와 패키지를 내려받을 인터넷 연결이 필요합니다.

## 2. 코드와 환경 설정

처음 내려받는 경우:

```powershell
git clone https://github.com/amirer21/message-flow-lab.git
cd message-flow-lab
```

이미 내려받았다면 해당 폴더로 이동합니다. 현재 PC의 경로 예시는 다음과 같습니다.

```powershell
cd C:\Users\amire\python_workspace\message-flow-lab
```

환경 파일을 생성합니다.

```powershell
python scripts/init_env.py
```

이 스크립트는 무작위 비밀번호·토큰이 포함된 `.env`와 `data` 폴더를 만들고, 내려받기용 `public/messageflow-lab-starter.zip`을 다시 생성합니다. 기존 `.env`가 있으면 덮어쓰지 않습니다. ZIP에는 `.env`와 실험 기록을 넣지 않습니다.

`.env`를 편집기로 열어 아래 값을 확인합니다. 비밀번호와 토큰은 본인의 PC에서만 사용하고 Git에 추가하지 않습니다. `.env`와 `data/`는 이미 Git 제외 대상으로 설정되어 있습니다.

| 변수 | 사용처 |
|---|---|
| `RABBIT_USER` | RabbitMQ 로그인 사용자, 기본 `lab` |
| `RABBIT_PASSWORD` | RabbitMQ 로그인과 API의 Broker 연결 |
| `LAB_TOKEN` | 학습 화면에서 실제 API 연결 인증 |
| `ALLOWED_ORIGINS` | API 접속을 허용할 브라우저 화면 주소 |

Compose가 Vhost `lab`, API의 Broker 주소 `rabbitmq`, 컨테이너 내부 로그 경로를 설정합니다. 기본 실습에서는 이를 수정할 필요가 없습니다. `.env.example`은 변수 설명용이며 예시 비밀번호 그대로 실행하지 않습니다.

## 3. 서비스 시작

```powershell
docker compose up --build -d
docker compose ps
```

처음에는 이미지 다운로드와 화면 빌드 때문에 시간이 걸립니다. RabbitMQ의 상태 확인이 통과하면 API가 시작되고, API의 상태 확인이 통과하면 화면이 시작됩니다. `rabbitmq`, `api`, `frontend`가 실행 중인지 확인합니다. RabbitMQ와 API에는 healthcheck가 있고 화면 서비스에는 없습니다.

시작 오류를 확인할 때:

```powershell
docker compose logs --tail 100 rabbitmq api frontend
```

| 접속 대상 | 주소 | 인증 |
|---|---|---|
| 로컬 학습 대시보드 | http://localhost:5173 | 실제 연결 시 `LAB_TOKEN` |
| FastAPI API 문서 | http://localhost:8000/docs | 보호된 API는 `X-Lab-Token` 헤더 |
| API 상태 확인 | http://localhost:8000/health | 없음 |
| RabbitMQ Management | http://localhost:15672 | `.env`의 RabbitMQ 사용자·비밀번호 |

```powershell
Invoke-RestMethod http://localhost:8000/health
```

`/health`는 API가 실행 중임을 확인합니다. Broker 연결 상태와 Queue 지표는 실제 연결 후 화면에서 확인하거나 인증이 필요한 `/snapshot`으로 확인합니다.

호스트 포트 `5173`, `8000`, `5672`, `15672`를 사용하며 모두 `127.0.0.1`에 바인딩됩니다. 같은 PC에서 접속하는 기본 실습 구성입니다.

## 4. 실제 연결과 첫 실험

1. 로컬 대시보드를 열고 **실제 연결**을 선택합니다. 초기 **설명용 예시** 모드의 버튼은 실제 Broker에 메시지를 보내지 않습니다.
2. Gateway에 `http://localhost:8000`, 토큰에 `.env`의 `LAB_TOKEN`을 입력합니다. 토큰은 브라우저에 영구 저장하지 않습니다.
3. Phase 1을 선택하고 `hello` Queue의 Consumer를 멈춥니다. 이전 실험 메시지가 있다면 먼저 처리하고 ACK하여 Queue를 비웁니다.
4. 메시지를 3개 발행합니다. Ready 3 / Unacked 0을 확인합니다.
5. Consumer를 시작합니다. Prefetch 1이므로 Ready 2 / Unacked 1로 바뀝니다.
6. 전달된 메시지에 ACK를 보내고 다음 전달을 확인합니다. 3개를 모두 ACK하면 Ready와 Unacked가 0이 됩니다.
7. 실험 기록에 예상, 관찰, 설명을 남깁니다.

관리 지표는 주기적으로 수집되므로 조작 후 잠시 기다립니다. Consumer를 멈추면 연결이 닫히며 ACK하지 않은 메시지는 재전달될 수 있습니다. 브라우저를 닫거나 예시 모드로 전환하는 것만으로 Consumer가 종료되지는 않습니다.

다음 실험은 [Phase 2: ACK 전후 강제 종료](phase2.md), [Phase 3: Exchange와 Routing](phase3.md), [Phase 4: 발행 신뢰성](phase4.md)을 따릅니다. Phase 3 새 실험은 해당 Phase의 대기 메시지를 삭제합니다. Phase 4 Broker 재시작 실험은 다른 실험을 마친 뒤 해당 문서의 절차로 실행합니다.

## 5. Python으로 직접 메시지 처리

UI Consumer를 먼저 멈춥니다. UI와 독립 Consumer가 동시에 실행되면 메시지를 나누어 받을 수 있습니다.

```powershell
docker compose exec api python scripts/producer.py hello --count 3
docker compose exec api python workers/pika_worker/consumer.py --seconds 2
```

Producer는 3개를 발행하고 독립 Consumer는 메시지 처리 2초 뒤 ACK합니다. Consumer는 계속 대기하므로 종료하려면 해당 터미널에서 `Ctrl+C`를 누릅니다. 이 프로세스의 관측은 콘솔에서 확인하며 API 세션의 발행·ACK 카운터에는 합산되지 않습니다.

## 6. 정상 동작 검증

먼저 UI Consumer와 독립 Consumer를 모두 멈추고 진행 중인 실험을 완료합니다. Phase 1·2 검증은 기존 메시지나 Consumer가 있으면 중단하며 자동으로 Queue를 비우지 않습니다. Phase 3·4 검증은 해당 Phase의 실험 토폴로지를 초기화하므로 진행 중인 사용자 실험과 함께 실행하지 않습니다.

```powershell
docker compose exec -T api python -m unittest discover -s tests
docker compose exec -T api python scripts/smoke.py
docker compose exec -T api python scripts/smoke_phase2.py
docker compose exec -T api python scripts/smoke_phase3.py
docker compose exec -T api python scripts/smoke_phase4.py
```

각 명령이 오류 없이 종료되는지 확인합니다. 단위 검증과 실제 Broker 통합 검증은 범위가 다릅니다. 기존 검증 환경과 결과는 [검증 기록](verification.md)에 있습니다. 위 명령은 사용자 PC의 현재 구성을 확인하기 위한 절차입니다.

## 7. 종료, 재실행, 코드 업데이트

실습을 마치면 화면의 Consumer를 멈추고 서비스를 내립니다.

```powershell
docker compose down
```

RabbitMQ의 `rabbit-data` volume과 호스트 `data/` 파일은 유지됩니다. `data/events.jsonl`에는 이벤트, `data/phase2-effects.jsonl`에는 Phase 2 업무 반영 기록이 저장됩니다. API를 다시 시작하면 메모리의 세션 카운터는 초기화되므로 남아 있는 Queue 메시지 수와 다를 수 있습니다.

다음 실행:

```powershell
docker compose up -d
```

코드를 업데이트할 때는 로컬 수정 상태를 확인하고 fast-forward로 가져온 후 다시 빌드합니다.

```powershell
git status
git pull --ff-only github main
docker compose up --build -d
```

위 원격 이름 `github`는 현재 저장소 설정입니다. 새로 `git clone`한 저장소는 보통 `origin`이므로 `git remote -v`로 확인하고 `git pull --ff-only origin main`을 사용합니다. 로컬 변경이나 브랜치 분기로 업데이트가 중단되면 변경을 보존한 뒤 해결합니다.

`docker compose down -v`는 RabbitMQ volume을 삭제하므로 일상 종료에는 사용하지 않습니다. 이 옵션은 호스트 `data/` 기록까지 삭제하지 않습니다. 기존 volume에서는 `.env`의 사용자·비밀번호를 바꿔도 Broker 계정이 자동 갱신되지 않으므로 최초 설정을 유지합니다.

## 8. 자주 발생하는 문제

| 증상 | 확인 및 해결 |
|---|---|
| `docker` 명령 없음 또는 서버 연결 실패 | Docker Desktop 설치·실행과 Linux 컨테이너 설정을 확인하고 새 터미널에서 재시도 |
| 환경 변수 누락으로 Compose 시작 실패 | 루트에서 `python scripts/init_env.py` 실행 후 `.env` 존재와 값 확인 |
| 포트 사용 중 오류 | 같은 포트를 사용하는 다른 프로그램이나 다른 실습 Compose를 확인하고 중지 |
| RabbitMQ 로그인 또는 API 연결 실패 | 기존 volume을 만들 때의 계정과 현재 `.env` 비교; 데이터 삭제로 바로 해결하지 않기 |
| 화면은 열리지만 메시지가 실제로 발행되지 않음 | 설명용 예시 모드인지 확인하고 실제 연결 및 Gateway·토큰 설정 확인 |
| HTTP 401 | `LAB_TOKEN` 확인; `.env` 변경 후 `docker compose up -d api`로 환경 반영 |
| 브라우저 CORS 오류 | 접속한 화면 주소가 `ALLOWED_ORIGINS`에 있는지 확인하고 API 환경 반영 |
| HTTP 409 / stale ACK | 현재 전달의 Attempt ID를 새로 확인하고 해당 메시지에 ACK |
| HTTP 422 | 입력 형식과 API 문서 확인 |
| HTTP 503 / 지표 수집 실패 | `docker compose ps`와 RabbitMQ·API 로그 확인; 발행 오류 뒤에는 Queue와 로그를 확인한 후 재시도 판단 |
| Ready·Unacked가 예상과 다름 | 기존 메시지, 독립 Consumer, 미완료 ACK, 지표 수집 지연 확인 |
| `data/` 쓰기 권한 오류 | API는 컨테이너의 `lab` 사용자로 실행됨; Docker의 폴더 접근 권한과 Linux 사용 시 bind mount 소유권 확인 |

게시된 HTTPS Sites 화면을 사용할 경우 접근 가능한 HTTPS Gateway와 해당 사이트 주소의 CORS 허용이 필요합니다. 로컬 실습은 `http://localhost:5173` 화면을 사용합니다. 관련 설명은 [README의 Sites 연결 안내](../README.md#게시된-sites-화면과-연결)를 참고하세요.

## 9. 선택 사항: 로컬 개발 검증

화면이나 API 코드를 수정할 때만 사용합니다. 아래 절차는 테스트와 화면 빌드이며 전체 서비스를 실행하는 명령은 아닙니다. 화면 빌드용 Node.js는 Docker와 같은 22 계열을 사용하되 설치한 Vite의 엔진 요구사항을 충족하는 버전을 선택합니다.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
$env:PYTHONPATH = 'backend'
.venv/Scripts/python -m unittest discover -s backend/tests
npm ci
npm run build
```

기본 실습 실행에는 1–7절의 Compose 절차를 사용합니다. 코드 구조를 함께 배우려면 [코드 해설](code-explained.md)과 [Phase별 코드 학습 안내](phase-code-study.md)를 참고하세요.
