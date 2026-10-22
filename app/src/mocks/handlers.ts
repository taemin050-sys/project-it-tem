import { http, HttpResponse } from 'msw'
import { API_BASE_URL } from '../config'
import type { Job, JobResult } from '../types/draft'

const jobs = new Map<string, number>()

const sampleResult: JobResult = {
  analysis: {
    product_type: '세럼',
    container: '유리 스포이드 병',
    colors: ['투명', '연한 골드'],
    label_text: 'GLOW SERUM 30ml',
    mood: '내추럴',
  },
  copy: {
    purpose: '신제품 출시',
    target: '20~30대 건성 피부',
    concept: '아침 햇살 같은 촉촉함',
    key_message: '가볍게 스며드는 보습',
    headline: '하루 종일 촉촉하게 빛나는 피부결',
    subline: '가볍게 스며드는 데일리 보습 세럼',
    cta: '지금 만나보세요',
    caption: '건조한 아침, 한 방울로 시작하는 촉촉한 하루',
    hashtags: ['#보습세럼', '#데일리케어', '#신제품'],
  },
  review: [
    {
      expression: '피부 재생',
      reason: '의약품 오인 우려 표현',
      suggestion: '피부결 관리',
    },
  ],
  image: {
    scene_underlay: '/mock/scene_underlay.svg',
    product_rgba: '/mock/product_rgba.svg',
    product_box: [0.3, 0.12, 0.4, 0.5],
    text_safe_zone: [0.08, 0.68, 0.84, 0.26],
    warnings: [],
    needs_manual_check: false,
  },
}

// 시작 후 경과 시간으로 상태를 흉내 낸다: 대기 → 진행 → 완료
function jobAt(jobId: string, startedAt: number): Job {
  const elapsed = Date.now() - startedAt
  if (elapsed < 1500) return { job_id: jobId, status: 'queued' }
  if (elapsed < 5000) return { job_id: jobId, status: 'running', progress: Math.round(((elapsed - 1500) / 3500) * 100) }
  return { job_id: jobId, status: 'done', progress: 100, result: sampleResult }
}

export const handlers = [
  http.post(`${API_BASE_URL}/api/jobs`, () => {
    const jobId = crypto.randomUUID()
    jobs.set(jobId, Date.now())
    return HttpResponse.json({ job_id: jobId }, { status: 202 })
  }),
  http.get(`${API_BASE_URL}/api/jobs/:jobId`, ({ params }) => {
    const jobId = String(params.jobId)
    const startedAt = jobs.get(jobId)
    if (startedAt === undefined) return new HttpResponse(null, { status: 404 })
    return HttpResponse.json(jobAt(jobId, startedAt))
  }),
]
