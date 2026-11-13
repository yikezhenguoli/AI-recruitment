<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, errorMessage, type Candidate, type Job } from '../api'

const items = ref<Candidate[]>([])
const jobs = ref<Job[]>([])
const selected = ref<Candidate | null>(null)
const detailVisible = ref(false)
const createVisible = ref(false)
const saving = ref(false)
const loading = ref(false)
const file = ref<File | null>(null)
interface Resume { id: string; file_name: string; parse_status: string; created_at: string }
interface Claim { id: string; type: string; raw_text: string; needs_review: boolean }
const resumes = ref<Resume[]>([])
const claims = ref<Claim[]>([])
const claimStatus = ref('')
const form = reactive({ display_name: '', job_id: '' })
const jobName = (id: string | null) => jobs.value.find(job => job.id === id)?.title || '未关联岗位'

async function load() {
  loading.value = true
  try {
    const [candidates, openings] = await Promise.all([
      api.get<{ items: Candidate[] }>('/candidates', { params: { limit: 100 } }),
      api.get<{ items: Job[] }>('/jobs', { params: { limit: 100 } }),
    ])
    items.value = candidates.data.items
    jobs.value = openings.data.items
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { loading.value = false }
}
function openCreate() {
  form.display_name = ''
  form.job_id = ''
  file.value = null
  createVisible.value = true
}
async function save() {
  if (!form.display_name.trim()) return ElMessage.warning('请填写合成候选人姓名')
  saving.value = true
  try {
    const { data } = await api.post<Candidate>('/candidates', {
      display_name: form.display_name.trim(), job_id: form.job_id || null,
      source: 'demo', is_synthetic: true,
    })
    if (file.value) {
      const upload = new FormData()
      upload.append('candidate_id', data.id)
      if (form.job_id) upload.append('job_id', form.job_id)
      upload.append('file', file.value)
      try { await api.post('/resumes', upload) }
      catch (error) { ElMessage.warning(`候选人已创建，但简历上传失败：${errorMessage(error)}`) }
    }
    createVisible.value = false
    await load()
    ElMessage.success('合成候选人已创建')
  } catch (error) { ElMessage.error(errorMessage(error)) }
  finally { saving.value = false }
}
async function show(row: Candidate) {
  try {
    selected.value = (await api.get<Candidate>(`/candidates/${row.id}`)).data
    await loadResumes()
    detailVisible.value = true
  } catch (error) { ElMessage.error(errorMessage(error)) }
}
async function loadResumes() {
  if (!selected.value) return
  resumes.value = (await api.get<{ items: Resume[] }>(`/candidates/${selected.value.id}/resumes`)).data.items
  if (resumes.value[0]) await loadClaims(resumes.value[0].id)
  else { claims.value = []; claimStatus.value = '' }
}
async function loadClaims(id: string) {
  try {
    const { data } = await api.get<{ status: string; claims: Claim[] }>(`/resumes/${id}/claims`)
    claims.value = data.claims
    claimStatus.value = data.status || '等待解析'
  } catch (error) { ElMessage.error(errorMessage(error)) }
}
function chooseFile(event: Event) {
  const target = event.target as HTMLInputElement
  file.value = target.files?.[0] || null
  if (file.value && !/\.(pdf|docx|txt)$/i.test(file.value.name)) {
    file.value = null; target.value = ''; ElMessage.warning('仅支持 PDF、DOCX 和 TXT')
  }
}
const syntheticOnly = computed(() => items.value.every(item => item.is_synthetic))
onMounted(load)
</script>

<template>
  <section class="api-page">
    <div class="api-heading"><div><h1>候选人</h1><p>仅创建经授权的合成样本；不上传真实候选人简历。</p></div><el-button type="primary" @click="openCreate">添加合成候选人</el-button></div>
    <el-alert v-if="!syntheticOnly" title="包含非合成候选人；请确认已取得知情授权" type="warning" show-icon :closable="false" style="margin-bottom:16px" />
    <el-card><el-table v-loading="loading" :data="items" row-key="id" empty-text="暂无候选人" @row-click="show">
      <el-table-column prop="display_name" label="姓名" min-width="150" />
      <el-table-column label="应聘岗位" min-width="200"><template #default="{ row }">{{ jobName(row.job_id) }}</template></el-table-column>
      <el-table-column label="来源" width="120"><template #default="{ row }">{{ row.source }}</template></el-table-column>
      <el-table-column label="样本" width="100"><template #default="{ row }"><el-tag :type="row.is_synthetic ? 'success' : 'warning'">{{ row.is_synthetic ? '合成' : '真实' }}</el-tag></template></el-table-column>
      <el-table-column label="创建时间" width="190"><template #default="{ row }">{{ new Date(row.created_at).toLocaleString() }}</template></el-table-column>
    </el-table></el-card>
    <el-drawer v-model="detailVisible" title="候选人档案" size="420px">
      <template v-if="selected"><h2>{{ selected.display_name }}</h2><p>编号：{{ selected.id }}</p><p>岗位：{{ jobName(selected.job_id) }}</p><p>来源：{{ selected.source }}</p><p>创建时间：{{ new Date(selected.created_at).toLocaleString() }}</p>
        <h3>简历记录 <el-button link type="primary" @click="loadResumes">刷新解析结果</el-button></h3>
        <el-empty v-if="!resumes.length" description="尚未上传简历" :image-size="60" />
        <p v-for="resume in resumes" :key="resume.id"><el-button link type="primary" @click="loadClaims(resume.id)">{{ resume.file_name }}</el-button> {{ resume.parse_status }}</p>
        <h3 v-if="resumes.length">抽取字段（{{ claimStatus || '等待解析' }}）</h3>
        <p v-for="claim in claims" :key="claim.id">{{ claim.type }}：{{ claim.raw_text }}{{ claim.needs_review ? '（待复核）' : '' }}</p>
        <el-alert title="仅展示接口返回的事实字段，未解析的简历不显示虚构评分。" type="info" :closable="false" />
      </template>
    </el-drawer>
    <el-dialog v-model="createVisible" title="添加合成候选人" width="520px">
      <el-form label-position="top" @submit.prevent="save">
        <el-form-item label="合成姓名" required><el-input v-model="form.display_name" maxlength="80" placeholder="仅填写虚构样本姓名" /></el-form-item>
        <el-form-item label="应聘岗位"><el-select v-model="form.job_id" clearable style="width:100%"><el-option v-for="job in jobs.filter(item => item.status !== 'archived')" :key="job.id" :label="job.title" :value="job.id" /></el-select></el-form-item>
        <el-form-item label="合成简历（可选）"><input type="file" accept=".pdf,.docx,.txt" @change="chooseFile" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="createVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">创建</el-button></template>
    </el-dialog>
  </section>
</template>
