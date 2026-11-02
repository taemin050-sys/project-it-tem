import { AI_REQUEST_TIMEOUT_MS } from '../config'
import type { Step } from '../lib/pipeline'
import type { Job } from '../types/draft'
import type { ProductInput } from '../types/textSchema'
import { request, send } from './client'

const json = (body: unknown) => ({ headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// 레거시 구현(f979331) 경로 + 신규 Wire 제안(UP-EXT의 product_input_json). 성공 응답은 래퍼 없는 Job JSON.
// 레거시 서버는 product_input_json을 받지 않고 무시한다
export function createJob(productImages: File[], referenceImages: File[], input: ProductInput) {
  const form = new FormData()
  productImages.forEach((f) => form.append('product_images', f))
  referenceImages.forEach((f) => form.append('reference_images', f))
  form.append('product_input_json', JSON.stringify(input))
  return request<Job>('/api/v1/jobs', { method: 'POST', body: form })
}

export function getJob(jobId: string) {
  return request<Job>(`/api/v1/jobs/${jobId}`)
}

export function runStep(jobId: string, step: Step, body?: unknown) {
  return request<Job>(`/api/v1/jobs/${jobId}/${step}`, {
    method: 'POST',
    timeoutMs: AI_REQUEST_TIMEOUT_MS,
    ...(body === undefined ? {} : json(body)),
  })
}

// 거절하면 COPY_REJECTED·IMAGE_REJECTED로 끝난다 (거절 후 수정·재승인은 고도화)
// shortcut: 레거시는 { approved } 만 받는다. 카피 승인 V2(copy_revision·copy_sha256)가 동결되면 필드 추가
export function review(jobId: string, kind: 'copy' | 'image', approved: boolean) {
  return request<Job>(`/api/v1/jobs/${jobId}/approvals/${kind}`, { method: 'POST', ...json({ approved }) })
}

// Asset·산출물 다운로드 경로는 서버가 준 값(download_url 등)을 그대로 쓴다
export async function getBlob(path: string) {
  return (await send(path)).blob()
}
