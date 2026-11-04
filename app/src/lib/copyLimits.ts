import type { AdCopy } from '../types/textSchema'

// 텍스트 담당 기준(copy_generator.py): 헤드 15자, 서브 25자, CTA 10자
export const COPY_LIMITS = { headline: 15, subline: 25, cta: 10 } as const
export type LimitedField = keyof typeof COPY_LIMITS

const LABELS: Record<LimitedField, string> = { headline: '헤드', subline: '서브', cta: 'CTA' }

// 공백·문장부호 포함, 줄바꿈 제외. 코드포인트 기준이라 텍스트 쪽 Python len과 같다
export const countChars = (s: string) => Array.from(s.replace(/\n/g, '')).length

// 기준을 넘은 항목 안내 문구 (없으면 빈 배열)
export const overLimits = (ad: AdCopy) =>
  (Object.keys(COPY_LIMITS) as LimitedField[])
    .filter((f) => countChars(ad[f]) > COPY_LIMITS[f])
    .map((f) => `${LABELS[f]} ${countChars(ad[f])}자 (기준 ${COPY_LIMITS[f]}자)`)
