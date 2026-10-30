import type { AdCopyOutput, ComplianceIssue, CopyField } from '../types/textSchema'

export type Segment = { text: string; issue?: ComplianceIssue }

// 검수 대상 문구. 텍스트 모듈 rule_checker.copy_fields와 같다 (해시태그는 공백으로 이어 붙인 문자열 기준)
export function copyFieldText(copy: AdCopyOutput, field: CopyField): string | undefined {
  switch (field) {
    case 'headline':
    case 'subline':
    case 'cta':
      return copy.ad_copy[field]
    case 'caption':
      return copy.caption
    case 'hashtags':
      return copy.hashtags.join(' ')
    default:
      return undefined
  }
}

// start/end는 Python str 위치(코드포인트, end 미포함)라 Array.from으로 자른다 — JS slice는 이모지 뒤부터 어긋난다.
// 위치로 자른 글자가 issue.text와 다르면 issue.text로 다시 찾는다 (텍스트 담당 권장, 다른 표현을 칠하지 않기 위해)
export function splitByIssues(text: string, issues: ComplianceIssue[]): Segment[] {
  const chars = Array.from(text)
  const segments: Segment[] = []
  let pos = 0
  for (const issue of [...issues].sort((a, b) => a.start - b.start)) {
    let { start, end } = issue
    if (chars.slice(start, end).join('') !== issue.text) {
      const at = issue.text ? text.indexOf(issue.text, chars.slice(0, pos).join('').length) : -1
      if (at < 0) continue
      start = Array.from(text.slice(0, at)).length
      end = start + Array.from(issue.text).length
    }
    // 겹치거나 범위를 벗어난 위치값은 하이라이트하지 않는다 (검수 목록에는 그대로 나온다)
    if (start < pos || end > chars.length || start >= end) continue
    if (start > pos) segments.push({ text: chars.slice(pos, start).join('') })
    segments.push({ text: chars.slice(start, end).join(''), issue })
    pos = end
  }
  if (pos < chars.length) segments.push({ text: chars.slice(pos).join('') })
  return segments
}
