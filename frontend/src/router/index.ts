import { createRouter, createWebHistory } from 'vue-router'
import PlaceholderView from '../views/PlaceholderView.vue'
import LoginView from '../views/LoginView.vue'
import JobsView from '../views/JobsView.vue'
import CandidatesView from '../views/CandidatesView.vue'
import { session } from '../api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/jobs' },
    { path: '/login', component: LoginView, meta: { title: '登录', public: true } },
    { path: '/dashboard', redirect: '/jobs' },
    { path: '/jobs', component: JobsView, meta: { title: '岗位管理' } },
    { path: '/talents', component: CandidatesView, meta: { title: '人才库' } },
    { path: '/evidence', component: PlaceholderView, meta: { title: '公开证据核验', description: '围绕候选人经历整理来源、证据与待核实信息', icon: 'Search', features: ['证据来源管理', '原文与结论关联', '证据等级与人工复核'] } },
    { path: '/assessment', component: PlaceholderView, meta: { title: '人才评估', description: '基于岗位要求与可追溯证据辅助 HR 进行人才评估', icon: 'DataAnalysis', features: ['岗位匹配分析', '多维能力评估', '风险与待核实项'] } },
    { path: '/interviews', component: PlaceholderView, meta: { title: 'AI 面试室', description: '管理面试安排、面试过程与候选人回答', icon: 'ChatDotRound', features: ['面试授权确认', '文字 / 语音交互', '面试过程记录'] } },
    { path: '/reports', component: PlaceholderView, meta: { title: '面试报告', description: '汇总面试记录、回答证据与 HR 复核意见', icon: 'Document', features: ['面试摘要', '能力维度总结', 'HR 备注与复核'] } },
  ],
})
router.beforeEach(to => {
  if (!to.meta.public && !session.get()) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.path === '/login' && session.get()) return '/jobs'
})
export default router
