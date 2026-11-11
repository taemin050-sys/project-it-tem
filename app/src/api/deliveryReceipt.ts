/** User-download proof for a genuine completed LIVE Image Owner Job.
 * Never interpret an offline/mock composition receipt as proof of a billable model.
 */
export function assertLiveReceiptBinding(
  value: unknown, jobId: string, imageSha: string,
): asserts value is Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw Error('LIVE_RECEIPT_INVALID')
  const receipt=value as Record<string, unknown>
  const ev=receipt.image_provider_evidence
  if (!ev || typeof ev !== 'object' || Array.isArray(ev))
    throw Error('LIVE_RECEIPT_PROVIDER_EVIDENCE_MISSING')
  const proof=ev as Record<string, unknown>
  // The Owner composition receipt does not contain a Job ID. The authenticated
  // artifact endpoint binds it via X-IT-TEM-Job-ID, checked before this call.
  if ((receipt.job_id !== undefined && receipt.job_id !== jobId) ||
      proof.image_sha256 !== imageSha ||
      typeof proof.owner_attempt_id !== 'string' || !proof.owner_attempt_id ||
      typeof proof.provider_request_id !== 'string' || !proof.provider_request_id ||
      typeof proof.model !== 'string' || !proof.model ||
      !proof.usage || typeof proof.usage !== 'object' ||
      Array.isArray(proof.usage) || Object.keys(proof.usage).length === 0)
    throw Error('LIVE_RECEIPT_JOB_PROVIDER_BINDING_INVALID')
}
