import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fitWithin } from '../src/lib/shrinkImage.ts'
import { validateImages } from '../src/lib/validateImages.ts'

const limits = { minFiles: 2, maxFiles: 5, acceptTypes: ['image/png'] }
const png = (name: string, size = 1) => new File([new Uint8Array(size)], name, { type: 'image/png' })

test('정상 파일은 오류 없음 (용량 제한 없음)', () => {
  assert.deepEqual(validateImages([png('a.png', 50_000_000), png('b.png')], limits, '제품 사진'), [])
})

test('1장·6장 개수 오류', () => {
  assert.match(validateImages([png('a')], limits, '제품 사진')[0], /제품 사진을 2장 이상/)
  assert.match(validateImages(Array.from({ length: 6 }, (_, i) => png(`${i}`)), limits, '제품 사진')[0], /최대 5장/)
})

test('형식 오류', () => {
  const gif = new File(['x'], 'a.gif', { type: 'image/gif' })
  assert.match(validateImages([gif, png('b')], limits, '제품 사진')[0], /a\.gif.*형식/)
})

test('자동 축소: 긴 변만 기준에 맞추고 비율 유지, 작은 사진은 그대로', () => {
  assert.deepEqual(fitWithin(4000, 3000, 2048), { width: 2048, height: 1536 })
  assert.deepEqual(fitWithin(3000, 6000, 2048), { width: 1024, height: 2048 })
  assert.deepEqual(fitWithin(800, 600, 2048), { width: 800, height: 600 })
})
