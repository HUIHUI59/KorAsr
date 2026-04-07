<template>
  <div class="history-item" @click="$emit('select', session.id)">
    <div class="info">
      <div class="title">{{ session.name }}</div>
      <div class="meta">
        {{ formatDate(session.started_at) }} · {{ session.duration_seconds ? Math.floor(session.duration_seconds / 60) + ' min' : 'In progress' }} · {{ session.segment_count }} segments
      </div>
    </div>
    <div class="actions" @click.stop>
      <span class="tag" :class="session.summary ? 'done' : 'pending'">
        {{ session.summary ? '✦ Summarized' : 'Pending' }}
      </span>
      <a :href="`/api/sessions/${session.id}/export?format=md`" class="btn-export" download>MD</a>
      <a :href="`/api/sessions/${session.id}/export?format=txt`" class="btn-export" download>TXT</a>
      <button class="btn-delete" @click="$emit('delete', session.id)">Delete</button>
    </div>
  </div>
</template>

<script setup>
defineProps(['session'])
defineEmits(['select', 'delete'])
function formatDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.history-item {
  padding: 14px 20px; border-bottom: 1px solid #f5f5f5; cursor: pointer;
  display: flex; align-items: center; gap: 16px;
}
.history-item:hover { background: #fafafa; }
.info { flex: 1; }
.title { font-size: 15px; font-weight: 600; }
.meta { font-size: 12px; color: #888; margin-top: 4px; }
.actions { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }
.tag { font-size: 11px; padding: 3px 8px; border-radius: 10px; }
.tag.done { background: #e8f5e9; color: #2e7d32; }
.tag.pending { background: #fff3e0; color: #e65100; }
.btn-export { font-size: 12px; padding: 4px 10px; border-radius: 8px; background: #f0f0f5; color: #333; text-decoration: none; }
.btn-delete { font-size: 12px; padding: 4px 10px; border-radius: 8px; background: #fff0f0; color: #ff3b30; border: none; cursor: pointer; }
</style>
