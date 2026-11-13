import { Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { RequireAuth } from './components/RequireAuth'
import LoginPage from './pages/LoginPage'
import WorkbenchHome from './pages/WorkbenchHome'
import JobListPage from './pages/JobListPage'
import JobCreatePage from './pages/JobCreatePage'
import JobDetailPage from './pages/JobDetailPage'
import CandidatesPage from './pages/CandidatesPage'
import CandidateDetailPage from './pages/CandidateDetailPage'
import CandidateReportPage from './pages/CandidateReportPage'
import SessionsPage from './pages/SessionsPage'
import SessionDetailPage from './pages/SessionDetailPage'
import AdminPage from './pages/AdminPage'

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<WorkbenchHome />} />
        <Route path="jobs" element={<JobListPage />} />
        <Route path="jobs/new" element={<JobCreatePage />} />
        <Route path="jobs/:id" element={<JobDetailPage />} />
        <Route path="candidates" element={<CandidatesPage />} />
        <Route path="candidates/:id/report" element={<CandidateReportPage />} />
        <Route path="candidates/:id" element={<CandidateDetailPage />} />
        <Route path="sessions" element={<SessionsPage />} />
        <Route path="sessions/:id" element={<SessionDetailPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
