<template>
  <div class="polish-feed">
    <div class="header">
      <span class="title">✨ 精修翻译</span>
    </div>
    <div class="chunks" ref="chunksEl">
      <div v-if="chunks.length === 0" class="empty">
        会话开始后每 60 秒生成一段精修翻译…
      </div>
      <div v-for="c in chunks" :key="c.id" class="chunk">
        <div class="chunk-meta">
          #{{ c.chunkIndex + 1 }}
          <span class="seg-range">segments {{ c.startSeq }}–{{ c.endSeq }}</span>
        </div>
        <div class="chunk-zh">{{ c.zh }}</div>
        <details class="chunk-ko">
          <summary>原文 (韩)</summary>
          <div>{{ c.ko }}</div>
        </details>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
const props = defineProps(['chunks'])
const chunksEl = ref(null)

watch(() => props.chunks.length, async () => {
  await nextTick()
  if (chunksEl.value) chunksEl.value.scrollTop = chunksEl.value.scrollHeight
})
</script>

<style scoped>
.polish-feed { display: flex; flex-direction: column; height: 100%; border-top: 1px solid #f0f0f0; background: #fafafe; }
.header {
  padding: 8px 16px; background: #f4f3fa; border-bottom: 1px solid #ece9f5;
  display: flex; align-items: baseline; gap: 12px; flex-shrink: 0;
}
.title { font-size: 14px; font-weight: 700; color: #5856d6; }
.chunks { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
.empty { color: #aaa; text-align: center; margin-top: 20px; font-style: italic; font-size: 13px; }
.chunk {
  padding: 12px 14px; border-radius: 12px; background: #fff;
  border-left: 4px solid #aa3bff;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.chunk-meta { font-size: 11px; color: #aa3bff; font-weight: 600; margin-bottom: 6px; }
.seg-range { color: #c7c7cc; font-weight: 400; margin-left: 8px; }
.chunk-zh { font-size: 18px; line-height: 1.7; color: #1c1c1e; white-space: pre-wrap; }
.chunk-ko { margin-top: 8px; font-size: 12px; color: #8e8e93; }
.chunk-ko summary { cursor: pointer; user-select: none; outline: none; }
.chunk-ko summary:hover { color: #5856d6; }
.chunk-ko > div { margin-top: 6px; padding: 8px 10px; background: #f8f8fc; border-radius: 8px; line-height: 1.6; }
</style>
