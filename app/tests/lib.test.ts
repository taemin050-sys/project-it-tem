import assert from 'node:assert/strict'
import { test } from 'node:test'
import { countChars, overLimits } from '../src/lib/copyLimits.ts'
import { fitWithin } from '../src/lib/shrinkImage.ts'
import { validateImages } from '../src/lib/validateImages.ts'

const limits = { minFiles: 2, maxFiles: 5, acceptTypes: ['image/png'] }
const png = (name: string, size = 1) => new File([new Uint8Array(size)], name, { type: 'image/png' })

test('글자 수: 공백 포함·줄바꿈 제외, 헤드 15·서브 25·CTA 10자 초과만 막는다', () => {
  assert.equal(countChars('가볍게 스며드는\n데일리 보습'), 14)
  assert.equal(countChars('💧 촉촉'), 4)
  const ok = { headline: '가'.repeat(15), subline: `${'나'.repeat(15)}\n${'다'.repeat(10)}`, cta: '라'.repeat(10) }
  assert.deepEqual(overLimits(ok), [])
  assert.deepEqual(overLimits({ ...ok, headline: '가'.repeat(16), cta: '라'.repeat(11) }), ['헤드 16자 (기준 15자)', 'CTA 11자 (기준 10자)'])
})

test('서브: 총 25자 안이어도 한 줄 15자·2줄을 넘으면 막고, 헤드·CTA는 1줄만', () => {
  const ok = { headline: '헤드', subline: '서브', cta: 'CTA' }
  assert.deepEqual(overLimits({ ...ok, subline: `${'가'.repeat(16)}\n${'나'.repeat(9)}` }), ['서브 한 줄 16자 (기준 15자)'])
  assert.deepEqual(overLimits({ ...ok, subline: `${'가'.repeat(15)}\n${'나'.repeat(10)}` }), [])
  assert.deepEqual(overLimits({ ...ok, subline: '가\n나\n다' }), ['서브 3줄 (기준 2줄)'])
  assert.deepEqual(overLimits({ ...ok, headline: '헤드\n둘', cta: '보기\n하기' }), ['헤드에 줄바꿈 있음 (기준 1줄)', 'CTA에 줄바꿈 있음 (기준 1줄)'])
})

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
