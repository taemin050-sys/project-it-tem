// 텍스트 모듈 스키마 v0.10(김다혜) 원본을 옮긴 타입.
// 출처: dev src/text_generation/schemas.py (#25 병합본). 원본과 다르면 원본이 우선.
// 서빙 응답에 어떻게 실릴지(필드 이름·감싸는 형식)는 이형기 님과 정하는 중이다
// 프론트가 쓰지 않는 ImagePromptOutput(이미지 담당용), LLMIssue(텍스트 내부용)는 옮기지 않았다.

// ---------- 공통 선택값 (화면 버튼 목록으로도 쓴다) ----------

export const PRODUCT_TYPES = ['스킨케어', '선케어', '베이스 메이크업', '색조', '클렌징', '마스크팩', '바디', '헤어', '기타'] as const
export const CONTAINER_TYPES = ['병', '튜브', '펌프', '스포이드', '자', '콤팩트', '스프레이', '파우치', '어플리케이터', '스틱', '기타'] as const
// v0.5 ad_purpose는 자유 문자열. 화면 선택지는 v0.3 목록 유지 (10/23 사용자 결정)
export const AD_PURPOSES = ['신제품 홍보', '할인 프로모션', '효능 강조', '감성 브랜딩'] as const
// 사진 분석(VLM) 결과도 'AI 추론'으로 분류한다 (10/26 결정)
export const SOURCE_TYPES = ['사용자 입력', '검색 결과', 'AI 추론'] as const
export const RISK_LEVELS = ['정상', '근거 확인 필요', '위반 의심'] as const
export const RISK_CATEGORIES = [
  '의약품 오인', '기능성 오인', '효능 과장', '소비자 오인', '수치·임상 표현',
  '순위·최상급 표현', '전문가·매체 추천', '가상 후기', '확정 정보 불일치', '기타',
] as const
export const COPY_FIELDS = ['product_name', 'headline', 'subline', 'cta', 'caption', 'hashtags', 'user_text'] as const
// 화장품법 시행규칙 제2조 기능성화장품의 범위 (텍스트 schemas.py FunctionalType과 같은 순서). 여드름완화는 인체세정용 제품만
export const FUNCTIONAL_TYPES = ['미백', '주름개선', '태닝', '자외선차단', '모발색상변화', '체모제거', '탈모완화', '여드름완화', '가려움개선', '튼살붉은선완화'] as const
// 게시글 본문 이모티콘 정도 (헤드·서브·CTA·해시태그에는 텍스트 쪽에서 넣지 않음)
export const EMOJI_LEVELS = ['없음', '보통', '많이'] as const

export type ProductType = (typeof PRODUCT_TYPES)[number]
export type ContainerType = (typeof CONTAINER_TYPES)[number]
export type SourceType = (typeof SOURCE_TYPES)[number]
export type RiskLevel = (typeof RISK_LEVELS)[number]
export type RiskCategory = (typeof RISK_CATEGORIES)[number]
export type CopyField = (typeof COPY_FIELDS)[number]
export type FunctionalType = (typeof FUNCTIONAL_TYPES)[number]
export type EmojiLevel = (typeof EMOJI_LEVELS)[number]

// ---------- 1. 사용자 입력 (React → 서빙 → 텍스트) ----------

export type ProductInput = {
  brand_name: string | null
  product_name: string
  /** 사용자가 고른 카테고리, 미선택 null (VLM product_type과 별개) */
  product_category: string | null
  features: string
  ad_purpose: string
  is_functional: boolean
  /** 심사(보고)받은 기능성 종류. 고르면 서버에서 is_functional=true로 맞춘다 */
  functional_types: FunctionalType[]
  emoji_level: EmojiLevel
  /** 사진 사용 권한 확인 체크 (권한을 AI가 증명하는 것은 아님) */
  photo_verified: boolean
  /** 2~5 */
  product_image_count: number
  /** 0~5 */
  reference_image_count: number
}

// ---------- 2. 사진 분석 (VLM) ----------

export type ProductAnalysis = {
  /** false면 이후 단계 차단·재업로드 안내 */
  is_cosmetic: boolean
  product_type: ProductType
  container_type: ContainerType
  colors: string[]
  label_text: string[]
  mood: string[]
  is_transparent: boolean
}

// ---------- 3. 기획 AI 사전 조사 ----------

export type Insight = { text: string; source: SourceType; citations?: Citation[] }

export type ResearchOutput = {
  product_summary: string
  functional_notes: string
  market_insights: Insight[]
  /** 방향 참고만, 문구 인용 금지 */
  similar_products: Insight[]
  ad_direction: string
  /** 카피 검토 화면용 요약 (기획 AI가 같은 호출에서 생성) */
  display_summary: Insight[]
}

/** OpenAI 응답의 실제 url_citation에서 꺼낸 값만 */
export type Citation = { title: string | null; url: string }

export type ResearchResult = {
  research: ResearchOutput
  citations: Citation[]
  /** false면 검색 실패 — 조사 내용은 전부 AI 추론 */
  research_performed: boolean
  /** 실패 이유 (성공하면 null) */
  error?: string | null
}

// ---------- 4. 기획안·카피 ----------

export type AdPlan = {
  target: string
  concept: string
  key_message: string
  tone: string
  mood: string[]
}

export type AdCopy = {
  headline: string
  subline: string
  cta: string
}

export type AdCopyOutput = {
  plan: AdPlan
  ad_copy: AdCopy
  caption: string
  hashtags: string[]
}

// ---------- 5. 규제 검수 리포트 ----------

export type ComplianceIssue = {
  field: CopyField
  /** 위험 표현 원문 */
  text: string
  /** field 문자열 안 코드포인트 위치, [start, end) */
  start: number
  end: number
  category: RiskCategory
  risk_level: RiskLevel
  reason: string
  /** 대체 문구, 삭제 권장이면 null */
  suggestion: string | null
  basis: string | null
  basis_url?: string | null
  detected_by: 'rule' | 'llm'
  auto_fixed: boolean
}

export type ComplianceReport = {
  /** '위반 의심'이 하나도 없으면 true — false면 카피 승인 불가 */
  passed: boolean
  issues: ComplianceIssue[]
  revised_fields: Record<string, string>
  /** 게시 전 사용자가 직접 확인할 항목 */
  checklist: string[]
  notice: string
}
