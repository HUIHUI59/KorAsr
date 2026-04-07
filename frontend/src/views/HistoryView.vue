<template>
  <div class="history-view">
    <div class="header">
      <router-link to="/" class="back-btn">← Back</router-link>
      <h2>Session History</h2>
      <input v-model="search" placeholder="Search sessions..." class="search" />
    </div>

    <!-- Session list -->
    <div class="list" v-if="!selectedSession">
      <SessionHistory
        v-for="sess in filteredSessions"
        :key="sess.id"
        :session="sess"
        @select="loadSession"
        @delete="deleteSession"
      />
      <div v-if="filteredSessions.length === 0" class="empty">No sessions found</div>
    </div>

    <!-- Session detail -->
    <div class="detail" v-else>
      <div class="detail-header">
        <button @click="selectedSession = null" class="back-btn">← Back to list</button>
        <h3>{{ selectedSession.session.name }}</h3>
        <button class="btn-summary" @click="triggerSummary" :disabled="summaryLoading">
          {{ summaryLoading ? 'Generating...' : '✦ AI Summary' }}
        </button>
      </div>

      <div class="detail-body">
        <div class="segments">
          <div
            v-for="seg in selectedSession.segments"
            :key="seg.id"
            class="seg-card"
            :class="{ starred: seg.is_starred }"
          >
            <span class="seg-ts">{{ formatTs(seg.timestamp_ms) }}</span>
            <div class="seg-ko">{{ seg.ko_text }}</div>
            <div class="seg-zh">{{ seg.zh_text }}</div>
          </div>
        </div>
        <div class="summary-panel" v-if="selectedSession.session.summary">
          <h4>AI Summary</h4>
          <pre class="summary-content">{{ selectedSession.session.summary }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import SessionHistory from '../components/SessionHistory.vue'

const sessions = ref([])
const search = ref('')
const selectedSession = ref(null)
const summaryLoading = ref(false)

const filteredSessions = computed(() =>
  sessions.value.filter(s => s.name.toLowerCase().includes(search.value.toLowerCase()))
)

onMounted(async () => {
  const res = await axios.get('/api/sessions')
  sessions.value = res.data
})

async function loadSession(id) {
  const res = await axios.get(`/api/sessions/${id}`)
  selectedSession.value = res.data
}

async function deleteSession(id) {
  if (!confirm('Delete this session? This cannot be undone.')) return
  await axios.delete(`/api/sessions/${id}`)
  sessions.value = sessions.value.filter(s => s.id !== id)
}

async function triggerSummary() {
  if (!selectedSession.value) return
  summaryLoading.value = true
  try {
    const res = await axios.post(`/api/sessions/${selectedSession.value.session.id}/summary`)
    selectedSession.value.session.summary = res.data.summary
  } finally {
    summaryLoading.value = false
  }
}

function formatTs(ms) {
  if (ms === null || ms === undefined) return ''
  const t = Math.floor(ms / 1000)
  return `${Math.floor(t / 60).toString().padStart(2, '0')}:${(t % 60).toString().padStart(2, '0')}`
}
</script>

<style scoped>
.history-view { display: flex; flex-direction: column; min-height: 100vh; }
.header {
  padding: 16px 20px; background: #fff; border-bottom: 1px solid #f0f0f0;
  display: flex; align-items: center; gap: 16px; position: sticky; top: 0; z-index: 5;
}
.header h2 { margin: 0; font-size: 18px; }
.back-btn { font-size: 14px; color: #5856d6; text-decoration: none; border: none; background: none; cursor: pointer; }
.search { margin-left: auto; padding: 7px 12px; border: 1px solid #ddd; border-radius: 10px; font-size: 13px; outline: none; }
.empty { text-align: center; padding: 40px; color: #aaa; font-style: italic; }
.list { flex: 1; }

.detail-header {
  padding: 14px 20px; background: #fff; border-bottom: 1px solid #f0f0f0;
  display: flex; align-items: center; gap: 16px;
}
.detail-header h3 { margin: 0; flex: 1; font-size: 16px; }
.btn-summary { padding: 7px 14px; background: #5856d6; color: #fff; border: none; border-radius: 10px; cursor: pointer; font-weight: 600; font-size: 13px; }
.btn-summary:disabled { opacity: 0.5; cursor: not-allowed; }
.detail-body { display: flex; flex: 1; overflow: hidden; height: calc(100vh - 61px); }
.segments { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.seg-card { padding: 10px 12px; border-radius: 10px; background: #f8f8fc; border-left: 3px solid #5856d6; }
.seg-card.starred { border-left-color: #ff9500; background: #fffcf0; }
.seg-ts { font-size: 11px; color: #c7c7cc; }
.seg-ko { font-size: 14px; font-weight: 600; margin-top: 3px; }
.seg-zh { font-size: 13px; color: #636366; margin-top: 3px; }
.summary-panel { width: 320px; border-left: 1px solid #f0f0f0; padding: 16px; overflow-y: auto; }
.summary-panel h4 { margin: 0 0 12px; font-size: 14px; color: #5856d6; }
.summary-content { font-size: 13px; line-height: 1.7; white-space: pre-wrap; margin: 0; font-family: inherit; }
</style>
