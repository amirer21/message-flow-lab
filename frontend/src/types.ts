export type LabEvent = { event_id: string; message_id: string; attempt_id?: string; event_type: string; timestamp: string; worker?: string; metadata: Record<string, unknown> }
export type Pending = { message_id: string; attempt_id: string; body: string; redelivered: boolean; processed?: boolean }
export type Effect = { effect_id: string; message_id: string; attempt_id: string; timestamp: string }
export type Snapshot = { queue: { name: string; ready: number; unacked: number; consumers: number }; pending: Pending | null; consumer_active: boolean; events: LabEvent[]; total_sent: number; ack_sent: number; collected_at: string; effects?: Effect[]; effect_counts?: Record<string, number>; effects_total?: number }

export type ReliabilityEvent = { event_id: string; message_id: string; event_type: string; timestamp: string; worker: string; metadata: Record<string, unknown> }
export type ReliabilityQueueInfo = { id: string; name: string; binding: string; durable: boolean; label: string; ready: number | null }
export type ReliabilityPublishResult = { message_id: string; scenario: string; routing_key: string; mandatory: boolean; delivery_mode: number; confirmed: boolean; nacked: boolean; returned: boolean; outcome_unknown: boolean }
export type ReceivedMessage = { queue_id: string; message_id: string; body: string; routing_key: string; scenario: string; redelivered: boolean; delivery_mode: number }
export type ReliabilitySnapshot = { exchange: string | null; queues: ReliabilityQueueInfo[]; events: ReliabilityEvent[]; last_publish: ReliabilityPublishResult | null; last_received: ReceivedMessage[]; collected_at: string }

export type RetryScenario = 'transient_2x' | 'permanent' | 'retry_exceed'
export type RetryEvent = { event_id: string; message_id: string; event_type: string; timestamp: string; worker: string; metadata: Record<string, unknown> }
export type RetryQueueInfo = { id: string; name: string; role: string; label: string; ready: number | null }
export type RetryProcessResult = { message_id: string; scenario: string; retry_count: number; outcome: 'success' | 'retry' | 'dlq'; confirmed: boolean }
export type RetrySnapshot = { work_exchange: string | null; queues: RetryQueueInfo[]; events: RetryEvent[]; last_publish: { message_id: string; scenario: string; confirmed: boolean } | null; last_process: RetryProcessResult | null; collected_at: string }

export type IdempotencyScenario = 'normal' | 'duplicate' | 'crash_after_commit'
export type IdempotencyEvent = { event_id: string; message_id: string; event_type: string; timestamp: string; worker: string; metadata: Record<string, unknown> }
export type IdempotencyQueueInfo = { id: string; name: string; role: string; label: string; ready: number | null }
export type BusinessEffect = { id: number; consumer_scope: string; idempotency_key: string; amount: number; created_at: string }
export type IdempotencySnapshot = {
  work_exchange: string | null
  queues: IdempotencyQueueInfo[]
  events: IdempotencyEvent[]
  effects: BusinessEffect[]
  processed_count: number
  last_publish: { message_id: string; idempotency_key: string; confirmed: boolean } | null
  last_process: { message_id: string; idempotency_key: string; outcome: 'applied' | 'skipped'; was_duplicate: boolean } | null
  collected_at: string
}
