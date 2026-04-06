// frontend/src/router/index.js
import { createRouter, createWebHistory } from 'vue-router'
import ClassroomView from '../views/ClassroomView.vue'
import HistoryView from '../views/HistoryView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: ClassroomView },
    { path: '/history', component: HistoryView },
  ],
})
