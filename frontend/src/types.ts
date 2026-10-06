export type LabEvent = { event_id: string; message_id: string; attempt_id?: string; event_type: string; timestamp: string; worker?: string; metadata: Record<string, unknown> }
export type Pending = { message_id: string; attempt_id: string; body: string; redelivered: boolean; processed?: boolean }
export type Effect = { effect_id: string; message_id: string; attempt_id: string; timestamp: string }
export type Snapshot = { queue: { name: string; ready: number; unacked: number; consumers: number }; pending: Pending | null; consumer_active: boolean; events: LabEvent[]; total_sent: number; ack_sent: number; collected_at: string; effects?: Effect[]; effect_counts?: Record<string, number>; effects_total?: number }
