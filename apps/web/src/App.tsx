import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import WorkbenchHome from './pages/WorkbenchHome'
import JobListPage from './pages/JobListPage'
import JobCreatePage from './pages/JobCreatePage'
import JobDetailPage from './pages/JobDetailPage'
import CandidatesPage from './pages/CandidatesPage'
import CandidateDetailPage from './pages/CandidateDetailPage'
import CandidateReportPage from './pages/CandidateReportPage'
import SessionsPage from './pages/SessionsPage'
import PlaceholderPage from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WorkbenchHome />} />
        <Route path="jobs" element={<JobListPage />} />
        <Route path="jobs/new" element={<JobCreatePage />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route
          path="jobs/:id/edit"
          element={
            <PlaceholderPage
              title="编辑岗位"
              description="岗位版本管理、权重方案与面试方案编辑将在后续阶段接入。"
              features={['JD 多版本比对', '权重方案编辑', '岗位锁定态', '关联候选人']}
            />
          }
        />

        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="candidates/:id/report" element={<CandidateReportPage />} />
        <Route path="candidates/:id" element={<CandidateDetailPage />} />
        <Route
          path="candidates/:id/evidence"
          element={
            <PlaceholderPage
              title="证据中心"
              description="实体抽取、公开来源检索、证据分级与冲突核验属于 M4 范围，当前后端尚未接入。"
              features={['实体分组', '公开来源卡', '证据分级 A/B/C/D', '冲突与待核验项']}
            />
          }
        />

        <Route path="sessions" element={<SessionsPage />} />
        <Route
          path="sessions/:id"
          element={
            <PlaceholderPage
              title="会话详情"
              description="语音会话状态、转写与通话分析报告将在后续阶段接入。"
              features={['会话状态机', '实时转写', '异常与重连提示', '通话分析']}
            />
          }
        />
        <Route
          path="admin"
          element={
            <PlaceholderPage
              title="管理后台"
              description="数据源、审计、指标与租户治理属于 M1/M8 范围，当前版本未接入。"
              features={['数据源管理', '审计留痕', '指标看板', '租户与权限']}
            />
          }
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
