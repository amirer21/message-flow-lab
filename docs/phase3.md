# Phase 3 · Exchange와 Routing

질문: 어떤 Queue가 같은 메시지를 받게 될까요?

## 실행

1. Phase 3을 선택합니다. 예시 또는 실제 연결 모드를 확인합니다.
2. Direct/Fanout/Topic을 선택하고 **선택한 종류로 새 실험**을 누릅니다.
3. Routing Key와 Binding Key를 입력하고 수신할 Queue A/B/C를 먼저 예측합니다.
4. 메시지를 발행합니다. Ready와 Message ID를 확인합니다.
5. **Queue별 한 개 수신 · ACK**를 눌러 예측과 실제 수신을 비교합니다.
6. Binding을 바꾸고 앞으로 발행한 메시지와 기존 대기 메시지의 차이를 비교합니다.
7. 실험 기록과 완료 기준을 작성합니다.

| 종류 | 기본 Binding A / B / C | Routing Key | 수신 Queue |
|---|---|---|---|
| Direct | error / info / error | error | A, C |
| Direct | error / info / error | info | B |
| Fanout | 무시 / 무시 / 무시 | 아무 값 | A, B, C |
| Topic | order.* / *.completed / # | order.created | A, C |
| Topic | order.* / *.completed / # | payment.completed | B, C |
| Topic | order.* / *.completed / # | order.created.eu | C |

Topic의 `*`는 한 단어, `#`는 0개 이상의 단어입니다. `order.#`는 `order`도 받을 수 있습니다. [RabbitMQ 공식 튜토리얼](https://www.rabbitmq.com/tutorials/tutorial-five-python)을 참고하세요.

## 관측과 범위

- Queue마다 같은 Message ID의 복사본이 전달될 수 있습니다. 예측은 메시지에 저장하지만 실제 수신 Queue를 결정하는 데 사용하지 않습니다.
- Ready는 passive queue_declare에서 조회한 Broker 실제 대기 수입니다. 이벤트는 basic_get으로 받은 복사본과 ACK 호출을 기록합니다.
- 수신 버튼은 각 Queue에서 최대 한 개를 소비하고 ACK합니다. 일반 지표 조회는 소비하지 않습니다.
- 최신 발행보다 오래된 메시지가 먼저 수신될 수 있으므로 Message ID를 비교합니다.
- Binding 변경은 기존 대기 메시지를 이동시키지 않습니다.
- 발행은 Confirm을 사용하지 않습니다. 미수신만으로 성공·유실을 확정하지 않습니다. 발행 신뢰성은 Phase 4에서 추가합니다.
- API의 전용 스레드·Pika 연결이 `phase3.<uuid>` Exchange와 exclusive 임시 Queue를 소유합니다. 새 실험은 이 단계의 Queue와 대기 메시지를 삭제합니다. 연결 종료 시에도 임시 Queue가 삭제됩니다.
- Phase 1·2의 Queue와 분리됩니다. 현재 Phase 3 토폴로지는 API 프로세스 안에서 공유하며 다중 사용자별 세션 분리는 없습니다.

## 실제 검증

```powershell
docker compose exec -T api python scripts/smoke_phase3.py
```

이 스크립트는 현재 Phase 3 실험을 초기화합니다. 진행 중인 사용자 실험과 함께 실행하지 마세요. Direct/Fanout/Topic, 같은 Message ID의 Queue별 전달, `#`의 0개 단어, Binding 변경 후 기존 메시지 유지, 잘못된 종류 변경의 409 응답을 확인합니다.
