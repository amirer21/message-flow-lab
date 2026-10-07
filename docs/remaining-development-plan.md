# MessageFlow Lab · 남은 단계 개발 계획서

작성일: 2026-10-06 · 기준 버전: v0.3.0 · 대상: Claude, Codex 등 후속 개발 에이전트

이 문서는 이전 대화를 읽지 않은 개발자가 Phase 4부터 구현할 수 있도록 작성한 인계 문서입니다. 작업 방식과 실행 지침은 [AI 에이전트 작업 지침](ai-agent-instructions.md)을 함께 읽으세요. 아래 신규 파일·API·DB 설계는 **제안**이며, 실제 구현에 맞춰 수정하고 근거를 기록합니다.

## 1. 제품 목표와 현재 상태

MessageFlow Lab은 Python 메시지 큐를 단계별로 배우는 한국어 학습·모니터링 대시보드입니다. 각 단계는 **질문 → 예측 → 실행 → 정상/실패 관찰 → 설명 → 완료 기준 확인**으로 구성합니다. 실제 Broker와 연결하지 않아도 개념을 익힐 수 있는 예시 모드와, Docker의 실제 실행 결과를 관찰하는 연결 모드를 제공합니다.

| 단계 | 현재 구현 및 검증 |
|---|---|
| Phase 0 | Docker Compose, RabbitMQ·API·Vue 환경, 토큰 연결, 실습 패키지 |
| Phase 1 | Pika 발행, Prefetch 1, Manual ACK, Ready/Unacked, 실제 3개 발행·소비 검증 |
| Phase 2 | 독립 자식 Consumer, 업무 기록 후 ACK 전/후 강제 종료, 재전달·중복 효과 실험 |
| Phase 3 | Direct/Fanout/Topic, Binding 편집, Queue 예측, Queue별 수신·ACK, 실제 Routing 검증 |
| Phase 4 | Confirm·Return·Persistent·Durable, 발행 신뢰성 실험 |
| Phase 5 | Retry·TTL·DLQ, 일시/영구 실패 분류, 재시도 한도 |
| Phase 6–12 | 학습 가이드·완료 기준은 존재. 실제 실습 기능은 미구현 |

현재 Python 단위 검증 21개, 예시 모델 검증 10개와 Vue/TypeScript 빌드가 통과했습니다. 자세한 실제 실행 결과는 [검증 기록](verification.md)에 있습니다. Celery·Kombu·Pyro5·PostgreSQL은 아직 설치·연동되지 않았습니다. `Pika`와 `Pyro5`는 서로 다른 라이브러리입니다.

저장소: [amirer21/message-flow-lab](https://github.com/amirer21/message-flow-lab) — public.

학습 사이트: [MessageFlow Lab](https://messageflow-lab-amire.mirohong.chatgpt.site) — 기존 접근 범위를 유지합니다. GitHub 공개 여부와 Sites 접근 범위는 별개입니다.

## 2. 구조와 확장 방향

현재 실행 흐름:

```text
Vue 대시보드 ─ HTTP + X-Lab-Token → FastAPI Gateway
                                      ├─ Pika → RabbitMQ / lab vhost
                                      ├─ Management API → Queue 지표
                                      ├─ Phase 2 자식 Consumer / IPC
                                      └─ data/ JSONL 업무·이벤트 기록
```

| 현재 경로 | 역할 |
|---|---|
| `frontend/src/App.vue` | 단계 선택, 예시/실제 모드, 연결, 가이드, 기기별 기록 |
| `frontend/src/PhaseTwo.vue`, `PhaseThree.vue` | 단계별 실험 화면 |
| `frontend/src/lab.ts`, `routing.ts` | 예시 모델과 HTTP 요청, Routing 예시 |
| `frontend/src/curriculum.ts`, `types.ts` | 로드맵과 관측 데이터 계약 |
| `backend/app/main.py` | 인증, CORS, Phase 1·2 API, 앱 생명주기 |
| `backend/app/consumer.py`, `experiments.py` | Consumer 제어와 Phase 2 자식 프로세스 |
| `backend/app/routing.py` | 전용 스레드가 소유하는 Phase 3 임시 토폴로지 |
| `backend/app/events.py`, `effects.py` | 세션 이벤트 및 디스크 업무 기록 |
| `workers/pika_worker/` | 직접 실행용 Pika Worker |
| `backend/app/phase2_worker.py` | 제어기가 실행하는 Phase 2 자식 Consumer |
| `docker-compose.yml`, `infra/` | 로컬 서비스와 RabbitMQ 설정 |
| `scripts/`, `backend/tests/`, `frontend/tests/` | 실행·패키징·실제 실험·단위 검증 |

후속 단계별 `PhaseFour.vue` 등의 화면과 `backend/app/reliability.py` 등의 APIRouter를 추가하는 방식을 권장합니다. 새 라우터에도 기존 인증을 적용합니다. 현재 API는 **한 프로세스**로 실행합니다. 메모리 기반 컨트롤러를 다중 Worker로 실행하면 상태·프로세스 소유권이 분리되므로 금지합니다. 다중 API 프로세스 지원은 별도의 설계 변경입니다.

단계별 Queue/Exchange와 실행 프로세스를 분리합니다. Phase 3의 `phase3.<uuid>` Queue는 exclusive 임시 자원이며, 새 실험과 연결 종료 시 삭제됩니다. 재시작·영속성 실험에는 이 Queue를 재사용하지 않습니다.

## 3. 구현 순서와 의존성

```text
Phase 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12
 Confirm  Retry  멱등   성능   Kombu Celery  운영   RPC   Outbox
```

Phase 6의 PostgreSQL·멱등 소비를 Phase 9의 업무 Task와 Phase 12의 Outbox 실험에서 재사용합니다. Phase 7의 동일 부하 정의는 Phase 8·9 비교에 재사용합니다. 단계를 한 번에 모두 구현하지 않고, 한 단계의 실제 성공·실패 검증과 문서를 마친 다음 진행합니다. 사용자가 특정 단계만 지정하면 그 범위를 우선합니다.

일정은 개발 시간과 설치 환경에 따라 달라지므로 고정 일수 대신 아래 완료 기준으로 진도를 판단합니다.

## 4. Phase 4 · 발행 신뢰성

**질문:** Producer는 무엇을 근거로 성공을 판단하는가?

구현:

- Phase 4 전용 Exchange와 Queue, 발행 설정(Confirm, mandatory, delivery_mode), 발행 결과 상세.
- Pika Confirm과 Return 처리. Confirm ACK/NACK, Return, 연결 실패/미확인을 별도 필드·이벤트로 기록.
- `PUBLISH_SENT`, `PUBLISH_CONFIRMED`, `PUBLISH_NACKED`, `PUBLISH_RETURNED`, `PUBLISH_OUTCOME_UNKNOWN` 등을 정의하되 실제 관측된 상태만 기록.
- durable Queue + persistent 메시지의 재시작 실험과 임시/비영속 비교 실험. Queue 속성을 바꿀 때 같은 이름으로 재선언하여 PRECONDITION_FAILED를 유발하지 않도록 토폴로지 분리.
- UI는 Broker 확인, 라우팅 결과, Consumer 업무 완료를 별도 표시. Confirm이 있는 unroutable 메시지에서도 mandatory Return을 독립적으로 처리.

검증·완료 기준:

1. 정상 라우팅의 Confirm 수신과 실제 Queue 보관을 확인한다.
2. binding 없는 key + mandatory의 Return과 Queue 미수신을 확인한다. Confirm과 Return을 하나의 성공/실패 boolean으로 합치지 않는다.
3. 단위 검증에서 연결 단절 후 미확인을 성공으로 표시하거나 무조건 재발행하지 않는지 검사한다. 실제 장애의 결과가 ACK/NACK/unknown 중 무엇이었는지 증거와 함께 기록한다.
4. **전용 실험 Broker 또는 독립 Compose 프로젝트**에서 정상 재시작 전후 durable+persistent 메시지 잔존을 확인한다. 이 결과를 강제 전원 종료·복제 장애까지 안전하다는 보장으로 확대하지 않는다.

산출물 제안: `reliability.py`, `PhaseFour.vue`, 예시 모델, `smoke_phase4.py`, `docs/phase4.md`.

## 5. Phase 5 · 실패, Retry, DLQ

**질문:** 다시 시도할 실패와 격리할 실패는 어떻게 나누는가?

구현:

- 메시지별 시나리오: 정상, N회 일시 실패 후 성공, 영구 실패. 입력은 고정 시나리오와 제한된 횟수·지연만 허용.
- 작업 Queue → Retry Queue(TTL + DLX) → 작업 Queue, 최종 DLQ 토폴로지. 앱 retry_count, attempt_id, 원래 message_id를 구분.
- bounded retry, 지연·백오프, 영구 실패 즉시 격리. 무한 immediate requeue를 기본 정책으로 사용하지 않음.
- DLQ 목록은 저장한 이력으로 조회. Queue에서 꺼내서 보여주는 행위는 소비임을 명시하고 일반 목록 조회와 분리.
- 재발행 기반 Retry를 선택하면 새 메시지의 Confirm 후 원본 ACK. 그 사이 장애로 중복이 생길 수 있음을 표시. DLX 기반 이동의 보장은 사용 Queue 종류/정책에 따라 공식 문서 확인.

검증·완료 기준:

1. 일시 실패 2회 후 성공: 업무 성공 1회, 시도 3회.
2. 영구 실패와 재시도 한도 초과: 각각 최종 DLQ 기록, 자동 반복 중단.
3. 실패 처리 중 Worker 종료: 메시지가 어디에 남는지 실제 Queue·이벤트로 추적.
4. TTL 지연은 최소 대기와 실제 관측 시간을 구분. 정밀한 스케줄러처럼 설명하지 않음.

산출물 제안: Retry Worker, `retry.py`, `PhaseFive.vue`, `smoke_phase5.py`, `docs/phase5.md`.

## 6. Phase 6 · PostgreSQL과 멱등 업무 처리

**질문:** 동일 요청이 중복·동시에 도착해도 업무 효과를 한 번만 반영할 수 있는가?

구현:

- PostgreSQL 서비스·healthcheck·영속 볼륨, 고정 버전의 DB 드라이버·migration 도구. 기존 RabbitMQ 볼륨 보존.
- 제안 테이블: `experiments`, `observed_events`, `processed_commands`, `business_effects`. 이벤트는 관측 시각·source·run_id·message_id·attempt_id·queue·metadata 저장.
- 업무 idempotency_key는 Message ID와 별도. `processed_commands(consumer_scope, idempotency_key)` 고유 제약과 업무 변경을 **동일 DB 트랜잭션**으로 커밋.
- 별도 트랜잭션의 먼저 처리됨 표시, 메모리 set, 단순 SELECT 후 INSERT로 동시 중복을 막았다고 주장하지 않음.
- 커밋 후 ACK, 중복 수신은 기존 처리 결과를 확인한 뒤 ACK. 업무 rollback 시 ACK하지 않음.
- 이벤트 이력 조회, cursor/limit, 재시작 후 조회. 기존 Phase 2 중복 효과 실험은 학습 비교용으로 유지.
- 관측 저장 실패와 업무 성공을 구분. 필요하면 저장 불가 상태를 표시하며 성공한 업무를 로그 오류만으로 반복하지 않음.

검증·완료 기준:

1. 동일 업무 키의 메시지를 다른 Worker에서 동시에 처리해 업무 효과 1회.
2. 트랜잭션 중 오류 → 업무와 처리 키 모두 rollback, 재시도 시 정상 반영.
3. DB commit 후 ACK 전 실제 Worker 종료 → 재전달, 업무 효과는 1회.
4. API·Worker·DB 재시작 후 업무 및 이력 유지. migration을 기존 DB에 적용 가능.

산출물 제안: DB migrations/repository, 멱등 Worker, `PhaseSix.vue`, `smoke_phase6.py`, `docs/phase6.md`.

## 7. Phase 7 · Worker와 Prefetch

**질문:** Worker나 Prefetch를 늘릴 때 처리량과 대기는 어떻게 변하는가?

구현:

- Worker 1/3개, Prefetch 1/10/100, 동일한 제한된 부하. 초기값 예: 메시지 30개, 짧은 작업 200ms·긴 작업 2s 혼합.
- 독립 run_id와 Queue, 생산 종료·처리 종료 조건, timeout·정리. 작업 수·대기시간·동시성에 상한을 둠.
- throughput, Worker별 처리 수, p50/p95 완료 시간, Ready/Unacked 시간 추이. 측정 시작·종료 기준과 clock 출처 기록.
- Unacked는 실행 중인 업무 수와 동일하지 않으며 대기 예약을 포함할 수 있음. 다른 호스트 시계로 계산한 지연은 동기화 전제 명시.

검증·완료 기준: 동일 메시지·작업·환경에서 조건 하나씩 변경, 모든 메시지의 최종 결과 대조, 최소 3회 측정과 산포 기록. 특정 설정이 반드시 더 빠르다는 결과를 강제하지 않음. 느린 작업이 있을 때 분배·대기를 실제 데이터로 설명.

산출물 제안: Benchmark runner, Worker profile, `PhaseSeven.vue`, `smoke_phase7.py`, `docs/phase7.md`.

## 8. Phase 8 · Kombu 재구현

**질문:** 추상화가 줄여 주는 코드와 여전히 필요한 책임은 무엇인가?

구현: Kombu Connection/Exchange/Queue/Producer/Consumer로 Phase 1의 발행·Manual ACK, Phase 3의 Routing, Phase 4의 Confirm/Return 대표 시나리오를 재현. Pika와 같은 입력·Queue 조건·관측 이벤트 계약 사용. 의존성 버전 고정. Raw Pika 실습은 유지.

검증·완료 기준: 정상 발행·ACK, ACK 전 종료 후 재전달, Routing 결과, 지원하는 Confirm/Return을 실제 RabbitMQ에서 비교. Kombu transport/버전에 따른 차이는 공식 문서와 실제 결과로 기록. 라이브러리를 바꿔도 exactly-once가 자동 보장된다고 설명하지 않음.

산출물 제안: `workers/kombu_worker/`, adapter, `PhaseEight.vue`, `smoke_phase8.py`, `docs/phase8.md`.

## 9. Phase 9 · Celery 기본

**질문:** Task Framework가 Broker 위에 어떤 기능을 추가하는가?

구현:

- RabbitMQ broker + Linux Celery Worker. native Windows prefork 실행 대신 Docker에서 실행.
- Result Backend는 설계 선택을 기록. 예: Redis 별도 서비스 또는 공식 지원 DB backend. Phase 6의 업무 DB와 결과 저장의 역할을 구분. RPC backend의 제약도 비교 가능.
- JSON serializer만 허용하고 고정된 Task 목록(합산·지연·멱등 업무 등)과 입력 제약 제공. 임의 Task 이름·코드 실행 금지.
- 발행 시 task_id 반환, 상세 조회, result/state, start/finish/failure 관측. `PENDING`은 미실행뿐 아니라 알 수 없는 ID/결과 만료일 수 있음.
- FastAPI 요청에서 `AsyncResult.get()`으로 긴 작업 완료를 기다리지 않음. browser polling을 우선하고 이벤트 스트림은 선택적으로 추가.

검증·완료 기준: Worker 정지 중 Task Queue 보관, 재시작 후 실행, Task ID로 결과 조회, 입력 오류와 실행 오류 구분, 결과 TTL 만료를 성공/실패로 오인하지 않음. 일반 Pika payload를 Celery Task Queue에 넣지 않음.

산출물 제안: `workers/celery_worker/`, tasks API, `PhaseNine.vue`, `smoke_phase9.py`, `docs/phase9.md`.

## 10. Phase 10 · Celery 운영

**질문:** Retry, ACK, Worker 종료 설정이 달라지면 결과는 어떻게 달라지는가?

구현:

- Queue Routing과 dedicated Worker, 제한된 `self.retry()`/autoretry, retry count·Task ID·각 실행 시도 이력.
- 실행 프로필별 `task_acks_late`, `task_reject_on_worker_lost`, 관련 ACK-on-failure/timeout 옵션, concurrency와 prefetch 설정을 저장.
- 비교 행렬: early ACK/late ACK × 실행 자식 종료/전체 Worker 종료 × worker-lost requeue 설정. warm shutdown과 강제 종료를 별도로 기록.
- Celery 이벤트 수집기와 stored history. 이벤트 누락·중복·수집기 중단을 반영하고 Celery state·RabbitMQ 지표·업무 DB를 함께 표시.
- 제어기는 소유한 고정 Worker에만 종료 요청. 사용자 입력 PID나 Docker socket을 HTTP API에 노출하지 않음.

검증·완료 기준: 최소 대표 프로필 3개에서 실제 종료 결과를 기록, Celery Retry와 Broker redelivery를 구분, poison-task 무한 재시작 방지. late ACK 하나만 켜면 모든 자식 종료에서 재실행된다고 단정하지 않음. 중복 가능한 업무에는 Phase 6 보호 적용.

산출물 제안: Worker profiles/controller, event collector, `PhaseTen.vue`, `smoke_phase10.py`, `docs/phase10.md`.

## 11. Phase 11 · Pyro5와 RPC/MQ 비교

**질문:** 즉시 원격 호출과 비동기 작업 요청에서 대기·장애는 어떻게 다른가?

구현:

- Pyro5 Calculator Daemon. Compose 내 직접 URI 연결부터 시작; Name Server는 필수로 추가하지 않아도 됨.
- 같은 계산을 Pyro5 호출과 Celery Task로 수행. 호출 timeout, 요청 시작/응답 시간, task_id/correlation_id 비교.
- 브라우저는 Pyro5에 직접 접속하지 않고 Gateway 사용. 필요한 메서드만 expose, 임의 객체·메서드 경로 입력 금지.
- 서비스 정지, timeout, 호출 중 연결 끊김. 클라이언트 timeout은 서버 실행 취소/미실행의 증거가 아님을 표시.

검증·완료 기준: 같은 입력의 정상 결과 일치, RPC 서비스 중단 시 호출 실패와 MQ Worker 중단 시 Queue 대기를 비교, timeout 후 서버 결과 확인. MQ 기반 request/reply도 가능함을 설명하고 선택한 실행 모델을 비교.

산출물 제안: `workers/pyro_service/`, rpc API, `PhaseEleven.vue`, `smoke_phase11.py`, `docs/phase11.md`.

## 12. Phase 12 · Outbox와 종합 장애 실험

**질문:** DB commit과 메시지 발행 사이에서 중단돼도 어떻게 복구하는가?

구현:

- 업무 변경과 outbox row 삽입을 같은 PostgreSQL 트랜잭션으로 commit.
- outbox schema 제안: event_id, aggregate_id, payload, created_at, status, attempts, next_attempt_at, lease_owner/lease_until, published_at. 인덱스·정리 정책 포함.
- Relay 경쟁 처리: claim·짧은 DB transaction·lease, 필요하면 `FOR UPDATE SKIP LOCKED`. 네트워크 발행 동안 긴 업무 transaction을 유지하지 않도록 설계.
- Confirm 이후 발행완료 표시. Confirm 후 DB 표시 전 장애는 재발행 가능. 소비자는 Phase 6의 안정된 업무 키로 중복 방어.
- 적체·최고 대기시간·retry·오류·복구 이력 화면. WebSocket을 추가한다면 DB cursor로 재접속 후 누락 복구, polling fallback, 인증 구현.

검증·완료 기준:

1. Broker 중단 중 업무 commit 성공 + 미발행 outbox 누적.
2. Broker 복구 후 제한된 재시도·backoff로 미발행분 처리.
3. 발행 Confirm 후 published 표시 전 Relay 실제 종료 → 동일 event 재발행, 소비 업무 효과 1회.
4. Relay 2개 동시 실행·lease 만료 회수·DB rollback 검사.
5. DB/Broker/Worker 종료 위치별 결과를 run_id 기준으로 추적하고 재실행 가능한 최종 시나리오로 제공.

산출물 제안: Outbox migration, Relay, scenario runner, `PhaseTwelve.vue`, `smoke_phase12.py`, `docs/phase12.md`.

## 13. 공통 데이터 계약 제안

향후 단계의 메시지 envelope:

```json
{
  "schema_version": 1,
  "message_id": "UUID",
  "run_id": "UUID",
  "correlation_id": "UUID",
  "idempotency_key": "stable-business-key",
  "created_at": "UTC ISO-8601",
  "retry_count": 0,
  "payload": {}
}
```

이는 새 단계의 제안이며 기존 Phase 1/2/3와 Celery wire protocol을 강제로 바꾸는 지시가 아닙니다. Celery Task는 Celery 표준 형식을 사용하고 application headers·arguments에 상관관계를 저장합니다.

`message_id`: 논리 메시지, `attempt_id`: 각 전달/실행 시도, `queue`: Fanout 복사 위치, `task_id`: Celery Task, `idempotency_key`: 업무 중복 기준. 모든 ID를 하나로 대체하지 않습니다.

관측 이벤트 최소 필드: event_id, run_id, message_id, event_type, observed_at(UTC), source, worker, queue, attempt_id, metadata. 기존 timestamp/metadata 계약을 바꾸면 adapter나 버전 필드를 추가하고 UI·검증을 함께 변경합니다. Broker 내부 ROUTED/QUEUED 시각은 측정 없이 생성하지 않습니다.

## 14. 공통 완료 조건

- 기존 단계 정상 동작, 단계별 예시 모델과 실제 실행 결과가 구분됨.
- 정상/실패 실제 RabbitMQ 또는 해당 외부 서비스 실험을 실행하고 증거 기록.
- 오류·수집 중단 때 이전 수집값과 시각 표시. 미수집 값을 0으로 대체하지 않음.
- 입력 제약·토큰 인증·CORS·고정 Worker 제어 적용, 비밀·실험 데이터는 공개 저장소와 ZIP에서 제외.
- 단계 가이드, 체크리스트, README, 검증 기록, 버전, 다운로드 패키지 함께 갱신.
- 수행하지 못한 실제 검증은 미검증으로 명시. 예시 결과를 실제 성공으로 보고하지 않음.
- 배포는 승인된 저장소·기존 Site에만 수행. Site 프런트 배포가 로컬 RabbitMQ/Worker/API 배포를 의미하지 않음.

## 15. 공식 참고 자료

2026-10-06 확인. 구현 시 설치 버전과 문서 버전을 다시 대조합니다. 현재 RabbitMQ 이미지는 4.2 계열이며 기본 웹 문서가 더 새 버전일 수 있습니다.

- [RabbitMQ Confirm/ACK](https://www.rabbitmq.com/docs/confirms): 발행 확인과 소비 ACK의 독립성.
- [RabbitMQ Exchanges](https://www.rabbitmq.com/docs/exchanges), [Topic Python 튜토리얼](https://www.rabbitmq.com/tutorials/tutorial-five-python): Routing 및 패턴.
- [RabbitMQ DLX](https://www.rabbitmq.com/docs/dlx), [TTL](https://www.rabbitmq.com/docs/ttl): Phase 5 구현 시 버전별 추가 확인.
- [Pika](https://pika.readthedocs.io/en/stable/), [Kombu](https://docs.celeryq.dev/projects/kombu/en/stable/): 사용 API와 transport별 기능 확인.
- [Celery Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html), [Configuration](https://docs.celeryq.dev/en/stable/userguide/configuration.html): ACK·Retry·worker-lost 관련 설정.
- [PostgreSQL Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): 동시 처리·트랜잭션 설계.
- [Pyro5 Client](https://pyro5.readthedocs.io/en/latest/clientcode.html): Proxy·timeout·접속 동작.

이 프로젝트의 단계 순서·화면·파일 제안·Outbox 구조는 위 문서를 바탕으로 한 **프로젝트 설계안**입니다. 라이브러리의 자동 제공 기능이나 전달 보장으로 간주하지 마세요.
