import assert from 'node:assert/strict'
import test from 'node:test'
import { dualArtifactPath, dualPath, matchesDualImageSize } from '../src/api/dualArtifacts.ts'

test('Dual artifact paths bind job, mode, kind and exact SHA before any GET', () => {
  const sha = 'a'.repeat(64)
  const job = 'id-with/slash'
  const url = `/demo/api/qa/jobs/id-with%2Fslash/dual/freeform/artifacts/final?sha256=${sha}`
  assert.equal(dualPath(job), '/demo/api/qa/jobs/id-with%2Fslash/dual')
  assert.equal(dualArtifactPath(job, 'freeform', 'final', url, sha), url)
  assert.equal(dualArtifactPath('another-job', 'freeform', 'final', url, sha), undefined)
  assert.equal(dualArtifactPath(job, 'composed', 'final', url, sha), undefined)
  assert.equal(dualArtifactPath(job, 'freeform', 'candidate', url, sha), undefined)
  assert.equal(dualArtifactPath(job, 'freeform', 'final', url, 'b'.repeat(64)), undefined)
  assert.equal(dualArtifactPath(job, 'freeform', 'final', url, null), undefined)
})

test('Dual candidates accept the native ratio while finals require exact export dimensions', () => {
  for (const [native, final] of [[1536, 1440], [1440, 1350], [2048, 1920]]) {
    const candidate = {width: 1152, height: native}
    const target = {width: 1080, height: final}
    assert.equal(matchesDualImageSize(candidate, target, 'candidate'), true)
    assert.equal(matchesDualImageSize(candidate, target, 'final'), false)
    assert.equal(matchesDualImageSize(target, target, 'final'), true)
    assert.equal(matchesDualImageSize({...candidate, height: native + 1}, target, 'candidate'), false)
  }
  assert.equal(matchesDualImageSize(undefined, {width: 1080, height: 1350}, 'candidate'), false)
})
