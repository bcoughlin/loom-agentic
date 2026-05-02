import { Routes, Route, Navigate } from 'react-router-dom'
import AdminNav from './components/AdminNav'
import Replay from './pages/Replay'
import Sessions from './pages/Sessions'
import Scorecards from './pages/Scorecards'

const ROUTES = [
  { path: '/replay',     label: 'Replay' },
  { path: '/sessions',   label: 'Sessions' },
  { path: '/scorecards', label: 'Scorecards' },
]

export default function App() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AdminNav routes={ROUTES} wordmark="LOOM" />
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Routes>
          <Route path="/"            element={<Navigate to="/replay" replace />} />
          <Route path="/replay"      element={<Replay />} />
          <Route path="/sessions"    element={<Sessions />} />
          <Route path="/scorecards"  element={<Scorecards />} />
          <Route path="*"            element={<Navigate to="/replay" replace />} />
        </Routes>
      </div>
    </div>
  )
}
