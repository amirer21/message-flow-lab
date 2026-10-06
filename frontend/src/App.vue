<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { Activity, ArrowRight, BookOpen, Check, CheckCircle2, ChevronRight, CircleHelp, ClipboardList, Code2, Download, ExternalLink, FlaskConical, Layers3, Link2, Menu, Play, Radio, RotateCcw, Send, Server, Settings2, Square, Terminal, Unplug, X } from 'lucide-vue-next'
import { phases } from './curriculum'
import { DemoLab, request } from './lab'
import type { LabEvent, Snapshot } from './types'

const safeRead = <T,>(key: string, fallback: T): T => { try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback } catch { return fallback } }
const safeSave = (key: string, value: unknown) => { try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* Optional device-local learning state. */ } }
const selected = ref(1)
const page = ref<'lab' | 'guide' | 'notes' | 'connection'>('lab')
const phase = computed(() => phases[selected.value]!)
const mode = ref<'demo' | 'live'>('demo')
let demo = new DemoLab()
const snapshot = ref<Snapshot>(demo.snapshot())
const gateway = ref(safeRead('mfl-gateway', 'http://localhost:8000'))
const token = ref('')
const connected = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const payload = ref('hello')
const mobileMenu = ref(false)
const steps = ref<Record<string, boolean>>(safeRead('mfl-checks', {}))
const notes = ref<Record<string, { prediction: string; observation: string; explanation: string }>>(safeRead('mfl-notes', {}))
const selectedEvent = ref<LabEvent | null>(null)
const currentNotes = computed(() => notes.value[selected.value] || { prediction: '', observation: '', explanation: '' })
const completed = computed(() => phases.filter(p => p.criteria.every((_, i) => steps.value[`${p.id}-${i}`])).length)
const progress = computed(() => Math.round(completed.value / phases.length * 100))
const editable = computed(() => mode.value === 'demo' || connected.value)
const timeline = computed(() => snapshot.value.events.slice(0, 12))
const trace = computed(() => selectedEvent.value ? snapshot.value.events.filter(e => e.message_id === selectedEvent.value!.message_id).reverse() : [])
const eventLabels: Record<string, string> = { PUBLISH_SENT: '발행 요청 전송', DELIVERED: 'Consumer 전달', ACK_SENT: 'ACK 전송', CONNECTION_CLOSED: 'Consumer 연결 종료', CONSUMER_STARTED: 'Consumer 시작', CONSUMER_STOPPED: 'Consumer 종료', CONSUMER_ERROR: 'Consumer 오류' }
const short = (value: string) => value.slice(0, 8)
const time = (value: string) => new Date(value).toLocaleTimeString('ko-KR', { hour12: false })
const checkKey = (index: number) => `${selected.value}-${index}`
function toggleCheck(index: number) { steps.value[checkKey(index)] = !steps.value[checkKey(index)]; safeSave('mfl-checks', steps.value) }
function updateNote(field: 'prediction' | 'observation' | 'explanation', event: Event) {
  notes.value[selected.value] = { ...currentNotes.value, [field]: (event.target as HTMLTextAreaElement).value }; safeSave('mfl-notes', notes.value)
}
function selectPhase(id: number) { selected.value = id; page.value = id < 2 ? 'lab' : 'guide'; mobileMenu.value = false; selectedEvent.value = null }
let generation = 0
let polling = false
async function refresh() {
  if (polling || mode.value !== 'live' || !connected.value) return
  const current = generation; polling = true
  try { const next = await request<Snapshot>(gateway.value, token.value, '/snapshot'); if (current === generation) { snapshot.value = next; error.value = '' } }
  catch (e) { if (current === generation) { connected.value = false; error.value = `실제 연결이 끊겼습니다. 마지막 수집값을 표시합니다. ${e instanceof Error ? e.message : ''}` } }
  finally { polling = false }
}
const interval = setInterval(() => void refresh(), 2000)
onBeforeUnmount(() => { clearInterval(interval); generation++ })
async function connect() {
  if (!token.value.trim()) { error.value = '실습 환경의 LAB_TOKEN을 입력하세요.'; return }
  busy.value = true; error.value = ''; generation++
  try {
    const url = new URL(gateway.value)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('HTTP 또는 HTTPS Gateway 주소를 입력하세요.')
    if (location.protocol === 'https:' && url.protocol === 'http:') throw new Error('게시된 사이트에서는 HTTPS Gateway가 필요합니다. 로컬 실습은 http://localhost:5173 화면을 사용하세요.')
    gateway.value = url.href.replace(/\/$/, '')
    const next = await request<Snapshot>(gateway.value, token.value, '/snapshot')
    snapshot.value = next; mode.value = 'live'; connected.value = true; safeSave('mfl-gateway', gateway.value); page.value = 'lab'; notice.value = '실제 RabbitMQ에 연결했습니다.'
  } catch (e) { connected.value = false; error.value = e instanceof Error ? e.message : '연결할 수 없습니다.' }
  finally { busy.value = false }
}
function switchDemo() { generation++; mode.value = 'demo'; connected.value = false; snapshot.value = demo.snapshot(); selectedEvent.value = null; error.value = ''; notice.value = ''; page.value = 'lab' }
async function action(kind: 'publish' | 'start' | 'stop' | 'ack', count = 1) {
  if (busy.value || !editable.value) return
  if (kind === 'publish' && (!payload.value.trim() || payload.value.length > 4096)) { error.value = '메시지는 1~4,096자로 입력하세요.'; return }
  busy.value = true; error.value = ''; notice.value = ''; const current = generation
  try {
    if (mode.value === 'demo') {
      if (kind === 'publish') demo.publish(payload.value, count)
      if (kind === 'start') demo.start()
      if (kind === 'stop') demo.stop()
      if (kind === 'ack' && snapshot.value.pending) demo.ack(snapshot.value.pending.attempt_id)
      snapshot.value = demo.snapshot()
    } else {
      const path = { publish: '/rabbit/messages', start: '/consumer/start', stop: '/consumer/stop', ack: '/consumer/ack' }[kind]
      const body = kind === 'publish' ? { body: payload.value, count } : kind === 'ack' ? { attempt_id: snapshot.value.pending?.attempt_id } : {}
      await request(gateway.value, token.value, path, body)
      const next = await request<Snapshot>(gateway.value, token.value, '/snapshot'); if (current === generation) snapshot.value = next
    }
  } catch (e) { error.value = `${e instanceof Error ? e.message : '요청 실패'} 다시 발행하기 전에 Queue와 기록을 확인하세요.` }
  finally { busy.value = false }
}
function resetDemo() { demo = new DemoLab(); snapshot.value = demo.snapshot(); selectedEvent.value = null; notice.value = '예시 실험을 초기화했습니다.' }
function exportNotes() {
  const content = phases.map(p => { const n = notes.value[p.id]; return `## Phase ${p.id}. ${p.title}\n\n예측: ${n?.prediction || ''}\n\n관찰: ${n?.observation || ''}\n\n설명: ${n?.explanation || ''}\n\n${p.criteria.map((c,i) => `- [${steps.value[`${p.id}-${i}`] ? 'x' : ' '}] ${c}`).join('\n')}` }).join('\n\n')
  const url = URL.createObjectURL(new Blob([`# MessageFlow Lab 학습 기록\n\n${content}`], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = 'messageflow-learning-notes.md'; link.click(); URL.revokeObjectURL(url)
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <button class="mobile-menu icon-button" aria-label="학습 메뉴 열기" @click="mobileMenu = !mobileMenu"><Menu :size="20" /></button>
      <a class="brand" href="#" @click.prevent="selectPhase(1)"><span class="brand-mark"><Layers3 :size="22" /></span><span>MessageFlow <strong>Lab</strong></span></a>
      <span class="top-divider"></span><span class="top-context">MQ 학습 실험실</span>
      <div class="top-right"><span class="version">PHASE 0–1 · v0.1</span><a href="https://www.rabbitmq.com/tutorials" target="_blank" rel="noopener noreferrer">공식 문서 <ExternalLink :size="13" /></a></div>
    </header>
    <aside class="sidebar" :class="{ 'is-open': mobileMenu }">
      <div class="sidebar-intro"><span class="eyebrow">LEARNING PATH</span><h2>작게 실험하고,<br>흐름을 이해하세요.</h2><div class="progress-label"><span>나의 학습 진행</span><strong>{{ completed }} / 13</strong></div><div class="progress-track"><span :style="{ width: progress + '%' }"></span></div></div>
      <nav aria-label="학습 단계"><template v-for="group in ['준비', '기초', '실무', '통합']" :key="group"><div class="nav-group">{{ group }} 과정</div><button v-for="p in phases.filter(p => p.category === group)" :key="p.id" class="phase-link" :class="{ selected: selected === p.id }" @click="selectPhase(p.id)"><span class="phase-number" :class="{ done: p.criteria.every((_,i) => steps[`${p.id}-${i}`]) }"><Check v-if="p.criteria.every((_,i) => steps[`${p.id}-${i}`])" :size="13" /><template v-else>{{ String(p.id).padStart(2, '0') }}</template></span><span>{{ p.title }}</span><span v-if="p.id > 1" class="planned-dot" title="실습 환경은 후속 단계에서 구현"></span></button></template></nav>
      <div class="sidebar-footer"><FlaskConical :size="17" /><span>예측 → 실험 → 관찰 → 설명</span></div>
    </aside>
    <main class="main">
      <div class="page-top"><div class="breadcrumb">학습 실험실 <ChevronRight :size="14" /> Phase {{ String(selected).padStart(2, '0') }}</div><button class="connection-chip" :class="{ live: mode === 'live' && connected, stale: mode === 'live' && !connected }" @click="page = 'connection'"><Radio :size="14" /><span>{{ mode === 'demo' ? '설명용 예시' : connected ? '실제 RabbitMQ 연결' : '연결 끊김 · 마지막 수집값' }}</span><Settings2 :size="13" /></button></div>
      <div class="page-title"><div><span class="phase-eyebrow">PHASE {{ String(selected).padStart(2, '0') }} <span>{{ phase.category }} 과정</span></span><h1>{{ phase.title }}</h1><p>{{ phase.description }}</p></div><div class="phase-status"><span v-if="selected < 2"><FlaskConical :size="15" /> 실습 가능</span><span v-else><BookOpen :size="15" /> 학습 안내 · 실습 구현 예정</span></div></div>
      <div class="tabs" role="tablist" aria-label="현재 단계 화면"><button role="tab" :aria-selected="page === 'lab'" :class="{ active: page === 'lab' }" @click="page = 'lab'"><FlaskConical :size="16" /> 실험실</button><button role="tab" :aria-selected="page === 'guide'" :class="{ active: page === 'guide' }" @click="page = 'guide'"><BookOpen :size="16" /> 학습 가이드</button><button role="tab" :aria-selected="page === 'notes'" :class="{ active: page === 'notes' }" @click="page = 'notes'"><ClipboardList :size="16" /> 나의 실험 기록</button><button role="tab" :aria-selected="page === 'connection'" :class="{ active: page === 'connection' }" @click="page = 'connection'"><Link2 :size="16" /> 실제 연결</button></div>
      <div v-if="error" class="alert error" role="alert"><CircleHelp :size="18" /><span>{{ error }}</span><button class="icon-button" aria-label="오류 안내 닫기" @click="error = ''"><X :size="16" /></button></div>
      <div v-if="notice" class="alert success" role="status"><CheckCircle2 :size="17" /><span>{{ notice }}</span></div>

      <template v-if="page === 'lab' && selected < 2">
        <div class="question-banner"><span class="question-icon"><CircleHelp :size="22" /></span><div><span>이번 실험의 질문</span><strong>{{ phase.question }}</strong></div><button class="text-button" @click="page = 'guide'">개념 살펴보기 <ChevronRight :size="15" /></button></div>
        <div class="metric-grid"><div class="metric-card"><div class="metric-label"><Send :size="16" /> 발행 요청 전송</div><div class="metric-value">{{ snapshot.total_sent }}<span>messages</span></div><div class="metric-foot">현재 세션 · Broker Confirm과 구분</div></div><div class="metric-card"><div class="metric-label"><Layers3 :size="16" /> Ready</div><div class="metric-value blue">{{ snapshot.queue.ready }}<span>messages</span></div><div class="metric-foot">Consumer에게 전달 대기</div></div><div class="metric-card"><div class="metric-label"><Activity :size="16" /> Unacked</div><div class="metric-value amber">{{ snapshot.queue.unacked }}<span>messages</span></div><div class="metric-foot">전달됨 · 아직 ACK 없음</div></div><div class="metric-card"><div class="metric-label"><CheckCircle2 :size="16" /> ACK 전송</div><div class="metric-value">{{ snapshot.ack_sent }}<span>messages</span></div><div class="metric-foot">현재 세션 · 앱 관측 기록</div></div></div>
        <section class="flow-card panel"><div class="panel-heading"><h2><Layers3 :size="17" /> 메시지 흐름</h2><span class="subtle">AMQP 0-9-1 · 기본 Exchange</span></div><div class="flow"><div class="flow-node"><div class="flow-icon"><Send :size="24" /></div><strong>Producer</strong><span>메시지를 발행</span></div><div class="flow-line"><span>publish</span><ArrowRight :size="20" /></div><div class="flow-node"><div class="flow-icon"><Layers3 :size="24" /></div><strong>Exchange</strong><span>기본 Exchange · ""</span></div><div class="flow-line"><span>key: hello</span><ArrowRight :size="20" /></div><div class="flow-node queue-node"><div class="queue-visual"><span v-for="i in 3" :key="i" :class="{ filled: snapshot.queue.ready >= i }"></span></div><strong>Queue <code>hello</code></strong><span>{{ snapshot.queue.ready }}개 전달 대기</span></div><div class="flow-line"><span>delivery</span><ArrowRight :size="20" /></div><div class="flow-node"><div class="flow-icon" :class="{ enabled: snapshot.consumer_active }"><Server :size="24" /></div><strong>Consumer</strong><span>{{ snapshot.consumer_active ? '연결됨 · Prefetch 1' : '연결 대기' }}</span></div></div><div class="flow-caption"><span class="tiny-square"></span> 구조를 설명하는 흐름도입니다. 각 단계의 실제 통과 시각을 의미하지 않습니다.</div></section>
        <div class="work-grid">
          <section class="panel producer-panel"><div class="panel-heading"><h2><Send :size="17" /> 메시지 발행</h2><span class="small-badge">PRODUCER</span></div><label for="payload">Message payload</label><div class="editor"><div class="editor-top"><span>TEXT</span><span>UTF-8</span></div><textarea id="payload" v-model="payload" spellcheck="false" maxlength="4096" rows="3" aria-label="발행할 메시지"></textarea></div><div class="routing-row"><div><span>Exchange</span><code>"" <small>default</small></code></div><div><span>Routing key</span><code>hello</code></div></div><div class="button-row"><button class="button primary" :disabled="busy || !editable" @click="action('publish')"><Send :size="15" /> 메시지 발행</button><button class="button secondary" :disabled="busy || !editable" @click="action('publish', 3)">3개 발행</button></div><p class="hint">첫 실험은 Consumer를 멈춘 상태에서 3개를 보내세요.</p></section>
          <section class="panel consumer-panel"><div class="panel-heading"><h2><Server :size="17" /> Consumer 실습</h2><span class="small-badge" :class="{ 'active-badge': snapshot.consumer_active }">{{ snapshot.consumer_active ? 'CONNECTED' : 'STOPPED' }}</span></div><div class="consumer-toolbar"><div><strong>consumer-lab</strong><span>Manual ACK <span class="dot-divider">·</span> Prefetch 1</span></div><button v-if="!snapshot.consumer_active" class="button secondary" :disabled="busy || !editable" @click="action('start')"><Play :size="14" /> 시작</button><button v-else class="button secondary" :disabled="busy || !editable" @click="action('stop')"><Square :size="13" /> 멈춤</button></div><div v-if="snapshot.pending" class="delivery-box"><div class="delivery-title"><span>ACK 대기 중</span><code>{{ short(snapshot.pending.message_id) }}</code></div><pre>{{ snapshot.pending.body }}</pre><div v-if="snapshot.pending.redelivered" class="redelivery">재전달된 메시지입니다.</div><button class="button ack-button" :disabled="busy || !editable" @click="action('ack')"><Check :size="16" /> 확인 후 ACK 보내기</button></div><div v-else class="consumer-empty"><div class="empty-icon"><Download :size="24" /></div><strong>{{ snapshot.consumer_active ? '메시지를 기다리고 있어요' : 'Consumer가 멈춰 있어요' }}</strong><p>{{ snapshot.consumer_active ? '메시지가 전달되면 여기에서 확인합니다.' : '발행 후 시작하면 메시지 하나를 받습니다.' }}</p></div></section>
        </div>
        <div class="bottom-grid"><section class="panel events-panel"><div class="panel-heading"><h2><Activity :size="17" /> 관측 이벤트</h2><div class="heading-actions"><span class="subtle">{{ mode === 'demo' ? '예시 시뮬레이션' : '실제 앱 기록' }}</span><button v-if="mode === 'demo'" class="icon-button" aria-label="예시 실험 초기화" title="예시 실험 초기화" @click="resetDemo"><RotateCcw :size="15" /></button></div></div><div v-if="!timeline.length" class="events-empty"><Terminal :size="20" /><div><strong>첫 메시지의 기록을 기다립니다.</strong><p>메시지를 발행하면 실제로 관측한 이벤트가 여기에 나타납니다.</p></div></div><div v-else class="event-table"><div class="event-table-head"><span>시각</span><span>이벤트</span><span>Message ID</span></div><button v-for="e in timeline" :key="e.event_id" class="event-row" @click="selectedEvent = e"><code>{{ time(e.timestamp) }}</code><span class="event-name" :class="e.event_type.toLowerCase()"><i></i>{{ eventLabels[e.event_type] || e.event_type }}</span><code>{{ short(e.message_id) }} <ChevronRight :size="12" /></code></button></div><div class="table-footer"><span>최근 {{ timeline.length }}개 · 메시지를 선택하면 처리 이력을 봅니다.</span><span v-if="mode === 'live'">수집 {{ time(snapshot.collected_at) }}</span></div></section><section class="panel checklist-panel"><div class="panel-heading"><h2><CheckCircle2 :size="17" /> 완료 기준</h2><span class="subtle">직접 확인하세요</span></div><button v-for="(criterion, i) in phase.criteria" :key="criterion" class="check-row" @click="toggleCheck(i)"><span class="checkbox" :class="{ checked: steps[checkKey(i)] }"><Check v-if="steps[checkKey(i)]" :size="13" /></span><span>{{ criterion }}</span></button><div class="checklist-footer"><span>체크는 이 기기에 저장됩니다.</span><button class="text-button" @click="page = 'notes'">실험 기록하기 <ChevronRight :size="14" /></button></div></section></div>
        <div class="mode-footnote"><CircleHelp :size="15" /><span v-if="mode === 'demo'">지금은 설명용 예시입니다. 실제 Broker에 메시지를 보내지 않습니다.</span><span v-else>실제 실습 환경의 수집값입니다. 이벤트는 앱의 관측 기록이며 Broker 내부의 모든 상태를 보여주지는 않습니다.</span></div>
      </template>

      <section v-if="page === 'guide' || (page === 'lab' && selected > 1)" class="guide-layout"><div><div class="question-banner"><span class="question-icon"><CircleHelp :size="22" /></span><div><span>이번 단계의 질문</span><strong>{{ phase.question }}</strong></div></div><section class="panel guide-panel"><h2>실험 순서</h2><ol class="experiment-steps"><li v-for="(step,i) in phase.steps" :key="step"><span>{{ String(i+1).padStart(2,'0') }}</span><div>{{ step }}</div></li></ol><div class="concept-callout"><BookOpen :size="20" /><div><strong>관찰할 때 기억하세요</strong><p>{{ phase.observe }}</p></div></div><template v-if="selected === 0"><h3>실습 환경 실행</h3><p>Docker Desktop이 실행 중인 PC에서 다운로드한 폴더를 엽니다.</p><pre class="code-block">python scripts/init_env.py
docker compose up --build</pre><p>로컬 화면: <code>http://localhost:5173</code><br>RabbitMQ 관리: <code>http://localhost:15672</code><br>API 설명: <code>http://localhost:8000/docs</code></p><a class="button primary" href="/messageflow-lab-starter.zip" download><Download :size="16" /> Phase 0~1 실습 패키지</a></template><template v-else-if="selected === 1"><h3>예측 → 확인</h3><div class="expected-grid"><div><span>3개 발행 후</span><strong>Ready 3 / Unacked 0</strong></div><div><span>Consumer 시작 후</span><strong>Ready 2 / Unacked 1</strong></div><div><span>세 메시지 모두 ACK 후</span><strong>Ready 0 / Unacked 0</strong></div></div><p class="hint">다른 Producer·Consumer가 없는 독립 실습 Queue를 기준으로 합니다.</p><button class="button primary" @click="page = 'lab'"><FlaskConical :size="16" /> 실험실 열기</button></template><div v-else class="future-notice"><Code2 :size="20" /><div><strong>이 단계의 실제 실습 기능은 이어서 구현합니다.</strong><p>Phase 0~1을 먼저 완료하고, 같은 환경 위에 기능을 추가합니다. 현재 화면은 학습 범위와 완료 기준을 안내합니다.</p></div></div></section></div><aside><section class="panel guide-panel"><h2>핵심 개념</h2><div class="concept-tags"><span v-for="concept in phase.concepts" :key="concept">{{ concept }}</span></div><h3>완료 기준</h3><button v-for="(criterion,i) in phase.criteria" :key="criterion" class="check-row" @click="toggleCheck(i)"><span class="checkbox" :class="{ checked: steps[checkKey(i)] }"><Check v-if="steps[checkKey(i)]" :size="13" /></span><span>{{ criterion }}</span></button><p class="hint">현재 기기에 저장되는 자기 점검입니다.</p><a href="https://www.rabbitmq.com/tutorials/tutorial-one-python" target="_blank" rel="noopener noreferrer" class="resource-link">RabbitMQ Python 튜토리얼 <ExternalLink :size="14" /></a><a href="https://www.rabbitmq.com/docs/confirms" target="_blank" rel="noopener noreferrer" class="resource-link">ACK와 Publisher Confirm <ExternalLink :size="14" /></a></section><button v-if="selected < 12" class="next-phase" @click="selectPhase(selected + 1)"><span>다음 학습 단계<strong>{{ phases[selected + 1]?.title }}</strong></span><ChevronRight :size="20" /></button></aside></section>

      <section v-if="page === 'notes'" class="notes-layout"><div class="panel notes-panel"><div class="panel-heading"><h2><ClipboardList :size="18" /> Phase {{ selected }} 실험 기록</h2><button class="button secondary" @click="exportNotes"><Download :size="15" /> 전체 기록 내보내기</button></div><p class="notes-intro">결과를 먼저 맞히려 하지 말고, 예상과 실제 결과가 왜 다른지 기록해 보세요.</p><label for="prediction">01 · 실행 전 예측</label><textarea id="prediction" :value="currentNotes.prediction" rows="3" placeholder="Consumer 없이 메시지를 보내면 어떻게 될까요?" @input="updateNote('prediction', $event)"></textarea><label for="observation">02 · 실제 관찰</label><textarea id="observation" :value="currentNotes.observation" rows="4" placeholder="변경한 설정, Queue 숫자, 관측 이벤트를 기록하세요." @input="updateNote('observation', $event)"></textarea><label for="explanation">03 · 나의 설명</label><textarea id="explanation" :value="currentNotes.explanation" rows="4" placeholder="결과가 나온 이유를 자신의 말로 설명해 보세요." @input="updateNote('explanation', $event)"></textarea><div class="saved-note"><CheckCircle2 :size="15" /> 입력 내용은 이 기기에 자동 저장됩니다. 기기 간 공유는 되지 않습니다.</div></div><aside class="panel guide-panel"><h2>좋은 실험 기록</h2><p>한 번에 한 가지 조건을 바꾸세요.</p><p>관찰한 사실과 추측을 구분하세요.</p><p>Ready 0만으로 업무 성공을 판단하지 마세요.</p><p>다시 실행할 수 있도록 절차와 설정을 남기세요.</p></aside></section>

      <section v-if="page === 'connection'" class="connection-layout"><div class="panel connection-panel"><div class="panel-heading"><h2><Link2 :size="18" /> 실제 실습 환경 연결</h2><span class="small-badge">PHASE 0–1</span></div><p>Docker 실습 패키지의 FastAPI Gateway에 연결합니다. RabbitMQ 접속 정보는 서버에서 관리합니다.</p><label for="gateway">Gateway 주소</label><input id="gateway" v-model="gateway" type="url" placeholder="https://your-lab-gateway.example.com" :disabled="busy" /><label for="token">실습 토큰 · LAB_TOKEN</label><input id="token" v-model="token" type="password" autocomplete="off" placeholder="실습 환경의 .env 파일에서 확인" :disabled="busy" /><p class="hint">토큰은 브라우저 저장소에 저장하지 않습니다.</p><div class="button-row"><button class="button primary" :disabled="busy" @click="connect"><Link2 :size="15" /> {{ busy ? '연결 확인 중…' : '실제 환경 연결' }}</button><button class="button secondary" :disabled="busy" @click="switchDemo"><Unplug :size="15" /> 예시로 돌아가기</button></div><div class="concept-callout"><CircleHelp :size="20" /><div><strong>로컬 실습과 게시된 사이트</strong><p>로컬 실습은 패키지의 http://localhost:5173 화면에서 연결하세요. 게시된 사이트에서 연결하려면 접근 가능한 HTTPS Gateway와 이 사이트를 허용한 CORS 설정이 필요합니다.</p></div></div><p class="hint">연결을 해제하거나 예시 모드로 전환해도 실제 Consumer는 자동 종료되지 않습니다. 실험실의 멈춤 버튼으로 종료하세요.</p></div><aside class="panel guide-panel"><h2>실습 패키지</h2><p>RabbitMQ, FastAPI, Pika, Vue 화면을 함께 실행합니다.</p><ul class="package-list"><li><Check :size="15" /> 전용 RabbitMQ 계정·vhost</li><li><Check :size="15" /> 수동 ACK Consumer</li><li><Check :size="15" /> Queue 조회와 이벤트 기록</li><li><Check :size="15" /> 실행 안내와 검증 코드</li></ul><a class="button secondary" href="/messageflow-lab-starter.zip" download><Download :size="16" /> 실습 패키지 다운로드</a><button class="text-button setup-link" @click="selected = 0; page = 'guide'">환경 준비 안내 보기 <ChevronRight :size="14" /></button></aside></section>
      <footer class="main-footer"><span>MessageFlow Lab <span class="dot-divider">/</span> 직접 실험하며 배우는 메시징</span><span>RabbitMQ → Pika → Kombu → Celery</span></footer>
    </main>
    <div v-if="selectedEvent" class="modal-backdrop" @click.self="selectedEvent = null"><section class="trace-modal" role="dialog" aria-modal="true" aria-label="메시지 관측 이력" @keydown.esc="selectedEvent = null"><div class="panel-heading"><h2>메시지 관측 이력</h2><button class="icon-button" aria-label="이력 닫기" @click="selectedEvent = null"><X :size="20" /></button></div><code class="full-id">{{ selectedEvent.message_id }}</code><p class="hint">{{ mode === 'demo' ? '설명용 시뮬레이션에서 생성된 기록입니다.' : '실제 앱이 기록한 이벤트입니다. 기록되지 않은 Broker 내부 상태는 추정하지 않습니다.' }}</p><div v-for="e in trace" :key="e.event_id" class="trace-item"><span class="trace-dot"></span><div><strong>{{ eventLabels[e.event_type] || e.event_type }}</strong><code>{{ e.event_type }}</code><span>{{ time(e.timestamp) }} · {{ e.worker }}</span><span v-if="e.attempt_id">시도 {{ short(e.attempt_id) }}</span></div></div></section></div>
  </div>
</template>
