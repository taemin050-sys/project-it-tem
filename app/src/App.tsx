import { Navigate, Route, Routes } from 'react-router-dom'
import CreateLayout from './components/CreateLayout'
import CopyPage from './pages/CopyPage'
import DraftPage from './pages/DraftPage'
import ExportPage from './pages/ExportPage'
import LandingPage from './pages/LandingPage'
import ProductPage from './pages/ProductPage'
import LiveEvaluationBoard from './demo/LiveEvaluationBoard'

export default function App() {
  return (
    <Routes>
      <Route index element={<LandingPage />} />
      <Route path="create" element={<CreateLayout />}>
        <Route index element={<Navigate to="product" replace />} />
        <Route path="product" element={<ProductPage />} />
        <Route path="copy" element={<CopyPage />} />
        <Route path="draft" element={<DraftPage />} />
        <Route path="export" element={<ExportPage />} />
      </Route>
      <Route path="team/evaluations" element={<LiveEvaluationBoard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
