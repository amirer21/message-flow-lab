# Release Notes

## v0.6 — Phase 6: 멱등성 (Idempotency)

### 새 기능

- **Phase 6 실습 추가** — "같은 요청이 두 번 와도 결과를 한 번만 반영할까?" 학습
- DB unique constraint + 트랜잭션으로 업무 중복을 방어하는 멱등성 패턴 실습
- SQLite 기반 멱등성 검사 (추가 Docker 서비스 불필요)
- 3가지 시나리오: 정상 처리 / 중복 발행 / Commit 후 장애
- 업무 효과 테이블(business_effects)로 중복 방어 결과를 직접 관찰
- Demo 모드 + 실제 RabbitMQ 연결 모드 모두 지원
- 시나리오 자동 실행 버튼으로 전체 흐름을 한 번에 확인
- 통합 테스트 스크립트 (`scripts/smoke_phase6.py`)

### 변경 파일

| 파일 | 변경 |
|------|------|
| `backend/app/database.py` | 신규 — SQLite 연결 및 테이블 관리 |
| `backend/app/idempotency.py` | 신규 — IdempotencyLab + APIRouter |
| `backend/app/main.py` | 수정 — Phase 6 router 등록, 버전 0–6 |
| `frontend/src/idempotency.ts` | 신규 — DemoIdempotency 브라우저 시뮬레이션 |
| `frontend/src/PhaseSix.vue` | 신규 — Phase 6 실험실 UI |
| `frontend/src/types.ts` | 수정 — Phase 6 타입 추가 |
| `frontend/src/App.vue` | 수정 — Phase 6 탭·가이드·버전 표기 |
| `frontend/src/curriculum.ts` | 수정 — Phase 6 학습 단계 상세화 |
| `docs/phase6.md` | 신규 — 학습 문서 |
| `scripts/smoke_phase6.py` | 신규 — 통합 테스트 |

### 검증

```bash
docker compose up --build
docker compose exec -T api python scripts/smoke_phase6.py
```

---

## v0.5 — Phase 5: 실패 · Retry · DLQ

- 실패 유형 분류 (일시/영구), TTL 기반 재시도, Dead Letter Queue
- 3가지 시나리오: transient_2x / permanent / retry_exceed

## v0.4 — Phase 4: 발행 신뢰성

- Publisher Confirm, mandatory Return, durable/persistent 비교

## v0.3 — Phase 3: Exchange와 Routing

- Direct, Fanout, Topic exchange 실험

## v0.2 — Phase 2: 전달과 ACK

- ACK 전후 종료 비교, 재전달과 중복 업무 관찰

## v0.1 — Phase 1: 첫 메시지 보내기

- Producer → Queue → Consumer 기본 흐름, Manual ACK

## v0.0 — Phase 0: 실습 환경 준비

- RabbitMQ + FastAPI + Vue 실습 환경 구성
