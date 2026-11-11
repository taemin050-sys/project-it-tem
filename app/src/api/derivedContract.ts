import type { AdCopy } from '../types/textSchema'

export type DerivedMode = 'composed_protected_product' | 'freeform_protected_product_hybrid'
export type DerivedState = 'QUEUED' | 'RENDERING' | 'REVIEW_REQUIRED' | 'APPROVED' |
  'COMPLETED' | 'REJECTED' | 'HOLD' | 'FAILED' | 'STALE'
export type DerivedArtifactKind = 'preview' | 'final' | 'caption' | 'receipt'
export type DerivedVisualReview = {
  source_pixels_preserved: boolean
  edges_acceptable: boolean
  no_duplicate_product: boolean
  no_ghost_product: boolean
  no_copy_occlusion: boolean
  cta_policy_matches: boolean
  label_ground_truth_confirmed: boolean
  mobile_readable: boolean
  observed_copy: AdCopy
}
export type DerivedProposal = {
  proposal_id: string
  render_mode: DerivedMode
  title: string
  recipe_sha: string
  recipe_file_sha?: string
  source_asset_id?: string
  hold_code?: string | null
  requires_ground_truth: boolean
}
export type DerivedRender = {
  derived_id: string
  job_id: string
  render_mode: DerivedMode
  state: DerivedState
  revision: number
  recipe_sha: string
  context_sha: string
  admission_sha: string
  preview_sha: string | null
  approval_sha: string | null
  final_sha: string | null
  caption_sha: string | null
  receipt_sha: string | null
  output_size: {width: number; height: number} | null
  artifacts: Partial<Record<DerivedArtifactKind, string>>
  hold_code: string | null
  checks?: Record<string, boolean | string | null>
}
export type DerivedSourceAsset = {
  asset_id: string
  sha256: string
  width: number
  height: number
  name?: string
}
export type DerivedMaskRef = {asset_id: string; sha256: string; content_id?: string}
export type DerivedConfiguration = {
  source_asset_id: string
  mask_ref: DerivedMaskRef | null
  source_crop: number[] | null
  registered_size: number[] | null
  output_offset: number[] | null
  protected_rois: Record<string, number[]> | null
  model_regions: number[][]
  copy_exclusions: number[][]
  acknowledge_regions: boolean
}
export type DerivedSnapshot = {
  job_id: string
  available: boolean
  can_admit: boolean
  can_review: boolean
  context_sha: string
  revision: number
  hold_code: string | null
  proposals: DerivedProposal[]
  renders: DerivedRender[]
  selected_derived_id: string | null
  source_assets?: DerivedSourceAsset[]
}
export type DerivedAdmission = {admission_sha: string; recipe_sha: string; context_sha: string; revision: number}

const SHA = /^[a-f0-9]{64}$/
const MODES: readonly string[] = ['composed_protected_product', 'freeform_protected_product_hybrid']
const STATES: readonly string[] = ['QUEUED', 'RENDERING', 'REVIEW_REQUIRED', 'APPROVED',
  'COMPLETED', 'REJECTED', 'HOLD', 'FAILED', 'STALE']
export const derivedModeLabel = (mode: DerivedMode) => mode === 'composed_protected_product'
  ? '합성형 + 원본 제품 보호' : '자유형 + 원본 제품 보호 합성'
export const derivedQueryKey = (jobId: string) => ['derived-job', jobId] as const
export const derivedPath = (jobId: string) => `/demo/api/live/jobs/${encodeURIComponent(jobId)}/derived`

export function derivedArtifactPath(render: DerivedRender, kind: DerivedArtifactKind) {
  const sha = kind === 'preview' ? render.preview_sha : render[`${kind}_sha`]
  if (!sha || !SHA.test(sha)) return undefined
  const expected = `${derivedPath(render.job_id)}/renders/${encodeURIComponent(render.derived_id)}/artifacts/${kind}?sha256=${sha}`
  return render.artifacts[kind] === expected ? expected : undefined
}

export function belongsToDerivedContext(snapshot: DerivedSnapshot, render: DerivedRender) {
  return snapshot.available && render.job_id === snapshot.job_id &&
    SHA.test(snapshot.context_sha) && render.context_sha === snapshot.context_sha &&
    Number.isSafeInteger(render.revision) && render.revision >= 0 &&
    SHA.test(render.recipe_sha) && SHA.test(render.admission_sha) &&
    MODES.includes(render.render_mode) && STATES.includes(render.state)
}

export function derivedReviewReady(snapshot: DerivedSnapshot, render: DerivedRender,
  review: DerivedVisualReview, approvedCopy: AdCopy | undefined) {
  return belongsToDerivedContext(snapshot, render) && snapshot.can_review &&
    render.state === 'REVIEW_REQUIRED' && !snapshot.hold_code && !render.hold_code &&
    Boolean(render.preview_sha && SHA.test(render.preview_sha)) &&
    Boolean(approvedCopy && (['headline', 'subline', 'cta'] as const).every(
      field => review.observed_copy[field] === approvedCopy[field])) &&
    review.source_pixels_preserved && review.edges_acceptable && review.no_duplicate_product &&
    review.no_ghost_product && review.no_copy_occlusion && review.cta_policy_matches &&
    review.label_ground_truth_confirmed && review.mobile_readable
}

export function derivedFinalizeReady(snapshot: DerivedSnapshot, render: DerivedRender) {
  return belongsToDerivedContext(snapshot, render) && snapshot.can_review &&
    render.state === 'APPROVED' && !snapshot.hold_code && !render.hold_code &&
    Boolean(render.approval_sha && SHA.test(render.approval_sha) &&
      render.preview_sha && SHA.test(render.preview_sha))
}

export function derivedProposalReady(snapshot: DerivedSnapshot, proposal: DerivedProposal) {
  return snapshot.available && snapshot.can_admit && !snapshot.hold_code && !proposal.hold_code &&
    SHA.test(snapshot.context_sha) && Number.isSafeInteger(snapshot.revision) && snapshot.revision >= 0 &&
    SHA.test(proposal.recipe_sha) && MODES.includes(proposal.render_mode) &&
    Boolean(proposal.proposal_id)
}

export function checkedDerivedSnapshot(value: DerivedSnapshot, jobId: string): DerivedSnapshot {
  if (value.job_id !== jobId || !Array.isArray(value.proposals) || !Array.isArray(value.renders) ||
    typeof value.available !== 'boolean' || typeof value.can_admit !== 'boolean' ||
    typeof value.can_review !== 'boolean' || typeof value.context_sha !== 'string' ||
    !Number.isSafeInteger(value.revision) || value.revision < 0 ||
    value.proposals.some(proposal => !MODES.includes(proposal.render_mode)) ||
    value.renders.some(render => render.job_id !== jobId || !MODES.includes(render.render_mode) ||
      !STATES.includes(render.state))) {
    throw Error('원본 제품 보호 시안의 작업·버전 정보를 확인할 수 없습니다.')
  }
  return value
}

function validCoordinates(value: unknown, count: number): value is number[] {
  return Array.isArray(value) && value.length === count &&
    value.every(number => Number.isSafeInteger(number) && number >= 0)
}

export function parseDerivedGeometry(input: string): Pick<DerivedConfiguration,
  'source_crop' | 'registered_size' | 'output_offset' | 'protected_rois' | 'model_regions' | 'copy_exclusions'> {
  let value: Record<string, unknown>
  try {
    value = JSON.parse(input)
  } catch {
    throw Error('배치 설정은 JSON 형식으로 입력해 주세요.')
  }
  const fields = ['source_crop', 'registered_size', 'output_offset', 'protected_rois', 'model_regions', 'copy_exclusions']
  if (!value || Array.isArray(value) || typeof value !== 'object' ||
      Object.keys(value).some(key => !fields.includes(key)) ||
      (value.source_crop !== null && !validCoordinates(value.source_crop, 4)) ||
      (value.registered_size !== null && !validCoordinates(value.registered_size, 2)) ||
      (value.output_offset !== null && !validCoordinates(value.output_offset, 2)) ||
      !Array.isArray(value.model_regions) || !value.model_regions.every(box => validCoordinates(box, 4)) ||
      !Array.isArray(value.copy_exclusions) || !value.copy_exclusions.every(box => validCoordinates(box, 4)) ||
      (value.protected_rois !== null && (typeof value.protected_rois !== 'object' ||
        Array.isArray(value.protected_rois) || !Object.values(value.protected_rois).every(box => validCoordinates(box, 4))))) {
    throw Error('크롭·출력 크기·위치와 영역 좌표는 0 이상 정수로 입력해 주세요. 허용된 배치 필드만 사용할 수 있습니다.')
  }
  return value as ReturnType<typeof parseDerivedGeometry>
}
