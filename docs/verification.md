# 실행 검증 · 2026-10-07

## 환경

- Windows 11 / WSL 3.0.1, 기본 WSL 2
- Docker Desktop 설치 완료, Linux 엔진 29.8.2
- Docker Compose 5.5.1
- 공식 hello-world 컨테이너 정상 실행
- RabbitMQ Management와 FastAPI를 실제 Docker 컨테이너로 실행

## 결과

| 검증 | 결과 |
|---|---|
| Vue·TypeScript 빌드 | 통과 |
| Python API·ACK·업무 기록·신뢰성 단위 검증 | 33개 통과 |
| 브라우저 예시 상태 모델 검증 | 17개 통과 |
| 실제 Phase 1 발행·소비 | 3개 발행 → Ready 3 → Unacked 1 → ACK 3회 → Queue 비움 |
| 실제 Phase 2 ACK 전 종료 | Consumer 자식 프로세스 강제 종료 후 동일 Message ID 재전달, 새 Attempt ID, redelivered=true |
| 실제 Phase 2 중복 업무 | 재전달 후 같은 메시지의 영속 업무 기록 2회 확인 |
| 실제 Phase 2 ACK 후 종료 | Broker 지표에서 ACK 반영 확인 후 강제 종료·재시작, 재전달 없음, 업무 기록 1회 |

| 실제 Phase 3 Direct | error → A/C, info → B, unmatched → 수신 없음 |
| 실제 Phase 3 Fanout | Routing Key와 무관하게 A/B/C에서 동일 Message ID 수신 |
| 실제 Phase 3 Topic | order.created → A/C, payment.completed → B/C, order.created.eu → C |
| 실제 Phase 3 # | order.# Binding은 order(추가 단어 0개) 수신 |
| 실제 Phase 3 Binding 변경 | 기존 메시지 유지, 이후 발행에 새 Binding 적용, 종류 변경 요청 409 |

| 실제 Phase 4 정상 Confirm | normal 발행 → Confirm ACK, Queue A Ready=1 |
| 실제 Phase 4 Mandatory Return | unroutable key + mandatory → Confirm ACK + Return 동시, Queue 미보관 |
| 실제 Phase 4 Confirm/Return 분리 | PUBLISH_CONFIRMED와 PUBLISH_RETURNED가 별도 이벤트로 기록 |
| 실제 Phase 4 Persistent | delivery_mode=2 → durable Queue B 보관, Confirm ACK |
| 실제 Phase 4 Transient | delivery_mode=1 → auto_delete Queue C 보관, Confirm ACK |
| 실제 Phase 4 수신·ACK | 3개 Queue에서 수신, delivery_mode 보존, 수신 후 Ready=0 |
| 실제 Phase 4 이벤트 완전성 | TOPOLOGY_CREATED, PUBLISH_SENT, PUBLISH_CONFIRMED, PUBLISH_RETURNED, DELIVERED, ACK_SENT 모두 기록 |

실제 장애 실험은 Linux 컨테이너에서 제어기가 생성한 자식 프로세스를 강제 종료하여 확인했습니다. 외부 프로세스나 Broker를 종료하지 않았습니다. Phase 1·2 검증은 기존 메시지를 자동 삭제하지 않습니다. Phase 3·4 검증은 해당 단계의 임시 토폴로지·대기 메시지를 초기화합니다. 다른 단계 Queue는 삭제하지 않습니다.

## 미검증

- Broker 재시작 후 durable+persistent 잔존 및 auto_delete 소멸은 수동 실험으로 안내. 자동 smoke에서 `docker compose restart rabbitmq`를 실행하지 않음 (진행 중인 실험 보호).
- NACK 시나리오는 정상 RabbitMQ에서 자연 발생이 드물어 mock 단위 검증으로 확인. 실제 NACK 유발은 미수행.
- 연결 실패(PUBLISH_OUTCOME_UNKNOWN)는 mock 단위 검증으로 확인. 실제 네트워크 단절은 미수행.

## 범위

Celery·Kombu·Pyro5는 아직 구현 단계가 아닙니다. 현재 실습은 Pika와 RabbitMQ를 사용합니다. 브라우저 예시 검증은 상태 모델을 검사하며, 실제 화면의 모든 클릭을 자동화한 검증은 아닙니다. 실제 환경 연결은 로컬 화면에서 사용합니다. 게시된 Sites 화면의 실제 연결에는 HTTPS Gateway가 별도로 필요합니다.

## 재실행

```powershell
docker compose up --build -d
docker compose exec -T api python scripts/smoke.py
docker compose exec -T api python scripts/smoke_phase2.py
docker compose exec -T api python scripts/smoke_phase3.py
docker compose exec -T api python scripts/smoke_phase4.py
```
