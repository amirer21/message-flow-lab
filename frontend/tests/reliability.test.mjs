import { describe, it } from 'node:test'
import assert from 'node:assert/strict'
import { DemoReliability } from '../src/reliability.ts'

describe('DemoReliability', () => {
  it('normal publish is confirmed and not returned', () => {
    const lab = new DemoReliability()
    const result = lab.publish('hello', 'normal')
    assert.equal(result.confirmed, true)
    assert.equal(result.returned, false)
    assert.equal(result.nacked, false)
    assert.equal(result.outcome_unknown, false)
    assert.equal(result.routing_key, 'routed')
    assert.equal(result.delivery_mode, 2)
    const snap = lab.snapshot()
    assert.equal(snap.queues.find(q => q.id === 'a').ready, 1)
    assert.equal(snap.queues.find(q => q.id === 'b').ready, 0)
    assert.equal(snap.queues.find(q => q.id === 'c').ready, 0)
  })

  it('mandatory_unroutable is confirmed AND returned', () => {
    const lab = new DemoReliability()
    const result = lab.publish('hello', 'mandatory_unroutable')
    assert.equal(result.confirmed, true, 'unroutable message should still be confirmed')
    assert.equal(result.returned, true, 'mandatory unroutable should be returned')
    assert.equal(result.mandatory, true)
    // No queue should have the message
    const snap = lab.snapshot()
    for (const q of snap.queues) {
      assert.equal(q.ready, 0, `Queue ${q.id} should be empty`)
    }
  })

  it('confirm and return are NOT merged into a single boolean', () => {
    const lab = new DemoReliability()
    const normal = lab.publish('a', 'normal')
    // Normal: confirmed=true, returned=false — they are separate
    assert.equal(normal.confirmed, true)
    assert.equal(normal.returned, false)
    const returned = lab.publish('b', 'mandatory_unroutable')
    // Both true simultaneously
    assert.equal(returned.confirmed, true)
    assert.equal(returned.returned, true)
    assert.notEqual(returned.confirmed, !returned.returned,
      'a returned message can also be confirmed; the fields are not opposites')
  })

  it('persistent uses delivery_mode 2, transient uses 1', () => {
    const lab = new DemoReliability()
    const persistent = lab.publish('p', 'persistent')
    assert.equal(persistent.delivery_mode, 2)
    assert.equal(persistent.routing_key, 'persistent')

    const transient = lab.publish('t', 'transient')
    assert.equal(transient.delivery_mode, 1)
    assert.equal(transient.routing_key, 'transient')
  })

  it('receive returns actual queue copies', () => {
    const lab = new DemoReliability()
    lab.publish('msg-a', 'normal')
    lab.publish('msg-b', 'persistent')
    const received = lab.receive()
    assert.equal(received.length, 2)
    assert.equal(received[0].queue_id, 'a')
    assert.equal(received[1].queue_id, 'b')
    // After receive, queues are empty
    const snap = lab.snapshot()
    for (const q of snap.queues) {
      assert.equal(q.ready, 0)
    }
  })

  it('setup resets all state', () => {
    const lab = new DemoReliability()
    lab.publish('x', 'normal')
    lab.setup()
    const snap = lab.snapshot()
    assert.equal(snap.last_publish, null)
    assert.equal(snap.last_received.length, 0)
    for (const q of snap.queues) {
      assert.equal(q.ready, 0)
    }
  })

  it('events record PUBLISH_SENT, PUBLISH_CONFIRMED, and PUBLISH_RETURNED separately', () => {
    const lab = new DemoReliability()
    lab.publish('x', 'mandatory_unroutable')
    const snap = lab.snapshot()
    const types = snap.events.map(e => e.event_type)
    assert.ok(types.includes('PUBLISH_SENT'))
    assert.ok(types.includes('PUBLISH_CONFIRMED'))
    assert.ok(types.includes('PUBLISH_RETURNED'))
  })
})
