<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const title = computed(() => String(route.meta.title || '功能模块'))
const description = computed(() => String(route.meta.description || ''))
const features = computed(() => (route.meta.features as string[] | undefined) || [])
const iconName = computed(() => String(route.meta.icon || 'Grid'))
</script>
<template>
  <div class="placeholder-page">
    <div class="eyebrow"><i></i>TTC WORKSPACE</div>
    <div class="placeholder-card">
      <div class="placeholder-icon"><el-icon><component :is="iconName" /></el-icon></div>
      <el-tag type="warning" effect="light" round>模块建设中</el-tag>
      <h1>{{title}}</h1><p>{{description}}</p>
      <div class="placeholder-divider"></div><h3>规划中的功能</h3>
      <div class="feature-grid"><div v-for="(feature,i) in features" :key="feature"><b>{{String(i+1).padStart(2,'0')}}</b>{{feature}}</div></div>
      <small>当前版本优先交付招聘工作台。该模块已预留导航入口，待业务接口确认后逐步接入。</small>
    </div>
  </div>
</template>
