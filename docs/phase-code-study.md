# Phase별 코드 학습 안내

기준: 2026-10-06 / Phase 0–3 구현 소스

각 문서는 **목표 → 파일·라이브러리 → 함수 입력/출력 → 데이터 흐름 → 상태 변화 → 실패 로직 → 코드 읽기 실험** 순서입니다. 기존 [도구와 코드 해설](code-explained.md)은 전체 구조를, 아래 문서는 각 Phase의 실행 경로를 상세히 설명합니다.

| Phase | 학습 문서 | 핵심 질문 |
|---|---|---|
| 0 | [환경 준비와 연결 코드](code-study/phase0.md) | 실행 환경과 API·Broker 연결은 어떻게 만들어지는가? |
| 1 | [발행·수신·Manual ACK 코드](code-study/phase1.md) | 버튼 입력이 메시지와 ACK로 어떻게 바뀌는가? |
| 2 | [프로세스 종료·재전달·중복 업무 코드](code-study/phase2.md) | 업무가 끝났는데 왜 다시 실행되는가? |
| 3 | [Exchange·Binding·Routing 코드](code-study/phase3.md) | 어떤 Queue가 메시지를 받고 어떻게 확인하는가? |

이 문서는 검증이 완료된 Phase 0–3을 기준으로 작성했습니다. 작성 중 작업 폴더에 Phase 4 관련 소스가 추가되고 있으나 이번 문서에서 완료 여부를 검증하지 않았습니다. Phase 4 이후 해설은 각 단계의 구현·검증이 끝난 소스를 기준으로 이어서 추가합니다. Celery는 Phase 9–10, Pyro5는 Phase 11 예정이며 [개발 계획서](remaining-development-plan.md)에 설계가 있습니다.

## 학습 방법

1. 각 문서의 파일을 열고 함수 이름을 검색합니다. `_run`처럼 밑줄로 시작하는 이름은 내부 처리 함수라는 관례이지 별도 실행 환경이라는 뜻은 아닙니다.
2. 실제 모드의 함수 호출 순서를 종이에 적습니다. HTTP 요청, Python 내부 명령, AMQP 메시지, IPC 이벤트를 다른 화살표로 구분합니다.
3. 발행/전달/ACK/업무 반영마다 바뀌는 필드를 찾습니다. API 응답의 snapshot과 Broker 상태는 같은 객체가 아닙니다.
4. 같은 동작을 예시 모드와 비교합니다. 계산된 예시 상태를 실제 Broker 관측으로 해석하지 않습니다.
5. 문서의 예측 문제를 풀고 한 조건씩 바꿔 실험합니다. 실제 버튼은 메시지 발행·소비·종료를 수행합니다. 진행 중인 실험을 보호하세요.

## 공통 ID와 통신 구분

| 이름 | 뜻 | 어디에서 쓰나? |
|---|---|---|
| message_id | 논리 메시지 ID | 발행·재전달·Fanout 복사 비교 |
| attempt_id | 각 전달 시도 ID | Phase 1/2의 stale ACK·중복 클릭 방지 |
| delivery_tag | channel 안의 전달 번호 | Pika basic_ack, 수신한 동일 channel에서 사용 |
| request_id | Phase 2 제어 명령의 ID | stdin 요청과 stdout 응답/Future 연결 |
| event_id | 관측 기록 ID | 이벤트 목록의 개별 기록 구분 |
| effect_id | 업무 반영 기록 ID | Phase 2 JSONL의 각 업무 효과 구분 |

HTTP는 화면과 Gateway 사이, AMQP는 Python과 RabbitMQ 사이, stdin/stdout IPC는 Phase 2 부모·자식 사이의 통신입니다. Python `queue.Queue`는 프로세스 내부 스레드 간 명령을 전달합니다. RabbitMQ Queue와 혼동하지 마세요.

실제 검증 기록은 [verification.md](verification.md)를 참고하세요. 이 문서를 추가하면서 별도의 발행·종료 실험을 실행한 것은 아닙니다.
