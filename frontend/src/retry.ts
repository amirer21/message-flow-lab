/** Phase 5: Browser-side demo model for retry / DLQ experiments. */

import type { RetrySnapshot, RetryEvent, RetryProcessResult, RetryScenario } from './types'

const MAX_RETRIES = 3
const RETRY_TTL_MS = 5000

interface QueueMsg {
  message_id: string
  body: string
  scenario: string
  retry_count: number
  enqueued_at: number  // timestamp for TTL simulation
}

interface QueueState {
  id: string
  name: string
  role: string
  label: string
  messages: QueueMsg[]
}

export class DemoRetry {
  private workExchange = 'phase5.demo.work'
  private retryExchange = 'phase5.demo.retry'
  private deadExchange = 'phase5.demo.dead'
  private queues: QueueState[] = []
  private events: RetryEvent[] = []
  private lastPublish: { message_id: string; scenario: string; confirmed: boolean } | null = null
  private lastProcess: RetryProcessResult | null = null
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
      timestamp: new Date().toISOString(), worker: 'retry-demo', metadata,
    })
    if (this.events.length > 200) this.events = this.events.slice(-200)
  }

  private queue(role: string): QueueState {
    return this.queues.find(q => q.role === role)!
  }

  setup(): void {
    this.queues = [
      { id: 'work', name: 'phase5.demo.work.q', role: 'work', label: '작업 Queue', messages: [] },
      { id: 'retry', name: 'phase5.demo.retry.q', role: 'retry', label: '재시도 대기 Queue', messages: [] },
      { id: 'dead', name: 'phase5.demo.dead.q', role: 'dead', label: 'Dead Letter Queue', messages: [] },
    ]
    this.events = []
    this.lastPublish = null
    this.lastProcess = null
    this.record('TOPOLOGY_CREATED', '', {
      work_exchange: this.workExchange,
      retry_exchange: this.retryExchange,
      dead_exchange: this.deadExchange,
    })
  }

  publish(body: string, scenario: RetryScenario): void {
    const message_id = this.uid()
    this.record('PUBLISH_SENT', message_id, { scenario })
    this.queue('work').messages.push({
      message_id, body, scenario, retry_count: 0, enqueued_at: Date.now(),
    })
    this.record('PUBLISH_CONFIRMED', message_id)
    this.lastPublish = { message_id, scenario, confirmed: true }
  }

  process(): void {
    const workQ = this.queue('work')
    const msg = workQ.messages.shift()
    if (!msg) return

    const { message_id, scenario, retry_count } = msg
    this.record('PROCESSING_STARTED', message_id, { retry_count, scenario })

    const outcome = this.decide(scenario, retry_count)

    if (outcome === 'success') {
      this.record('PROCESSING_SUCCEEDED', message_id, { retry_count })
      this.record('ACK_SENT', message_id)
    } else if (outcome === 'retry') {
      const failure_type = 'transient'
      this.record('PROCESSING_FAILED', message_id, { retry_count, failure_type })
      this.queue('retry').messages.push({
        ...msg, retry_count: retry_count + 1, enqueued_at: Date.now(),
      })
      this.record('RETRY_SCHEDULED', message_id, { retry_count: retry_count + 1, ttl_ms: RETRY_TTL_MS })
      this.record('ACK_SENT', message_id)
    } else {
      const failure_type = scenario === 'permanent' ? 'permanent' : 'retry_exceeded'
      this.record('PROCESSING_FAILED', message_id, { retry_count, failure_type })
      this.queue('dead').messages.push(msg)
      this.record('DLQ_STORED', message_id, { retry_count, failure_type })
      this.record('ACK_SENT', message_id)
    }

    this.lastProcess = { message_id, scenario, retry_count, outcome, confirmed: true }
  }

  /** Call periodically (e.g. every 2s) to move expired retry messages back to work queue. */
  tick(): void {
    const retryQ = this.queue('retry')
    const workQ = this.queue('work')
    const now = Date.now()
    const expired: QueueMsg[] = []
    const remaining: QueueMsg[] = []
    for (const msg of retryQ.messages) {
      if (now - msg.enqueued_at >= RETRY_TTL_MS) {
        expired.push(msg)
      } else {
        remaining.push(msg)
      }
    }
    retryQ.messages = remaining
    for (const msg of expired) {
      workQ.messages.push({ ...msg, enqueued_at: now })
      this.record('RETRY_RETURNED', msg.message_id, { retry_count: msg.retry_count })
    }
  }

  snapshot(): RetrySnapshot {
    return {
      work_exchange: this.workExchange,
      queues: this.queues.map(q => ({
        id: q.id, name: q.name, role: q.role, label: q.label, ready: q.messages.length,
      })),
      events: [...this.events].reverse(),
      last_publish: this.lastPublish,
      last_process: this.lastProcess,
      collected_at: new Date().toISOString(),
    }
  }

  private decide(scenario: string, retryCount: number): 'success' | 'retry' | 'dlq' {
    if (scenario === 'transient_2x') {
      return retryCount >= 2 ? 'success' : 'retry'
    } else if (scenario === 'permanent') {
      return 'dlq'
    } else if (scenario === 'retry_exceed') {
      return retryCount >= MAX_RETRIES ? 'dlq' : 'retry'
    }
    return 'dlq'
  }
}
