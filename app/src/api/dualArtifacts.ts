import type { DualMode } from './dualJobs'

export type DualProvenance = 'OFFLINE_FIXTURE' | 'LIVE_DUAL'
export type DualArtifactKind = 'candidate' | 'final' | 'caption' | 'receipt'
type Size = {width: number; height: number}

export const dualPath = (jobId: string, provenance: DualProvenance = 'OFFLINE_FIXTURE') =>
  `/demo/api/${provenance === 'LIVE_DUAL' ? 'live' : 'qa'}/jobs/${encodeURIComponent(jobId)}/dual`

export function checkedDualSnapshotRatio<T extends {image_size: unknown}>(snapshot: T): T {
  if (!snapshot || !['3:4', '4:5', '9:16'].includes(snapshot.image_size as string)) {
    throw Error('저장된 두 시안의 출력 비율을 확인하지 못했습니다.')
  }
  return snapshot
}

export function dualArtifactPath(jobId: string, mode: DualMode, kind: DualArtifactKind, supplied?: string, sha?: string | null, provenance: DualProvenance = 'OFFLINE_FIXTURE') {
  if (!sha || !/^[a-f0-9]{64}$/.test(sha)) return undefined
  const expected = `${dualPath(jobId, provenance)}/${mode}/artifacts/${kind}?sha256=${sha}`
  return supplied === expected ? expected : undefined
}

export function matchesDualImageSize(size: Size | undefined, target: Size, kind: 'candidate' | 'final') {
  if (!size?.width || !size.height) return false
  if (kind === 'final') return size.width === target.width && size.height === target.height
  return size.width * target.height === size.height * target.width
}
