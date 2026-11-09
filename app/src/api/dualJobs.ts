import { request } from './client'
import { dualPath, type DualArtifactKind, type DualProvenance } from './dualArtifacts'
import { copyApprovalPayload } from './liveJobs'
import type { LiveSnapshot, LiveState } from './liveMapping'
import type { Ratio } from '../config'

export type DualMode = 'composed' | 'freeform'
export type DualCost = {
  provider_attempt_count: number
  actual_usd: null
  status?: 'NOT_DISPATCHED' | 'AWAITING_RECEIPT' | 'UNPRICED' | 'BILLING_UNKNOWN'
  attempts?: Array<{attempt_id: string; stage: string; state: string; model: string | null;
    usage: Record<string, number> | null; billing_unknown: boolean}>
}
export type LiveVisualReview = {
  product_matches: boolean
  label_matches: boolean
  cta_policy_matches: boolean
  observed_copy?: {headline: string; subline: string; cta: string}
  no_extra_text?: boolean
}
export type DualVariant = {
  mode: DualMode
  state: LiveState | 'FAILED' | 'HOLD'
  dispatch_state: 'PENDING' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'BILLING_UNKNOWN' | null
  variant_job_id: string
  approval_sha: string | null
  review_sha: string | null
  image_review_sha: string | null
  candidate_sha: string | null
  final_sha: string | null
  caption_sha: string | null
  receipt_sha: string | null
  error_code: string | null
  output_size: {width: number; height: number} | null
  verification_state: 'FIXTURE_REVIEW_REQUIRED' | 'FIXTURE_REVIEWED' | 'FIXTURE_REJECTED' |
    'LIVE_REVIEW_REQUIRED' | 'LIVE_REVIEWED' | 'LIVE_REJECTED' | 'NOT_REVIEWED'
  artifacts: Partial<Record<DualArtifactKind, string>>
  cost: DualCost
  provider_evidence?: {shared_prompt_sha: string; provider_prompt_sha: string | null;
    provider_request_sha: string; owner_attempt_id: string; owner_receipt_sha: string;
    cost_attempt_id: string; cost_receipt_sha: string} | null
}
export type DualSnapshot = {
  job_id: string
  state: 'READY' | 'GENERATING' | 'REVIEW_REQUIRED' | 'PARTIAL' | 'COMPLETED' | 'FAILED' | 'HOLD'
  provenance: DualProvenance
  image_size: Ratio
  copy_sha: string | null
  copy_approval_sha: string | null
  preferred_variant: DualMode | null
  variants: Record<DualMode, DualVariant | null>
  hold_code?: string | null
  shared_text_cost?: DualCost
  image_request_count?: 2
}

export const snapshotDualProvenance = (snapshot: LiveSnapshot): DualProvenance =>
  snapshot.dual_provenance === 'LIVE_DUAL' ? 'LIVE_DUAL' : 'OFFLINE_FIXTURE'
export const dualQueryKey = (jobId: string, provenance: DualProvenance = 'OFFLINE_FIXTURE') =>
  ['dual-job', jobId, provenance] as const

function mutate(jobId: string, provenance: DualProvenance, action: string, body: unknown) {
  return request<DualSnapshot>(dualPath(jobId, provenance) + action, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  })
}

export const getDualJob = (jobId: string, provenance: DualProvenance = 'OFFLINE_FIXTURE') =>
  request<DualSnapshot>(dualPath(jobId, provenance))
export function startDualJob(snapshot: LiveSnapshot, acknowledgeEvidence: boolean, acknowledgeTwoImages = false) {
  const provenance = snapshotDualProvenance(snapshot)
  return mutate(snapshot.job_id, provenance, '/start', {
    ...copyApprovalPayload(snapshot, acknowledgeEvidence),
    ...(provenance === 'LIVE_DUAL' ? {acknowledge_two_images: acknowledgeTwoImages} : {}),
  })
}
export function decideDualVariant(group: DualSnapshot, mode: DualMode, imageSha: string,
  approve: boolean, visualReview?: LiveVisualReview) {
  return mutate(group.job_id, group.provenance, `/${mode}/decision`, {
    image_sha: imageSha, approve,
    ...(group.provenance === 'LIVE_DUAL'
      ? visualReview && {visual_review: visualReview} : {visual_checked: approve}),
  })
}
export const selectDualVariant = (group: DualSnapshot, mode: DualMode, finalSha: string) =>
  mutate(group.job_id, group.provenance, '/selection', {mode, final_sha: finalSha})

export function canResumeDualJob(snapshot: LiveSnapshot, group: DualSnapshot) {
  const awaitingDispatch = Object.values(group.variants).some(variant =>
    variant?.dispatch_state === 'PENDING' || variant?.dispatch_state === 'RUNNING')
  return group.provenance === 'OFFLINE_FIXTURE' && awaitingDispatch &&
    group.job_id === snapshot.job_id && snapshot.dual_requested === true &&
    snapshot.mode === 'OFFLINE_FIXTURE' && snapshot.approval_current && Boolean(group.copy_approval_sha) &&
    !['INPUT_STORED', 'COPY_REVIEW_REQUIRED', 'COPY_REJECTED'].includes(snapshot.state) &&
    Boolean(snapshot.review_sha && snapshot.copy_sha && snapshot.copy_sha === group.copy_sha) &&
    Number.isSafeInteger(snapshot.generation) && snapshot.generation > 0
}

export function resumeDualJob(snapshot: LiveSnapshot, group: DualSnapshot) {
  if (!canResumeDualJob(snapshot, group)) throw Error('현재 승인 상태에서 시안 준비를 이어갈 수 없습니다.')
  return mutate(snapshot.job_id, group.provenance, '/start', {expected_generation: snapshot.generation,
    expected_review_sha: snapshot.review_sha, acknowledge_evidence: true})
}
