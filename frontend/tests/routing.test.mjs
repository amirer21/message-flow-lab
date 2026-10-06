import test from 'node:test'
import assert from 'node:assert/strict'
import { RoutingDemo, defaults, topicMatches } from '../src/routing.ts'

test('direct can copy to two queues with the same binding',()=>{
  const lab=new RoutingDemo();lab.publish('hello','error',['b']);lab.receive()
  const copies=lab.snapshot().last_received
  assert.deepEqual(copies.map(c=>c.queue_id),['a','c'])
  assert.equal(new Set(copies.map(c=>c.message_id)).size,1)
  assert.deepEqual(copies[0].prediction,['b'])
})
test('fanout ignores routing key and preserves the same message ID',()=>{
  const lab=new RoutingDemo();lab.setup('fanout',defaults.fanout);lab.publish('hello','anything',[]);lab.receive()
  assert.deepEqual(lab.snapshot().last_received.map(c=>c.queue_id),['a','b','c'])
  assert.equal(new Set(lab.snapshot().last_received.map(c=>c.message_id)).size,1)
})
test('topic supports exactly one word and zero or more words',()=>{
  assert.equal(topicMatches('order.*','order.created'),true)
  assert.equal(topicMatches('order.*','order.created.eu'),false)
  assert.equal(topicMatches('order.#','order'),true)
  assert.equal(topicMatches('a.#.b','a.x.y.b'),true)
  assert.equal(topicMatches('#',''),true)
  const lab=new RoutingDemo();lab.setup('topic',defaults.topic);lab.publish('hello','payment.completed',[]);lab.receive()
  assert.deepEqual(lab.snapshot().last_received.map(c=>c.queue_id),['b','c'])
})
test('binding changes affect future publications only',()=>{
  const lab=new RoutingDemo();lab.publish('old','error',[]);lab.bind(['new','new','new']);lab.receive()
  assert.deepEqual(lab.snapshot().last_received.map(c=>c.body),['old','old'])
  lab.publish('new','error',[]);lab.receive()
  assert.equal(lab.snapshot().last_received.length,0)
})
test('receive consumes at most one per queue and new experiment resets only its state',()=>{
  const lab=new RoutingDemo();lab.publish('first','error',[]);lab.publish('second','error',[]);lab.receive()
  assert.deepEqual(lab.snapshot().queues.map(q=>q.ready),[1,0,1])
  lab.setup('topic',defaults.topic)
  assert.deepEqual(lab.snapshot().queues.map(q=>q.ready),[0,0,0])
  assert.equal(lab.snapshot().last_publish,null)
})
