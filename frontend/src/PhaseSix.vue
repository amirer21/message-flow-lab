<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Activity, AlertTriangle, Check, CheckCircle2, ChevronRight, CircleHelp, Database, Download, Key, Layers3, Play, Send, Shield, ShieldCheck, ShieldX, Zap } from 'lucide-vue-next'
import { request } from './lab'
import { DemoIdempotency } from './idempotency'
import type { IdempotencySnapshot, IdempotencyScenario } from './types'

const props = defineProps<{ active: boolean; mode: 'demo' | 'live'; editable: boolean; gateway: string; token: string; checks: boolean[] }>()
const emit = defineEmits<{ disconnect: [message: string]; check: [index: number]; notes: []; guide: [] }>()

const demo = new DemoIdempotency()
const data = ref<IdempotencySnapshot>(demo.snapshot())
const live = ref<IdempotencySnapshot | null>(null)
const scenario = ref<IdempotencyScenario>('normal')
const idempotencyKey = ref('order-001')
const amount = ref(1000)
const busy = ref(false)
const failure = ref('')
let generation = 0

const scenarios: { value: IdempotencyScenario; label: string; desc: string }[] = [
  { value: 'normal', label: '정상 처리', desc: '메시지 1건 발행 → 업무 효과 1회 기록' },
  { value: 'duplicate', label: '중복 발행', desc: '같은 키로 2회 발행 → 효과 1회만 확인' },
  { value: 'crash_after_commit', label: 'Commit 후 장애', desc: 'DB 커밋 후 ACK 전 장애 → 재전달 시 중복 방어' },
]

const criteria = [
  '중복 수신에도 업무 효과가 한 번만 발생함을 확인했다.',
  'DB unique constraint로 중복을 방지하는 원리를 설명한다.',
  'Commit 후 ACK 전 장애에서 재전달 메시지의 중복 방어를 확인했다.',
  '메시지를 한 번만 받는 보장과 업무 효과를 한 번만 반영하는 설계의 차이를 설명한다.',
]

const eventLabels: Record<string, string> = {
  TOPOLOGY_CREATED: '새 실험 시작',
  PUBLISH_SENT: '발행 요청 전송',
  PUBLISH_CONFIRMED: 'Broker Confirm ACK',
  PUBLISH_NACKED: 'Broker Confirm NACK',
  PUBLISH_OUTCOME_UNKNOWN: '결과 불명',
  PROCESSING_STARTED: '처리 시작',
  EFFECT_APPLIED: '업무 효과 반영',
  DUPLICATE_SKIPPED: '중복 건너뜀',
  CRASH_BEFORE_ACK: 'ACK 전 장애',
  CRASH_ARMED: '장애 시뮬레이션 예약',
  ACK_SENT: 'ACK 전송',
}

const short = (id: string) => id.slice(0, 8)
const time = (t: string) => new Date(t).toLocaleTimeString('ko-KR', { hour12: false })

const outcomeStatus = computed(() => {
  const proc = data.value.last_process
  if (!proc) return null
  if (proc.outcome === 'applied' && !proc.was_duplicate) return { label: '업무 효과 반영', desc: '새 키 — DB에 효과를 기록했습니다.', color: 'green' }
  if (proc.outcome === 'skipped') return { label: '중복 건너뜀', desc: '이미 처리된 키 — 효과를 추가하지 않았습니다.', color: 'amber' }
  return { label: '업무 효과 반영', desc: 'DB에 효과를 기록했습니다.', color: 'green' }
})

async function read() {
  if (!props.active || props.mode !== 'live' || !props.editable || busy.value) return
  const current = generation; busy.value = true
  try {
    const next = await request<IdempotencySnapshot>(props.gateway, props.token, '/idempotency/snapshot')
    if (current === generation) { live.value = next; data.value = next; failure.value = '' }
  } catch (e) {
    if (current === generation) { failure.value = '멱등성 실습 연결이 끊겼습니다.'; emit('disconnect', `${failure.value} ${e instanceof Error ? e.message : ''}`) }
  } finally { busy.value = false }
}

watch(() => [props.mode, props.active, props.editable, props.gateway, props.token], () => {
  generation++
  if (props.mode === 'demo') { data.value = demo.snapshot() }
  else if (live.value) { data.value = live.value }
  void read()
}, { immediate: true })

const timer = setInterval(() => void read(), 2000)
onBeforeUnmount(() => { clearInterval(timer); generation++ })

async function exec(action: 'setup' | 'publish' | 'process' | 'arm-crash') {
  const current = generation
  if (props.mode === 'demo') {
    if (action === 'setup') demo.setup()
    if (action === 'publish') demo.publish(idempotencyKey.value, amount.value)
    if (action === 'process') demo.process()
    if (action === 'arm-crash') demo.armCrash()
    data.value = demo.snapshot()
  } else {
    if (action === 'publish') {
      const next = await request<IdempotencySnapshot>(props.gateway, props.token, '/idempotency/publish', { idempotency_key: idempotencyKey.value, amount: amount.value })
      if (current === generation) { live.value = next; data.value = next }
    } else {
      const next = await request<IdempotencySnapshot>(props.gateway, props.token, `/idempotency/${action}`, {})
      if (current === generation) { live.value = next; data.value = next }
    }
  }
}

async function run(action: 'setup' | 'publish' | 'process' | 'arm-crash') {
  if (busy.value || !props.editable) return
  if (action === 'publish' && !idempotencyKey.value.trim()) { failure.value = 'Idempotency Key를 입력하세요.'; return }
  const current = generation; busy.value = true; failure.value = ''
  try {
    await exec(action)
  } catch (e) { if (current === generation) failure.value = `${e instanceof Error ? e.message : '요청 실패'}` }
  finally { busy.value = false }
}

async function runScenario() {
  if (busy.value || !props.editable) return
  if (!idempotencyKey.value.trim()) { failure.value = 'Idempotency Key를 입력하세요.'; return }
  busy.value = true; failure.value = ''
  const current = generation
  try {
    if (scenario.value === 'normal') {
      await exec('publish')
      await exec('process')
    } else if (scenario.value === 'duplicate') {
      await exec('publish')
      await exec('publish')
      await exec('process')
      await exec('process')
    } else if (scenario.value === 'crash_after_commit') {
      await exec('publish')
      await exec('arm-crash')
      await exec('process')
      await exec('process')
    }
  } catch (e) { if (current === generation) failure.value = `${e instanceof Error ? e.message : '시나리오 실행 실패'}` }
  finally { busy.value = false }
}

const effectAppliedEvents = computed(() => data.value.events.filter(e => e.event_type === 'EFFECT_APPLIED'))
const duplicateSkippedEvents = computed(() => data.value.events.filter(e => e.event_type === 'DUPLICATE_SKIPPED'))
</script>

<template>
  <div class="phase-four">
    <div class="question-banner"><span class="question-icon"><CircleHelp :size="22" /></span><div><span>이번 실험의 질문</span><strong>같은 요청이 두 번 와도 결과를 한 번만 반영할까?</strong></div><button class="text-button" @click="emit('guide')">개념 살펴보기 <ChevronRight :size="15" /></button></div>
    <div v-if="failure" class="alert error" role="alert">{{ failure }}</div>

    <!-- Scenario Selection -->
    <div class="exchange-choices">
      <button v-for="s in scenarios" :key="s.value" class="scenario-card" :class="{ chosen: scenario === s.value }" @click="scenario = s.value">
        <span class="scenario-number">
          <ShieldCheck v-if="s.value === 'normal'" :size="16" />
          <Key v-else-if="s.value === 'duplicate'" :size="16" />
          <Zap v-else :size="16" />
        </span>
        <strong>{{ s.label }}</strong>
        <span>{{ s.desc }}</span>
      </button>
    </div>

    <!-- Topology Setup -->
    <section class="panel topology-controls">
      <div>
        <h2><Layers3 :size="17" /> 실험 환경</h2>
        <p>Phase 6 전용 Exchange 1개 (work) · Confirm 모드 · SQLite DB 멱등 검사</p>
      </div>
      <button class="button secondary" :disabled="busy || !editable" @click="run('setup')"><Play :size="15" /> 새 실험 시작</button>
      <p class="hint">새 실험은 이전 Phase 6 토폴로지와 DB 데이터를 삭제하고 다시 만듭니다.</p>
    </section>

    <!-- Publish + Process -->
    <div class="routing-workspace">
      <section class="panel producer-panel">
        <div class="panel-heading"><h2><Send :size="17" /> 메시지 발행</h2><span class="small-badge">CONFIRM MODE</span></div>
        <label for="idem-key">Idempotency Key</label>
        <div class="editor"><textarea id="idem-key" v-model="idempotencyKey" rows="1" maxlength="256" spellcheck="false" placeholder="order-001"></textarea></div>
        <label for="idem-amount">Amount (금액)</label>
        <div class="editor"><textarea id="idem-amount" :value="String(amount)" rows="1" spellcheck="false" @input="amount = Number(($event.target as HTMLTextAreaElement).value) || 0"></textarea></div>
        <p class="hint">시나리오: <strong>{{ scenarios.find(s => s.value === scenario)?.label }}</strong></p>

        <div class="button-row">
          <button class="button primary" :disabled="busy || !editable" @click="run('publish')"><Send :size="15" /> 발행</button>
          <button class="button primary" :disabled="busy || !editable" @click="run('process')"><Download :size="15" /> 1개 처리</button>
        </div>

        <div style="margin-top: 12px">
          <button class="button secondary" :disabled="busy || !editable" @click="run('arm-crash')"><Zap :size="15" /> 장애 시뮬레이션 예약</button>
          <p class="hint">다음 처리에서 DB 커밋 후 ACK를 보내지 않고 NACK(requeue)합니다.</p>
        </div>

        <div style="margin-top: 12px; border-top: 1px solid var(--c-border, #e5e5e5); padding-top: 12px">
          <button class="button secondary" :disabled="busy || !editable" @click="runScenario"><Play :size="15" /> 시나리오 자동 실행</button>
          <p class="hint">선택한 시나리오의 발행·처리 절차를 순서대로 실행합니다.</p>
        </div>

        <!-- Process result -->
        <div v-if="data.last_process" class="confirm-result">
          <h3>처리 결과</h3>
          <div class="result-grid">
            <div class="result-cell" :class="outcomeStatus?.color">
              <CheckCircle2 v-if="data.last_process.outcome === 'applied'" :size="20" />
              <ShieldX v-else :size="20" />
              <div>
                <strong>{{ outcomeStatus?.label }}</strong>
                <span>{{ outcomeStatus?.desc }}</span>
              </div>
            </div>
          </div>
          <div class="publish-detail">
            <span>Message ID: <code>{{ short(data.last_process.message_id) }}</code></span>
            <span>Idempotency Key: <code>{{ data.last_process.idempotency_key }}</code></span>
            <span>결과: <code>{{ data.last_process.outcome }}</code></span>
            <span>중복 여부: <code>{{ data.last_process.was_duplicate ? '예' : '아니오' }}</code></span>
          </div>
        </div>
      </section>

      <!-- Queue + DB State -->
      <section class="panel route-panel">
        <div class="panel-heading"><h2><Layers3 :size="17" /> Queue · DB 상태</h2><code class="subtle">WORK QUEUE + SQLite</code></div>
        <div class="exchange-strip"><Shield :size="23" /><span>Work Exchange<strong>{{ data.work_exchange || '초기화 대기' }}</strong></span></div>
        <div class="routing-queue-grid">
          <div v-for="queue in data.queues" :key="queue.id" class="routing-queue">
            <div class="queue-card-heading">
              <strong>{{ queue.label }}</strong>
              <span><b>{{ queue.ready ?? '?' }}</b> Ready</span>
            </div>
          </div>
        </div>

        <!-- DB Status -->
        <div style="margin-top: 16px; padding: 12px; background: var(--c-bg-soft, #f8f8f8); border-radius: 8px;">
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px">
            <Database :size="17" />
            <strong>멱등성 DB 상태</strong>
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 0.85em">
            <div>처리된 키 수: <strong>{{ data.processed_count }}</strong></div>
            <div>업무 효과 수: <strong>{{ data.effects.length }}</strong></div>
          </div>
        </div>

        <!-- Business Effects Table -->
        <div v-if="data.effects.length" style="margin-top: 16px">
          <h3 style="font-size: 0.9em; margin-bottom: 8px"><Database :size="15" /> 업무 효과 (business_effects)</h3>
          <div class="event-table">
            <div class="event-table-head"><span>ID</span><span>Idempotency Key</span><span>금액</span><span>시각</span></div>
            <div v-for="effect in data.effects.slice(0, 20)" :key="effect.id" class="event-row">
              <code>{{ effect.id }}</code>
              <code>{{ effect.idempotency_key }}</code>
              <span>{{ effect.amount.toLocaleString() }}</span>
              <code>{{ time(effect.created_at) }}</code>
            </div>
          </div>
        </div>
      </section>
    </div>

    <!-- Concept callout -->
    <div class="concept-callout" style="margin-top:16px">
      <CircleHelp :size="20" />
      <div>
        <strong>Exactly-once delivery ≠ Exactly-once processing</strong>
        <p>메시지 브로커는 at-least-once 전달을 보장합니다. 같은 메시지가 두 번 이상 도착할 수 있으므로, 업무 효과를 한 번만 반영하려면 Consumer 측에서 멱등성을 구현해야 합니다. Idempotency Key + DB unique constraint + 트랜잭션으로 중복 효과를 방어합니다.</p>
      </div>
    </div>

    <!-- Events + Checklist -->
    <div class="bottom-grid">
      <section class="panel events-panel">
        <div class="panel-heading"><h2><Activity :size="17" /> 관측 이벤트</h2><span class="subtle">{{ mode === 'demo' ? '설명용 예시' : '실제 앱 기록' }}</span></div>
        <div v-if="!data.events.length" class="events-empty">발행하면 멱등 처리 이벤트가 기록됩니다.</div>
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
        <div class="panel-heading"><h2><CheckCircle2 :size="17" /> Phase 6 완료 기준</h2></div>
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

    <!-- Effect/Duplicate History -->
    <div v-if="effectAppliedEvents.length || duplicateSkippedEvents.length" class="bottom-grid" style="margin-top: 16px">
      <section v-if="effectAppliedEvents.length" class="panel events-panel">
        <div class="panel-heading"><h2><CheckCircle2 :size="17" /> 효과 반영 이력</h2></div>
        <div class="event-table">
          <div class="event-table-head"><span>시각</span><span>Message ID</span><span>Key</span></div>
          <div v-for="event in effectAppliedEvents.slice(0, 10)" :key="event.event_id" class="event-row">
            <code>{{ time(event.timestamp) }}</code>
            <code>{{ event.message_id ? short(event.message_id) : '—' }}</code>
            <span>{{ (event.metadata as any).idempotency_key ?? '—' }}</span>
          </div>
        </div>
      </section>
      <section v-if="duplicateSkippedEvents.length" class="panel events-panel">
        <div class="panel-heading"><h2><ShieldX :size="17" /> 중복 건너뜀 이력</h2></div>
        <div class="event-table">
          <div class="event-table-head"><span>시각</span><span>Message ID</span><span>Key</span></div>
          <div v-for="event in duplicateSkippedEvents.slice(0, 10)" :key="event.event_id" class="event-row">
            <code>{{ time(event.timestamp) }}</code>
            <code>{{ event.message_id ? short(event.message_id) : '—' }}</code>
            <span>{{ (event.metadata as any).idempotency_key ?? '—' }}</span>
          </div>
        </div>
      </section>
    </div>

    <div class="mode-footnote"><CircleHelp :size="15" /><span>{{ mode === 'demo' ? '예시 모드에서는 In-memory Set으로 중복 검사를 시뮬레이션합니다. 실제 DB unique constraint는 실제 연결 모드에서 확인하세요.' : '실제 SQLite DB의 unique constraint + 트랜잭션으로 멱등성을 보장합니다.' }}</span></div>
  </div>
</template>
