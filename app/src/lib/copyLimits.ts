import type { AdCopy } from '../types/textSchema'

// 텍스트 담당 기준(copy_generator.py check_copy_limits): 헤드 15자·1줄, 서브 25자·한 줄 15자·2줄, CTA 10자·1줄
export const COPY_LIMITS = { headline: 15, subline: 25, cta: 10 } as const
export const SUBLINE_LINE_MAX = 15
export const SUBLINE_MAX_LINES = 2

// 공백·문장부호 포함, 줄바꿈 제외. 코드포인트 기준이라 텍스트 쪽 Python len과 같다
export const countChars = (s: string) => Array.from(s.replace(/\n/g, '')).length

// 기준을 넘은 항목 안내 문구 (없으면 빈 배열). 문구는 텍스트 check_copy_limits와 같은 형식
export function overLimits(ad: AdCopy): string[] {
  const out: string[] = []
  const lines = ad.subline.split('\n')
  const lineMax = Math.max(...lines.map((l) => Array.from(l).length))
  if (countChars(ad.headline) > COPY_LIMITS.headline) out.push(`헤드 ${countChars(ad.headline)}자 (기준 ${COPY_LIMITS.headline}자)`)
  if (ad.headline.includes('\n')) out.push('헤드에 줄바꿈 있음 (기준 1줄)')
  if (countChars(ad.subline) > COPY_LIMITS.subline) out.push(`서브 ${countChars(ad.subline)}자 (기준 ${COPY_LIMITS.subline}자)`)
  if (lines.length > SUBLINE_MAX_LINES) out.push(`서브 ${lines.length}줄 (기준 ${SUBLINE_MAX_LINES}줄)`)
  if (lineMax > SUBLINE_LINE_MAX) out.push(`서브 한 줄 ${lineMax}자 (기준 ${SUBLINE_LINE_MAX}자)`)
  if (countChars(ad.cta) > COPY_LIMITS.cta) out.push(`CTA ${countChars(ad.cta)}자 (기준 ${COPY_LIMITS.cta}자)`)
  if (ad.cta.includes('\n')) out.push('CTA에 줄바꿈 있음 (기준 1줄)')
  return out
}
