/** Phase 6: Browser-side demo model for idempotency experiments. */

import type { IdempotencySnapshot, IdempotencyEvent, BusinessEffect, IdempotencyScenario } from './types'

interface QueueMsg {
  message_id: string
  idempotency_key: string
  amount: number
  enqueued_at: number
}

interface QueueState {
  id: string
  name: string
  role: string
  label: string
  messages: QueueMsg[]
}

export class DemoIdempotency {
  private workExchange = 'phase6.demo.work'
  private queues: QueueState[] = []
  private events: IdempotencyEvent[] = []
  private processedCommands = new Set<string>()
  private effects: BusinessEffect[] = []
  private effectCounter = 0
  private lastPublish: { message_id: string; idempotency_key: string; confirmed: boolean } | null = null
  private lastProcess: { message_id: string; idempotency_key: string; outcome: 'applied' | 'skipped'; was_duplicate: boolean } | null = null
  private simulateCrash = false
  private counter = 0

  constructor() {
    this.setup()
  }

  private uid(): string {
    return `demo-${Date.now()}-${++this.counter}`
  }

  private record(kind: string, message_id = '', metadata: Record<string, unknown> = {}): void {
    this.events.push({
      event_id: this.uid(), message_id, event_type: kind,
      timestamp: new Date().toISOString(), worker: 'idempotency-demo', metadata,
    })
    if (this.events.length > 200) this.events = this.events.slice(-200)
  }

  setup(): void {
    this.queues = [
      { id: 'work', name: 'phase6.demo.work.q', role: 'work', label: '작업 Queue', messages: [] },
    ]
    this.events = []
    this.processedCommands.clear()
    this.effects = []
    this.effectCounter = 0
    this.lastPublish = null
    this.lastProcess = null
    this.simulateCrash = false
    this.record('TOPOLOGY_CREATED', '', { work_exchange: this.workExchange })
  }

  publish(idempotencyKey: string, amount: number): void {
    const message_id = this.uid()
    this.record('PUBLISH_SENT', message_id, { idempotency_key: idempotencyKey, amount })
    this.queues[0].messages.push({
      message_id, idempotency_key: idempotencyKey, amount, enqueued_at: Date.now(),
    })
    this.record('PUBLISH_CONFIRMED', message_id)
    this.lastPublish = { message_id, idempotency_key: idempotencyKey, confirmed: true }
  }

  armCrash(): void {
    this.simulateCrash = true
    this.record('CRASH_ARMED', '', { simulate: true })
  }

  process(): void {
    const workQ = this.queues[0]
    const msg = workQ.messages.shift()
    if (!msg) return

    const { message_id, idempotency_key, amount } = msg
    this.record('PROCESSING_STARTED', message_id, { idempotency_key, amount })

    const key = `${idempotency_key}`
    const wasDuplicate = this.processedCommands.has(key)

    if (!wasDuplicate) {
      this.processedCommands.add(key)
      this.effects.push({
        id: ++this.effectCounter,
        consumer_scope: 'phase6-demo',
        idempotency_key,
        amount,
        created_at: new Date().toISOString(),
      })
      this.record('EFFECT_APPLIED', message_id, { idempotency_key, amount })
    } else {
      this.record('DUPLICATE_SKIPPED', message_id, { idempotency_key })
    }

    const outcome: 'applied' | 'skipped' = wasDuplicate ? 'skipped' : 'applied'

    if (this.simulateCrash) {
      this.simulateCrash = false
      this.record('CRASH_BEFORE_ACK', message_id, { idempotency_key, outcome })
      // Re-enqueue the message to simulate redelivery
      workQ.messages.unshift(msg)
      this.lastProcess = { message_id, idempotency_key, outcome, was_duplicate: wasDuplicate }
      return
    }

    this.record('ACK_SENT', message_id)
    this.lastProcess = { message_id, idempotency_key, outcome, was_duplicate: wasDuplicate }
  }

  snapshot(): IdempotencySnapshot {
    return {
      work_exchange: this.workExchange,
      queues: this.queues.map(q => ({
        id: q.id, name: q.name, role: q.role, label: q.label, ready: q.messages.length,
      })),
      events: [...this.events].reverse(),
      effects: [...this.effects].reverse(),
      processed_count: this.processedCommands.size,
      last_publish: this.lastPublish,
      last_process: this.lastProcess,
      collected_at: new Date().toISOString(),
    }
  }
}
