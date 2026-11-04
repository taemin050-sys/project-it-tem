import assert from 'node:assert/strict'
import { test } from 'node:test'
import { copyFieldText } from '../src/lib/highlight.ts'
import { overLimits } from '../src/lib/copyLimits.ts'
import { mockCopyReview, revisedMockCopy, reviewMockCopy, type CopyVariant } from '../src/mocks/sampleResult.ts'

for (const variant of ['default', 'blocked', 'long', 'short'] as CopyVariant[]) {
  const { copy, report } = mockCopyReview(variant)

  test(`mock 검수 위치값(start, end)이 원문과 일치 (${variant})`, () => {
    for (const issue of report.issues) {
      assert.equal(Array.from(copyFieldText(copy, issue.field)!).slice(issue.start, issue.end).join(''), issue.text, `${issue.field}: ${issue.text}`)
    }
  })

  test(`passed는 '위반 의심'이 없을 때만 true (${variant})`, () => {
    assert.equal(report.passed, !report.issues.some((i) => i.risk_level === '위반 의심'))
    assert.equal(report.passed, variant !== 'blocked')
  })
}

test('mock 수정 요청 카피는 매번 바뀌고 글자 수 기준 안이며 같은 규칙으로 다시 검수된다', () => {
  const { copy } = mockCopyReview('long')
  const revised = [0, 1, 2].map((n) => revisedMockCopy(copy, '더 짧게', n))
  assert.equal(new Set(revised.map((r) => r.ad_copy.headline)).size, 3)
  for (const r of revised) assert.deepEqual(overLimits(r.ad_copy), [])
  assert.match(revised[0].plan.concept, /더 짧게/)
  assert.equal(reviewMockCopy({ ...copy, caption: '피부 재생 세럼' }).passed, false)
})
