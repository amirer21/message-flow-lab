<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Activity, AlertTriangle, ArrowRight, Check, CheckCircle2, ChevronRight, CircleHelp, Download, Layers3, Play, RefreshCw, Send, Shield, ShieldAlert, ShieldCheck, ShieldX, Skull, Timer, XCircle } from 'lucide-vue-next'
import { request } from './lab'
import { DemoRetry } from './retry'
import type { RetrySnapshot, RetryScenario } from './types'

const props = defineProps<{ active: boolean; mode: 'demo' | 'live'; editable: boolean; gateway: string; token: string; checks: boolean[] }>()
const emit = defineEmits<{ disconnect: [message: string]; check: [index: number]; notes: []; guide: [] }>()

const demo = new DemoRetry()
const data = ref<RetrySnapshot>(demo.snapshot())
const live = ref<RetrySnapshot | null>(null)
const scenario = ref<RetryScenario>('transient_2x')
const body = ref('retry-test')
const busy = ref(false)
const failure = ref('')
let generation = 0

const scenarios: { value: RetryScenario; label: string; desc: string }[] = [
  { value: 'transient_2x', label: '일시 실패 2회', desc: '2회 실패 후 3번째에 성공 · Retry 관찰' },
  { value: 'permanent', label: '영구 실패', desc: '즉시 DLQ 격리 · 재시도 없음' },
  { value: 'retry_exceed', label: '재시도 한도 초과', desc: '3회 재시도 후 DLQ 격리' },
]

const criteria = [
  'Retry와 즉시 Requeue의 차이를 설명한다.',
  '영구 실패와 일시 실패를 분류하는 기준을 설명한다.',
  '무한 재전달을 방지하는 방법을 확인했다.',
  'DLQ에 격리된 메시지의 활용 방법을 설명한다.',
]

const eventLabels: Record<string, string> = {
  TOPOLOGY_CREATED: '새 실험 시작',
  PUBLISH_SENT: '발행 요청 전송',
  PUBLISH_CONFIRMED: 'Broker Confirm ACK',
  PUBLISH_NACKED: 'Broker Confirm NACK',
  PUBLISH_OUTCOME_UNKNOWN: '결과 불명',
  PROCESSING_STARTED: '처리 시작',
  PROCESSING_FAILED: '처리 실패',
  PROCESSING_SUCCEEDED: '처리 성공',
  RETRY_SCHEDULED: '재시도 예약',
  RETRY_RETURNED: 'Retry 만료 복귀',
  DLQ_STORED: 'DLQ 격리',
  ACK_SENT: 'ACK 전송',
}

const short = (id: string) => id.slice(0, 8)
const time = (t: string) => new Date(t).toLocaleTimeString('ko-KR', { hour12: false })

const outcomeStatus = computed(() => {
  const proc = data.value.last_process
  if (!proc) return null
  if (proc.outcome === 'success') return { label: '처리 성공', desc: `재시도 ${proc.retry_count}회 후 성공`, color: 'green' }
  if (proc.outcome === 'retry') return { label: '재시도 예약', desc: `${proc.retry_count + 1}번째 시도 예정 · TTL 대기`, color: 'amber' }
  return { label: 'DLQ 격리', desc: '재시도 불가 · Dead Letter Queue로 이동', color: 'red' }
})

async function read(syncForm = false) {
  if (!props.active || props.mode !== 'live' || !props.editable || busy.value) return
  const current = generation; busy.value = true
  try {
    const next = await request<RetrySnapshot>(props.gateway, props.token, '/retry/snapshot')
    if (current === generation) { live.value = next; data.value = next; failure.value = '' }
  } catch (e) {
    if (current === generation) { failure.value = '재시도 실습 연결이 끊겼습니다.'; emit('disconnect', `${failure.value} ${e instanceof Error ? e.message : ''}`) }
  } finally { busy.value = false }
}

watch(() => [props.mode, props.active, props.editable, props.gateway, props.token], () => {
  generation++
  if (props.mode === 'demo') { data.value = demo.snapshot() }
  else if (live.value) { data.value = live.value }
  void read(true)
}, { immediate: true })

const timer = setInterval(() => {
  if (props.mode === 'demo') { demo.tick(); data.value = demo.snapshot() }
  void read()
}, 2000)
onBeforeUnmount(() => { clearInterval(timer); generation++ })

async function run(action: 'setup' | 'publish' | 'process') {
  if (busy.value || !props.editable) return
  if (action === 'publish' && (!body.value.trim() || body.value.length > 4096)) { failure.value = '메시지는 1~4,096자로 입력하세요.'; return }
  const current = generation; busy.value = true; failure.value = ''
  try {
    if (props.mode === 'demo') {
      if (action === 'setup') demo.setup()
      if (action === 'publish') demo.publish(body.value, scenario.value)
      if (action === 'process') demo.process()
      data.value = demo.snapshot()
    } else {
      const payload = action === 'publish' ? { body: body.value, scenario: scenario.value } : {}
      const next = await request<RetrySnapshot>(props.gateway, props.token, `/retry/${action}`, payload)
      if (current === generation) { live.value = next; data.value = next }
    }
  } catch (e) { if (current === generation) failure.value = `${e instanceof Error ? e.message : '요청 실패'}` }
  finally { busy.value = false }
}

const dlqEvents = computed(() => data.value.events.filter(e => e.event_type === 'DLQ_STORED'))
const successEvents = computed(() => data.value.events.filter(e => e.event_type === 'PROCESSING_SUCCEEDED'))
</script>

<template>
  <div class="phase-four">
    <div class="question-banner"><span class="question-icon"><CircleHelp :size="22" /></span><div><span>이번 실험의 질문</span><strong>다시 처리할 실패와 격리할 실패는 어떻게 나눌까?</strong></div><button class="text-button" @click="emit('guide')">개념 살펴보기 <ChevronRight :size="15" /></button></div>
    <div v-if="failure" class="alert error" role="alert">{{ failure }}</div>

    <!-- Scenario Selection -->
    <div class="exchange-choices">
      <button v-for="s in scenarios" :key="s.value" class="scenario-card" :class="{ chosen: scenario === s.value }" @click="scenario = s.value">
        <span class="scenario-number">
          <RefreshCw v-if="s.value === 'transient_2x'" :size="16" />
          <Skull v-else-if="s.value === 'permanent'" :size="16" />
          <XCircle v-else :size="16" />
        </span>
        <strong>{{ s.label }}</strong>
        <span>{{ s.desc }}</span>
      </button>
    </div>

    <!-- Topology Setup -->
    <section class="panel topology-controls">
      <div>
        <h2><Layers3 :size="17" /> 실험 환경</h2>
        <p>Phase 5 전용 Exchange 3개 (work · retry · dead) · Confirm 모드 · TTL 5초</p>
      </div>
      <button class="button secondary" :disabled="busy || !editable" @click="run('setup')"><Play :size="15" /> 새 실험 시작</button>
      <p class="hint">새 실험은 이전 Phase 5 토폴로지를 삭제하고 다시 만듭니다.</p>
    </section>

    <!-- Publish + Process -->
    <div class="routing-workspace">
      <section class="panel producer-panel">
        <div class="panel-heading"><h2><Send :size="17" /> 메시지 발행</h2><span class="small-badge">CONFIRM MODE</span></div>
        <label for="retry-body">Message payload</label>
        <div class="editor"><textarea id="retry-body" v-model="body" rows="2" maxlength="4096" spellcheck="false"></textarea></div>
        <p class="hint">시나리오: <strong>{{ scenarios.find(s => s.value === scenario)?.label }}</strong></p>
        <button class="button primary" :disabled="busy || !editable" @click="run('publish')"><Send :size="15" /> 작업 Queue에 발행</button>

        <div style="margin-top: 16px">
          <button class="button primary" :disabled="busy || !editable" @click="run('process')"><Download :size="15" /> 작업 Queue에서 1개 처리</button>
          <p class="hint">작업 Queue에서 메시지 1개를 소비하고 시나리오에 따라 성공/재시도/DLQ를 결정합니다.</p>
        </div>

        <!-- Process result -->
        <div v-if="data.last_process" class="confirm-result">
          <h3>처리 결과</h3>
          <div class="result-grid">
            <div class="result-cell" :class="outcomeStatus?.color">
              <CheckCircle2 v-if="data.last_process.outcome === 'success'" :size="20" />
              <RefreshCw v-else-if="data.last_process.outcome === 'retry'" :size="20" />
              <ShieldX v-else :size="20" />
              <div>
                <strong>{{ outcomeStatus?.label }}</strong>
                <span>{{ outcomeStatus?.desc }}</span>
              </div>
            </div>
          </div>
          <div class="publish-detail">
            <span>Message ID: <code>{{ short(data.last_process.message_id) }}</code></span>
            <span>시나리오: <code>{{ data.last_process.scenario }}</code></span>
            <span>재시도 횟수: <code>{{ data.last_process.retry_count }}</code></span>
            <span>결과: <code>{{ data.last_process.outcome }}</code></span>
          </div>
        </div>
      </section>

      <!-- Queues -->
      <section class="panel route-panel">
        <div class="panel-heading"><h2><Layers3 :size="17" /> Queue 상태</h2><code class="subtle">WORK · RETRY · DLQ</code></div>
        <div class="exchange-strip"><Shield :size="23" /><span>Work Exchange<strong>{{ data.work_exchange || '초기화 대기' }}</strong></span></div>
        <div class="routing-queue-grid">
          <div v-for="queue in data.queues" :key="queue.id" class="routing-queue">
            <div class="queue-card-heading">
              <strong>{{ queue.label }}</strong>
              <span><b>{{ queue.ready ?? '?' }}</b> Ready</span>
            </div>
            <div class="queue-props">
              <span>role: <code>{{ queue.role }}</code></span>
              <span v-if="queue.role === 'retry'">TTL: <code>5000ms</code></span>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Concept callout -->
    <div class="concept-callout" style="margin-top:16px">
      <CircleHelp :size="20" />
      <div>
        <strong>Retry ≠ Requeue</strong>
        <p>즉시 requeue하면 실패 메시지가 반복적으로 자원을 차지합니다. TTL이 있는 별도 retry Queue를 사용하면 대기 시간을 두고 재시도 횟수를 제한할 수 있습니다. 영구 실패(잘못된 형식, 누락된 필드 등)는 재시도 없이 즉시 DLQ로 보냅니다.</p>
      </div>
    </div>

    <!-- DLQ + Success history + Events + Checklist -->
    <div class="bottom-grid">
      <section class="panel events-panel">
        <div class="panel-heading"><h2><Activity :size="17" /> 관측 이벤트</h2><span class="subtle">{{ mode === 'demo' ? '설명용 예시' : '실제 앱 기록' }}</span></div>
        <div v-if="!data.events.length" class="events-empty">발행하면 처리·재시도·DLQ 이벤트가 기록됩니다.</div>
        <div v-else class="event-table">
          <div class="event-table-head"><span>시각</span><span>이벤트</span><span>Message ID</span></div>
          <div v-for="event in data.events.slice(0, 30)" :key="event.event_id" class="event-row" :class="event.event_type.toLowerCase()">
            <code>{{ time(event.timestamp) }}</code>
            <span class="event-name" :class="event.event_type.toLowerCase()"><i></i>{{ eventLabels[event.event_type] || event.event_type }}</span>
            <code>{{ event.message_id ? short(event.message_id) : '—' }}</code>
          </div>
        </div>
        <div class="table-footer"><span>최근 이벤트 · 수집 {{ time(data.collected_at) }}</span></div>
      </section>

      <section class="panel checklist-panel">
        <div class="panel-heading"><h2><CheckCircle2 :size="17" /> Phase 5 완료 기준</h2></div>
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

    <!-- DLQ History -->
    <div v-if="dlqEvents.length || successEvents.length" class="bottom-grid" style="margin-top: 16px">
      <section v-if="successEvents.length" class="panel events-panel">
        <div class="panel-heading"><h2><CheckCircle2 :size="17" /> 성공 이력</h2></div>
        <div class="event-table">
          <div class="event-table-head"><span>시각</span><span>Message ID</span><span>재시도</span></div>
          <div v-for="event in successEvents.slice(0, 10)" :key="event.event_id" class="event-row">
            <code>{{ time(event.timestamp) }}</code>
            <code>{{ event.message_id ? short(event.message_id) : '—' }}</code>
            <span>{{ (event.metadata as any).retry_count ?? 0 }}회</span>
          </div>
        </div>
      </section>
      <section v-if="dlqEvents.length" class="panel events-panel">
        <div class="panel-heading"><h2><ShieldX :size="17" /> DLQ 이력</h2></div>
        <div class="event-table">
          <div class="event-table-head"><span>시각</span><span>Message ID</span><span>사유</span></div>
          <div v-for="event in dlqEvents.slice(0, 10)" :key="event.event_id" class="event-row">
            <code>{{ time(event.timestamp) }}</code>
            <code>{{ event.message_id ? short(event.message_id) : '—' }}</code>
            <span>{{ (event.metadata as any).failure_type === 'permanent' ? '영구 실패' : '한도 초과' }}</span>
          </div>
        </div>
      </section>
    </div>

    <div class="mode-footnote"><CircleHelp :size="15" /><span>{{ mode === 'demo' ? '예시 모드에서는 TTL을 타임스탬프 비교로 시뮬레이션합니다. 실제 Broker의 DLX 동작은 실제 연결 모드에서 확인하세요.' : '실제 RabbitMQ에서 TTL 만료 후 DLX를 통해 메시지가 work Queue로 복귀합니다.' }}</span></div>
  </div>
</template>
