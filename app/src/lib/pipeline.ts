import type { Job, JobStatus } from '../types/draft'

// 서버가 자동으로 진행하지 않고 화면이 단계별 POST를 보낸다 (레거시 구현과 신규 Wire 제안이 모두 이 방식)
export type Flow = 'legacy' | 'v2'
export type Step =
  | 'mock/plan' | 'mock/copy' | 'mock/image' | 'mock/compose'
  | 'ai/analyze' | 'ai/research' | 'ai/copy-review' | 'ai/image' | 'compose'

export const STEP_LABELS: Record<Step, string> = {
  'mock/plan': '기획안(mock)을 만들고 있습니다',
  'mock/copy': '카피(mock)를 만들고 있습니다',
  'mock/image': '이미지(mock)를 만들고 있습니다',
  'mock/compose': '최종 광고(mock)를 합성하고 있습니다',
  'ai/analyze': '열심히 문구를 생성중입니다',
  'ai/research': '열심히 문구를 생성중입니다',
  'ai/copy-review': '열심히 문구를 생성중입니다',
  'ai/image': '열심히 이미지를 생성중입니다',
  compose: '카피와 이미지를 합성하고 있습니다',
}

// 레거시 구현(f979331 mock_workflow.py)의 상태 전이
const LEGACY: Partial<Record<JobStatus, Step>> = {
  INPUTS_VALIDATED: 'mock/plan',
  PLAN_READY: 'mock/copy',
  COPY_APPROVED: 'mock/image',
  IMAGE_APPROVED: 'mock/compose',
}

// 서버 Job 기준으로 다음에 보낼 단계를 정한다. 사용자 승인이 필요하거나 끝났으면 null
// shortcut: v2 경로는 wire_proposals.json 제안값(BLOCKED_WIRE), 조사가 카피 호출 안으로 합쳐지면 'ai/research'를 뺀다
export function nextStep(job: Job, flow: Flow): Step | null {
  if (flow === 'legacy') return LEGACY[job.status] ?? null
  switch (job.status) {
    case 'INPUTS_VALIDATED':
    case 'PLAN_READY':
      if (!job.product_analysis) return 'ai/analyze'
      if (!job.product_analysis.is_cosmetic) return null
      return job.research_result ? 'ai/copy-review' : 'ai/research'
    case 'COPY_APPROVED':
      return 'ai/image'
    case 'IMAGE_APPROVED':
      return 'compose'
    default:
      return null
  }
}

// 검수 리포트가 있으면 통과(위반 의심 0건)일 때만 승인 가능. 리포트 없이 승인할 수 있는 건
// 레거시 mock 문구(실제 AI 카피 아님, 흐름 확인용)뿐 — 실제 카피에 검수가 없으면 승인 불가 (계약 2.6)
export function canApproveCopy(job: Job): boolean {
  if (job.status !== 'COPY_REVIEW_REQUIRED') return false
  if (job.compliance_report) return job.compliance_report.passed
  return job.copy_candidate?.mock === true
}

// 생성 이미지 경로: v2 제안은 Asset, 레거시는 image 산출물
export function imagePath(job: Job): string | undefined {
  const assetId = job.image_candidate?.asset_id
  return assetId ? `/api/v1/jobs/${job.job_id}/assets/${assetId}` : job.artifacts?.image?.download_url
}

// 서버가 mock 결과라고 표시한 단계가 하나라도 있으면 실제 AI 결과가 아니다
export function isMockJob(job: Job): boolean {
  return [job.plan, job.copy_candidate, job.image_candidate, job.final_output].some((x) => x?.mock === true)
}
