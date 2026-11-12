import assert from 'node:assert/strict'
import test from 'node:test'
import {readFileSync} from 'node:fs'
import {revisionArtifactPath,revisionPath} from '../src/api/resultRevisionContract.ts'

test('Final inpainting downloads are bound to the independent final source namespace',()=>{
  const job='a'.repeat(32),id='b'.repeat(32),sha='c'.repeat(64)
  const url=`${revisionPath(job,'final-inpainting')}/${id}/artifacts/final?sha256=${sha}`
  assert.equal(revisionArtifactPath(job,'final-inpainting',id,'final',url,sha),url)
  assert.equal(revisionArtifactPath(job,'image-corrections',id,'final',url,sha),undefined)
  assert.equal(revisionArtifactPath(job,'final-inpainting',id,'preview',url,sha),undefined)
  assert.equal(revisionArtifactPath('f'.repeat(32),'final-inpainting',id,'final',url,sha),undefined)
})

test('MIT mask editor is pinned and license notices are shipped',()=>{
  const pkg=JSON.parse(readFileSync(new URL('../package.json',import.meta.url),'utf8'))
  assert.equal(pkg.dependencies['react-konva'],'19.3.2')
  assert.equal(pkg.dependencies.konva,'10.9.1')
  for(const file of ['konva-MIT.txt','react-konva-MIT.txt']){
    const license=readFileSync(new URL('../public/licenses/'+file,import.meta.url),'utf8')
    assert.ok(license.includes('MIT License')&&license.includes('Copyright'))
  }
})
