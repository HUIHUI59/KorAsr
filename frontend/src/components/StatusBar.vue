<template>
  <div class="status-bar">
    <div class="left">
      <span class="dot" :class="{ active: isRecording, error: !isConnected && !isRecording }"></span>
      <input
        v-if="isRecording"
        class="session-name-input"
        :value="sessionName"
        @blur="$emit('rename', $event.target.value)"
      />
      <span v-else class="session-name">{{ sessionName || 'No active session' }}</span>
      <span v-if="isRecording" class="timer">{{ elapsedFormatted }}</span>
    </div>
    <div class="right">
      <button v-if="!isRecording" class="btn btn-start" @click="$emit('start')">Start</button>
      <template v-else>
        <button class="btn btn-summary" @click="$emit('summary')">✦ AI Summary</button>
        <button class="btn btn-stop" @click="$emit('stop')">■ Stop</button>
      </template>
      <router-link to="/history" class="btn btn-history">History</router-link>
    </div>
  </div>
</template>

<script setup>
defineProps(['isRecording', 'isConnected', 'sessionName', 'elapsedFormatted'])
defineEmits(['start', 'stop', 'summary', 'rename'])
</script>

<style scoped>
.status-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; background: #fff; border-bottom: 1px solid #f0f0f0;
  position: sticky; top: 0; z-index: 10;
}
.left { display: flex; align-items: center; gap: 10px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #8e8e93; }
.dot.active { background: #34c759; box-shadow: 0 0 6px #34c759; animation: pulse 1.5s infinite; }
.dot.error { background: #ff3b30; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.session-name { font-weight: 600; font-size: 15px; }
.session-name-input {
  font-weight: 600; font-size: 15px; border: none; outline: none;
  border-bottom: 1px dashed #ccc; background: transparent; min-width: 200px;
}
.timer { font-size: 13px; color: #888; font-family: monospace; }
.right { display: flex; gap: 8px; }
.btn { padding: 7px 14px; border-radius: 10px; border: none; cursor: pointer; font-size: 13px; font-weight: 600; text-decoration: none; }
.btn-start { background: #5856d6; color: #fff; }
.btn-stop { background: #ff3b30; color: #fff; }
.btn-summary { background: #f0f0f5; color: #5856d6; }
.btn-history { background: #f0f0f5; color: #333; }
</style>
