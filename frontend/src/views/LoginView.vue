<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, errorMessage, session } from '../api'

const router = useRouter()
const route = useRoute()
const form = reactive({ tenant_slug: '', email: '', password: '' })
const loading = ref(false)
async function submit() {
  if (!form.tenant_slug.trim() || !form.email.trim() || !form.password) return ElMessage.warning('请填写租户、邮箱和密码')
  loading.value = true
  try {
    const { data } = await api.post('/auth/login', form)
    session.set(data)
    const { data: user } = await api.get('/me')
    if (!['hr', 'admin'].includes(user.role)) {
      session.clear()
      return ElMessage.error('当前工作台仅支持 HR 或管理员账号')
    }
    await router.replace(typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') && !route.query.redirect.startsWith('//') ? route.query.redirect : '/jobs')
  } catch (error) { session.clear(); ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}
</script>

<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h1>TTC · 才多对</h1>
      <p>登录招聘工作空间</p>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="租户标识"><el-input v-model="form.tenant_slug" autocomplete="organization" placeholder="请输入租户 slug" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" type="email" autocomplete="username" placeholder="请输入邮箱" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="current-password" placeholder="请输入密码" /></el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" style="width:100%">登录</el-button>
      </el-form>
      <small>没有账号？请联系管理员在对应租户中创建账号。</small>
    </el-card>
  </div>
</template>
