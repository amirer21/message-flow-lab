# 실행 검증 · 2026-10-06

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
| Python API·ACK·업무 기록 단위 검증 | 15개 통과 |
| 브라우저 예시 상태 모델 검증 | 5개 통과 |
| 실제 Phase 1 발행·소비 | 3개 발행 → Ready 3 → Unacked 1 → ACK 3회 → Queue 비움 |
| 실제 Phase 2 ACK 전 종료 | Consumer 자식 프로세스 강제 종료 후 동일 Message ID 재전달, 새 Attempt ID, redelivered=true |
| 실제 Phase 2 중복 업무 | 재전달 후 같은 메시지의 영속 업무 기록 2회 확인 |
| 실제 Phase 2 ACK 후 종료 | Broker 지표에서 ACK 반영 확인 후 강제 종료·재시작, 재전달 없음, 업무 기록 1회 |

실제 장애 실험은 Linux 컨테이너에서 제어기가 생성한 자식 프로세스를 강제 종료하여 확인했습니다. 외부 프로세스나 Broker를 종료하지 않았습니다. 검증 스크립트는 기존 메시지를 자동 삭제하지 않습니다.

## 범위

Celery·Kombu·Pyro5는 아직 구현 단계가 아닙니다. 현재 실습은 Pika와 RabbitMQ를 사용합니다. 브라우저 예시 검증은 상태 모델을 검사하며, 실제 화면의 모든 클릭을 자동화한 검증은 아닙니다. 실제 환경 연결은 로컬 화면에서 사용합니다. 게시된 Sites 화면의 실제 연결에는 HTTPS Gateway가 별도로 필요합니다.

## 재실행

```powershell
docker compose up --build -d
docker compose exec -T api python scripts/smoke.py
docker compose exec -T api python scripts/smoke_phase2.py
```
