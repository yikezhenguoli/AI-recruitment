<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, errorMessage, type Job } from '../api'

const items = ref<Job[]>([])
const selected = ref<Job | null>(null)
const detailVisible = ref(false)
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const editing = ref(false)
const form = reactive({ title: '', department: '', headcount: null as number | null, jd_text: '' })
const jdText = ref('')
const jdSaving = ref(false)
const generating = ref(false)
const labels: Record<string, string> = { draft: '草稿', published: '已发布', locked: '已锁定', archived: '已归档' }

async function load() {
  loading.value = true
  try { items.value = (await api.get<{ items: Job[] }>('/jobs', { params: { limit: 100 } })).data.items }
  catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}
async function detail(id: string) {
  try {
    selected.value = (await api.get<Job>(`/jobs/${id}`)).data
    jdText.value = selected.value.current_version?.jd_text || ''
    detailVisible.value = true
  }
  catch (error) { ElMessage.error(errorMessage(error)) }
}
function openCreate() {
  editing.value = false
  Object.assign(form, { title: '', department: '', headcount: null, jd_text: '' })
  dialog.value = true
}
function openEdit() {
  if (!selected.value) return
  editing.value = true
  Object.assign(form, { title: selected.value.title, department: selected.value.department || '', headcount: selected.value.headcount, jd_text: '' })
  dialog.value = true
}
async function save() {
  if (!form.title.trim()) return ElMessage.warning('请填写岗位名称')
  if (!editing.value && form.jd_text && form.jd_text.length < 20) return ElMessage.warning('岗位描述至少 20 字')
  saving.value = true
  try {
    const body = { title: form.title.trim(), department: form.department.trim() || null, headcount: form.headcount }
    if (editing.value && selected.value) {
      await api.patch(`/jobs/${selected.value.id}`, body, { headers: { 'If-Match': selected.value.updated_at } })
      await detail(selected.value.id)
    } else {
      const { data } = await api.post('/jobs', { ...body, jd_text: form.jd_text.trim() || null })
      await detail(data.id)
    }
    dialog.value = false
    await load()
    ElMessage.success('岗位已保存')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { saving.value = false }
}
async function publish() {
  if (!selected.value) return
  try {
    await ElMessageBox.confirm('确认发布当前岗位？发布前需有岗位描述。', '发布岗位')
    await api.post(`/jobs/${selected.value.id}/publish`)
    await detail(selected.value.id)
    await load()
    ElMessage.success('岗位已发布')
  } catch (error) { if (error !== 'cancel') ElMessage.error(errorMessage(error)) }
}
async function saveJd() {
  if (!selected.value || jdText.value.trim().length < 20) return ElMessage.warning('岗位描述至少 20 字')
  jdSaving.value = true
  try {
    const id = selected.value.id
    const { data } = await api.post(`/jobs/${id}/jd/versions`, {
      jd_text: jdText.value.trim(), structured: { role_title: selected.value.title },
    })
    await api.post(`/jobs/${id}/jd/versions/${data.id}/select`)
    await detail(id); await load(); ElMessage.success('JD 版本已选用')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { jdSaving.value = false }
}
async function generateJd() {
  if (!selected.value || jdText.value.trim().length < 10) return ElMessage.warning('请填写至少 10 字的生成要求')
  generating.value = true
  try {
    const id = selected.value.id
    const { data } = await api.post(`/jobs/${id}/jd/generate`, { prompt: jdText.value.trim(), variants: 1 })
    const version = data.versions?.[0]
    if (!version) throw new Error('模型未生成可用的岗位描述')
    await api.post(`/jobs/${id}/jd/versions/${version.id}/select`)
    await detail(id); await load(); ElMessage.success('AI 生成的 JD 已选用，请人工复核')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { generating.value = false }
}
onMounted(load)
</script>

<template>
  <section class="api-page">
    <div class="api-heading"><div><h1>岗位管理</h1><p>岗位数据来自招聘系统，未配置的描述不会自动生成。</p></div><el-button type="primary" @click="openCreate">创建岗位</el-button></div>
    <el-card>
      <el-table v-loading="loading" :data="items" row-key="id" empty-text="暂无岗位，点击右上角创建" @row-click="(row: Job) => detail(row.id)">
        <el-table-column prop="title" label="岗位" min-width="200" />
        <el-table-column prop="department" label="部门" min-width="140"><template #default="{ row }">{{ row.department || '—' }}</template></el-table-column>
        <el-table-column prop="headcount" label="计划人数" width="115"><template #default="{ row }">{{ row.headcount ?? '—' }}</template></el-table-column>
        <el-table-column label="状态" width="115"><template #default="{ row }"><el-tag>{{ labels[row.status] || row.status }}</el-tag></template></el-table-column>
        <el-table-column label="创建时间" width="190"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="{ row }"><el-button link type="primary" @click.stop="detail(row.id)">查看</el-button></template></el-table-column>
      </el-table>
    </el-card>
    <el-drawer v-model="detailVisible" title="岗位详情" size="480px">
      <template v-if="selected">
        <h2>{{ selected.title }}</h2>
        <p>部门：{{ selected.department || '—' }} · 计划人数：{{ selected.headcount ?? '—' }} · {{ labels[selected.status] || selected.status }}</p>
        <h3>岗位描述 / AI 生成要求</h3>
        <el-input v-model="jdText" type="textarea" :rows="9" maxlength="20000" :disabled="selected.status === 'locked' || selected.status === 'archived'" />
        <div v-if="selected.status !== 'locked' && selected.status !== 'archived'" style="margin:12px 0 24px"><el-button :loading="jdSaving" @click="saveJd">保存并选用 JD</el-button><el-button :loading="generating" @click="generateJd">AI 生成并选用 JD</el-button></div>
        <el-button v-if="selected.status === 'draft' || selected.status === 'published'" @click="openEdit">编辑信息</el-button>
        <el-button v-if="selected.status === 'draft'" type="primary" @click="publish">发布岗位</el-button>
      </template>
    </el-drawer>
    <el-dialog v-model="dialog" :title="editing ? '编辑岗位' : '创建岗位'" width="520px">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="岗位名称" required><el-input v-model="form.title" maxlength="160" /></el-form-item>
        <el-form-item label="部门"><el-input v-model="form.department" /></el-form-item>
        <el-form-item label="计划人数"><el-input-number v-model="form.headcount" :min="1" :max="10000" /></el-form-item>
        <el-form-item v-if="!editing" label="岗位描述（至少 20 字，发布前必填）"><el-input v-model="form.jd_text" type="textarea" :rows="5" maxlength="20000" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </section>
</template>
