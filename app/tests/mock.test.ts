import assert from 'node:assert/strict'
import { test } from 'node:test'
import { copyFieldText } from '../src/lib/highlight.ts'
import { mockCopyReview, type CopyVariant } from '../src/mocks/sampleResult.ts'

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
