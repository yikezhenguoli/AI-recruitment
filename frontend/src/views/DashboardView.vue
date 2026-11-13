<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'

type Status = '待筛选' | '待面试' | '面试中' | '已通过' | '待复核'
interface Candidate {
  id: string; name: string; role: string; education: string; score: number;
  status: Status; updated: string; source: string; skills: string[]; summary: string
}
const candidates = ref<Candidate[]>([
  { id:'C-202611-001', name:'林知夏', role:'AI 产品经理', education:'硕士 · 北京理工大学', score:92, status:'待面试', updated:'今天 14:32', source:'官网投递', skills:['AI 产品设计','需求分析','Prompt Engineering'], summary:'具备 AI 应用产品从 0 到 1 的项目经验。建议面试进一步核实业务指标与实际贡献。' },
  { id:'C-202611-002', name:'陈屿', role:'算法工程师（大模型应用）', education:'硕士 · 南开大学', score:88, status:'待复核', updated:'今天 13:18', source:'内推', skills:['Python','RAG','模型评测'], summary:'具备检索增强生成与模型评测相关经历，部分项目指标仍需人工核验。' },
  { id:'C-202611-003', name:'周予安', role:'前端开发工程师', education:'本科 · 天津大学', score:84, status:'面试中', updated:'今天 11:46', source:'校园招聘', skills:['Vue 3','TypeScript','可视化'], summary:'有较完整的前端项目实践，建议重点了解工程化、组件设计和协作经验。' },
  { id:'C-202611-004', name:'许清和', role:'AI 产品经理', education:'本科 · 北京邮电大学', score:79, status:'待筛选', updated:'昨天 18:20', source:'招聘平台', skills:['用户研究','原型设计','数据分析'], summary:'具备产品实习经历，AI 产品落地经验仍需进一步确认。' },
  { id:'C-202611-005', name:'沈嘉木', role:'算法工程师（大模型应用）', education:'博士 · 中国科学技术大学', score:95, status:'已通过', updated:'昨天 16:05', source:'学术推荐', skills:['LLM','Agent','深度学习'], summary:'具备大模型应用与智能体研究经历，进入下一轮前仍需按统一标准完成人工面试评估。' },
  { id:'C-202611-006', name:'唐以宁', role:'前端开发工程师', education:'本科 · 西安电子科技大学', score:81, status:'待面试', updated:'11 月 12 日', source:'招聘平台', skills:['React','Vue','工程化'], summary:'有前端工程实践与跨团队协作经历，建议结合代码样例进一步确认工程质量。' },
])
const keyword = ref('')
const statusFilter = ref('全部状态')
const selected = ref<Candidate | null>(null)
const drawerVisible = ref(false)
const addVisible = ref(false)
const form = ref({ name:'', role:'AI 产品经理', education:'' })
const statusOptions = ['全部状态','待筛选','待面试','面试中','已通过','待复核']
const filtered = computed(() => candidates.value.filter(c => {
  const q = keyword.value.trim().toLowerCase()
  const matches = !q || c.name.toLowerCase().includes(q) || c.role.toLowerCase().includes(q) || c.id.toLowerCase().includes(q)
  return matches && (statusFilter.value === '全部状态' || c.status === statusFilter.value)
}))
const statusType = (s: Status) => ({待筛选:'info',待面试:'warning',面试中:'primary',已通过:'success',待复核:'danger'}[s])
const scoreColor = (s:number) => s >= 90 ? '#26a77a' : s >= 80 ? '#4d83e8' : '#d99a45'
function handleRowClick(row: Candidate) {
  selected.value = row
  drawerVisible.value = true
}
function addCandidate() {
  if (!form.value.name.trim() || !form.value.education.trim()) return ElMessage.warning('请填写候选人姓名和教育背景')
  const name = form.value.name.trim()
  candidates.value.unshift({ id:`C-${Date.now().toString().slice(-6)}`, name, role:form.value.role, education:form.value.education.trim(), score:0, status:'待筛选', updated:'刚刚', source:'手动添加', skills:[], summary:'该候选人由招聘管理员手动添加，等待简历上传与后续分析。' })
  form.value = { name:'', role:'AI 产品经理', education:'' }; addVisible.value = false
  ElMessage.success('候选人已加入当前演示列表')
}
function exportCsv() {
  const rows = [['候选人编号','姓名','应聘岗位','教育背景','匹配参考分','当前状态','来源'], ...filtered.value.map(c => [c.id,c.name,c.role,c.education,c.score,c.status,c.source])]
  const csv = rows.map(row => row.map(v => '"' + String(v).replaceAll('"','""') + '"').join(',')).join('\r\n')
  const url = URL.createObjectURL(new Blob(['\uFEFF'+csv], {type:'text/csv;charset=utf-8;'}))
  const a = document.createElement('a'); a.href=url; a.download='TTC_候选人列表.csv'; a.click(); URL.revokeObjectURL(url)
  ElMessage.success('候选人列表已导出')
}
const stages = [
  {label:'收到简历',count:286,width:100,color:'#7c8cf8'},
  {label:'初步筛选',count:164,width:57,color:'#5b8def'},
  {label:'待面试',count:72,width:25,color:'#38b8b0'},
  {label:'面试中',count:38,width:13,color:'#e9a64b'},
  {label:'进入下一轮',count:16,width:6,color:'#6ebd8a'},
]
const jobs = [
  {title:'AI 产品经理',dept:'产品研发部',place:'北京 · 混合办公',applicants:48},
  {title:'算法工程师（大模型应用）',dept:'人工智能部',place:'北京 · 现场办公',applicants:76},
  {title:'前端开发工程师',dept:'平台研发部',place:'天津 · 混合办公',applicants:32},
]
</script>

<template>
  <div class="dashboard">
    <section class="page-heading">
      <div><div class="eyebrow"><i></i>TALENT OVERVIEW</div><h1>招聘工作台</h1><p>欢迎回来，招聘团队。这里是今天的人才招聘概览。</p></div>
      <div class="heading-actions">
        <div class="date-chip"><el-icon><Calendar /></el-icon>2026 年 11 月 13 日</div>
        <el-button type="primary" class="primary-btn" @click="addVisible=true"><el-icon><Plus /></el-icon>添加候选人</el-button>
      </div>
    </section>

    <section class="kpi-grid">
      <article class="kpi-card"><div class="kpi-top"><span>活跃岗位</span><div class="kpi-icon blue"><el-icon><Briefcase /></el-icon></div></div><div class="kpi-value">12<span>个</span></div><div class="kpi-foot"><b>↗ 2</b>较上周新增</div><i class="kpi-orb blue-orb"></i></article>
      <article class="kpi-card"><div class="kpi-top"><span>候选人人才库</span><div class="kpi-icon purple"><el-icon><User /></el-icon></div></div><div class="kpi-value">286<span>人</span></div><div class="kpi-foot"><b>↗ 12.8%</b>较上周增长</div><i class="kpi-orb purple-orb"></i></article>
      <article class="kpi-card"><div class="kpi-top"><span>待处理简历</span><div class="kpi-icon orange"><el-icon><Document /></el-icon></div></div><div class="kpi-value">18<span>份</span></div><div class="kpi-foot"><b class="orange-text">需要关注</b>建议及时处理</div><i class="kpi-orb orange-orb"></i></article>
      <article class="kpi-card"><div class="kpi-top"><span>本周面试</span><div class="kpi-icon green"><el-icon><Calendar /></el-icon></div></div><div class="kpi-value">24<span>场</span></div><div class="kpi-foot"><b>↗ 4</b>较上周增加</div><i class="kpi-orb green-orb"></i></article>
    </section>

    <section class="overview-grid">
      <article class="surface-card pipeline-card">
        <div class="card-heading"><div><h2>招聘流程概览</h2><p>候选人在各招聘阶段的分布情况</p></div><el-tag type="info" effect="plain" round>演示数据</el-tag></div>
        <div class="pipeline-total"><div><strong>286</strong><span>累计候选人</span></div><small><i></i>本月数据</small></div>
        <div class="stage-list">
          <div v-for="stage in stages" :key="stage.label" class="stage-row"><span>{{stage.label}}</span><div class="stage-track"><i :style="{width:stage.width+'%',background:stage.color}"></i></div><b>{{stage.count}}</b></div>
        </div>
        <div class="pipeline-foot"><span><i></i>招聘流程阶段</span><span>数据为前端演示样例</span></div>
      </article>
      <article class="surface-card jobs-card">
        <div class="card-heading"><div><h2>重点招聘岗位</h2><p>当前正在推进的岗位</p></div><el-button text type="primary" @click="$router.push('/jobs')">查看全部 <el-icon><ArrowRight /></el-icon></el-button></div>
        <div class="job-list">
          <div v-for="job in jobs" :key="job.title" class="job-row"><div class="job-icon"><el-icon><Briefcase /></el-icon></div><div class="job-info"><strong>{{job.title}}</strong><span>{{job.dept}} · {{job.place}}</span><div class="job-progress"><i><b :style="{width:Math.min(100,job.applicants/1.2)+'%'}"></b></i><small>{{job.applicants}} 人申请</small></div></div><el-tag type="success" effect="light" size="small">招聘中</el-tag></div>
        </div>
      </article>
    </section>

    <section class="surface-card candidate-card">
      <div class="card-heading candidate-heading"><div><h2>近期候选人</h2><p>查看候选人动态，快速进入人才详情</p></div>
        <div class="table-tools">
          <el-input v-model="keyword" clearable placeholder="搜索姓名、岗位或编号" class="search-input"><template #prefix><el-icon><Search /></el-icon></template></el-input>
          <el-select v-model="statusFilter" class="status-select"><el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" /></el-select>
          <el-button class="export-btn" @click="exportCsv"><el-icon><Download /></el-icon>导出</el-button>
        </div>
      </div>
     <el-table :data="filtered" row-key="id" class="candidate-table" @row-click="handleRowClick" empty-text="没有找到符合条件的候选人">
        <el-table-column label="候选人" min-width="175"><template #default="{row}"><div class="person-cell"><el-avatar :size="36" class="person-avatar">{{row.name.slice(0,1)}}</el-avatar><div><strong>{{row.name}}</strong><small>{{row.id}}</small></div></div></template></el-table-column>
        <el-table-column prop="role" label="应聘岗位" min-width="190" show-overflow-tooltip />
        <el-table-column prop="education" label="教育背景" min-width="185" />
        <el-table-column label="匹配参考分" min-width="125"><template #default="{row}"><strong :style="{color:scoreColor(row.score)}" class="score">{{row.score || '—'}}</strong><small v-if="row.score" class="score-total"> / 100</small></template></el-table-column>
        <el-table-column label="当前状态" min-width="110"><template #default="{row}"><el-tag :type="statusType(row.status)" effect="light" round>{{row.status}}</el-tag></template></el-table-column>
        <el-table-column prop="updated" label="最近更新" min-width="115" />
        <el-table-column label="" width="55" align="right"><template #default><el-icon class="more-icon"><MoreFilled /></el-icon></template></el-table-column>
      </el-table>
      <div class="table-footer">当前显示 <b>{{filtered.length}}</b> 位候选人 <span>点击候选人行查看详情</span></div>
    </section>

    <el-drawer v-model="drawerVisible" size="430px" :with-header="false">
      <div v-if="selected" class="drawer-body">
        <div class="drawer-head"><span>候选人档案</span><el-button text circle @click="drawerVisible=false"><el-icon><Close /></el-icon></el-button></div>
        <div class="drawer-person"><el-avatar :size="62">{{selected.name.slice(0,1)}}</el-avatar><div><h2>{{selected.name}}</h2><p>{{selected.role}}</p><el-tag :type="statusType(selected.status)" effect="light" round>{{selected.status}}</el-tag></div></div>
        <div class="drawer-score"><span>岗位匹配参考分</span><strong>{{selected.score || '待评估'}}<small v-if="selected.score"> / 100</small></strong></div>
        <h3>基本信息</h3>
        <div class="info-row"><span>候选人编号</span><b>{{selected.id}}</b></div><div class="info-row"><span>教育背景</span><b>{{selected.education}}</b></div><div class="info-row"><span>简历来源</span><b>{{selected.source}}</b></div>
        <h3>技能标签</h3><div class="skill-list"><el-tag v-for="skill in selected.skills" :key="skill" effect="plain" round>{{skill}}</el-tag><span v-if="!selected.skills.length">暂无技能标签</span></div>
        <h3>初步摘要</h3><p class="summary-box">{{selected.summary}}</p>
        <div class="disclaimer"><el-icon><InfoFilled /></el-icon>匹配参考分与摘要仅用于演示，不构成自动录用或淘汰结论。实际招聘决策应由 HR 结合原始材料人工复核。</div>
        <el-button type="primary" class="drawer-action" @click="ElMessage.info('人才评估模块将在后续阶段接入')">进入人才评估 <el-icon><ArrowRight /></el-icon></el-button>
      </div>
    </el-drawer>

    <el-dialog v-model="addVisible" title="添加候选人" width="460px" destroy-on-close>
      <p class="dialog-tip">先将候选人加入本地演示列表，后续可在简历中心补充材料。</p>
      <el-form label-position="top">
        <el-form-item label="候选人姓名" required><el-input v-model="form.name" placeholder="请输入姓名" /></el-form-item>
        <el-form-item label="应聘岗位"><el-select v-model="form.role" style="width:100%"><el-option label="AI 产品经理" value="AI 产品经理"/><el-option label="算法工程师（大模型应用）" value="算法工程师（大模型应用）"/><el-option label="前端开发工程师" value="前端开发工程师"/></el-select></el-form-item>
        <el-form-item label="教育背景" required><el-input v-model="form.education" placeholder="例如：本科 · XX大学" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="addVisible=false">取消</el-button><el-button type="primary" @click="addCandidate">确认添加</el-button></template>
    </el-dialog>
  </div>
</template>
