import test from 'node:test'
import assert from 'node:assert/strict'
import { hasEmbeddedMpoSignature, hasMpoPrimarySignature, isMpoFile } from '../src/lib/mpo.ts'
import { A51D_MPO_FIXTURE, confirmedMpoChoice, requiresMpoFixtureSelection
} from '../src/lib/a51dMpoSelection.ts'

function file(name:string, mpf:boolean) {
  const jpeg = new Uint8Array([
    255,216,255,226,0,6,mpf ? 77 : 65,mpf ? 80 : 66,mpf ? 70 : 67,0,
    255,217, 1,2,3,4,5,6,7,8,9,10
  ])
  return new File([jpeg], name, {type:'image/jpeg'})
}

test('A51D actual MPO signature detects .jpg and .mpo without trusting extension', async() => {
  const jpgMpo=file('beauty-product.jpg',true)
  const classicMpo=file('beauty-product.mpo',true)
  assert.equal(isMpoFile(jpgMpo),false)
  assert.equal(isMpoFile(classicMpo),true)
  assert.equal(await hasMpoPrimarySignature(jpgMpo),false)
  assert.equal(await hasEmbeddedMpoSignature(jpgMpo),true)
  assert.equal(await hasEmbeddedMpoSignature(classicMpo),true)
  assert.equal(await hasEmbeddedMpoSignature(file('beauty-product.jpg',false)),false)
  assert.equal(await hasEmbeddedMpoSignature(file('beauty-product.png',true)),false)
})

test('A51D fixture opt-in defaults off and does not implicitly choose frames', async() => {
  const source=file('product.jpg',true)
  assert.equal(A51D_MPO_FIXTURE,false)
  assert.equal(confirmedMpoChoice(source),undefined)
  assert.equal(await requiresMpoFixtureSelection(source),false)
})
