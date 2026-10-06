import test from 'node:test'
import assert from 'node:assert/strict'
import { DemoLab } from '../src/lab.ts'

test('three messages remain queued without a consumer and ACK drains one at a time', () => {
  const lab = new DemoLab()
  lab.publish('hello', 3)
  assert.equal(lab.snapshot().queue.ready, 3)
  assert.equal(lab.snapshot().queue.unacked, 0)
  lab.start()
  assert.equal(lab.snapshot().queue.ready, 2)
  assert.equal(lab.snapshot().queue.unacked, 1)
  for (let i = 0; i < 3; i++) lab.ack(lab.snapshot().pending.attempt_id)
  assert.equal(lab.snapshot().queue.ready, 0)
  assert.equal(lab.snapshot().queue.unacked, 0)
  assert.equal(lab.snapshot().ack_sent, 3)
})

test('stale ACK cannot acknowledge the next message', () => {
  const lab = new DemoLab(); lab.publish('hello', 3); lab.start()
  const attempt = lab.snapshot().pending.attempt_id
  lab.ack(attempt)
  assert.throws(() => lab.ack(attempt))
  assert.equal(lab.snapshot().queue.unacked, 1)
  assert.equal(lab.snapshot().ack_sent, 1)
})

test('closing without ACK requeues the same message with a new attempt', () => {
  const lab = new DemoLab(); lab.publish('hello', 1); lab.start()
  const first = lab.snapshot().pending
  lab.stop()
  assert.equal(lab.snapshot().queue.ready, 1)
  assert.equal(lab.snapshot().queue.unacked, 0)
  lab.start()
  const second = lab.snapshot().pending
  assert.equal(first.message_id, second.message_id)
  assert.notEqual(first.attempt_id, second.attempt_id)
  assert.equal(second.redelivered, true)
})

test('Phase 2 reproduces a duplicate business effect after crash before ACK', () => {
  const lab = new DemoLab('phase2.ack_lab', true)
  lab.publish('business', 1); lab.start()
  const first = lab.snapshot().pending
  lab.process(first.attempt_id); lab.crash(); lab.start()
  const second = lab.snapshot().pending
  assert.equal(first.message_id, second.message_id)
  assert.notEqual(first.attempt_id, second.attempt_id)
  assert.equal(second.redelivered, true)
  lab.process(second.attempt_id); lab.ack(second.attempt_id)
  assert.equal(lab.snapshot().effect_counts[first.message_id], 2)
  assert.equal(lab.snapshot().queue.unacked, 0)
})

test('Phase 2 acknowledged message is not redelivered after crash', () => {
  const lab = new DemoLab('phase2.ack_lab', true)
  lab.publish('business', 1); lab.start()
  const pending = lab.snapshot().pending
  assert.throws(() => lab.ack(pending.attempt_id))
  lab.process(pending.attempt_id); lab.ack(pending.attempt_id)
  lab.crash(); lab.start()
  assert.equal(lab.snapshot().pending, null)
  assert.equal(lab.snapshot().effect_counts[pending.message_id], 1)
  assert.equal(lab.snapshot().queue.ready, 0)
})
