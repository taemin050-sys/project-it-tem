/** A51E SSO-only NONBILLABLE integration candidate.

PM confirmed REJECT_MULTIFRAME_V1 in Issue #38 on 2026-11-11. The
existing pre-resize MPO rejection remains the chosen Beta policy. This feature flag does not authorize real photos,
paid workers, GCP deployment or commercial release.
*/
import { hasEmbeddedMpoSignature, isMpoFile } from './mpo.ts'

export const A51E_SIGNED_BETA_CANDIDATE =
  import.meta.env?.VITE_A51E_SIGNED_BETA_CANDIDATE === 'YES'

export async function isPendingMpo(file:File):Promise<boolean> {
  if(!A51E_SIGNED_BETA_CANDIDATE)return false
  // An early UX check only: server performs full decoded-container denial.
  return isMpoFile(file) || hasEmbeddedMpoSignature(file)
}

export function newUploadRequestId():string {
  // Stable through a retry of the same form input, but never reuse for a
  // changed set of photos or changed copy/mode/ratio inputs.
  return crypto.randomUUID().replace(/-/g,'')
}
