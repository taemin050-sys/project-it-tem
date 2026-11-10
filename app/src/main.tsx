import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import 'pretendard/dist/web/variable/pretendardvariable.css'
import './index.css'
import { queryClient } from './api/queryClient'
import DemoGate from './demo/DemoGate.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <DemoGate />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
