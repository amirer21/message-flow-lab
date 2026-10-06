# MessageFlow Lab · Phase 0–4

RabbitMQ → Pika → Kombu → Celery 순서로 배우는 실습 프로젝트입니다. 현재 구현은 Phase 0~4입니다. Phase 5~12는 사이트에서 학습 범위와 완료 기준을 확인할 수 있고, 실습 기능은 후속 단계에서 추가합니다.

[GitHub 공개 저장소](https://github.com/amirer21/message-flow-lab) · [Sites 학습 화면](https://messageflow-lab-amire.mirohong.chatgpt.site)

## 처음 실행

처음 준비하는 PC에서는 [실습 환경 구축 및 실행 가이드](docs/setup-and-run.md)를 따라 도구 확인, 환경 설정, 실행, 첫 실험, 검증과 오류 해결을 진행하세요.

코드를 함께 배우려면 [도구와 코드 해설](docs/code-explained.md)을 먼저 읽으세요. 현재 구현된 RabbitMQ·Pika 코드와 앞으로 도입할 Celery·Pyro5 예시를 구분하여 설명합니다.

단계별 함수·입출력·상태 변화·데이터 흐름은 [Phase별 코드 학습 안내](docs/phase-code-study.md)에서 Phase 0–3 문서로 따라가세요.

Docker Desktop(Docker Compose 포함), Python 3.12 이상이 필요합니다. Docker의 Linux 컨테이너 모드를 사용하세요.

```powershell
python scripts/init_env.py
docker compose up --build
```

최초 시작에는 이미지 다운로드와 화면 빌드 시간이 필요합니다.

| 화면 | 주소 |
|---|---|
| 로컬 학습 대시보드 | http://localhost:5173 |
| FastAPI 설명 | http://localhost:8000/docs |
| RabbitMQ Management | http://localhost:15672 |

RabbitMQ 관리 화면의 계정은 `.env`의 `RABBIT_USER`와 `RABBIT_PASSWORD`입니다. 사이트의 **실제 연결**에서 Gateway `http://localhost:8000`과 `.env`의 `LAB_TOKEN`을 입력하세요. 토큰은 브라우저에 영구 저장하지 않습니다.

기본 화면은 **설명용 예시**입니다. 예시 버튼은 실제 RabbitMQ에 메시지를 보내지 않습니다. 실제 연결을 확인한 뒤 실험하세요.

## 첫 실험

ACK가 처음이라면 화면의 **ACK란 무엇인가요?**와 **실습 용어 쉽게 이해하기**를 먼저 읽어 보세요. 같은 설명은 [Phase 1 용어 안내](docs/phase1.md)에도 있습니다.

1. 독립된 `hello` Queue에서 Consumer를 멈춥니다.
2. 메시지 `hello`를 **3개 발행**합니다.
3. Ready 3 / Unacked 0인지 확인합니다.
4. Consumer를 시작합니다. Ready 2 / Unacked 1로 바뀝니다.
5. 전달된 메시지를 확인하고 ACK를 보냅니다.
6. 세 메시지를 모두 ACK하면 Ready·Unacked가 0입니다.
7. 실험 기록에 예상, 관찰, 설명을 남깁니다.

관리 지표는 주기적으로 수집됩니다. 조작 직후 숫자가 잠시 늦게 바뀔 수 있습니다. 실습 Consumer는 Prefetch 1, Manual ACK이며 UI가 현재 전달의 `attempt_id`를 확인한 후 ACK합니다. Consumer 멈춤은 연결을 닫으므로 ACK하지 않은 메시지가 재전달될 수 있습니다.

## Phase 2 · ACK 전후 강제 종료

Phase 2는 `phase2.ack_lab` Queue와 별도 Python Consumer 프로세스를 사용합니다. Phase 1의 `hello` Queue와 Consumer에 영향을 주지 않습니다.

실험 A:

1. 메시지 1개를 발행하고 Consumer를 시작합니다.
2. **업무 반영** 버튼으로 학습용 기록을 디스크에 저장합니다.
3. ACK를 보내기 전에 **Consumer 강제 종료**를 누릅니다.
4. Consumer를 다시 시작합니다. Message ID는 같고 Attempt ID는 새로 생깁니다. `redelivered=true`를 확인합니다.
5. 업무를 다시 반영합니다. 같은 메시지의 업무 반영 횟수가 2가 됩니다.
6. ACK를 보내고 Queue가 비는지 확인한 뒤 정상 종료합니다.

실험 B:

1. 새 메시지 1개를 발행하고 Consumer를 시작합니다.
2. 업무 반영 후 ACK를 보냅니다.
3. **Ready·Unacked가 0으로 수집된 것을 확인한 뒤** 강제 종료합니다.
4. Consumer를 다시 시작해 메시지가 재전달되지 않는지 확인합니다.

ACK_SENT와 Broker의 ACK 처리 시각은 다릅니다. ACK 직후 무조건 재전달이 없다고 단정하지 않고 Queue 지표까지 확인합니다. 실제 Broker의 연결 종료 감지와 지표 수집에는 지연이 있을 수 있습니다.

업무 반영은 `data/phase2-effects.jsonl`에 append·flush·fsync하는 학습용 효과입니다. 실제 결제·이메일·외부 API 호출을 하지 않습니다. Consumer나 API를 재시작해도 이 파일은 유지됩니다. Phase 2는 의도적으로 Message ID별 멱등 처리를 하지 않습니다. 같은 시도에서 중복 클릭은 막지만, 재전달된 새로운 시도는 업무를 다시 반영할 수 있습니다. Phase 6에서 이를 해결합니다.

관리 API는 고정된 실습 프로세스의 `start/process/ack/stop/crash`만 허용합니다. 임의 명령, 실행 파일, PID, Docker 제어 권한을 UI에서 받지 않습니다. Linux 컨테이너의 강제 종료는 해당 자식 프로세스에 SIGKILL을 보내며, API와 RabbitMQ는 유지됩니다.

## Phase 3 · Exchange와 Routing

Direct/Fanout/Topic을 선택하고 Queue A/B/C의 Binding을 편집합니다. 수신 Queue를 먼저 예측한 뒤 메시지를 발행하고 **Queue별 한 개 수신 · ACK**로 실제 수신을 비교합니다. 같은 Message ID의 Queue별 복사와 Topic `*`/`#` 패턴을 확인하세요.

Phase 3은 `phase3.<uuid>`의 임시 Exchange·exclusive Queue를 사용합니다. 새 실험은 현재 Phase 3의 대기 메시지를 삭제하며 API 연결 종료 시에도 임시 Queue가 삭제됩니다. Phase 1·2와 분리됩니다. Binding 변경은 기존 대기 메시지를 이동시키지 않습니다. Publisher Confirm은 Phase 4에서 추가합니다. 상세 절차는 [Phase 3 안내](docs/phase3.md)를 참고하세요.

## Phase 4 · 발행 신뢰성

Publisher Confirm, mandatory Return, durable/persistent 메시지를 별도로 비교합니다. Phase 4 전용 Exchange와 Queue를 사용하며 Confirm 모드에서 발행합니다.

4가지 시나리오:
- **정상 Confirm**: durable Queue에 라우팅 → Confirm ACK 수신
- **Mandatory Return**: binding 없는 key + mandatory → Confirm ACK + Return 동시 수신
- **영속 메시지**: delivery_mode=2 + durable Queue → 재시작 후 잔존
- **임시 메시지**: delivery_mode=1 + auto_delete Queue → 재시작 후 소멸

Confirm ACK는 Broker 수락이며 Consumer 처리 완료가 아닙니다. Return과 Confirm은 독립적인 사실입니다. 상세 절차는 [Phase 4 안내](docs/phase4.md)를 참고하세요.

## Python으로 직접 실습

UI와 API를 거치지 않는 Pika Producer:

```powershell
docker compose exec api python scripts/producer.py hello --count 3
```

독립 Pika Consumer(처리 2초 후 ACK):

```powershell
docker compose exec api python workers/pika_worker/consumer.py --seconds 2
```

독립 Consumer를 사용할 때는 UI Consumer를 멈추세요. 독립 프로세스의 이벤트는 콘솔과 로그에서 확인하며 API 세션의 발행·ACK 카운터에 합산되지 않습니다.

## 관측값의 의미

- Ready / Unacked / Consumer 수: RabbitMQ Management API 지표.
- 발행 요청 / ACK 전송: 현재 API 프로세스가 관측한 세션 카운터.
- `PUBLISH_SENT`: 전송 API가 반환된 사실. Phase 1에서는 Publisher Confirm을 사용하지 않으며 Broker 수락이나 소비 완료를 보장하지 않습니다.
- `DELIVERED`: 앱이 Consumer callback에서 기록한 전달.
- `ACK_SENT`: 앱이 ACK 호출을 보낸 기록. Broker 내부 ACK 처리 시각을 추정하지 않습니다.
- API 세션은 재시작하면 초기화됩니다. 영속 Queue가 남아 있으면 세션 발행 수와 Ready가 다를 수 있습니다.
- `data/events.jsonl`에는 관측 기록을 계속 추가합니다. Phase 6에서 PostgreSQL과 이력 재조회 기능을 추가합니다.
- `GET /rabbit/messages`는 관측 이벤트를 조회합니다. Queue에서 메시지를 꺼내는 읽기 방식은 사용하지 않습니다.
- API 실행 상태 `/health`와 RabbitMQ 연결 상태 `/snapshot`을 구분합니다.

API는 한 프로세스로 실행하세요. 교육용 Consumer 컨트롤러는 메모리를 공유하며 다중 API Worker 구성은 현재 범위에 포함되지 않습니다.

## 검증

실제 Docker·RabbitMQ 환경에서 Phase 1·2·3·4를 검증했습니다. 환경, 결과와 범위는 [검증 기록](docs/verification.md)을 참고하세요.

실제 Broker 통합 검증(Queue에 기존 메시지나 Consumer가 있으면 중단하며 자동 purge하지 않습니다):

```powershell
docker compose exec api python scripts/smoke.py
docker compose exec api python scripts/smoke_phase2.py
docker compose exec api python scripts/smoke_phase3.py
docker compose exec api python scripts/smoke_phase4.py
```

API·ACK 방어·업무 효과 저장 검증:

```powershell
docker compose exec api python -m unittest discover -s tests
```

로컬 개발 검증:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
$env:PYTHONPATH = 'backend'
.venv/Scripts/python -m unittest discover -s backend/tests
npm ci
npm run build
```

## 게시된 Sites 화면과 연결

게시된 사이트는 학습 안내와 예시 실험을 바로 이용할 수 있습니다. PC의 RabbitMQ는 별도 실행해야 합니다. 실제 연결에는 사용자가 접근 가능한 **HTTPS Gateway**와 `ALLOWED_ORIGINS`에 실제 사이트 주소가 필요합니다. HTTPS 페이지에서 HTTP localhost 접속은 차단될 수 있으므로 로컬 실습에는 패키지의 로컬 화면을 사용합니다.

RabbitMQ의 AMQP와 Management 포트는 공개하지 않습니다. 실습 환경은 기본적으로 loopback에만 노출됩니다. Gateway를 별도 호스팅할 경우 HTTPS, 접근 제한, 토큰 설정을 적용하세요.

토큰 오류는 401, 잘못된 입력은 422, stale ACK는 409, Broker·지표 수집 오류는 503으로 반환합니다. 수집 실패 시 화면은 마지막 값을 보존하고 연결 끊김을 표시합니다. 발행 오류 후 자동 재시도하지 않습니다. 일부 메시지가 전송됐을 수 있으므로 Queue와 로그를 먼저 확인합니다.

브라우저를 닫거나 예시 모드로 전환해도 실제 Consumer는 종료되지 않습니다. **멈춤**으로 종료하거나 API 서비스를 내리세요.

## 종료와 보존

```powershell
docker compose down
```

RabbitMQ volume과 `data/events.jsonl`은 유지됩니다. 기존 RabbitMQ volume이 있으면 `.env`의 계정을 바꿔도 기존 Broker 계정이 자동으로 바뀌지 않습니다. 처음 생성한 설정을 유지하세요.

## 다른 AI 에이전트에게 개발 인계

- [남은 단계 개발 계획서](docs/remaining-development-plan.md): Phase 4–12 구현 범위·의존성·완료 기준.
- [AI 에이전트 작업 지침](docs/ai-agent-instructions.md): 구조·실행·검증·데이터 보호·배포·시작 요청.

두 문서를 Claude Code 등에게 먼저 읽도록 전달하세요. Phase 3 통합 검증은 현재 Phase 3 임시 실험을 초기화하므로 진행 중인 실험과 함께 실행하지 않습니다.

## 다음 단계

`docs/learning-plan.md`의 완료 기준을 따라 Phase 5부터 확장합니다. 데이터베이스·Kombu·Celery·Pyro는 각 학습 단계에서 도입합니다.

공식 자료: [RabbitMQ Python 튜토리얼](https://www.rabbitmq.com/tutorials), [ACK와 Confirm](https://www.rabbitmq.com/docs/confirms), [Pika](https://pika.readthedocs.io/en/stable/), [Vue](https://vuejs.org/guide/quick-start.html).

## Phase별 자세한 기술 학습

각 Phase의 **학습 가이드** 탭에서 전체 흐름, 용어 정의, 내부 동작, 코드 해설, 실험·예상 결과, 흔한 오해를 읽을 수 있습니다. Phase 0–3은 실제 구현 코드 발췌이며, Phase 4–12는 실행 환경을 추가해야 하는 교육용 설계 예시입니다. [기술 학습 문서 모음](docs/technical-learning-guide.md)에서 같은 내용을 Markdown으로 읽을 수 있습니다.
