import type { Effect, LabEvent, Pending, Snapshot } from './types'
type Message = { message_id: string; body: string; redelivered: boolean }
export class DemoLab {
  private messages: Message[] = []
  private events: LabEvent[] = []
  private pending: Pending | null = null
  private active = false
  private sent = 0
  private acked = 0
  private effects: Effect[] = []
  private readonly queue: string
  private readonly requiresProcessing: boolean
  constructor(queue = 'hello', requiresProcessing = false) { this.queue = queue; this.requiresProcessing = requiresProcessing }
  private record(type: string, message: Message | Pending, attempt?: string) {
    this.events.push({ event_id: crypto.randomUUID(), message_id: message.message_id, attempt_id: attempt, event_type: type, timestamp: new Date().toISOString(), worker: type === 'PUBLISH_SENT' ? 'producer-demo' : 'consumer-demo', metadata: { body: message.body, redelivered: message.redelivered } })
  }
  private deliver() {
    if (!this.active || this.pending || !this.messages.length) return
    const message = this.messages.shift()!
    this.pending = { ...message, attempt_id: crypto.randomUUID(), processed: false }
    this.record('DELIVERED', message, this.pending.attempt_id)
  }
  publish(body: string, count: number) {
    for (let i = 0; i < count; i++) {
      const message = { message_id: crypto.randomUUID(), body: count === 1 ? body : `${body} ${i + 1}`, redelivered: false }
      this.messages.push(message); this.sent++; this.record('PUBLISH_SENT', message)
    }
    this.deliver()
  }
  start() { this.active = true; this.deliver() }
  stop() {
    if (this.pending) { this.messages.unshift({ ...this.pending, redelivered: true }); this.record('CONNECTION_CLOSED', this.pending, this.pending.attempt_id); this.pending = null }
    this.active = false
  }
  ack(attempt: string) {
    if (!this.pending || this.pending.attempt_id !== attempt) throw new Error('현재 전달과 일치하지 않는 ACK입니다.')
    if (this.requiresProcessing && !this.pending.processed) throw new Error('업무 반영을 확인한 뒤 ACK를 보내세요.')
    this.record('ACK_SENT', this.pending, attempt); this.acked++; this.pending = null; this.deliver()
  }
  process(attempt: string) {
    if (!this.pending || this.pending.attempt_id !== attempt) throw new Error('현재 전달과 일치하지 않는 처리 시도입니다.')
    if (this.pending.processed) throw new Error('이 처리 시도는 이미 업무를 반영했습니다.')
    this.pending.processed = true
    this.effects.push({ effect_id: crypto.randomUUID(), message_id: this.pending.message_id, attempt_id: attempt, timestamp: new Date().toISOString() })
    this.record('PROCESSED', this.pending, attempt)
  }
  crash() {
    const message = this.pending || { message_id: '', body: '', redelivered: false }
    this.record('WORKER_KILLED', message, this.pending?.attempt_id)
    if (this.pending) { this.messages.unshift({ ...this.pending, redelivered: true }); this.pending = null }
    this.active = false
  }
  snapshot(): Snapshot {
    const counts: Record<string, number> = {}
    for (const effect of this.effects) counts[effect.message_id] = (counts[effect.message_id] || 0) + 1
    return { queue: { name: this.queue, ready: this.messages.length, unacked: this.pending ? 1 : 0, consumers: this.active ? 1 : 0 }, pending: this.pending ? { ...this.pending } : null, consumer_active: this.active, events: [...this.events].reverse(), total_sent: this.sent, ack_sent: this.acked, collected_at: new Date().toISOString(), effects: [...this.effects].reverse(), effect_counts: counts, effects_total: this.effects.length }
  }
}

export async function request<T>(base: string, token: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${base.replace(/\/$/, '')}${path}`, { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Lab-Token': token, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(10000) })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `요청 실패 (${response.status})`)
  return data as T
}
