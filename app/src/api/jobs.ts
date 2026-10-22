import type { AdSettings, Job, ProductInfo } from '../types/draft'
import { request } from './client'

// shortcut: 엔드포인트·필드명은 이형기 API 명세 수신 전 가정값
export function createJob(images: File[], product: ProductInfo, settings: AdSettings) {
  const form = new FormData()
  images.forEach((f) => form.append('images', f))
  form.append('product', JSON.stringify(product))
  form.append('settings', JSON.stringify(settings))
  return request<{ job_id: string }>('/api/jobs', { method: 'POST', body: form })
}

export function getJob(jobId: string) {
  return request<Job>(`/api/jobs/${jobId}`)
}
