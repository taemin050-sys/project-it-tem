import { request } from './client'
import { dualPath, type DualArtifactKind } from './dualArtifacts'
import { copyApprovalPayload } from './liveJobs'
import type { LiveSnapshot, LiveState } from './liveMapping'
import type { Ratio } from '../config'

export type DualMode = 'composed' | 'freeform'
export type DualVariant = {
  mode: DualMode
  state: LiveState | 'FAILED'
  dispatch_state: 'PENDING' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | null
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
  verification_state: 'FIXTURE_REVIEW_REQUIRED' | 'FIXTURE_REVIEWED' | 'FIXTURE_REJECTED' | 'NOT_REVIEWED'
  artifacts: Partial<Record<DualArtifactKind, string>>
  cost: {provider_attempt_count: 0; actual_usd: null}
}
export type DualSnapshot = {
  job_id: string
  state: 'READY' | 'GENERATING' | 'REVIEW_REQUIRED' | 'PARTIAL' | 'COMPLETED' | 'FAILED'
  provenance: 'OFFLINE_FIXTURE'
  image_size: Ratio
  copy_sha: string | null
  copy_approval_sha: string | null
  preferred_variant: DualMode | null
  variants: Record<DualMode, DualVariant | null>
}

export const dualQueryKey = (jobId: string) => ['dual-job', jobId] as const

function mutate(jobId: string, action: string, body: unknown) {
  return request<DualSnapshot>(dualPath(jobId) + action, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  })
}

export const getDualJob = (jobId: string) => request<DualSnapshot>(dualPath(jobId))
export const startDualJob = (snapshot: LiveSnapshot, acknowledgeEvidence: boolean) =>
  mutate(snapshot.job_id, '/start', copyApprovalPayload(snapshot, acknowledgeEvidence))
export const decideDualVariant = (jobId: string, mode: DualMode, imageSha: string, approve: boolean, visualChecked: boolean) =>
  mutate(jobId, `/${mode}/decision`, {image_sha: imageSha, approve, visual_checked: visualChecked})
export const selectDualVariant = (jobId: string, mode: DualMode, finalSha: string) =>
  mutate(jobId, '/selection', {mode, final_sha: finalSha})

export function canResumeDualJob(snapshot: LiveSnapshot, group: DualSnapshot) {
  const awaitingDispatch = Object.values(group.variants).some(variant =>
    variant?.dispatch_state === 'PENDING' || variant?.dispatch_state === 'RUNNING')
  return awaitingDispatch && group.job_id === snapshot.job_id && snapshot.dual_requested === true &&
    snapshot.mode === 'OFFLINE_FIXTURE' && snapshot.approval_current && Boolean(group.copy_approval_sha) &&
    !['INPUT_STORED', 'COPY_REVIEW_REQUIRED', 'COPY_REJECTED'].includes(snapshot.state) &&
    Boolean(snapshot.review_sha && snapshot.copy_sha && snapshot.copy_sha === group.copy_sha) &&
    Number.isSafeInteger(snapshot.generation) && snapshot.generation > 0
}

export function resumeDualJob(snapshot: LiveSnapshot, group: DualSnapshot) {
  if (!canResumeDualJob(snapshot, group)) throw Error('현재 승인 상태에서 시안 준비를 이어갈 수 없습니다.')
  return mutate(snapshot.job_id, '/start', {expected_generation: snapshot.generation,
    expected_review_sha: snapshot.review_sha, acknowledge_evidence: true})
}
