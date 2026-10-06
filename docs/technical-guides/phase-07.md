# Phase 7 · Worker·Prefetch·처리량을 실측하기

학습용 설계 예시입니다. 실제 실습 코드와 별도로 읽으며, 실행하려면 연결·의존성·토폴로지·Worker 구성과 장애 처리를 준비해야 합니다. 예제의 예상 결과는 실제 검증 완료 기록이 아닙니다.

Worker 수와 메시지 예약량은 다른 설정입니다. 같은 작업 부하에서 하나씩 변경해 처리량, 대기 시간, Worker별 분배를 함께 비교합니다. “더 많이”가 항상 “더 빠르게”를 뜻하지 않습니다.

## 전체 흐름

동일 부하 발행 → Worker 1개 / 3개 → Prefetch 1 / 10 / 100 → 처리 완료 시각 기록 → throughput + p50/p95 비교

## 용어

- **Concurrency**: 동시에 실행하는 업무 수입니다. Prefetch와 동일하지 않습니다.
- **Throughput**: 측정 구간에서 완료한 작업 수를 경과 시간으로 나눈 처리량입니다.
- **Latency**: 발행부터 시작·완료까지 걸린 시간입니다. 어떤 구간을 재는지 정해야 합니다.
- **p50 / p95**: 측정 분포의 중간과 느린 쪽 지점을 나타냅니다. 평균에 가려진 긴 대기를 볼 수 있습니다.

## Prefetch가 제한하는 것

일반적인 basic_consume + manual ACK에서 Prefetch는 ACK하지 않은 전달량을 제한합니다. 한 Worker가 순차 처리해도 Prefetch 10이면 실행 전 메시지가 미리 예약될 수 있습니다. 그래서 Unacked 10은 업무 10개 동시 실행이 아닙니다.

큰 Prefetch가 왕복 대기를 줄일 때도 있지만 느린 Worker에 메시지가 예약돼 분배가 나빠질 수도 있습니다. RabbitMQ의 Consumer QoS와 channel global 옵션, Celery의 별도 multiplier를 구분합니다.

## 공정한 비교 설계

예를 들어 30개 메시지에 짧은 작업 200ms와 긴 작업 2초를 섞고 입력 순서를 고정합니다. Worker 수, 작업 수, 동시성, Prefetch 중 한 항목만 바꾸며 같은 장비·Queue 종류를 유지합니다.

측정 전에 이전 run의 Ready·Unacked를 정리 확인하고 run_id를 새로 만듭니다. 최소 3회 반복해 측정 변동도 기록합니다. Worker 3개가 정확히 세 배 빠르다는 정답을 미리 정하지 않습니다.

## 시간 측정의 경계

아래 함수는 완료 시간 목록을 통계로 요약하는 순수 예시입니다. 실제 시각 수집·Worker 운영 코드는 포함하지 않습니다. 단일 시계에서 경과 시간은 monotonic 계열로 측정하고 이벤트 표시에는 UTC 시각을 사용합니다.

호스트가 다르면 UTC 차감에 시계 차이가 섞일 수 있습니다. 발행과 완료가 어느 프로세스에서 기록됐는지 함께 저장해야 수치를 해석할 수 있습니다.

## 설계 예시 · 같은 수집 기준으로 통계 계산

```python
import math

def summarize(completion_latencies, elapsed_seconds):
    if not completion_latencies or elapsed_seconds <= 0:
        raise ValueError("실제로 완료된 표본과 양의 측정 시간이 필요합니다")
    ordered = sorted(completion_latencies)
    def percentile(p):
        return ordered[max(0, math.ceil(len(ordered) * p) - 1)]
    return {
        "completed": len(ordered),
        "throughput_per_sec": len(ordered) / elapsed_seconds,
        "p50_sec": percentile(0.50),
        "p95_sec": percentile(0.95),
    }
```

- percentile은 nearest-rank 계산입니다. 표본 수가 작으면 p95가 최댓값과 가까워질 수 있어 표본 수도 함께 표시합니다.
- 누락·실패 메시지를 완료 표본에 넣어 좋은 수치를 만들지 않습니다. 성공·실패·미완료 수를 별도로 대조합니다.

## 실험과 예상 관찰

| 동작 | 예상 관찰 | 기술적 이유 |
|---|---|---|
| Worker 1 → 3, 나머지 동일 | 처리량·분배·대기 비교 | 장비 자원이나 DB 경합 때문에 선형 증가하지 않을 수 있습니다. |
| Prefetch 1 → 100 | Unacked와 Worker별 작업 수 비교 | 미리 예약한 양과 동시 실행 수를 구분합니다. |
| 긴 작업 혼합 | p95와 평균의 차이 관찰 | 늦은 작업의 영향을 평균만으로 숨기지 않습니다. |

## 주의할 오해

- 발행 개수를 throughput의 완료 개수 대신 쓰면 실패·누락을 숨깁니다.
- CPU 작업과 대기 작업은 병목이 다릅니다. sleep 실험 결과를 CPU 계산 성능으로 일반화하지 않습니다.

## 설명해 보기

- Unacked가 100인데 Worker 동시성은 1일 수 있나요?
- Worker와 Prefetch를 동시에 바꾸면 왜 원인을 판단하기 어렵나요?

## 참고 자료

- [RabbitMQ Consumer Prefetch](https://www.rabbitmq.com/docs/consumer-prefetch)

공식 문서의 기본 버전은 설치 버전과 다를 수 있습니다. 예제는 프로젝트 학습 목적의 코드이며 실제 검증 여부는 docs/verification.md를 참고하세요.
