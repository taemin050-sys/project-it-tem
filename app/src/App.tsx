import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import AdSettingsPage from './pages/AdSettingsPage'
import CopyPage from './pages/CopyPage'
import DraftPage from './pages/DraftPage'
import ExportPage from './pages/ExportPage'
import HomePage from './pages/HomePage'
import ProductPage from './pages/ProductPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="product" element={<ProductPage />} />
        <Route path="settings" element={<AdSettingsPage />} />
        <Route path="copy" element={<CopyPage />} />
        <Route path="draft" element={<DraftPage />} />
        <Route path="export" element={<ExportPage />} />
      </Route>
    </Routes>
  )
}
