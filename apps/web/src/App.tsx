import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { useAuthStore } from './store/authStore'
import LoginPage from './pages/LoginPage'
import WorkbenchHome from './pages/WorkbenchHome'
import JobListPage from './pages/JobListPage'
import JobCreatePage from './pages/JobCreatePage'
import JobDetailPage from './pages/JobDetailPage'
import CandidatesPage from './pages/CandidatesPage'
import CandidateDetailPage from './pages/CandidateDetailPage'
import CandidateReportPage from './pages/CandidateReportPage'
import EvidencePage from './pages/EvidencePage'
import SessionsPage from './pages/SessionsPage'
import AdminPage from './pages/AdminPage'
import PlaceholderPage from './pages/PlaceholderPage'

function RequireAuth() {
  const tokens = useAuthStore((state) => state.tokens)
  if (!tokens?.access_token) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<WorkbenchHome />} />
          <Route path="jobs" element={<JobListPage />} />
          <Route path="jobs/new" element={<JobCreatePage />} />
          <Route path="jobs/:id" element={<JobDetailPage />} />

          <Route path="candidates" element={<CandidatesPage />} />
          <Route path="candidates/:id/report" element={<CandidateReportPage />} />
          <Route path="candidates/:id/evidence" element={<EvidencePage />} />
          <Route path="candidates/:id" element={<CandidateDetailPage />} />

          <Route path="sessions" element={<SessionsPage />} />
          <Route path="admin" element={<AdminPage />} />
          <Route
            path="*"
            element={
              <PlaceholderPage
                title="页面不存在"
                description="该路径尚未接入，请从左侧导航进入已实现的工作区。"
                features={['工作台首页', '岗位管理', '候选人筛选', '语音会话', '管理后台']}
              />
            }
          />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
