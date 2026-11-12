export type CopyFields = {headline: string; subline: string; cta: string}
export type TextRegion = [number, number, number, number]
export type RevisionKind = 'image-corrections' | 'composed-copy-edits' | 'final-inpainting'
export const revisionPath = (jobId: string, kind: RevisionKind) =>
  `/demo/api/live/jobs/${encodeURIComponent(jobId)}/${kind}`

export function revisionSourcePath(jobId: string, path: string | undefined, sha: string) {
  const expected = `${revisionPath(jobId, 'image-corrections')}/source?sha256=${sha}`
  return /^[a-f0-9]{64}$/.test(sha) && path === expected ? path : undefined
}

/** The edit rectangle is deliberate, small and positive; never default to the whole ad. */
export function validTextRegion(region: TextRegion) {
  const [left, top, right, bottom] = region
  return region.every(Number.isFinite) && left >= 0 && top >= 0 && right <= 1 && bottom <= 1 &&
    right > left && bottom > top && (right - left) * (bottom - top) <= 0.25
}

export function revisionArtifactPath(jobId: string, kind: RevisionKind, recordId: string,
  artifact: string, path: string | undefined, sha: string | null | undefined) {
  if (!path || !sha || !/^[a-f0-9]{64}$/.test(sha) || !/^[a-f0-9]{32}$/.test(recordId)) return undefined
  const expected = `${revisionPath(jobId, kind)}/${recordId}/artifacts/${artifact}?sha256=${sha}`
  return path === expected ? path : undefined
}
