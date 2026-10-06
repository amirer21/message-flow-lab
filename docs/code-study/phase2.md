# Phase 2 · 프로세스 종료·재전달·중복 업무 코드

학습 목표: API 부모 프로세스와 Consumer 자식 프로세스의 역할을 구분하고, 업무 기록과 ACK 사이 장애가 왜 중복 업무로 이어지는지 설명합니다.

## 1. 읽을 파일과 라이브러리

| 파일 | 역할 | 도구·라이브러리 |
|---|---|---|
| [PhaseTwo.vue](../../frontend/src/PhaseTwo.vue) / [App.vue](../../frontend/src/App.vue) | process/ack/crash 버튼, 현재 시도·업무 횟수 표시 | Vue |
| [main.py](../../backend/app/main.py) | experiments API | FastAPI, Pydantic |
| [experiments.py](../../backend/app/experiments.py) | 부모의 자식 실행·명령·수신·종료 제어 | subprocess, Thread, Lock, Event, Future |
| [phase2_worker.py](../../backend/app/phase2_worker.py) | 자식 Consumer, 업무·ACK 실행 | Pika, json, sys, Queue |
| [effects.py](../../backend/app/effects.py) | 업무 파일 쓰기·집계 | pathlib, os.fsync, json, deque |
| [events.py](../../backend/app/events.py) | 부모가 읽은 관측 이벤트 기록 | EventStore |
| [lab.ts](../../frontend/src/lab.ts) | DemoLab의 process/crash | 예시 메모리 모델 |

Phase 2는 `phase2.ack_lab` Queue를 사용합니다. Phase 1의 hello Consumer는 API의 스레드이며, Phase 2의 Consumer는 **별도 Python 프로세스**입니다.

## 2. 두 프로세스의 관계

```text
브라우저 → FastAPI 부모
                ├─ ExperimentConsumer.start(): 자식 실행
                ├─ stdin: process / ack / stop 명령
                ├─ stdout reader: ready / event / response / error 해석
                └─ crash(): 자신이 만든 자식 kill

Consumer 자식 app.phase2_worker
  ├─ stdin 읽기 Thread → 내부 Python Queue
  └─ main Thread: Pika connection/channel 소유
       → RabbitMQ 전달 / Queue에서 제어 명령 꺼냄
       → 업무 JSONL 기록 또는 ACK
       → stdout에 JSON 이벤트/응답
```

stdin/stdout은 운영체제의 프로세스 간 통신(IPC)입니다. 부모의 HTTP 명령을 RabbitMQ나 Pyro5로 보내는 구조가 아닙니다. 자식 stdin 읽기 스레드는 Pika를 조작하지 않고 내부 Queue에 명령만 넣습니다.

## 3. 부모 ExperimentConsumer의 함수

| 함수 | 입력 | 출력·효과 |
|---|---|---|
| `start()` | 없음 | 이전 reader 정리, 고정 자식 명령 실행, ready 대기, 현재 view |
| `view()` | 없음 | consumer_active와 pending의 복사 |
| `_read(process)` | 자식 프로세스 | stdout JSON 처리, pending/last_ack 갱신, Future 완료, 이벤트 기록 |
| `command(command, attempt_id)` | process/ack/stop 및 현재 시도 | request_id 생성, stdin 전송, Future 결과 |
| `crash()` | 없음 | 소유 자식 kill/wait, reader join, WORKER_KILLED, status/ack_sent |
| `shutdown()` | 없음 | 정상 stop 시도, 필요한 경우 자식 종료, reader join |

실제 실행 명령은 `[sys.executable, '-u', '-m', 'app.phase2_worker']`입니다. 사용자 입력 실행 파일·shell command·PID를 받지 않습니다. `-u`는 출력 버퍼링을 줄여 reader가 JSON 기록을 빠르게 읽게 합니다.

`_requests[request_id]`는 명령별 Future입니다. 동시에 여러 명령이 있더라도 stdout 응답의 request_id로 올바른 호출을 완료합니다. 이전 reader가 늦게 끝나도 새 자식의 상태를 지우지 않도록 `self._process is process`를 대조합니다.

## 4. 자식 함수와 메시지 종류

| 코드 | 입력 | 동작 |
|---|---|---|
| `emit(kind, **fields)` | 구조화 데이터 | 한 줄 JSON stdout + flush |
| `main()` | 서버 settings, stdin 명령 | Pika 준비, 소비, 명령 처리 루프, 종료 코드 |
| `read_commands()` | stdin 각 줄 | JSON 파싱 → 내부 Queue; 부모 입력 종료 시 stop 명령 |
| `receive(ch, method, properties, body)` | Broker 전달 | pending과 delivery_tag 저장, DELIVERED emit |
| 명령 process 분기 | attempt_id | 현재 시도 검사, append_effect, processed=True, PROCESSED |
| 명령 ack 분기 | attempt_id | processed 여부 검사, basic_ack, ACK_SENT, pending 비움 |
| 명령 stop 분기 | 없음 | 연결 닫기, 루프 종료 |

stdout의 kind는 `ready`, `event`, `response`, `error`입니다. `event_type`은 DELIVERED/PROCESSED/ACK_SENT 등의 관측 종류입니다. kind와 event_type을 혼동하지 않습니다. 명령 검증 실패는 `response`의 ok=False이며 부모가 ValueError로 변환합니다.

## 5. 업무 반영 버튼의 데이터 흐름

```text
PhaseTwo 버튼 → emit action('process') → App.action()
 → POST /experiments/process {attempt_id:A1}
 → main.experiment_control()
 → experiment.command('process', A1)
 → request_id=R1, Future 저장
 → stdin {command:'process', attempt_id:A1, request_id:R1}
 → 자식 read_commands() → Python Queue → main 처리 분기
 → A1 == 현재 시도 확인 / 아직 processed=False 확인
 → append_effect(M1, A1) → JSONL append/flush/fsync
 → pending.processed=True
 → stdout event(PROCESSED) + response(R1, ok=True)
 → 부모 _read(): pending 갱신, events.record, Future 완료
 → HTTP 응답 → App의 /experiments/snapshot 재조회
 → read_effects()가 파일의 업무 횟수 집계 → 화면 표시
```

예시 데이터 형식입니다. 실제 UUID 대신 기호를 사용합니다.

```json
{
  "effect_id": "E1",
  "message_id": "M1",
  "attempt_id": "A1",
  "timestamp": "UTC ISO-8601"
}
```

`request_id=R1`은 제어 명령, `attempt_id=A1`은 전달, `effect_id=E1`은 업무 기록입니다. 세 역할이 다르므로 같은 ID로 대체하지 않습니다.

## 6. 업무 파일 함수의 로직

`append_effect(message_id, attempt_id)`는 파일 경로를 준비하고 append 모드로 JSON 한 줄을 씁니다. `flush()`는 Python 버퍼를 내보내고 `os.fsync()`는 파일 내용을 디스크에 반영하도록 요청합니다. 반환된 record가 PROCESSED 이벤트에도 포함됩니다.

`read_effects()`는 파일을 줄 단위로 읽고 Message ID별 횟수를 집계합니다. 최근 200개 기록만 화면 목록에 유지하지만 effect_counts/effects_total은 읽은 유효 기록 전체 기준입니다. 마지막 줄이 장애로 불완전할 수 있으므로 JSON 파싱 오류·필수 ID 누락 줄은 건너뜁니다.

이 파일은 학습용 업무 효과입니다. 거래 DB의 트랜잭션·동시성·멱등성 보장이 아닙니다. processed 플래그도 자식 메모리이므로 재전달 시 복원되지 않습니다.

## 7. ACK 전 종료: 중복이 생기는 순서

| 순서 | Broker/Consumer | 업무 파일 |
|---|---|---|
| M1 전달 | pending=M1/A1, Unacked 1 | 없음 |
| process A1 | processed=True, 아직 ACK 전 | M1/A1 기록 1개 |
| crash | 자식 SIGKILL, 연결 끊김 | 기록 유지 |
| Broker 종료 감지 | M1 재전달 가능 | 기록 유지 |
| 재시작·재전달 | M1/A2, redelivered=True, processed=False | 여전히 1개 |
| process A2 | 새 시도 업무 반영 | M1/A1 + M1/A2, 횟수 2 |
| ACK A2 | 확인 전송·Broker 반영 | 횟수 2 유지 |

같은 시도의 process 두 번 클릭은 막지만, 새 시도의 업무 실행은 막지 않습니다. 바로 이 차이를 관찰하고 Phase 6에서 안정된 업무 키·DB 고유 제약·트랜잭션으로 보호합니다.

## 8. ACK 후 종료: 무엇을 확인해야 하나?

자식 ACK 분기는 processed=True를 요구합니다. 업무 후 basic_ack를 호출하고 ACK_SENT를 emit한 다음 pending을 비웁니다. 부모의 `_last_ack`는 최근 ACK 전송을 기억합니다.

`crash()`의 반환 `ack_sent=True`는 부모가 ACK_SENT를 관측했다는 뜻입니다. **Broker가 ACK를 반영했다는 증거는 아닙니다.** ACK 후 종료 비교 실험은 Ready/Unacked가 0으로 수집된 것을 확인한 뒤 종료합니다. `scripts/smoke_phase2.py`도 이 조건을 기다립니다.

상태 응답 `experiment_snapshot()`은 `queue_stats(phase2 Queue)`, experiment.view(), events.view(phase2 Queue), read_effects(), collected_at을 합칩니다. 이 중 Broker 지표·메모리 상태·디스크 기록의 출처는 서로 다릅니다.

## 9. 예시 모델과 실제 장애의 차이

App의 `demo2`는 `new DemoLab('phase2.ack_lab', true)`입니다. true는 ACK 전에 process가 필요함을 뜻합니다. `process()`는 메모리 effects에 추가하고, `crash()`는 stop으로 pending을 다시 대기 상태로 만듭니다.

예시는 SIGKILL이나 디스크 쓰기를 하지 않습니다. 실제 모드의 파일·Broker 감지 지연·IPC 실패와 구분하세요. 예시 모드의 횟수를 실제 업무 파일 증거로 사용하지 않습니다.

## 10. 함수와 함께 하는 실험

1. process와 ACK가 다른 분기인 위치를 찾고, 하나의 함수로 합치면 관찰하기 어려운 장애 구간을 설명하세요.
2. M1/A1 업무 후 종료했다면 재시작 시 어떤 필드를 유지/재생성할지 예측하세요.
3. 자식에 이전 A1 ACK를 보내면 어떤 분기에서 막히는지 찾으세요.
4. `_read()`의 response 처리와 event 처리가 왜 별개인지 설명하세요.
5. `read_effects()`의 counts와 deque의 길이가 다른 이유를 설명하세요.
6. ACK_SENT만 관측하고 바로 종료한 결과를 재전달 없음으로 확정하면 안 되는 이유를 설명하세요.

실제 종료·검증은 [Phase 2 실험 안내](../phase2.md)를 따릅니다. 현재 사용자 메시지를 삭제하거나 외부 프로세스를 종료하지 않습니다.

다음 문서: [Phase 3 · Exchange·Binding·Routing](phase3.md).
