# 학습 로드맵 v3

각 Phase는 질문 → 예측 → 구현 → 정상/실패 실험 → 관찰 → 설명 순서로 진행합니다. 달력보다 완료 기준을 우선합니다.

| Phase | 학습 | 완료 기준 | 구현 상태 |
|---|---|---|---|
| 0 | 최소 환경·AMQP·Management | 환경 시작/종료 재현, 포트 역할 설명 | 구현 |
| 1 | Pika·Producer·Consumer·Manual ACK | 3개 발행 → Ready 3 → Unacked 1 → ACK 후 0 | 구현 |
| 2 | 전달·ACK·Consumer 종료 | ACK 전/후 강제 종료, 재전달과 중복 업무 반영 비교 | 구현 |
| 3 | Direct·Fanout·Topic Routing | Binding에 따른 수신 Queue 예측 | 구현 |
| 4 | Confirm·Return·Persistent·Durable | Broker 수락과 라우팅·업무 완료 구분 | 구현 |
| 5 | Retry·Requeue·TTL·DLQ | 제한된 재시도와 영구 실패 격리 | 구현 |
| 6 | PostgreSQL·멱등성 | 동시 중복 요청에도 업무 효과 한 번 | 예정 |
| 7 | Worker·Prefetch·성능 | 같은 부하에서 처리량과 대기시간 비교 | 예정 |
| 8 | Kombu 재구현 | 동일 실험에서 Pika 대응 개념 설명 | 예정 |
| 9 | Celery 기본·Result Backend | 요청·실행 분리, Task ID 결과 조회 | 예정 |
| 10 | Celery ACK·Retry·Routing·Events | 설정별 Worker 종료 결과 비교 | 예정 |
| 11 | Pyro5와 RPC/MQ | 대기·버퍼링·Timeout 차이 설명 | 예정 |
| 12 | Outbox·Relay·종합 장애 | 미발행 이벤트 복구와 중복 방어 | 예정 |

## 관측 원칙

구조 설명용 흐름도와 관측 이벤트를 구분합니다. Broker 내부의 ROUTED·QUEUED 시각을 측정 없이 만들어내지 않습니다. Fanout은 Queue별 전달로, Retry/재전달은 시도별 기록으로 확장합니다. Unacked에는 아직 실행되지 않은 예약 메시지가 포함될 수 있습니다.

Publisher Confirm과 Consumer ACK는 독립적입니다. Mandatory Return을 함께 배워 라우팅 실패를 구분합니다. Durable Queue와 Persistent Message만으로 모든 장애에 안전한 것은 아닙니다.

Celery early/late ACK와 task_reject_on_worker_lost를 별도 실험합니다. Exactly-once 전달을 기본 보장으로 설명하지 않고 멱등성을 통해 업무 효과를 보호합니다. Outbox Relay는 중복 발행 가능성을 남기므로 멱등 소비와 함께 구현합니다.

## 데이터와 화면의 확장

Phase 0~1: 단계별 안내, 예시/실제 연결, 메시지 발행, Queue 요약, 수동 ACK, 관측 이력, 기기별 실험 기록.

Phase 2: 별도 Queue와 실제 자식 Consumer 프로세스, ACK 전/후 강제 종료, 같은 메시지의 시도 이력, 영속 학습용 업무 반영 횟수.

Phase 3: Direct/Fanout/Topic의 임시 Exchange·Queue, Binding 편집, Queue 예측과 실제 복사본 수신 비교.

Phase 4~5: Confirm/Return, Retry와 DLQ 화면.

Phase 6~10: PostgreSQL 실험/관측 이벤트 저장, Worker 비교, Kombu 비교, Task 상세와 Celery 이벤트.

Phase 11~12: RPC/MQ 비교, Outbox 적체·복구 이력.

RabbitMQ 지표는 서버에서 주기적으로 수집하고, 앱 이벤트는 직접 기록합니다. 관측 기반이 갖춰진 뒤 브라우저로의 WebSocket 전달과 누락된 저장 이벤트 재조회를 추가합니다.

## 선택 심화

Quorum Queue 복제 장애와 안전한 dead-lettering, Celery Canvas/Beat/Autoscaling, OpenTelemetry, Saga. 단일 Broker 재시작과 다중 노드 고가용성 실험은 구분합니다. Lazy Queue 설정은 역사적 내용으로만 다룹니다.

## 실험 기록

질문, 고정 조건, 변경한 설정, 예상, 절차, 실제 지표/로그, 설명, 재실행·정리 방법을 기록합니다. 부하 실험에는 메시지 수·작업 시간·동시 실행 수·Worker 수·Prefetch를 함께 남깁니다.

## 개발 인계

후속 구현은 [남은 단계 개발 계획서](remaining-development-plan.md)와 [AI 에이전트 작업 지침](ai-agent-instructions.md)을 따릅니다. 다음 구현 단계는 Phase 5입니다.
