import assert from 'node:assert/strict'
import { test } from 'node:test'
import { toPixelBox } from '../src/lib/geometry.ts'
import { validateImages } from '../src/lib/validateImages.ts'

const limits = { minFiles: 1, maxFiles: 3, maxBytes: 10, acceptTypes: ['image/png'] }
const png = (name: string, size = 1) => new File([new Uint8Array(size)], name, { type: 'image/png' })

test('정상 파일은 오류 없음', () => {
  assert.deepEqual(validateImages([png('a.png')], limits), [])
})

test('0장·4장 개수 오류', () => {
  assert.equal(validateImages([], limits).length, 1)
  assert.equal(validateImages([png('a'), png('b'), png('c'), png('d')], limits).length, 1)
})

test('형식·용량 오류', () => {
  const gif = new File(['x'], 'a.gif', { type: 'image/gif' })
  const [typeErr, sizeErr] = validateImages([gif, png('big.png', 11)], limits)
  assert.match(typeErr, /a\.gif.*형식/)
  assert.match(sizeErr, /big\.png.*MB/)
})

test('정규화 좌표 → 1080×1350 픽셀', () => {
  assert.deepEqual(toPixelBox([0.25, 0.5, 0.5, 0.25], 1080, 1350), {
    left: 270, top: 675, width: 540, height: 338,
  })
})
