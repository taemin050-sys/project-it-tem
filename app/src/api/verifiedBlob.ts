/** FE SHA contract: an image or caption must be the exact immutable server artifact.
 * Cache keys must include the expected SHA, not only an otherwise reusable URL.
 * Fail closed on malformed SHA, changed bytes, or a missing secure SubtleCrypto.
 */
export async function assertBlobSha(blob: Blob, expectedSha: string): Promise<Blob> {
  if (!/^[0-9a-f]{64}$/.test(expectedSha)) throw Error('ARTIFACT_SHA_INVALID')
  if (!globalThis.crypto?.subtle) throw Error('ARTIFACT_SHA_VERIFICATION_UNAVAILABLE')
  const bytes = new Uint8Array(await blob.arrayBuffer())
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
  const actual = Array.from(digest, byte => byte.toString(16).padStart(2, '0')).join('')
  if (actual !== expectedSha) throw Error('ARTIFACT_SHA_MISMATCH')
  return blob
}
