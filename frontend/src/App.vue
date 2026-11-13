<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const collapsed = ref(false)
const title = computed(() => String(route.meta.title || '招聘工作台'))
const groups = [
  { label: '工作空间', items: [
    { label: '招聘工作台', path: '/dashboard', icon: 'DataBoard' },
    { label: '岗位管理', path: '/jobs', icon: 'Briefcase' },
    { label: '人才库', path: '/talents', icon: 'User' },
  ]},
  { label: 'AI 招聘能力', items: [
    { label: '公开证据核验', path: '/evidence', icon: 'Search' },
    { label: '人才评估', path: '/assessment', icon: 'DataAnalysis' },
    { label: 'AI 面试室', path: '/interviews', icon: 'ChatDotRound' },
    { label: '面试报告', path: '/reports', icon: 'Document' },
  ]},
]
</script>

<template>
  <div class="app-shell" :class="{ compact: collapsed }">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">T</div>
        <div v-if="!collapsed" class="brand-copy">
          <div class="brand-name">TTC <span>才多对</span></div>
          <div class="brand-sub">TALENT TRUST & CONNECT</div>
        </div>
        <button class="collapse-btn" @click="collapsed = !collapsed" :title="collapsed ? '展开导航' : '收起导航'">
          <el-icon><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
        </button>
      </div>
      <div v-if="!collapsed" class="workspace-label">招聘管理中心</div>
      <nav class="side-nav">
        <section v-for="group in groups" :key="group.label" class="nav-group">
          <div v-if="!collapsed" class="nav-group-title">{{ group.label }}</div>
          <router-link v-for="item in group.items" :key="item.path" :to="item.path"
            class="nav-link" :class="{ active: route.path === item.path }" :title="collapsed ? item.label : ''">
            <el-icon><component :is="item.icon" /></el-icon>
            <span v-if="!collapsed">{{ item.label }}</span>
          </router-link>
        </section>
      </nav>
      <div class="sidebar-bottom">
        <div v-if="!collapsed" class="help-card">
          <div class="help-symbol"><el-icon><Service /></el-icon></div>
          <div><strong>需要帮助？</strong><span>查看产品使用指南</span></div>
          <el-icon class="help-arrow"><ArrowRight /></el-icon>
        </div>
        <div class="profile">
          <el-avatar :size="35">HR</el-avatar>
          <div v-if="!collapsed" class="profile-copy"><strong>招聘管理员</strong><span>企业工作空间</span></div>
          <el-icon v-if="!collapsed" class="profile-more"><MoreFilled /></el-icon>
        </div>
      </div>
    </aside>

    <div class="main-shell">
      <header class="topbar">
        <div class="breadcrumb"><span>工作空间</span><el-icon><ArrowRight /></el-icon><strong>{{ title }}</strong></div>
        <div class="topbar-right">
          <div class="system-state"><i></i>系统运行正常</div>
          <button class="icon-btn" aria-label="通知"><el-icon><Bell /></el-icon><b></b></button>
          <div class="top-divider"></div>
          <el-avatar :size="34">HR</el-avatar>
          <div class="top-profile"><strong>招聘管理员</strong><span>管理员</span></div>
          <el-icon class="muted"><ArrowDown /></el-icon>
        </div>
      </header>
      <main class="content">
        <router-view />
        <footer class="footer"><span>© 2026 TTC · Talent Trust & Connect</span><span>AI 辅助决策 · 人工最终复核</span></footer>
      </main>
    </div>
  </div>
</template>
