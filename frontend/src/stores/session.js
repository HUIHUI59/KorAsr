// frontend/src/stores/session.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export const useSessionStore = defineStore('session', () => {
  const currentSessionId = ref(null)
  const sessionName = ref('')
  const segments = ref([])
  const polishChunks = ref([])    // 60s 一批的 LLM 精修翻译块
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
    polishChunks.value = []
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
      // 精修块独立通道：60s 一批 LLM 重译，追加到 polishChunks
      if (data.status === 'polish') {
        polishChunks.value.push({
          id: data.id,
          chunkIndex: data.chunk_index,
          startSeq: data.start_segment_seq,
          endSeq: data.end_segment_seq,
          ko: data.ko_combined,
          zh: data.zh_polished,
          createdAt: data.created_at,
        })
        return
      }
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
    isRecording.value = false   // 立即让 ClassroomView 的 watch 关麦克风、不再 _sendAudio
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      try { ws && ws.close() } catch (_) {}
      return
    }
    // graceful 关闭：先发 stop 信号让 backend 跑完尾段 final/polish 推回来，再让 backend 主动 close
    try {
      ws.send(JSON.stringify({ action: 'stop' }))
    } catch (_) {
      ws.close()
      return
    }
    // 8s 兜底：backend 卡住就强制关
    const fallbackClose = setTimeout(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        console.warn('[WS] graceful stop timeout, force closing')
        try { ws.close() } catch (_) {}
      }
    }, 8000)
    const prevOnClose = ws.onclose
    ws.onclose = (e) => {
      clearTimeout(fallbackClose)
      prevOnClose && prevOnClose(e)
    }
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
    currentSessionId, sessionName, segments, polishChunks, isRecording, isConnected,
    elapsedMs, elapsedFormatted, notes,
    startSession, stopSession, toggleStar, saveNotes, _sendAudio,
  }
})
