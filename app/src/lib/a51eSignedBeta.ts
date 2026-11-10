/** A51E SSO-only NONBILLABLE integration candidate.

Owner/PM MPO policy is PENDING, thus reject multi-frame on the UI and on
the actual server. This feature flag does not authorize real photos,
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
