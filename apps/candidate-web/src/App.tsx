import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AppLayout } from './components/AppLayout'
import { RequireAuth } from './components/RequireAuth'
import { CursorTrail } from './components/visual/CursorTrail'
import ApplicationDetailPage from './pages/ApplicationDetailPage'
import ApplicationsPage from './pages/ApplicationsPage'
import HomePage from './pages/HomePage'
import InterviewDetailPage from './pages/InterviewDetailPage'
import InterviewsPage from './pages/InterviewsPage'
import JobBoardPage from './pages/JobBoardPage'
import JobDetailPage from './pages/JobDetailPage'
import LoginPage from './pages/LoginPage'
import ProfilePage from './pages/ProfilePage'
import RegisterPage from './pages/RegisterPage'

export default function App() {
  return (
    <BrowserRouter>
      <CursorTrail />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />

        <Route element={<RequireAuth />}>
          <Route element={<AppLayout />}>
            <Route index element={<HomePage />} />
            <Route path="/jobs" element={<JobBoardPage />} />
            <Route path="/jobs/:id" element={<JobDetailPage />} />
            <Route path="/applications" element={<ApplicationsPage />} />
            <Route path="/applications/:id" element={<ApplicationDetailPage />} />
            <Route path="/interviews" element={<InterviewsPage />} />
            <Route path="/interviews/:id" element={<InterviewDetailPage />} />
            <Route path="/profile" element={<ProfilePage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/jobs" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
