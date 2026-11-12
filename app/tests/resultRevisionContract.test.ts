import assert from 'node:assert/strict'
import test from 'node:test'
import { revisionArtifactPath, revisionPath, revisionSourcePath, validTextRegion } from '../src/api/resultRevisionContract.ts'

test('Text editing requires an intentional bounded region; malformed or whole-ad requests are rejected', () => {
  assert.equal(validTextRegion([0.2, 0.14, 0.8, 0.22]), true)
  for (const region of [[0,0,0,0], [0,0,1,1], [0.8,0.2,0.2,0.3], [-0.1,0,0.2,0.2], [0,NaN,0.2,0.3]]) {
    assert.equal(validTextRegion(region as [number,number,number,number]), false)
  }
})

test('Correction downloads cannot mix another Job, edit type, result or hash', () => {
  const job='a'.repeat(32), id='b'.repeat(32), sha='c'.repeat(64)
  const url=`${revisionPath(job,'image-corrections')}/${id}/artifacts/final?sha256=${sha}`
  assert.equal(revisionArtifactPath(job,'image-corrections',id,'final',url,sha),url)
  assert.equal(revisionArtifactPath(job,'composed-copy-edits',id,'final',url,sha),undefined)
  assert.equal(revisionArtifactPath('d'.repeat(32),'image-corrections',id,'final',url,sha),undefined)
  assert.equal(revisionArtifactPath(job,'image-corrections','e'.repeat(32),'final',url,sha),undefined)
  assert.equal(revisionArtifactPath(job,'image-corrections',id,'final',url,'f'.repeat(64)),undefined)
  assert.equal(revisionArtifactPath(job,'image-corrections',id,'preview',url,sha),undefined)
  const source = `${revisionPath(job,'image-corrections')}/source?sha256=${sha}`
  assert.equal(revisionSourcePath(job,source,sha),source)
  assert.equal(revisionSourcePath('e'.repeat(32),source,sha),undefined)
  assert.equal(revisionSourcePath(job,'https://example.com/private.png',sha),undefined)
})
