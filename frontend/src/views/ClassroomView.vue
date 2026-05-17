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

    <!-- Desktop: feed + polish stacked vertically | notes on right -->
    <div class="desktop-layout" v-if="!isMobile">
      <div class="feed-column">
        <TranscriptFeed :segments="store.segments" @star="store.toggleStar" class="feed-panel" />
        <PolishFeed :chunks="store.polishChunks" class="polish-panel" />
      </div>
      <NotesPad v-model="notesModel" class="notes-panel" />
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
.desktop-layout { display: flex; flex: 1; overflow: hidden; min-height: 0; }
.feed-column { flex: 0 0 65%; display: flex; flex-direction: column; min-height: 0; }
.feed-panel { flex: 1 1 60%; display: flex; flex-direction: column; min-height: 0; }
.polish-panel { flex: 1 1 40%; display: flex; flex-direction: column; min-height: 0; }
.notes-panel { flex: 0 0 35%; display: flex; flex-direction: column; min-height: 0; }
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
