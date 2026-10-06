"""Actual Phase 3 routing. Resets ONLY the current temporary Phase 3 topology."""
import os
import httpx

client=httpx.Client(base_url='http://localhost:8000',headers={'X-Lab-Token':os.environ['LAB_TOKEN']},timeout=15)
def command(action,**body):
    response=client.post('/routing/'+action,json=body)
    response.raise_for_status()
    return response.json()

def expect(key,queues):
    published=command('messages',body='phase3-smoke-'+key,routing_key=key,prediction=queues)
    message_id=published['last_publish']['message_id']
    state=command('receive')
    copies=state['last_received']
    assert [copy['queue_id'] for copy in copies]==queues,(key,copies)
    assert all(copy['message_id']==message_id for copy in copies)
    assert all(copy['prediction']==queues for copy in copies)
    assert all(queue['ready']==0 for queue in state['queues'])
    print('PASS',state['exchange_type'],repr(key),'→',queues,'same Message ID')

command('setup',exchange_type='direct',bindings=['error','info','error'])
expect('error',['a','c']);expect('info',['b']);expect('unmatched',[])
command('setup',exchange_type='fanout',bindings=['','',''])
expect('anything',['a','b','c'])
command('setup',exchange_type='topic',bindings=['order.*','*.completed','#'])
expect('order.created',['a','c']);expect('payment.completed',['b','c']);expect('order.created.eu',['c'])
command('bindings',exchange_type='topic',bindings=['order.*','*.completed','order.#'])
expect('order',['c'])
old=command('messages',body='before-binding-change',routing_key='order.created')['last_publish']['message_id']
command('bindings',exchange_type='topic',bindings=['never','never','never'])
state=command('receive')
assert [copy['queue_id'] for copy in state['last_received']]==['a','c']
assert all(copy['message_id']==old for copy in state['last_received'])
expect('order.created',[])
response=client.post('/routing/bindings',json={'exchange_type':'direct','bindings':['a','b','c']})
assert response.status_code==409
print('PASS binding changes preserve old queue contents; incompatible kind rejected')
command('setup',exchange_type='direct',bindings=['error','info','error'])
client.close()
