# MessageFlow Lab · AI 에이전트 작업 지침

작성일: 2026-10-06 · 대상: Claude Code, Codex 등 코드와 로컬 실행 환경에 접근 가능한 에이전트

## 1. 시작할 때 읽을 파일

1. 이 파일.
2. [남은 단계 개발 계획서](remaining-development-plan.md).
3. [README](../README.md), [학습 로드맵](learning-plan.md), [실행 검증 기록](verification.md).
4. 해당 Phase 문서, 수정 대상 소스와 가까운 검증 코드.
5. 저장소나 상위 디렉터리에 `AGENTS.md` 등 적용되는 작업 규칙이 있으면 확인.

현재 코드의 학습용 설명은 [도구와 코드 해설](code-explained.md)을 참고하고, 새 Phase 구현 시 해당 도구·주요 코드·실행 흐름 설명도 함께 갱신하세요. 미구현 도구의 설명용 예시를 실제 구현으로 표시하지 마세요.

문서 작성 기준으로 Phase 0–3이 구현됐으며 **다음 작업은 Phase 4**입니다. 시작 시 실제 Git 상태와 소스를 확인하고 문서와 다르면 차이를 기록하세요. 미완료 단계를 완료로 표시하거나 예시 화면만 만들고 실제 연동을 완료했다고 보고하지 마세요.

## 2. 환경·저장소

| 항목 | 현재 기준 |
|---|---|
| Windows 작업 폴더 | `C:\Users\amire\python_workspace\message-flow-lab` |
| 공개 GitHub 저장소 | `https://github.com/amirer21/message-flow-lab` |
| Git remote | `github` — 시작 시 `git remote -v`로 실제 URL 확인 |
| 기존 branch | `main` — 실제 현재 branch 확인 |
| 프런트 | Vue 3, TypeScript, Vite, npm lockfile |
| API | FastAPI, Uvicorn, Python 3.12 컨테이너, Pika 1.3.2 |
| 로컬 Broker | RabbitMQ `4.2-management`, vhost `lab` |
| Docker | Docker Desktop + WSL 2 Linux 엔진 구성 완료 |
| 로컬 화면 | `http://localhost:5173` |
| API / 설명 | `http://localhost:8000` / `/docs` |
| RabbitMQ 관리 | `http://localhost:15672` |

다른 PC에서는 절대 경로를 바꾸고 저장소를 clone합니다. 이 문서의 경로를 디렉터리 생성·삭제 명령에 무조건 적용하지 마세요. Docker/WSL을 다시 설치하지 않고 먼저 실행 상태를 확인합니다.

현재 PC의 Docker CLI 위치:

```powershell
$taskDockerDirectory = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin'
$env:PATH = $taskDockerDirectory + ';' + $env:PATH
docker version
docker compose ps
```

일반 환경에서는 Docker가 PATH에 있으면 위 경로 추가가 필요 없습니다. 개인 PC의 도구 경로를 프로젝트 소스에 하드코딩하지 마세요.

Git ownership 오류가 날 경우 checkout 경로와 소유권을 확인한 뒤 필요한 명령에만 `git -c safe.directory=<확인한 프로젝트 절대 경로> ...`를 사용합니다. `safe.directory=*`로 전역 신뢰를 완화하지 마세요.

## 3. 권장 작업 절차

1. `git status`, branch, remote, Docker 상태와 현재 구현을 확인. 사용자의 미커밋 수정은 보존.
2. 사용자에게 지정받은 Phase의 목표·파일·API·데이터·실제 실험을 짧게 정리.
3. 단계별 모듈과 화면을 구현하고 기존 계약 유지. 필요한 경우 먼저 공통 타입을 정의.
4. 설명용 예시 모델 구현. 실제 연결은 실제 API 관측값만 사용.
5. 입력 검증·실패 상태·종료/재시작·현재 실험 정리 동작 구현.
6. 위험한 상태 전이·동시성·ACK·미확인 실패에 필요한 단위 검증과 실제 서비스 실험 실행.
7. 단계 문서와 검증 기록 업데이트, 패키지 재생성, 최종 프런트 빌드.
8. 해당 작업에서 승인된 범위라면 commit/push/기존 Site 배포. 다른 에이전트에게 인계되었다는 이유만으로 사용자의 외부 배포 권한을 새로 추정하지 않음.
9. 구현 내용, 실제 수행한 검증, 미검증 범위, 실행 방법, 다음 단계를 한국어로 보고.

사용자가 한 단계만 요청하면 남은 전체 Phase를 한 번에 구현하지 마세요. 단순 계획·동의 응답으로 끝내지 말고 지정된 범위의 동작하는 결과와 검증을 마칩니다.

## 4. 구현 규칙

### UI와 학습 흐름

- 기존 한국어 UI와 디자인을 유지. 화면에 개발 내부 구조를 과하게 노출하지 않음.
- 질문 → 예측 → 실행 → 관측 → 설명 순서, 완료 체크와 실험 기록 제공.
- 예시/실제 연결 상태와 수집 시각을 명확히 표시. 예시 동작에서 실제 서비스 호출 금지.
- 단계 이동·모드 전환 중 도착한 이전 요청 응답이 다른 단계 상태를 덮어쓰지 않도록 generation/cancellation 처리.
- 연결 실패 때 수집값을 초기화하지 않고 마지막 관측값 + 오류 표시. 잘못된 토큰·Broker 정지·시간 초과를 성공으로 처리하지 않음.
- hosted HTTPS 화면에서 HTTP localhost Gateway에 직접 연결하는 제약을 안내. 실제 로컬 실험은 로컬 화면 사용.
- 단계별 컴포넌트로 확장. `App.vue`에 모든 Worker·Task·DB 분기를 계속 넣지 않음.

### API와 Worker

- 새 실험 라우터에 기존 `authorize` 의존성 적용. `.env`의 `LAB_TOKEN`을 `X-Lab-Token`으로 검증.
- CORS는 지정 Origin 목록. 브라우저 storage에 토큰·Broker 비밀번호 저장 금지.
- 입력은 Pydantic 타입, 길이·범위·UTF-8 AMQP key 한도 등을 검증. 임의 Queue 이름/명령/파일/PID를 실행 요청으로 받지 않음.
- Pika connection/channel은 소유 스레드/프로세스에서만 사용. HTTP Worker 스레드에서 공유 channel을 직접 조작하지 않음.
- fixed command IPC 또는 소유권이 명확한 controller 사용. Docker socket을 API에 mount하여 임의 컨테이너 제어를 열지 않음.
- Worker 종료는 해당 실험의 자식만 대상으로 함. 종료의 실제 방식·신호와 ACK/commit 위치 기록.
- 제한 없는 소비·시도·로그·이벤트 배열을 만들지 않음. timeout과 shutdown 정리 필요.
- 단순 GET 지표 조회는 메시지 소비·ACK·삭제를 하지 않음. Phase 3의 명시적 POST `/routing/receive`는 예외가 아니라 의도된 소비 액션.
- 발행 HTTP 요청 실패 후 자동 재시도는 금지. 이미 발행됐을 가능성을 표시하고 사용자가 Queue·이력을 확인하도록 함.

### MQ 의미와 관측

- Confirm, Return, Consumer ACK, 업무 commit, Task result는 각각 독립된 사실.
- `PUBLISH_SENT`와 `ACK_SENT`는 앱의 전송 기록. Broker 처리 시각·업무 완료를 의미하지 않음.
- Queue 지표 없음을 Ready 0으로 대체하지 않음. 앱 세션 카운터와 Broker 현재 지표 구분.
- `message_id`와 `attempt_id` 분리. Fanout은 같은 메시지의 Queue별 복사; retry/redelivery는 새로운 전달 시도.
- exactly-once 전달을 기본 보장으로 주장하지 않음. DB 트랜잭션·고유 제약으로 업무 효과를 보호.
- Celery retry와 Broker requeue/redelivery, early/late ACK와 worker-lost 옵션을 분리.
- 외부 호출·결제·이메일은 학습용 DB 효과/계산으로 대체. 실제 사용자·외부 시스템에 자동 전송하지 않음.
- logger 실패 때문에 성공한 업무를 다시 실행하지 않음. 로그 저장 실패를 별도 상태로 다룸.

## 5. 기존 API와 상태를 깨지 말 것

| 범위 | 기존 API |
|---|---|
| 공통 | `GET /health`, `GET /snapshot` |
| Phase 1 | `POST /rabbit/messages`, `GET /rabbit/messages`, `POST /consumer/start`, `/stop`, `/ack` |
| Phase 2 | `GET /experiments/snapshot`, `POST /experiments/messages`, `/start`, `/stop`, `/process`, `/ack`, `/crash` |
| Phase 3 | `GET /routing/snapshot`, `POST /routing/setup`, `/bindings`, `/messages`, `/receive` |

Phase 1 ACK와 Phase 2 process/ACK는현재 delivery의 `attempt_id`를 사용합니다. stale 시도에 대한 동작은 409이며 다음 전달을 ACK해서는 안 됩니다.

Phase 2 효과는 `data/phase2-effects.jsonl`에 append/flush/fsync합니다. 같은 재전달 메시지의 업무가 중복 반영되는 현상을 의도적으로 보여 줍니다. Phase 6을 추가하면서 이 비교 실험의 중복을 몰래 제거하지 마세요.

Phase 3는 API 프로세스의 별도 Pika 연결과 UUID 토폴로지 한 개를 공유합니다. 다중 사용자별 격리는 현재 구현돼 있지 않습니다. `/routing/setup`은 해당 토폴로지의 Queue·대기 메시지를 삭제하고 다시 만듭니다. 임시 Queue는 연결 종료 시 사라지므로 영속성 실험으로 사용하지 마세요. Ready는 passive queue_declare의 실제 count, 수신은 basic_get 후 같은 channel ACK입니다. 예측 결과가 실제 수신 이벤트로 둔갑해서는 안 됩니다.

## 6. 실행과 검증

프로젝트 루트에서 실행합니다. 기존 `.env`가 있으면 재생성하거나 내용을 출력하지 마세요.

```powershell
python scripts/init_env.py
docker compose up --build -d
```

실제 화면의 연결 토큰은 사용자가 `.env`에서 직접 확인합니다. 에이전트는 명령 인자·응답·문서에 토큰을 노출하지 않습니다. 통합 스크립트는 컨테이너 환경변수로 토큰을 읽습니다.

현재 의존성 설치와 검증:

```powershell
npm ci
npm run build
node --test frontend/tests/*.test.mjs
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
$env:PYTHONPATH = 'backend'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

기존 `.venv`가 준비돼 있으면 재생성할 필요가 없습니다. 현재 PC에서 npm 실행 래퍼가 실패하는 경우의 대안:

```powershell
node 'C:\nvm4w\nodejs\node_modules\npm\bin\npm-cli.js' run build
```

현재 실제 서비스 실험:

```powershell
docker compose exec -T api python scripts/smoke.py
docker compose exec -T api python scripts/smoke_phase2.py
docker compose exec -T api python scripts/smoke_phase3.py
```

Phase 1/2 스크립트는 기존 메시지·Consumer가 있으면 중단하고 자동 purge하지 않습니다. Phase 3 스크립트는 **현재 Phase 3 임시 토폴로지와 대기 메시지를 초기화**합니다. 진행 중인 사용자 실험이 있는지 확인하고 전용 테스트 환경에서 실행하는 방식을 우선합니다.

새 단계마다 실제 정상/실패 smoke 스크립트를 추가합니다. 실패 원인과 실제 실행 증거를 남기고 예상값을 맞추려고 메시지를 임의 삭제하지 마세요. 단위 검증의 mock 통과를 실제 Broker 검증으로 보고하지 않습니다.

검증 완료 후:

```powershell
python scripts/package_lab.py
npm run build
docker compose up --build -d frontend
```

ZIP은 현재 whitelisted 파일·폴더만 포함합니다. 새 필수 파일이 다른 위치에 생기면 패키징 목록을 수정합니다. 산출물에 `.env`, data, 비밀번호, `.git`, `.openai`, node_modules, 가상환경이 없는지 검사합니다. localhost 화면의 응답과 주요 단계·반응형 UI도 확인하되 자동 브라우저 검사 수행 여부를 정확히 보고합니다.

## 7. 데이터·장애 실험 보호

- 사용자 기존 메시지, `data/`, RabbitMQ/PostgreSQL 볼륨을 유지.
- `docker compose down -v`, 전체 purge, workspace 재귀 삭제, `git reset --hard`, 강제 push를 기본 정리 명령으로 사용하지 않음.
- Broker/DB 전체 중단·볼륨 삭제·데이터 손실 실험은 영향 범위를 먼저 제시하고 전용 실험 환경 사용. 별도 사용자 승인 범위를 넘어 실행하지 않음.
- 재시작과 삭제는 다름. `.env` 비밀번호 변경만으로 기존 RabbitMQ 영속 볼륨의 계정이 자동 변경된다고 가정하지 않음.
- stdout에 환경변수·접속 URL 전체·토큰을 덤프하지 않음. 로그와 스크린샷에서도 비밀을 제외.
- DB migration은 번호·upgrade 경로·실행 기록 유지. 사용자 데이터 삭제가 필요한 변경은 별도 검토.
- dependency 고정 버전, lockfile, 공식 문서 버전 대조. 전체 dependencies를 이유 없이 최신으로 일괄 업그레이드하지 않음.

## 8. 문서와 배포 인계

매 Phase 완료 때 `docs/phaseN.md`에 질문, 고정/변경 조건, 절차, 기대 결과, 실제 결과, 장애·복구, 정리 방법을 작성합니다. 아래 문서를 함께 갱신:

- `README.md`: 구현 범위, 실행 방법, 변경된 서비스.
- `docs/learning-plan.md`: 구현/예정 상태.
- `docs/verification.md`: 실제 실행일·환경·검증 수·미검증 범위.
- 이 문서와 `remaining-development-plan.md`: 현재 완료 단계·다음 단계.
- `frontend/src/curriculum.ts`, 화면 버전/실습 가능 표시, `package.json`·lockfile.
- `public/messageflow-lab-starter.zip`: 소스·문서 최신 상태.

GitHub push가 작업 범위에 포함돼 있으면 사용자 지정 계정과 remote를 확인하고 비밀 제외 검사를 한 뒤 push합니다. 다른 작성자의 커밋·로컬 변경을 덮어쓰지 마세요.

Sites를 수정·배포하도록 요청된 경우 `.openai/hosting.json`의 기존 project_id를 재사용하고 접근 범위를 보존합니다. Sites는 정적 Vue 화면 배포이며 Docker RabbitMQ·Python 프로세스를 그 안에서 실행하지 않습니다. 해당 도구가 있는 에이전트는 설치된 Sites 스킬의 공식 절차를 따릅니다. Claude 등 Sites 도구가 없는 환경에서는 소스·빌드·GitHub 결과를 인계하고 **Sites 배포 미실행**으로 명시합니다. 임의 호스팅 가입, 기존 Site 재등록, 다른 호스팅으로 이동하지 마세요. Sites의 단기 Git 토큰을 문서나 파일로 전달하지 않습니다.

## 9. 완료 보고 형식

```text
구현: Phase N의 동작과 변경 이유
검증: 실제 실행한 빌드/단위 검증/서비스 실험과 결과
실행: 사용자가 화면에서 확인하는 절차
문서: 변경한 단계 문서와 인계 문서
미검증·제한: 외부 서비스/브라우저/장애 시나리오별 미실행 항목
저장·배포: commit/원격 반영/로컬 화면/Sites 각각의 실제 상태
다음 단계: 다음 Phase와 남은 작업
```

## 10. 다른 AI 에이전트에게 전달할 시작 요청

아래 요청을 사용하고, 특정 Phase만 진행하거나 배포 여부를 바꾸려면 마지막 문장을 수정하세요.

```text
MessageFlow Lab 프로젝트의 개발을 이어서 진행해 주세요.
먼저 docs/ai-agent-instructions.md와 docs/remaining-development-plan.md,
README.md, docs/verification.md를 읽고 실제 소스·Git 상태를 확인하세요.
현재 기준 Phase 0–3이 구현되어 있습니다. 우선 Phase 4의 발행 신뢰성 실험을 구현하세요.
기존 한국어 Vue UI, 예시/실제 모드, 토큰 인증과 Phase 1–3 동작을 유지하세요.
Confirm, mandatory Return, durable/persistent를 구분하고 실제 RabbitMQ 검증까지 수행하세요.
Broker 재시작은 사용자 진행 중인 실험을 보호하도록 전용 테스트 환경에서 실행하세요.
검증·문서·실습 패키지를 갱신하고 수행하지 못한 검증은 명확히 보고하세요.
이번 요청에서는 구현과 로컬 검증까지만 진행하고 외부 push·배포는 별도 지시를 따르세요.
```

이 지침은 에이전트에게 작업 배경을 전달하기 위한 문서이며, 사용자의 현재 지시나 실행 환경의 승인 정책을 대체하지 않습니다.
