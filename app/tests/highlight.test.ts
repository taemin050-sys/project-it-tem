import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { copyFieldText, splitByIssues } from '../src/lib/highlight.ts'
import type { AdCopyOutput, ComplianceIssue, ComplianceReport } from '../src/types/textSchema.ts'

// 텍스트 담당 실제 출력: feat/text-generation(c558539) scripts/test_highlight.py 예시 카피를 review_copy로 검수한 결과
const { copy, report } = JSON.parse(readFileSync(new URL('./fixtures/text_highlight_report.json', import.meta.url), 'utf8')) as
  { copy: AdCopyOutput; report: ComplianceReport }

const marked = (field: ComplianceIssue['field'], issues = report.issues) =>
  splitByIssues(copyFieldText(copy, field)!, issues.filter((i) => i.field === field)).filter((s) => s.issue).map((s) => s.text)

test('실제 검수 결과 10건이 모두 원문 표현 그대로 칠해진다 (이모지 뒤·해시태그 포함)', () => {
  const all = (['headline', 'subline', 'cta', 'caption', 'hashtags'] as const).flatMap((f) => marked(f))
  assert.deepEqual(all, report.issues.map((i) => i.text))
  assert.deepEqual(marked('subline'), ['피부 재생', '주름 개선'])
  assert.deepEqual(marked('hashtags'), ['필수템', '줄기세포'])
})

test('위치값이 JS(UTF-16) 기준으로 어긋나 와도 issue.text로 다시 찾아 칠한다', () => {
  const utf16 = report.issues.map((i) => {
    const text = copyFieldText(copy, i.field)!
    const at = text.indexOf(i.text)
    return { ...i, start: at, end: at + i.text.length }
  })
  assert.deepEqual(marked('subline', utf16), ['피부 재생', '주름 개선'])
  assert.deepEqual(marked('caption', utf16), ['2주 만에', '20% 개선', '진정', '의사가 추천'])
})

test('같은 표현이 여러 번 나오면: 위치가 맞으면 그 자리, 어긋나면 start에 가장 가까운 자리', () => {
  const text = '진정 효과 🌿 진정 케어 🌿 진정'
  const issue = (start: number, end: number) => ({ ...report.issues[0], text: '진정', start, end })
  const where = (i: ComplianceIssue) => {
    const segs = splitByIssues(text, [i])
    return Array.from(segs.slice(0, segs.findIndex((s) => s.issue)).map((s) => s.text).join('')).length
  }
  assert.equal(where(issue(8, 10)), 8)                   // 두 번째 '진정'(코드포인트 8) 그대로
  assert.equal(where(issue(9, 11)), 8)                   // UTF-16 기준(이모지로 1칸 밀림) → 가장 가까운 8
  assert.equal(where(issue(18, 20)), 16)                 // 세 번째(UTF-16 18, 이모지 2개로 2칸 밀림) → 16
})

test('겹치거나 찾을 수 없는 표현은 칠하지 않고 원문은 그대로 둔다', () => {
  const issue = (text: string, start: number, end: number) => ({ ...report.issues[0], text, start, end })
  const segs = splitByIssues('가나다라마', [issue('가나', 0, 2), issue('나다', 1, 3), issue('없음', 3, 5)])
  assert.equal(segs.map((s) => s.text).join(''), '가나다라마')
  assert.deepEqual(segs.filter((s) => s.issue).map((s) => s.text), ['가나'])
})
