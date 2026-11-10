import { AI_REQUEST_TIMEOUT_MS } from '../config'
import type { Step } from '../lib/pipeline'
import type { Job } from '../types/draft'
import type { ProductInput } from '../types/textSchema'
import { request, send } from './client'
import {A51D_MPO_FIXTURE,confirmedMpoChoice} from '../lib/a51dMpoSelection'

const json = (body: unknown) => ({ headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// 레거시 구현(f979331) 경로 + 신규 Wire 제안(UP-EXT의 product_input_json). 성공 응답은 래퍼 없는 Job JSON.
// 레거시 서버는 product_input_json을 받지 않고 무시한다
export function createJob(productImages: File[], referenceImages: File[], input: ProductInput) {
  const form = new FormData()
  productImages.forEach((f) => form.append('product_images', f))
  referenceImages.forEach((f) => form.append('reference_images', f))
  form.append('product_input_json', JSON.stringify(input))
  if(A51D_MPO_FIXTURE){
    // Only explicit, visually confirmed MPO candidates use the provisional
    // authenticated HTTP→B0 Job bridge. Legacy B0 jobs remain unchanged.
    const choices=[
      ...productImages.map((file,index)=>({file,index,category:'product'})),
      ...referenceImages.map((file,index)=>({file,index,category:'reference'})),
    ].flatMap(({file,index,category})=>{
      const chosen=confirmedMpoChoice(file)
      return chosen ? [{
        category,index,token:chosen.token,
        selected_frame_index:chosen.selected_frame_index,
        selected_preview_sha256:chosen.selected_preview_sha256,
      }] : []
    })
    if(choices.length){
      form.append('mpo_choices_json',JSON.stringify(choices))
      return request<Job>('/demo/api/a51d/mpo/jobs',{method:'POST',body:form})
    }
  }
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

// 거절하면 COPY_REJECTED·IMAGE_REJECTED로 끝난다 (mock은 거절 대신 reviseJob으로 수정 요청)
// shortcut: 레거시는 { approved } 만 받는다. 카피 승인 V2(copy_revision·copy_sha256)가 동결되면 필드 추가
export function review(jobId: string, kind: 'copy' | 'image', approved: boolean) {
  return request<Job>(`/api/v1/jobs/${jobId}/approvals/${kind}`, { method: 'POST', ...json({ approved }) })
}

// shortcut: 아래 둘은 mock 전용 경로(서버 API 없음), 서빙 API 명세를 받으면 경로·본문을 맞춘다
// 거절 대신 요구사항을 보내 모델이 고친 카피·이미지를 다시 검토 단계로 받는다. 직전 버전은 서버가 보관한다
export function reviseJob(jobId: string, kind: 'copy' | 'image', instruction: string) {
  return request<Job>(`/api/v1/jobs/${jobId}/revise/${kind}`, { method: 'POST', timeoutMs: AI_REQUEST_TIMEOUT_MS, ...json({ instruction }) })
}

// 현재 버전과 직전 버전을 바꾼다 (다시 누르면 원래대로)
export function restorePrevious(jobId: string, kind: 'copy' | 'image') {
  return request<Job>(`/api/v1/jobs/${jobId}/restore/${kind}`, { method: 'POST' })
}

// Asset·산출물 다운로드 경로는 서버가 준 값(download_url 등)을 그대로 쓴다
export async function getBlob(path: string) {
  return (await send(path)).blob()
}
