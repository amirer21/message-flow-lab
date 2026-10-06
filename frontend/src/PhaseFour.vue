<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Activity, AlertTriangle, ArrowRight, Check, CheckCircle2, ChevronRight, CircleHelp, Download, HardDrive, Layers3, Play, Send, Shield, ShieldAlert, ShieldCheck, ShieldX } from 'lucide-vue-next'
import { request } from './lab'
import { DemoReliability } from './reliability'
import type { ReliabilitySnapshot } from './types'

type Scenario = 'normal' | 'mandatory_unroutable' | 'persistent' | 'transient'

const props = defineProps<{ active: boolean; mode: 'demo' | 'live'; editable: boolean; gateway: string; token: string; checks: boolean[] }>()
const emit = defineEmits<{ disconnect: [message: string]; check: [index: number]; notes: []; guide: [] }>()

const demo = new DemoReliability()
const data = ref<ReliabilitySnapshot>(demo.snapshot())
const live = ref<ReliabilitySnapshot | null>(null)
const scenario = ref<Scenario>('normal')
const body = ref('reliability-test')
const busy = ref(false)
const failure = ref('')
let generation = 0

const scenarios: { value: Scenario; label: string; desc: string }[] = [
  { value: 'normal', label: '정상 Confirm', desc: 'durable Queue에 라우팅 · Confirm ACK 수신' },
  { value: 'mandatory_unroutable', label: 'Mandatory Return', desc: 'binding 없는 key + mandatory → Confirm + Return' },
  { value: 'persistent', label: '영속 메시지', desc: 'delivery_mode=2 + durable Queue · 재시작 잔존' },
  { value: 'transient', label: '임시 메시지', desc: 'delivery_mode=1 + auto_delete Queue · 재시작 소멸' },
]

const criteria = [
  'Broker Confirm(수락)과 Consumer 처리 완료가 다름을 설명한다.',
  'mandatory Return과 Confirm ACK가 독립적인 사실임을 확인했다.',
  'Confirm 미확인 상태의 불확실성을 설명한다.',
  'durable+persistent와 임시 Queue의 재시작 차이를 확인했다.',
]

const eventLabels: Record<string, string> = {
  TOPOLOGY_CREATED: '새 실험 시작',
  PUBLISH_SENT: '발행 요청 전송',
  PUBLISH_CONFIRMED: 'Broker Confirm ACK',
  PUBLISH_NACKED: 'Broker Confirm NACK',
  PUBLISH_RETURNED: 'Mandatory Return',
  PUBLISH_OUTCOME_UNKNOWN: '결과 불명',
  DELIVERED: 'Queue에서 수신',
  ACK_SENT: 'ACK 전송',
}

const short = (id: string) => id.slice(0, 8)
const time = (t: string) => new Date(t).toLocaleTimeString('ko-KR', { hour12: false })

const confirmStatus = computed(() => {
  const pub = data.value.last_publish
  if (!pub) return null
  if (pub.outcome_unknown) return { icon: 'unknown', label: '결과 불명', desc: '연결 실패로 Broker 수락 여부를 확인하지 못했습니다.', color: 'amber' }
  if (pub.nacked) return { icon: 'nack', label: 'NACK', desc: 'Broker가 메시지를 거부했습니다.', color: 'red' }
  if (pub.confirmed) return { icon: 'ack', label: 'Confirm ACK', desc: 'Broker가 메시지를 수락했습니다. Consumer 처리 완료를 뜻하지 않습니다.', color: 'green' }
  return null
})

const returnStatus = computed(() => {
  const pub = data.value.last_publish
  if (!pub) return null
  if (pub.returned) return { label: 'Return 수신', desc: '메시지가 어떤 Queue에도 전달되지 않았습니다.', color: 'amber' }
  if (pub.mandatory) return { label: 'Return 없음', desc: '정상 라우팅되어 Return이 발생하지 않았습니다.', color: 'green' }
  return { label: 'mandatory 없음', desc: 'mandatory 플래그 없이 발행했습니다. Return이 발생하지 않습니다.', color: 'muted' }
})

async function read(syncForm = false) {
  if (!props.active || props.mode !== 'live' || !props.editable || busy.value) return
  const current = generation; busy.value = true
  try {
    const next = await request<ReliabilitySnapshot>(props.gateway, props.token, '/reliability/snapshot')
    if (current === generation) { live.value = next; data.value = next; failure.value = '' }
  } catch (e) {
    if (current === generation) { failure.value = '발행 신뢰성 실습 연결이 끊겼습니다.'; emit('disconnect', `${failure.value} ${e instanceof Error ? e.message : ''}`) }
  } finally { busy.value = false }
}

watch(() => [props.mode, props.active, props.editable, props.gateway, props.token], () => {
  generation++
  if (props.mode === 'demo') { data.value = demo.snapshot() }
  else if (live.value) { data.value = live.value }
  void read(true)
}, { immediate: true })

const timer = setInterval(() => void read(), 2000)
onBeforeUnmount(() => { clearInterval(timer); generation++ })

async function run(action: 'setup' | 'publish' | 'receive') {
  if (busy.value || !props.editable) return
  if (action === 'publish' && (!body.value.trim() || body.value.length > 4096)) { failure.value = '메시지는 1~4,096자로 입력하세요.'; return }
  const current = generation; busy.value = true; failure.value = ''
  try {
    if (props.mode === 'demo') {
      if (action === 'setup') demo.setup()
      if (action === 'publish') demo.publish(body.value, scenario.value)
      if (action === 'receive') demo.receive()
      data.value = demo.snapshot()
    } else {
      const payload = action === 'publish' ? { body: body.value, scenario: scenario.value } : {}
      const next = await request<ReliabilitySnapshot>(props.gateway, props.token, `/reliability/${action}`, payload)
      if (current === generation) { live.value = next; data.value = next }
    }
  } catch (e) { if (current === generation) failure.value = `${e instanceof Error ? e.message : '요청 실패'} 발행을 자동 재시도하지 않습니다.` }
  finally { busy.value = false }
}
</script>

<template>
  <div class="phase-four">
    <div class="question-banner"><span class="question-icon"><CircleHelp :size="22" /></span><div><span>이번 실험의 질문</span><strong>Producer는 무엇을 근거로 성공을 판단할까?</strong></div><button class="text-button" @click="emit('guide')">개념 살펴보기 <ChevronRight :size="15" /></button></div>
    <div v-if="failure" class="alert error" role="alert">{{ failure }}</div>

    <!-- Scenario Selection -->
    <div class="exchange-choices">
      <button v-for="s in scenarios" :key="s.value" class="scenario-card" :class="{ chosen: scenario === s.value }" @click="scenario = s.value">
        <span class="scenario-number">
          <ShieldCheck v-if="s.value === 'normal'" :size="16" />
          <ShieldAlert v-else-if="s.value === 'mandatory_unroutable'" :size="16" />
          <HardDrive v-else-if="s.value === 'persistent'" :size="16" />
          <AlertTriangle v-else :size="16" />
        </span>
        <strong>{{ s.label }}</strong>
        <span>{{ s.desc }}</span>
      </button>
    </div>

    <!-- Topology Setup -->
    <section class="panel topology-controls">
      <div>
        <h2><Layers3 :size="17" /> 실험 환경</h2>
        <p>Phase 4 전용 Exchange (direct, durable) · Confirm 모드 활성화 · Queue 3개</p>
      </div>
      <button class="button secondary" :disabled="busy || !editable" @click="run('setup')"><Play :size="15" /> 새 실험 시작</button>
      <p class="hint">새 실험은 이전 Phase 4 토폴로지를 삭제하고 다시 만듭니다. 다른 Phase에는 영향을 주지 않습니다.</p>
    </section>

    <!-- Publish + Results -->
    <div class="routing-workspace">
      <section class="panel producer-panel">
        <div class="panel-heading"><h2><Send :size="17" /> 메시지 발행</h2><span class="small-badge">CONFIRM MODE</span></div>
        <label for="reliability-body">Message payload</label>
        <div class="editor"><textarea id="reliability-body" v-model="body" rows="2" maxlength="4096" spellcheck="false"></textarea></div>
        <p class="hint">시나리오: <strong>{{ scenarios.find(s => s.value === scenario)?.label }}</strong></p>
        <button class="button primary" :disabled="busy || !editable" @click="run('publish')"><Send :size="15" /> 발행하고 Confirm 관찰</button>
        <p class="hint">발행 후 Broker Confirm과 Return을 별도로 확인합니다. HTTP 요청이 실패하면 이미 발행됐을 수 있으므로 Queue와 이력을 먼저 확인하세요.</p>

        <!-- Confirm/Return result -->
        <div v-if="data.last_publish" class="confirm-result">
          <h3>발행 결과 상세</h3>
          <div class="result-grid">
            <div class="result-cell" :class="confirmStatus?.color">
              <ShieldCheck v-if="confirmStatus?.icon === 'ack'" :size="20" />
              <ShieldX v-else-if="confirmStatus?.icon === 'nack'" :size="20" />
              <ShieldAlert v-else :size="20" />
              <div>
                <strong>Broker Confirm: {{ confirmStatus?.label }}</strong>
                <span>{{ confirmStatus?.desc }}</span>
              </div>
            </div>
            <div class="result-cell" :class="returnStatus?.color">
              <AlertTriangle v-if="data.last_publish.returned" :size="20" />
              <CheckCircle2 v-else :size="20" />
              <div>
                <strong>{{ returnStatus?.label }}</strong>
                <span>{{ returnStatus?.desc }}</span>
              </div>
            </div>
          </div>
          <div class="publish-detail">
            <span>Message ID: <code>{{ short(data.last_publish.message_id) }}</code></span>
            <span>Routing Key: <code>{{ data.last_publish.routing_key }}</code></span>
            <span>delivery_mode: <code>{{ data.last_publish.delivery_mode }}</code></span>
            <span>mandatory: <code>{{ data.last_publish.mandatory }}</code></span>
          </div>
        </div>
      </section>

      <!-- Queues -->
      <section class="panel route-panel">
        <div class="panel-heading"><h2><Layers3 :size="17" /> Queue 상태</h2><code class="subtle">DIRECT · CONFIRM</code></div>
        <div class="exchange-strip"><Shield :size="23" /><span>Exchange<strong>{{ data.exchange || '초기화 대기' }}</strong></span></div>
        <div class="routing-queue-grid">
          <div v-for="queue in data.queues" :key="queue.id" class="routing-queue">
            <div class="queue-card-heading">
              <strong>Queue {{ queue.id.toUpperCase() }}: {{ queue.label }}</strong>
              <span><b>{{ queue.ready ?? '?' }}</b> Ready</span>
            </div>
            <div class="queue-props">
              <span>binding: <code>{{ queue.binding }}</code></span>
              <span>durable: <code>{{ queue.durable }}</code></span>
            </div>
            <div class="received-copies">
              <template v-for="copy in data.last_received.filter(item => item.queue_id === queue.id)" :key="copy.message_id">
                <span class="copy-label"><Download :size="13" /> {{ mode === 'demo' ? '예시 수신' : '실제 수신' }}</span>
                <code>{{ short(copy.message_id) }}</code>
                <pre>{{ copy.body }}</pre>
                <span>delivery_mode: {{ copy.delivery_mode }} · scenario: {{ copy.scenario }}</span>
              </template>
              <span v-if="!data.last_received.some(item => item.queue_id === queue.id)" class="empty-copy">수신 대기</span>
            </div>
          </div>
        </div>
        <div class="button-row">
          <button class="button primary" :disabled="busy || !editable" @click="run('receive')"><Download :size="15" /> Queue별 한 개 수신 · ACK</button>
        </div>
        <p class="hint">수신 버튼은 각 Queue에서 최대 한 개씩 소비하고 ACK합니다. 지표 조회(Ready)는 소비하지 않습니다.</p>
      </section>
    </div>

    <!-- Concept callout -->
    <div class="concept-callout" style="margin-top:16px">
      <CircleHelp :size="20" />
      <div>
        <strong>Confirm ≠ 처리 완료</strong>
        <p>Broker Confirm ACK는 메시지를 Queue에 보관했다는 뜻입니다. Consumer가 업무를 처리하고 ACK를 보냈다는 뜻은 아닙니다. mandatory Return은 Confirm과 독립적으로 발생합니다. durable Queue + persistent 메시지(delivery_mode=2)라도 모든 장애에 안전하지는 않습니다.</p>
      </div>
    </div>

    <!-- Events + Checklist -->
    <div class="bottom-grid">
      <section class="panel events-panel">
        <div class="panel-heading"><h2><Activity :size="17" /> 관측 이벤트</h2><span class="subtle">{{ mode === 'demo' ? '설명용 예시' : '실제 앱 기록' }}</span></div>
        <div v-if="!data.events.length" class="events-empty">발행하면 Confirm·Return·수신 이벤트가 기록됩니다.</div>
        <div v-else class="event-table">
          <div class="event-table-head"><span>시각</span><span>이벤트</span><span>Message ID</span></div>
          <div v-for="event in data.events.slice(0, 20)" :key="event.event_id" class="event-row" :class="event.event_type.toLowerCase()">
            <code>{{ time(event.timestamp) }}</code>
            <span class="event-name" :class="event.event_type.toLowerCase()"><i></i>{{ eventLabels[event.event_type] || event.event_type }}</span>
            <code>{{ event.message_id ? short(event.message_id) : '—' }}</code>
          </div>
        </div>
        <div class="table-footer"><span>최근 이벤트 · 수집 {{ time(data.collected_at) }}</span></div>
      </section>

      <section class="panel checklist-panel">
        <div class="panel-heading"><h2><CheckCircle2 :size="17" /> Phase 4 완료 기준</h2></div>
        <button v-for="(criterion, index) in criteria" :key="criterion" class="check-row" @click="emit('check', index)">
          <span class="checkbox" :class="{ checked: checks[index] }"><Check v-if="checks[index]" :size="13" /></span>
          <span>{{ criterion }}</span>
        </button>
        <div class="checklist-footer">
          <span>현재 기기에 저장됩니다.</span>
          <button class="text-button" @click="emit('notes')">실험 기록 <ChevronRight :size="14" /></button>
        </div>
      </section>
    </div>

    <div class="mode-footnote"><CircleHelp :size="15" /><span>{{ mode === 'demo' ? '예시 모드에서는 Confirm과 Return을 시뮬레이션합니다. 실제 Broker의 응답은 실제 연결 모드에서 확인하세요.' : '실제 RabbitMQ에서 Confirm·Return을 관측합니다. PUBLISH_SENT는 앱의 전송 기록이며 Broker 처리 시각과 같지 않습니다.' }}</span></div>
  </div>
</template>
