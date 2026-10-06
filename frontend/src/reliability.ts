/** Phase 4: Browser-side demo model for publisher reliability experiments. */

import type { ReliabilitySnapshot, ReliabilityPublishResult, ReceivedMessage, ReliabilityEvent } from './types'

type Scenario = 'normal' | 'mandatory_unroutable' | 'persistent' | 'transient'

interface QueueState {
  id: string
  name: string
  binding: string
  durable: boolean
  label: string
  messages: { message_id: string; body: string; scenario: string; delivery_mode: number; routing_key: string }[]
}

export class DemoReliability {
  private exchange = 'phase4.demo'
  private queues: QueueState[] = []
  private events: ReliabilityEvent[] = []
  private lastPublish: ReliabilityPublishResult | null = null
  private lastReceived: ReceivedMessage[] = []
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
      timestamp: new Date().toISOString(), worker: 'reliability-demo', metadata,
    })
    if (this.events.length > 200) this.events = this.events.slice(-200)
  }

  setup(): void {
    this.exchange = 'phase4.demo'
    this.queues = [
      { id: 'a', name: 'phase4.demo.routed', binding: 'routed', durable: true, label: '정상 라우팅', messages: [] },
      { id: 'b', name: 'phase4.demo.persistent', binding: 'persistent', durable: true, label: '영속 메시지', messages: [] },
      { id: 'c', name: 'phase4.demo.transient', binding: 'transient', durable: false, label: '임시 Queue', messages: [] },
    ]
    this.events = []
    this.lastPublish = null
    this.lastReceived = []
    this.record('TOPOLOGY_CREATED', '', { exchange: this.exchange, exchange_type: 'direct' })
  }

  publish(body: string, scenario: Scenario): ReliabilityPublishResult {
    const message_id = this.uid()

    let routing_key: string
    let mandatory = false
    let delivery_mode: number

    switch (scenario) {
      case 'normal':
        routing_key = 'routed'; delivery_mode = 2; break
      case 'mandatory_unroutable':
        routing_key = 'unroutable'; mandatory = true; delivery_mode = 2; break
      case 'persistent':
        routing_key = 'persistent'; delivery_mode = 2; break
      case 'transient':
        routing_key = 'transient'; delivery_mode = 1; break
    }

    this.record('PUBLISH_SENT', message_id, { scenario, routing_key, mandatory, delivery_mode })

    // Simulate confirm — always ACK in demo
    const confirmed = true
    const nacked = false
    const outcome_unknown = false
    this.record('PUBLISH_CONFIRMED', message_id)

    // Simulate routing
    let returned = false
    const target = this.queues.find(q => q.binding === routing_key)
    if (target) {
      target.messages.push({ message_id, body, scenario, delivery_mode, routing_key })
    } else if (mandatory) {
      returned = true
      this.record('PUBLISH_RETURNED', message_id, { routing_key, reply_code: 312, reply_text: 'NO_ROUTE' })
    }

    this.lastPublish = {
      message_id, scenario, routing_key, mandatory, delivery_mode,
      confirmed, nacked, returned, outcome_unknown,
    }
    return this.lastPublish
  }

  receive(): ReceivedMessage[] {
    this.lastReceived = []
    for (const queue of this.queues) {
      const msg = queue.messages.shift()
      if (!msg) continue
      const item: ReceivedMessage = {
        queue_id: queue.id, message_id: msg.message_id,
        body: msg.body, routing_key: msg.routing_key,
        scenario: msg.scenario, redelivered: false,
        delivery_mode: msg.delivery_mode,
      }
      this.record('DELIVERED', msg.message_id, { queue_id: queue.id })
      this.record('ACK_SENT', msg.message_id, { queue_id: queue.id })
      this.lastReceived.push(item)
    }
    return this.lastReceived
  }

  snapshot(): ReliabilitySnapshot {
    return {
      exchange: this.exchange,
      queues: this.queues.map(q => ({ id: q.id, name: q.name, binding: q.binding, durable: q.durable, label: q.label, ready: q.messages.length })),
      events: [...this.events].reverse(),
      last_publish: this.lastPublish,
      last_received: this.lastReceived,
      collected_at: new Date().toISOString(),
    }
  }
}
