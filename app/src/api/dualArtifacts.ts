import type { DualMode } from './dualJobs'

export type DualArtifactKind = 'candidate' | 'final' | 'caption' | 'receipt'
type Size = {width: number; height: number}

export const dualPath = (jobId: string) => `/demo/api/qa/jobs/${encodeURIComponent(jobId)}/dual`

export function dualArtifactPath(jobId: string, mode: DualMode, kind: DualArtifactKind, supplied?: string, sha?: string | null) {
  if (!sha || !/^[a-f0-9]{64}$/.test(sha)) return undefined
  const expected = `${dualPath(jobId)}/${mode}/artifacts/${kind}?sha256=${sha}`
  return supplied === expected ? expected : undefined
}

export function matchesDualImageSize(size: Size | undefined, target: Size, kind: 'candidate' | 'final') {
  if (!size?.width || !size.height) return false
  if (kind === 'final') return size.width === target.width && size.height === target.height
  return size.width * target.height === size.height * target.width
}
