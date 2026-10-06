# Phase 2 · 프로세스 장애와 중복 업무의 원인

현재 프로젝트 구현의 핵심 코드를 발췌합니다. 파일의 주변 선언·imports·연결은 생략될 수 있으므로 전체 파일과 함께 읽으세요.

메시지가 Queue에 남는지뿐 아니라 업무가 몇 번 실행되는지 관찰합니다. DB 저장과 ACK는 서로 다른 시스템의 작업이므로 그 사이에 죽으면 같은 업무가 다시 실행될 수 있습니다.

## 전체 흐름

메시지 수신 · attempt A → 업무 기록 저장 → ACK 전 강제 종료 → 재전달 · attempt B → 같은 업무 다시 실행

## 용어

- **Side effect · 업무 효과**: 파일 기록·DB 변경처럼 실행 뒤에 남는 결과입니다. 현재 실습은 JSONL 파일에 효과를 기록합니다.
- **Redelivered**: Broker가 재전달한 전달의 표시입니다. 업무가 이미 실행됐는지는 이 값만으로 알 수 없습니다.
- **Process / IPC**: Consumer는 별도 자식 프로세스입니다. 부모 API와 stdin/stdout의 구조화된 메시지로 명령·결과를 주고받습니다.
- **fsync**: 파일 기록을 운영체제에 flush한 뒤 저장 장치에 반영하도록 요청합니다. DB 트랜잭션이나 ACK와 원자적으로 묶는 기능은 아닙니다.

## 장애 위치가 결과를 바꿉니다

업무 반영 전에 종료하면 재전달 후 처음 업무를 처리할 수 있습니다. 업무 반영 후 ACK 전에 종료하면 효과는 이미 남았지만 Broker는 완료를 모릅니다. 재전달 시 업무를 반복하면 같은 Message ID의 효과가 두 개 남습니다.

ACK 호출 직후에는 Broker가 아직 반영 중일 수 있습니다. 실험 B는 Queue의 Ready·Unacked가 0으로 수집된 것을 확인한 뒤 종료합니다. 앱의 ACK_SENT 시각을 Broker 처리 시각으로 단정하지 않습니다.

## 왜 별도 프로세스를 사용하나요?

API 내부 상태를 가짜로 초기화하는 대신 실제 Linux Consumer 자식을 강제 종료합니다. Broker·API는 계속 실행되고 ACK하지 않은 연결이 닫히며 재전달을 관찰할 수 있습니다.

고정된 자식만 제어하므로 임의 PID·프로그램 실행을 노출하지 않습니다. stdin 명령은 process/ack/stop이며 부모의 crash가 자신이 생성한 자식을 kill합니다.

## 왜 같은 시도의 중복 클릭만 막을까요?

processed=True는 현재 전달에서 업무 버튼을 두 번 누르는 것을 막습니다. 그러나 자식이 죽고 새 attempt_id로 재전달되면 processed는 다시 False입니다. Message ID를 기준으로 영속 중복 판정을 하지 않기 때문입니다.

이 차이를 의도적으로 보여 주고 Phase 6에서 DB 고유 제약과 트랜잭션으로 해결합니다. 메시지가 다시 오는 것을 막는 것과 업무를 한 번만 반영하는 것은 다른 문제입니다.

## 실제 코드 · 영속 학습용 효과 기록

출처: [backend/app/effects.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/effects.py)

```python
def append_effect(message_id, attempt_id):
    record = {"effect_id": str(uuid4()), "message_id": message_id, "attempt_id": attempt_id,
              "timestamp": datetime.now(timezone.utc).isoformat()}
    path = Path(settings.effect_log)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return record
```

- 효과마다 effect_id를 만들고 message_id·attempt_id를 함께 저장합니다. 재전달의 두 효과를 나란히 비교할 수 있습니다.
- append → flush → fsync로 완료된 기록을 남깁니다. 동일 message_id의 기록을 거절하는 고유 제약은 없습니다.

## 실제 코드 · 업무 반영과 ACK는 다른 명령

출처: [backend/app/phase2_worker.py](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/phase2_worker.py)

```python
if kind == "process":
    if pending["processed"]:
        raise ValueError("이 처리 시도는 이미 업무를 반영했습니다.")
    effect = append_effect(pending["message_id"], pending["attempt_id"])
    # 업무 기록 후 ACK 전 종료하면 새 전달에서 업무가 반복될 수 있다.
    pending["processed"] = True
    emit("event", event_type="PROCESSED", pending=pending, effect=effect)
else:
    if not pending["processed"]:
        raise ValueError("업무 반영을 확인한 뒤 ACK를 보내세요.")
    channel.basic_ack(delivery_tag=tag)
    emit("event", event_type="ACK_SENT", pending=pending)
    pending = None
    tag = None
```

- process 명령은 append_effect 후 processed를 바꿉니다. 이 지점에서 종료하면 효과만 남고 ACK는 없습니다.
- ack 명령은 processed를 확인한 뒤 basic_ack를 보냅니다. 두 명령 사이 장애가 중복의 핵심입니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| 업무 반영 후 ACK 전 강제 종료 | 같은 Message ID, 새 Attempt ID로 재전달 | Broker는 아직 ACK를 반영하지 못했습니다. |
| 재전달 후 업무를 다시 반영 | 업무 효과 2개 | 현재 실습은 메시지별 멱등 처리를 하지 않습니다. |
| ACK와 Queue 비움 확인 후 종료 | 새로 시작해도 해당 메시지 미수신 | Broker의 해당 전달 완료 처리가 반영됐습니다. |

## 주의할 오해

- redelivered=False도 중복 업무가 절대 없다는 증거는 아닙니다. Producer 재발행 등 다른 원인이 있습니다.
- 업무 성공과 ACK를 하나의 atomic 작업처럼 설명하지 않습니다. 파일 기록에도 별도 장애 한계가 있습니다.

## 설명해 보기

- Message ID를 유지하면서 Attempt ID를 새로 만드는 이유는 무엇인가요?
- 업무 기록을 먼저 남겼는데 왜 Broker는 메시지를 다시 보내나요?

## 참고 자료

- [프로젝트 장애 Worker](https://github.com/amirer21/message-flow-lab/blob/main/backend/app/phase2_worker.py)
- [RabbitMQ Reliability](https://www.rabbitmq.com/docs/reliability)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
