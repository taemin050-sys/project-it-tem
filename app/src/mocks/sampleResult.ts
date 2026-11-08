import type {
  AdCopy, AdCopyOutput, ComplianceIssue, ComplianceReport, CopyField, ProductAnalysis, ResearchResult,
} from '../types/textSchema'

// mock 응답과 랜딩 페이지 예시가 같이 쓴다. 형식은 통합 계약 v0.2 fixtures(스키마 v0.5) 기준

export const analysis: ProductAnalysis = {
  is_cosmetic: true,
  product_type: '스킨케어',
  container_type: '스포이드',
  colors: ['투명', '연한 골드'],
  label_text: ['GLOW', 'SERUM', '30 ml'],
  mood: ['내추럴', '미니멀'],
  is_transparent: true,
}

export const research: ResearchResult = {
  research: {
    product_summary: '가볍게 스며드는 30ml 보습 세럼 (사용자 입력 기준)',
    functional_notes: '기능성 화장품이 아니므로 미백·주름개선 등 기능성 표현은 쓸 수 없습니다.',
    market_insights: [{ text: '보습 세럼 광고는 사용감·피부결 표현을 많이 씁니다.', source: '검색 결과' }],
    similar_products: [],
    ad_direction: '아침 루틴 속 가벼운 보습을 강조',
    display_summary: [
      { text: '가볍게 스며드는 보습 세럼이라는 제품 특징', source: '사용자 입력' },
      { text: '투명 스포이드 용기, 미니멀한 분위기의 제품 사진', source: 'AI 추론' },
      { text: '보습 세럼 광고는 사용감·피부결 표현을 많이 씀', source: '검색 결과' },
      { text: '아침 루틴 속 가벼운 보습을 강조하는 광고 방향', source: 'AI 추론' },
    ],
  },
  citations: [{ title: '(mock) 보습 세럼 광고 동향 예시', url: 'https://example.com/mock-research' }],
  research_performed: true,
}

// 검색 실패: 인용 없이 전부 AI 추론으로 표시 (계약 fixture research_result_no_search.json과 같은 규칙)
export const researchWithoutSearch: ResearchResult = {
  research: {
    ...research.research,
    market_insights: [{ text: '사용감 중심 표현이 적합할 수 있습니다.', source: 'AI 추론' }],
    display_summary: [
      { text: '가볍게 스며드는 보습 세럼이라는 제품 특징', source: '사용자 입력' },
      { text: '아침 루틴 속 가벼운 보습을 강조하는 광고 방향', source: 'AI 추론' },
    ],
  },
  citations: [],
  research_performed: false,
}

const plan: AdCopyOutput['plan'] = {
  target: '건조함이 고민인 20~30대',
  concept: '아침 햇살 같은 촉촉함',
  key_message: '가볍게 스며드는 데일리 보습',
  tone: '친근한',
  mood: ['내추럴', '미니멀'],
}

const adCopy: AdCopy = { headline: '하루 종일 촉촉한 피부결', subline: '가볍게 스며드는\n데일리 보습 세럼', cta: '지금 만나보세요' }
const HASHTAGS = ['#보습세럼', '#데일리케어', '#신제품']

// 글자 수 기준(10/30): 헤드 15자, 서브 15자×2줄(\n, 총 25자), CTA 10자. default·blocked는 기준 안, long(기준 초과)·short(아주 짧음)는 화면이 깨지지 않는지 보려는 예시
export type CopyVariant = 'default' | 'blocked' | 'long' | 'short'

const COPIES: Record<CopyVariant, Omit<AdCopyOutput, 'plan'>> = {
  default: {
    ad_copy: adCopy,
    caption: '💧 건조한 아침, 한 방울로 시작하는 촉촉한 하루. 가볍게 스며드는 글로우 세럼을 만나 보세요.',
    hashtags: HASHTAGS,
  },
  blocked: {
    ad_copy: adCopy,
    caption: '💧 건조한 아침, 한 방울로 시작하는 촉촉한 하루. 피부 재생까지 생각한 글로우 세럼 ✨',
    hashtags: HASHTAGS,
  },
  long: {
    ad_copy: {
      headline: '건조한 계절에도 하루 종일 촉촉함이 오래 머무는 가벼운 데일리 보습 세럼으로 매일 아침을 산뜻하게 시작하세요',
      subline: '끈적임 없이 빠르게 스며드는 가벼운 제형이라 바쁜 아침 메이크업 전에도 부담 없이 바를 수 있고, 저녁 루틴의 마지막 단계로도 잘 어울립니다',
      cta: '지금 글로우 세럼 자세히 알아보기',
    },
    caption: '💧 '.concat('아침마다 피부가 당기고 건조하게 느껴진다면 가볍게 스며드는 글로우 세럼으로 루틴을 바꿔 보세요. ', '끈적임 없이 산뜻하게 마무리되어 메이크업 전에도 부담이 없고, 한 방울만으로도 피부결이 부드럽게 정돈되는 느낌을 받을 수 있어요. ', '30ml 스포이드 용기라 필요한 만큼만 덜어 쓰기 편하고, 파우치에 넣어 다니며 낮 동안 건조할 때마다 덧바르기에도 좋아요. ', '이번 신제품 출시를 기념해 기간 한정 할인도 준비했으니 놓치지 마세요. 자세한 내용은 프로필 링크에서 확인할 수 있어요.'),
    hashtags: ['#보습세럼', '#데일리케어', '#신제품', '#세럼추천', '#건성피부', '#아침루틴', '#스킨케어', '#가벼운제형', '#촉촉피부', '#글로우세럼'],
  },
  short: {
    ad_copy: { headline: '촉촉', subline: '보습 세럼', cta: '보기' },
    caption: '촉촉한 하루.',
    hashtags: ['#세럼'],
  },
}

// start/end는 서버(Python)처럼 코드포인트 기준·end 미포함으로 계산한다
function issue(field: CopyField, source: string, text: string, rest: Omit<ComplianceIssue, 'field' | 'text' | 'start' | 'end'>): ComplianceIssue {
  const start = Array.from(source.slice(0, source.indexOf(text))).length
  return { field, text, start, end: start + Array.from(text).length, ...rest }
}

const NOTICE = '검수 결과는 참고용이며 법적 판단이 아닙니다. 게시 전 최종 확인 책임은 사용자에게 있습니다.'
const CHECKLIST = ['제품명·용량이 실제 제품과 같은지 확인하세요.', '지속 시간·효능 표현은 시험 근거가 있는지 확인하세요.']

export function mockCopyReview(variant: CopyVariant): { copy: AdCopyOutput; report: ComplianceReport } {
  const copy: AdCopyOutput = { plan, ...COPIES[variant] }
  return { copy, report: reviewMockCopy(copy) }
}

// mock 수정 요청 결과: 글자 수 기준 안의 대체 카피를 차례로 돌려준다 (요구사항 반영은 실제 모델 몫)
const REVISIONS: AdCopy[] = [
  { headline: '아침을 깨우는 촉촉함', subline: '한 방울로 시작하는\n가벼운 보습 루틴', cta: '자세히 보기' },
  { headline: '가볍게, 더 촉촉하게', subline: '끈적임 없이 스며드는\n데일리 보습 세럼', cta: '지금 만나보세요' },
  { headline: '매일 쓰는 보습 세럼', subline: '산뜻하게 마무리되는\n글로우 세럼', cta: '구매하기' },
]
export const revisedMockCopy = (copy: AdCopyOutput, instruction: string, n: number): AdCopyOutput =>
  ({ ...copy, plan: { ...copy.plan, concept: `${copy.plan.concept} (수정 요청: ${instruction})` }, ad_copy: REVISIONS[n % REVISIONS.length] })

// '하루 종일'은 근거 확인 필요(승인 가능), '피부 재생'은 위반 의심(승인 차단). 수정한 카피도 같은 규칙으로 다시 검수한다
export function reviewMockCopy(copy: AdCopyOutput): ComplianceReport {
  const issues: ComplianceIssue[] = []
  if (copy.caption.includes('피부 재생')) {
    issues.push(issue('caption', copy.caption, '피부 재생', {
      category: '의약품 오인',
      risk_level: '위반 의심',
      reason: '피부 재생은 의약품으로 오인될 수 있는 표현입니다.',
      suggestion: '피부결 관리',
      basis: '지침 근거 (mock 예시)',
      detected_by: 'rule',
      auto_fixed: false,
    }))
  }
  if (copy.ad_copy.headline.includes('하루 종일')) {
    issues.push(issue('headline', copy.ad_copy.headline, '하루 종일', {
      category: '효능 과장',
      risk_level: '근거 확인 필요',
      reason: '지속 시간 표현은 시험 근거가 있어야 쓸 수 있습니다.',
      suggestion: null,
      basis: null,
      detected_by: 'llm',
      auto_fixed: false,
    }))
  }
  const passed = !issues.some((i) => i.risk_level === '위반 의심')
  return {
    passed,
    issues,
    revised_fields: passed ? {} : { caption: copy.caption.replace('피부 재생', '피부결 관리') },
    checklist: CHECKLIST,
    notice: NOTICE,
  }
}

export const MOCK_IMAGE_URL = '/mock/ad_beige.svg'
// mock 이미지 수정 요청은 이 순서로 다른 배경을 돌려준다
export const MOCK_IMAGE_URLS = [MOCK_IMAGE_URL, '/mock/ad_moss.svg', '/mock/ad_tile.svg']

type Size = { width: number; height: number }

// mock 이미지(1080×1350 SVG)를 고른 비율 크기로 바꾼다. 비율이 다르면 가운데를 채워 자른다
export const mockImageAtSize = (svg: string, { width, height }: Size) =>
  svg.replace(/<svg([^>]*?) width="\d+" height="\d+"/, `<svg$1 width="${width}" height="${height}" preserveAspectRatio="xMidYMid slice"`)

const escapeXml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

// mock 합성: 생성 이미지 SVG 위에 카피를 글자 레이어로 올린다 (실제 합성은 이미지 담당·서버, 방식은 실험 중)
// 글자 레이어는 viewBox(1080×1350) 좌표라 비율이 바뀐 이미지에서도 같이 맞춰 잘린다
export function composeMockSvg(baseSvg: string, copy: AdCopy): string {
  const layer = `<foreignObject x="0" y="0" width="1080" height="1350"><div xmlns="http://www.w3.org/1999/xhtml" style="height:1350px;display:flex;flex-direction:column;justify-content:flex-end">`
    + `<div style="display:flex;flex-direction:column;align-items:flex-start;gap:20px;padding:180px 54px 67.5px;color:#fff;background:linear-gradient(rgba(0,0,0,0),rgba(0,0,0,.55) 180px);font-family:sans-serif;word-break:keep-all">`
    + `<p style="margin:0;font-size:72px;font-weight:800;line-height:1.25">${escapeXml(copy.headline)}</p>`
    + `<p style="margin:0;font-size:38px;line-height:1.4;white-space:pre-line">${escapeXml(copy.subline)}</p>`
    + `<span style="padding:14px 32px;border-radius:999px;background:#fff;color:#1f2328;font-size:32px;font-weight:700">${escapeXml(copy.cta)}</span>`
    + `</div></div></foreignObject>`
  return baseSvg.replace(/<\/svg>\s*$/, `${layer}</svg>`)
}

// 랜딩 페이지 예시 시안 (실제 생성 결과가 아닌 설명용 예시)
export const adExamples = [
  {
    mood: '숲속 무드',
    imageUrl: '/mock/ad_moss.svg',
    copy: { headline: '숲에서 시작하는 하루의 결', subline: '차분한 아침을 위한\n데일리 보습 세럼', cta: '지금 만나보세요' },
  },
  { mood: '웜 베이지', imageUrl: MOCK_IMAGE_URL, copy: adCopy },
  {
    mood: '그린 타일',
    imageUrl: '/mock/ad_tile.svg',
    copy: { headline: '욕실 선반 위 작은 루틴', subline: '가볍게 스며드는\n데일리 보습 세럼', cta: '자세히 보기' },
  },
]
