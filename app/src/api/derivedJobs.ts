import { ApiError, request } from './client'
import {
  belongsToDerivedContext, checkedDerivedSnapshot, derivedFinalizeReady, derivedPath,
  derivedProposalReady, derivedReviewReady,
  type DerivedAdmission, type DerivedConfiguration, type DerivedMaskRef, type DerivedProposal,
  type DerivedRender, type DerivedSnapshot, type DerivedVisualReview,
} from './derivedContract'
import type { AdCopy } from '../types/textSchema'

export * from './derivedContract'
const SHA = /^[a-f0-9]{64}$/

async function mutate<T>(jobId: string, action: string, body: unknown): Promise<T> {
  return request<T>(derivedPath(jobId) + action, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  })
}

export async function getDerivedJob(jobId: string) {
  try {
    return checkedDerivedSnapshot(await request<DerivedSnapshot>(derivedPath(jobId)), jobId)
  } catch (cause) {
    if (cause instanceof ApiError && [404, 405, 501].includes(cause.status)) return null
    throw cause
  }
}

export async function prepareDerivedRender(snapshot: DerivedSnapshot, proposal: DerivedProposal) {
  if (!derivedProposalReady(snapshot, proposal)) throw Error('현재 검토 상태에서 원본 제품 보호 시안을 준비할 수 없습니다.')
  const admission = await mutate<DerivedAdmission>(snapshot.job_id, '/recipes/admit', {
    proposal_id: proposal.proposal_id, expected_context_sha: snapshot.context_sha,
    expected_recipe_sha: proposal.recipe_sha, expected_revision: snapshot.revision,
    acknowledge_source: true,
  })
  if (admission.recipe_sha !== proposal.recipe_sha || admission.context_sha !== snapshot.context_sha ||
    !SHA.test(admission.admission_sha)) throw Error('승인한 Recipe와 준비할 시안의 맥락이 일치하지 않습니다.')
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(
    [proposal.proposal_id, proposal.recipe_sha, snapshot.context_sha, admission.admission_sha].join('\n')))
  const idempotencyKey = Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('')
  return mutate<DerivedRender>(snapshot.job_id, '/renders', {
    admission_sha: admission.admission_sha, expected_recipe_sha: proposal.recipe_sha,
    expected_context_sha: snapshot.context_sha, idempotency_key: idempotencyKey,
  })
}

export function decideDerivedRender(snapshot: DerivedSnapshot, render: DerivedRender,
  approve: boolean, visualReview: DerivedVisualReview, approvedCopy: AdCopy | undefined) {
  if (!belongsToDerivedContext(snapshot, render) || !snapshot.can_review ||
    render.state !== 'REVIEW_REQUIRED' || !render.preview_sha ||
    (approve && !derivedReviewReady(snapshot, render, visualReview, approvedCopy))) {
    throw Error('현재 시안의 승인 맥락과 검수 항목을 확인해 주세요.')
  }
  return mutate<DerivedRender>(render.job_id, `/renders/${encodeURIComponent(render.derived_id)}/decision`, {
    expected_revision: render.revision, expected_preview_sha: render.preview_sha,
    expected_recipe_sha: render.recipe_sha, expected_context_sha: render.context_sha,
    approve, visual_review: visualReview,
  })
}

export function finalizeDerivedRender(snapshot: DerivedSnapshot, render: DerivedRender) {
  if (!derivedFinalizeReady(snapshot, render)) throw Error('승인된 원본 제품 보호 시안을 확인해 주세요.')
  return mutate<DerivedRender>(render.job_id, `/renders/${encodeURIComponent(render.derived_id)}/finalize`, {
    expected_revision: render.revision, expected_approval_sha: render.approval_sha,
    expected_preview_sha: render.preview_sha,
  })
}

export function selectDerivedRender(snapshot: DerivedSnapshot, render: DerivedRender) {
  if (!belongsToDerivedContext(snapshot, render) || render.state !== 'COMPLETED' ||
    !render.final_sha || !SHA.test(render.final_sha) || !render.approval_sha || !SHA.test(render.approval_sha)) {
    throw Error('완료된 원본 제품 보호 시안을 확인해 주세요.')
  }
  return mutate<DerivedSnapshot>(render.job_id, '/selection', {
    derived_id: render.derived_id, expected_final_sha: render.final_sha,
    expected_approval_sha: render.approval_sha,
  })
}


export async function uploadDerivedMask(jobId: string, file: File) {
  if (file.type !== 'image/png' && !file.name.toLowerCase().endsWith('.png')) {
    throw Error('제품 마스크는 PNG 파일로 올려 주세요.')
  }
  const form = new FormData()
  form.append('kind', 'product_mask')
  form.append('file', file)
  const ref = await request<DerivedMaskRef>(derivedPath(jobId) + '/assets', {method: 'POST', body: form})
  if (!ref.asset_id || !SHA.test(ref.sha256)) throw Error('마스크 자산의 저장 기록을 확인하지 못했습니다.')
  return ref
}

export function configureDerivedProposal(snapshot: DerivedSnapshot, body: DerivedConfiguration) {
  if (!snapshot.available || !snapshot.can_admit || !body.acknowledge_regions ||
      !snapshot.source_assets?.some(asset => asset.asset_id === body.source_asset_id)) {
    throw Error('원본 제품과 배치·검토 영역을 확인해 주세요.')
  }
  return mutate<unknown>(snapshot.job_id, '/proposals', body)
}
