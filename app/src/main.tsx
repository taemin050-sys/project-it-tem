import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/noto-serif-kr/700.css'
import '@fontsource/noto-serif-kr/900.css'
import 'pretendard/dist/web/variable/pretendardvariable.css'
import './index.css'
import { queryClient } from './api/queryClient'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
