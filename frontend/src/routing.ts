import type { LabEvent } from './types'
export type ExchangeKind = 'direct' | 'fanout' | 'topic'
export type ReceivedCopy = { queue_id: string; message_id: string; body: string; routing_key: string; prediction: string[]; redelivered: boolean }
export type RoutingSnapshot = { exchange_type: ExchangeKind; exchange: string; queues: { id: string; name: string; binding: string; ready: number }[]; events: LabEvent[]; last_received: ReceivedCopy[]; last_publish: { message_id: string; routing_key: string; prediction: string[]; publisher_confirmed: boolean } | null; collected_at: string }
export const defaults: Record<ExchangeKind,string[]> = { direct: ['error','info','error'], fanout: ['','',''], topic: ['order.*','*.completed','#'] }
export function topicMatches(binding: string, key: string): boolean {
  const pattern = binding ? binding.split('.') : [], words = key ? key.split('.') : []
  const cache = new Map<string, boolean>()
  function match(i: number,j: number): boolean {
    const state = `${i}:${j}`; if (cache.has(state)) return cache.get(state)!
    const result = i === pattern.length ? j === words.length : pattern[i] === '#' ? match(i+1,j) || (j < words.length && match(i,j+1)) : j < words.length && (pattern[i] === '*' || pattern[i] === words[j]) && match(i+1,j+1)
    cache.set(state,result); return result
  }
  return match(0,0)
}
export class RoutingDemo {
  private kind: ExchangeKind = 'direct'
  private bindings = [...defaults.direct]
  private messages: ReceivedCopy[][] = [[],[],[]]
  private events: LabEvent[] = []
  private received: ReceivedCopy[] = []
  private lastPublish: RoutingSnapshot['last_publish'] = null
  private record(kind: string, message_id = '', metadata: Record<string, unknown> = {}) { this.events.push({ event_id: crypto.randomUUID(), message_id, event_type: kind, timestamp: new Date().toISOString(), worker: 'routing-demo', metadata }) }
  setup(kind: ExchangeKind, bindings: string[]) { this.kind=kind; this.bindings=[...bindings]; this.messages=[[],[],[]]; this.events=[]; this.received=[]; this.lastPublish=null; this.record('TOPOLOGY_CREATED','',{ exchange_type:kind }) }
  bind(bindings: string[]) { this.bindings=[...bindings]; this.record('BINDINGS_CHANGED','',{bindings:[...bindings]}) }
  publish(body: string,key: string,prediction: string[]) {
    const id=crypto.randomUUID(); this.lastPublish={ message_id:id,routing_key:key,prediction:[...prediction],publisher_confirmed:false }; this.record('PUBLISH_SENT',id,{routing_key:key,prediction:[...prediction]})
    this.bindings.forEach((binding,index) => { if(this.kind==='fanout' || (this.kind==='direct' ? binding===key : topicMatches(binding,key))) this.messages[index]!.push({queue_id:'abc'[index]!,message_id:id,body,routing_key:key,prediction:[...prediction],redelivered:false}) })
  }
  receive() { this.received=[]; this.messages.forEach(messages => { const copy=messages.shift(); if(copy) {this.received.push(copy);this.record('DELIVERED',copy.message_id,{...copy});this.record('ACK_SENT',copy.message_id,{queue_id:copy.queue_id})} }) }
  snapshot(): RoutingSnapshot { return { exchange_type:this.kind, exchange:`phase3.demo.${this.kind}`, queues:this.bindings.map((binding,i)=>({id:'abc'[i]!,name:`phase3.demo.${'abc'[i]}`,binding,ready:this.messages[i]!.length})),events:[...this.events].reverse(),last_received:this.received.map(copy=>({...copy})),last_publish:this.lastPublish,collected_at:new Date().toISOString() } }
}
