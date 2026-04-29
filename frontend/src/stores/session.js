// frontend/src/stores/session.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useSessionStore = defineStore('session', () => {
  const currentSessionId = ref(null)
  const sessionName = ref('')
  const segments = ref([])
  const isRecording = ref(false)
  const isConnected = ref(false)
  const elapsedMs = ref(0)
  const notes = ref('')

  let ws = null
  let timerInterval = null
  let notesSaveTimeout = null

  const elapsedFormatted = computed(() => {
    const total = Math.floor(elapsedMs.value / 1000)
    const m = Math.floor(total / 60).toString().padStart(2, '0')
    const s = (total % 60).toString().padStart(2, '0')
    return `${m}:${s}`
  })

  async function startSession(name) {
    const res = await axios.post('/api/sessions', { name })
    currentSessionId.value = res.data.id
    sessionName.value = name
    segments.value = []
    notes.value = ''
    elapsedMs.value = 0

    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    ws = new WebSocket(`${protocol}//${location.host}/ws/${res.data.id}`)

    ws.onopen = () => {
      isConnected.value = true
      isRecording.value = true
      timerInterval = setInterval(() => { elapsedMs.value += 100 }, 100)
    }

    const STATUS_PRIORITY = { interim: 0, translating: 1, done: 2 }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.status === 'remove') {
        segments.value = segments.value.filter(s => s.id !== data.id)
        return
      }
      const idx = segments.value.findIndex(s => s.id === data.id)
      if (idx >= 0) {
        const curP = STATUS_PRIORITY[segments.value[idx].status] ?? -1
        const newP = STATUS_PRIORITY[data.status] ?? -1
        if (newP >= curP) {
          segments.value[idx] = { ...segments.value[idx], ...data }
        }
        // stale interim arriving after translating/done → silently discard
      } else {
        segments.value.push({ ...data, is_starred: false })
      }
    }

    ws.onclose = () => {
      isConnected.value = false
      isRecording.value = false
      clearInterval(timerInterval)
    }

    ws.onerror = () => {
      isConnected.value = false
      isRecording.value = false
      clearInterval(timerInterval)
    }

    return res.data.id
  }

  function stopSession() {
    if (ws) ws.close()
    isRecording.value = false
  }

  async function toggleStar(segmentId) {
    const seg = segments.value.find(s => s.id === segmentId)
    if (!seg) return
    seg.is_starred = !seg.is_starred
    await axios.patch(`/api/segments/${segmentId}`, { is_starred: seg.is_starred })
  }

  function saveNotes(text) {
    notes.value = text
    clearTimeout(notesSaveTimeout)
    notesSaveTimeout = setTimeout(async () => {
      if (currentSessionId.value) {
        await axios.patch(`/api/sessions/${currentSessionId.value}`, { notes: text })
      }
    }, 1000)
  }

  function _sendAudio(buffer) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(buffer)
    }
  }

  return {
    currentSessionId, sessionName, segments, isRecording, isConnected,
    elapsedMs, elapsedFormatted, notes,
    startSession, stopSession, toggleStar, saveNotes, _sendAudio,
  }
})
