<template>
  <div class="feed" ref="feedEl">
    <div v-if="segments.length === 0" class="empty">Waiting for audio input...</div>
    <div
      v-for="seg in segments"
      :key="seg.id"
      class="card"
      :class="seg.status"
    >
      <button class="star" :class="{ active: seg.is_starred }" @click="$emit('star', seg.id)">
        {{ seg.is_starred ? '★' : '☆' }}
      </button>
      <div class="ko">{{ seg.ko }}</div>
      <div class="zh" :class="{ pending: seg.status !== 'done' }">{{ seg.zh }}</div>
      <div class="ts">{{ formatTs(seg.timestamp_ms) }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
const props = defineProps(['segments'])
defineEmits(['star'])
const feedEl = ref(null)

watch(() => props.segments.length, async () => {
  await nextTick()
  if (feedEl.value) feedEl.value.scrollTop = feedEl.value.scrollHeight
})

function formatTs(ms) {
  if (ms === null || ms === undefined) return ''
  const total = Math.floor(ms / 1000)
  const m = Math.floor(total / 60).toString().padStart(2, '0')
  const s = (total % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}
</script>

<style scoped>
.feed { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.empty { color: #aaa; text-align: center; margin-top: 40px; font-style: italic; }
.card {
  padding: 12px 14px; border-radius: 12px; border-left: 4px solid #5856d6;
  background: #f8f8fc; animation: fadeUp .3s ease; position: relative;
}
.card.interim { border-left-color: #ff9500; background: #fffcf0; }
.card.translating { border-left-color: #5856d6; }
@keyframes fadeUp { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
.star { position: absolute; top: 10px; right: 12px; background: none; border: none; cursor: pointer; font-size: 16px; opacity: .4; }
.star.active { opacity: 1; }
.ko { font-size: 15px; font-weight: 600; line-height: 1.5; padding-right: 24px; }
.zh { font-size: 16px; color: #1c1c1e; margin-top: 4px; line-height: 1.55; }
.zh.pending { color: #aaa; font-style: italic; animation: blink 1s infinite alternate; }
@keyframes blink { 0%{opacity:1} 100%{opacity:.4} }
.ts { font-size: 11px; color: #c7c7cc; margin-top: 6px; }
</style>
