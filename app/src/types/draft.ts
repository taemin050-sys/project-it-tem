// 서빙 Job 형식. 상태값·assets·artifacts·legacy 필드는 레거시 구현(f979331 job_store.py·mock_workflow.py) 기준,
// v0.5 결과 키(product_analysis 등)는 신규 Wire 제안(wire_proposals.json) 기준이다.
// shortcut: 신규 Wire는 BLOCKED_WIRE(미동결)라 가정값, 서빙 OpenAPI가 나오면 생성 타입으로 바꾼다
import type { AdCopyOutput, ComplianceReport, ProductAnalysis, ResearchResult } from './textSchema'

export const JOB_STATUSES = [
  'INPUTS_VALIDATED', 'PLAN_READY', 'COPY_REVIEW_REQUIRED', 'COPY_APPROVED', 'COPY_REJECTED',
  'IMAGE_REVIEW_REQUIRED', 'IMAGE_APPROVED', 'IMAGE_REJECTED', 'COMPLETED',
] as const
export type JobStatus = (typeof JOB_STATUSES)[number]

export type Asset = {
  asset_id: string
  role: 'product' | 'reference'
  original_filename: string
  content_type: string
  size_bytes: number
  width: number
  height: number
  sha256: string
}

export type ArtifactKind = 'plan' | 'copy' | 'image' | 'final' | 'caption'
export type Artifact = { kind: ArtifactKind; content_type: string; size_bytes: number; download_url: string }

/** 레거시 mock/plan 결과 (실제 조사 아님) */
export type LegacyPlan = {
  mock: boolean
  research_performed: boolean
  brand_name: string
  product_name: string
  audience: string
  direction: string
  disclaimer: string
}

/** 레거시 mock/copy 결과: 구조 없는 문구 1개, 규제 검수 없음 */
export type LegacyCopy = { mock: boolean; text: string; compliance_checked: boolean; disclaimer: string }

/** v2 제안은 asset_id·preservation_review, 레거시는 mock·source·size만 준다 */
export type ImageCandidate = {
  asset_id?: string
  preservation_review?: string
  mock?: boolean
}

export type Job = {
  job_id: string
  status: JobStatus
  assets?: Asset[]
  artifacts?: Partial<Record<ArtifactKind, Artifact>>
  // v0.2 제안 (MSW fixture 흐름)
  product_analysis?: ProductAnalysis
  research_result?: ResearchResult
  copy_output?: AdCopyOutput
  compliance_report?: ComplianceReport
  // 레거시 구현
  plan?: LegacyPlan
  copy_candidate?: LegacyCopy
  image_candidate?: ImageCandidate
  final_output?: { mock: boolean; width: number; height: number; format: string }
}
