import { Navigate, Route, Routes } from 'react-router-dom'
import CreateLayout from './components/CreateLayout'
import CopyPage from './pages/CopyPage'
import DraftPage from './pages/DraftPage'
import ExportPage from './pages/ExportPage'
import LandingPage from './pages/LandingPage'
import ProductPage from './pages/ProductPage'
import LiveEvaluationBoard from './demo/LiveEvaluationBoard'
import { useProjectStore } from './store/projectStore'

// /create로 들어오면: 진행 중인 작업은 카피 검토(현재 진행 상황과 다음 단계 링크가 있는 곳)로, 없으면 제품 정보로
function CreateIndex() {
  const jobId = useProjectStore((s) => s.jobId)
  return <Navigate to={jobId ? 'copy' : 'product'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route index element={<LandingPage />} />
      <Route path="create" element={<CreateLayout />}>
        <Route index element={<CreateIndex />} />
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
