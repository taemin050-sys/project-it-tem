import test from 'node:test'
import assert from 'node:assert/strict'
import {createHash} from 'node:crypto'
import {assertBlobSha} from '../src/api/verifiedBlob.ts'

test('live candidate and final bytes must match their exact server SHA', async () => {
  const payload = new Blob([new Uint8Array([137, 80, 78, 71, 1, 2, 3])], {type:'image/png'})
  const expected = createHash('sha256').update(Buffer.from(await payload.arrayBuffer())).digest('hex')
  assert.equal(await assertBlobSha(payload, expected), payload)
  await assert.rejects(assertBlobSha(new Blob(['older candidate']), expected), /ARTIFACT_SHA_MISMATCH/)
  await assert.rejects(assertBlobSha(payload, 'invalid'), /ARTIFACT_SHA_INVALID/)
})

test('UTF-8 caption bytes are also SHA-bound', async () => {
  const caption = new Blob(['한글 카피\n#화장품'], {type:'text/plain;charset=utf-8'})
  const expected = createHash('sha256').update(Buffer.from(await caption.arrayBuffer())).digest('hex')
  assert.equal(await assertBlobSha(caption, expected), caption)
  await assert.rejects(assertBlobSha(new Blob(['한글 카피\n#기타']), expected), /ARTIFACT_SHA_MISMATCH/)
})
