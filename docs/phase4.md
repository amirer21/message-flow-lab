# Phase 4 · 발행 신뢰성

## 학습 질문

Producer는 무엇을 근거로 성공을 판단하는가?

## 예상과 관찰

| 시나리오 | Confirm | Return | Queue 보관 | 설명 |
|---|---|---|---|---|
| normal (routed key) | ACK | 없음 | Queue A | 정상 라우팅, Broker가 수락 |
| mandatory_unroutable | ACK | 수신 | 없음 | Broker는 수락했으나 라우팅 불가 |
| persistent (delivery_mode=2) | ACK | 없음 | Queue B (durable) | 재시작 후 잔존 |
| transient (delivery_mode=1) | ACK | 없음 | Queue C (auto_delete) | 재시작 후 소멸 |

Confirm ACK는 Broker가 메시지를 수락했다는 응답이며, Consumer가 처리를 완료했다는 뜻이 아닙니다. mandatory Return은 Confirm과 독립적으로 발생합니다.

## 실행

1. Phase 4를 선택합니다. 예시 또는 실제 연결 모드를 확인합니다.
2. 시나리오를 선택합니다 (정상 Confirm / Mandatory Return / 영속 / 임시).
3. 메시지를 발행하고 Confirm 상태와 Return 상태를 별도로 확인합니다.
4. Queue별 Ready 지표를 확인합니다.
5. Queue별 한 개 수신 · ACK를 눌러 실제 보관 여부를 확인합니다.
6. 완료 기준을 체크합니다.

## 토폴로지

- Exchange: `phase4.<uuid>` (direct, durable)
- Queue A: `phase4.<uuid>.routed` (durable, binding key=`routed`)
- Queue B: `phase4.<uuid>.persistent` (durable, binding key=`persistent`)
- Queue C: `phase4.<uuid>.transient` (auto_delete, binding key=`transient`)
- binding 없는 key `unroutable`로 mandatory Return 실험

Pika Confirm 모드(`confirm_delivery()`)를 사용하여 `basic_publish` 호출 시 Broker ACK/NACK을 동기적으로 확인합니다.

## 이벤트 타입

- `PUBLISH_SENT`: 앱이 publish를 호출한 기록. Broker 수신 확인 이전.
- `PUBLISH_CONFIRMED`: Broker Confirm ACK 수신. Queue에 보관됨.
- `PUBLISH_NACKED`: Broker Confirm NACK 수신. Broker가 거부.
- `PUBLISH_RETURNED`: mandatory 메시지의 Return. Confirm과 독립적.
- `PUBLISH_OUTCOME_UNKNOWN`: 연결 실패 등으로 결과 불명.
- `DELIVERED`, `ACK_SENT`: 기존과 동일.

Confirm과 Return을 하나의 성공/실패 boolean으로 합치지 않습니다.

## 영속성 실험 (수동)

자동 smoke에서 Broker 재시작을 실행하지 않습니다. 수동 실험:

1. persistent 시나리오로 메시지를 발행합니다 (Queue B에 보관).
2. transient 시나리오로 메시지를 발행합니다 (Queue C에 보관).
3. `docker compose restart rabbitmq`로 Broker를 정상 재시작합니다.
4. Queue B의 persistent 메시지가 잔존하는지 확인합니다.
5. Queue C(auto_delete)는 연결 종료 시 삭제되므로 메시지도 소멸합니다.

durable Queue + persistent 메시지라도 강제 전원 종료·복제 장애까지 안전하다는 보장은 아닙니다.

## 완료 기준

- Broker Confirm(수락)과 Consumer 처리 완료가 다름을 설명한다.
- mandatory Return과 Confirm ACK가 독립적인 사실임을 확인했다.
- Confirm 미확인 상태의 불확실성을 설명한다.
- durable+persistent와 임시 Queue의 재시작 차이를 확인했다.

## 실제 검증

```powershell
docker compose exec -T api python scripts/smoke_phase4.py
```

이 스크립트는 Phase 4 토폴로지를 초기화합니다. 진행 중인 Phase 4 사용자 실험과 함께 실행하지 마세요. 다른 Phase에는 영향을 주지 않습니다.

[RabbitMQ Publisher Confirm 공식 문서](https://www.rabbitmq.com/docs/confirms)
