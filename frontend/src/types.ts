export type LabEvent = { event_id: string; message_id: string; attempt_id?: string; event_type: string; timestamp: string; worker?: string; metadata: Record<string, unknown> }
export type Pending = { message_id: string; attempt_id: string; body: string; redelivered: boolean; processed?: boolean }
export type Effect = { effect_id: string; message_id: string; attempt_id: string; timestamp: string }
export type Snapshot = { queue: { name: string; ready: number; unacked: number; consumers: number }; pending: Pending | null; consumer_active: boolean; events: LabEvent[]; total_sent: number; ack_sent: number; collected_at: string; effects?: Effect[]; effect_counts?: Record<string, number>; effects_total?: number }

export type ReliabilityEvent = { event_id: string; message_id: string; event_type: string; timestamp: string; worker: string; metadata: Record<string, unknown> }
export type ReliabilityQueueInfo = { id: string; name: string; binding: string; durable: boolean; label: string; ready: number | null }
export type ReliabilityPublishResult = { message_id: string; scenario: string; routing_key: string; mandatory: boolean; delivery_mode: number; confirmed: boolean; nacked: boolean; returned: boolean; outcome_unknown: boolean }
export type ReceivedMessage = { queue_id: string; message_id: string; body: string; routing_key: string; scenario: string; redelivered: boolean; delivery_mode: number }
export type ReliabilitySnapshot = { exchange: string | null; queues: ReliabilityQueueInfo[]; events: ReliabilityEvent[]; last_publish: ReliabilityPublishResult | null; last_received: ReceivedMessage[]; collected_at: string }
