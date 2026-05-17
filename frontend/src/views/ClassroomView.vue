<template>
  <div class="classroom">
    <StatusBar
      :is-recording="store.isRecording"
      :is-connected="store.isConnected"
      :session-name="store.sessionName"
      :elapsed-formatted="store.elapsedFormatted"
      @start="onStart"
      @stop="onStop"
      @summary="onSummary"
      @rename="onRename"
    />

    <!-- Desktop: Live | splitter | Polish, with Notes drawer slide-in -->
    <div class="desktop-layout" v-if="!isMobile" ref="layoutRef">
      <div class="pane live-pane" :style="{ flexBasis: livePercent + '%' }">
        <TranscriptFeed :segments="store.segments" @star="store.toggleStar" />
      </div>
      <div
        class="splitter"
        :class="{ dragging: isDragging }"
        @mousedown="onSplitterDown"
        @dblclick="resetSplitter"
        title="拖动调宽 / 双击重置 50:50"
      ></div>
      <div class="pane polish-pane" :style="{ flexBasis: (100 - livePercent) + '%' }">
        <PolishFeed :chunks="store.polishChunks" />
      </div>

      <div class="notes-drawer" :class="{ open: notesOpen }">
        <div class="drawer-header">
          <span class="drawer-title">📝 笔记</span>
          <button class="drawer-close" @click="notesOpen = false" title="关闭">✕</button>
        </div>
        <NotesPad v-model="notesModel" style="flex:1" />
      </div>

      <button
        class="notes-toggle"
        :class="{ open: notesOpen }"
        @click="notesOpen = !notesOpen"
        :title="notesOpen ? '关闭笔记' : '打开笔记'"
      >
        {{ notesOpen ? '✕' : '📝' }}
      </button>
    </div>

    <!-- Mobile: tab layout (含精修 tab) -->
    <div class="mobile-layout" v-else>
      <div class="tab-bar">
        <button :class="{ active: activeTab === 'feed' }" @click="activeTab = 'feed'">Live</button>
        <button :class="{ active: activeTab === 'polish' }" @click="activeTab = 'polish'">✨ Polish</button>
        <button :class="{ active: activeTab === 'notes' }" @click="activeTab = 'notes'">Notes</button>
      </div>
      <div class="tab-content">
        <TranscriptFeed v-if="activeTab === 'feed'" :segments="store.segments" @star="store.toggleStar" />
        <PolishFeed v-else-if="activeTab === 'polish'" :chunks="store.polishChunks" />
        <NotesPad v-else v-model="notesModel" style="flex:1" />
      </div>
    </div>

    <!-- Start modal -->
    <div class="start-modal" v-if="showStartModal" @click.self="showStartModal = false">
      <div class="modal-card">
        <h3>New Session</h3>
        <input v-model="newSessionName" placeholder="e.g. Economics Lecture Apr 7" @keyup.enter="confirmStart" autofocus />
        <div class="modal-btns">
          <button class="btn-cancel" @click="showStartModal = false">Cancel</button>
          <button class="btn-confirm" @click="confirmStart">Start</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { useSessionStore } from '../stores/session.js'
import StatusBar from '../components/StatusBar.vue'
import TranscriptFeed from '../components/TranscriptFeed.vue'
import PolishFeed from '../components/PolishFeed.vue'
import NotesPad from '../components/NotesPad.vue'

const store = useSessionStore()
const isMobile = ref(window.innerWidth < 768)
function _onResize() { isMobile.value = window.innerWidth < 768 }
onMounted(() => window.addEventListener('resize', _onResize))
onUnmounted(() => window.removeEventListener('resize', _onResize))
const activeTab = ref('feed')
const showStartModal = ref(false)
const newSessionName = ref('')

// --- desktop layout state: splitter + notes drawer (persisted) ---
const LS_LIVE_PCT = 'korasr.livePercent'
const LS_NOTES_OPEN = 'korasr.notesOpen'
const _storedPct = parseFloat(localStorage.getItem(LS_LIVE_PCT))
const livePercent = ref(Number.isFinite(_storedPct) && _storedPct >= 20 && _storedPct <= 80 ? _storedPct : 50)
const notesOpen = ref(localStorage.getItem(LS_NOTES_OPEN) === '1')
watch(notesOpen, (v) => localStorage.setItem(LS_NOTES_OPEN, v ? '1' : '0'))

const layoutRef = ref(null)
const isDragging = ref(false)
function onSplitterDown(e) {
  e.preventDefault()
  isDragging.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onSplitterMove)
  document.addEventListener('mouseup', onSplitterUp)
}
function onSplitterMove(e) {
  if (!isDragging.value || !layoutRef.value) return
  const rect = layoutRef.value.getBoundingClientRect()
  // Notes drawer (when open) eats some right-edge width; splitter percent is of Live+Polish region only.
  const drawerWidth = notesOpen.value ? Math.min(360, window.innerWidth * 0.35) : 0
  const livePolishWidth = rect.width - drawerWidth - 6 // 6 = splitter width
  const xRelative = e.clientX - rect.left
  let pct = (xRelative / livePolishWidth) * 100
  pct = Math.max(20, Math.min(80, pct))
  livePercent.value = pct
}
function onSplitterUp() {
  if (!isDragging.value) return
  isDragging.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  document.removeEventListener('mousemove', onSplitterMove)
  document.removeEventListener('mouseup', onSplitterUp)
  localStorage.setItem(LS_LIVE_PCT, String(Math.round(livePercent.value)))
}
function resetSplitter() {
  livePercent.value = 50
  localStorage.setItem(LS_LIVE_PCT, '50')
}
onUnmounted(() => {
  document.removeEventListener('mousemove', onSplitterMove)
  document.removeEventListener('mouseup', onSplitterUp)
})

const notesModel = computed({
  get: () => store.notes,
  set: (v) => store.saveNotes(v),
})

function onStart() {
  const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric' })
  newSessionName.value = `Lecture ${today}`
  showStartModal.value = true
}

async function confirmStart() {
  if (!newSessionName.value.trim()) return
  showStartModal.value = false
  await store.startSession(newSessionName.value.trim())
  await startMicrophone()
}

async function startMicrophone() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const ctx = new AudioContext({ sampleRate: 16000 })
    const source = ctx.createMediaStreamSource(stream)
    const processor = ctx.createScriptProcessor(4096, 1, 1)
    source.connect(processor)
    processor.connect(ctx.destination)

    processor.onaudioprocess = (e) => {
      store._sendAudio(e.inputBuffer.getChannelData(0).buffer)
    }

    const unwatchRecording = watch(() => store.isRecording, (v) => {
      if (!v) {
        processor.disconnect()
        stream.getTracks().forEach(t => t.stop())
        ctx.close()
        unwatchRecording()
      }
    })
  } catch (e) {
    if (!navigator.mediaDevices) {
      alert('Microphone unavailable.\n\nBrowser blocks microphone on HTTP. Use one of:\n• http://localhost:8000 (on this machine)\n• https://... via Tailscale')
    } else {
      alert('Microphone access failed: ' + e.message)
    }
  }
}

function onStop() { store.stopSession() }

function onRename(name) {
  if (store.currentSessionId) {
    axios.patch(`/api/sessions/${store.currentSessionId}`, { name })
  }
}

async function onSummary() {
  if (!store.currentSessionId) return
  try {
    const res = await axios.post(`/api/sessions/${store.currentSessionId}/summary`)
    alert('AI Summary generated!\n\n' + res.data.summary.substring(0, 300) + (res.data.summary.length > 300 ? '...' : ''))
  } catch (e) {
    alert('Summary failed: ' + e.message)
  }
}
</script>

<style scoped>
.classroom { display: flex; flex-direction: column; height: 100vh; height: 100dvh; }
.desktop-layout { display: flex; flex: 1; overflow: hidden; min-height: 0; position: relative; }
.pane {
  display: flex; flex-direction: column; min-height: 0; min-width: 200px;
  flex-grow: 0; flex-shrink: 1;
}
.splitter {
  flex: 0 0 6px; cursor: col-resize; background: #ece9f5;
  transition: background 0.15s ease; position: relative; z-index: 1;
}
.splitter:hover, .splitter.dragging { background: #5856d6; }
.splitter::before {
  content: ''; position: absolute; top: 50%; left: -3px; transform: translateY(-50%);
  width: 12px; height: 36px; border-radius: 6px;
}

.notes-drawer {
  width: 0; transition: width 0.25s ease;
  display: flex; flex-direction: column;
  background: #fafafe; border-left: 1px solid #ece9f5; overflow: hidden;
  flex: 0 0 auto;
}
.notes-drawer.open { width: min(360px, 35vw); }
.drawer-header {
  padding: 10px 16px; border-bottom: 1px solid #ece9f5; background: #f4f3fa;
  display: flex; align-items: center; justify-content: space-between; flex-shrink: 0;
}
.drawer-title { font-size: 14px; font-weight: 700; color: #5856d6; }
.drawer-close {
  background: none; border: none; cursor: pointer; font-size: 16px; color: #8e8e93;
  padding: 4px 8px; border-radius: 6px;
}
.drawer-close:hover { background: #ece9f5; color: #1c1c1e; }

.notes-toggle {
  position: absolute; top: 12px; right: 12px; z-index: 10;
  width: 40px; height: 40px; border: none; border-radius: 20px;
  background: #5856d6; color: #fff; font-size: 18px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(88,86,214,.3);
  display: flex; align-items: center; justify-content: center;
  transition: transform 0.2s ease, background 0.2s ease;
}
.notes-toggle:hover { transform: scale(1.05); }
.notes-toggle.open {
  background: #fff; color: #5856d6; border: 1px solid #ece9f5;
  right: calc(min(360px, 35vw) + 12px);
}

.mobile-layout { display: flex; flex-direction: column; flex: 1; overflow: hidden; min-height: 0; }
.tab-bar { display: flex; border-bottom: 1px solid #f0f0f0; flex-shrink: 0; }
.tab-bar button { flex: 1; padding: 10px; border: none; background: #fafafa; font-size: 13px; font-weight: 600; cursor: pointer; }
.tab-bar button.active { background: #fff; color: #5856d6; border-bottom: 2px solid #5856d6; }
.tab-content { flex: 1; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }

.start-modal {
  position: fixed; inset: 0; background: rgba(0,0,0,.4);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal-card { background: #fff; border-radius: 16px; padding: 24px; width: 320px; }
.modal-card h3 { margin: 0 0 16px; font-size: 17px; }
.modal-card input {
  width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 10px;
  font-size: 14px; outline: none; box-sizing: border-box;
}
.modal-btns { display: flex; gap: 10px; margin-top: 16px; justify-content: flex-end; }
.btn-cancel { padding: 8px 16px; border: none; background: #f0f0f5; border-radius: 10px; cursor: pointer; }
.btn-confirm { padding: 8px 16px; border: none; background: #5856d6; color: #fff; border-radius: 10px; cursor: pointer; font-weight: 600; }
</style>
