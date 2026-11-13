import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from '../views/DashboardView.vue'
import PlaceholderView from '../views/PlaceholderView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardView, meta: { title: '招聘工作台' } },
    { path: '/jobs', component: PlaceholderView, meta: { title: '岗位管理', description: '统一管理招聘岗位、岗位要求与招聘进度', icon: 'Briefcase', features: ['创建与编辑岗位', '岗位 JD 管理', '招聘进度跟踪'] } },
    { path: '/talents', component: PlaceholderView, meta: { title: '人才库', description: '集中查看候选人档案与人才流转状态', icon: 'User', features: ['候选人档案', '简历解析记录', '人才标签与搜索'] } },
    { path: '/evidence', component: PlaceholderView, meta: { title: '公开证据核验', description: '围绕候选人经历整理来源、证据与待核实信息', icon: 'Search', features: ['证据来源管理', '原文与结论关联', '证据等级与人工复核'] } },
    { path: '/assessment', component: PlaceholderView, meta: { title: '人才评估', description: '基于岗位要求与可追溯证据辅助 HR 进行人才评估', icon: 'DataAnalysis', features: ['岗位匹配分析', '多维能力评估', '风险与待核实项'] } },
    { path: '/interviews', component: PlaceholderView, meta: { title: 'AI 面试室', description: '管理面试安排、面试过程与候选人回答', icon: 'ChatDotRound', features: ['面试授权确认', '文字 / 语音交互', '面试过程记录'] } },
    { path: '/reports', component: PlaceholderView, meta: { title: '面试报告', description: '汇总面试记录、回答证据与 HR 复核意见', icon: 'Document', features: ['面试摘要', '能力维度总结', 'HR 备注与复核'] } },
  ],
})
export default router
