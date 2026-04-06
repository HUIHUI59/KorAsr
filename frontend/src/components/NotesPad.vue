<template>
  <div class="notes-pad">
    <div class="header">
      <span>📝 Notes</span>
      <span class="saved-hint" v-if="savedHint">Saved</span>
    </div>
    <textarea
      class="editor"
      placeholder="Record key points, questions, ideas..."
      :value="modelValue"
      @input="onInput"
    ></textarea>
  </div>
</template>

<script setup>
import { ref } from 'vue'
const props = defineProps(['modelValue'])
const emit = defineEmits(['update:modelValue'])
const savedHint = ref(false)
let hintTimer = null

function onInput(e) {
  emit('update:modelValue', e.target.value)
  clearTimeout(hintTimer)
  savedHint.value = false
  hintTimer = setTimeout(() => { savedHint.value = true }, 1200)
}
</script>

<style scoped>
.notes-pad { display: flex; flex-direction: column; height: 100%; border-left: 1px solid #f0f0f0; }
.header {
  padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #f0f0f0;
  font-size: 13px; font-weight: 700; display: flex; justify-content: space-between;
}
.saved-hint { font-size: 12px; color: #34c759; font-weight: 400; }
.editor {
  flex: 1; padding: 14px 16px; border: none; outline: none; resize: none;
  font-size: 13px; line-height: 1.7; font-family: inherit; background: #fff;
}
</style>
