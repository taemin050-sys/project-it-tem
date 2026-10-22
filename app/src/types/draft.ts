// shortcut: 김다혜 스키마 초안(10/21)·이형기 API 명세 수신 전, 체크리스트 v4 1장 기준 임시 타입.
// 필드명은 전부 가정이다. 초안을 받으면 이 파일을 교체한다.

export type ProductInfo = {
  name: string
  product_type: string
  volume: string
  is_functional: boolean
  functional_items: string[]
  photo_rights_confirmed: boolean
}

export type AdSettings = {
  purpose: string
  channel: string
  tone: string
  mood: string
}

export type JobStatus = 'queued' | 'running' | 'needs_review' | 'done' | 'failed'

export type ProductAnalysis = {
  product_type: string
  container: string
  colors: string[]
  label_text: string
  mood: string
}

export type AdCopy = {
  purpose: string
  target: string
  concept: string
  key_message: string
  headline: string
  subline: string
  cta: string
  caption: string
  hashtags: string[]
}

export type ReviewIssue = {
  expression: string
  reason: string
  suggestion: string
  // 위치값 포함 여부 미확정 (김다혜 확인 필요)
  start?: number
  end?: number
}

// 정규화 좌표 [x, y, w, h], 0~1, 좌상단 원점 (픽셀 변환 규칙은 pi와 합의 필요)
export type NormBox = [number, number, number, number]

export type ImageResult = {
  scene_underlay: string
  product_rgba: string
  composed_preview?: string
  product_box: NormBox
  text_safe_zone: NormBox
  warnings: string[]
  needs_manual_check: boolean
}

export type JobResult = {
  analysis: ProductAnalysis
  copy: AdCopy
  review: ReviewIssue[]
  image: ImageResult
}

export type Job = {
  job_id: string
  status: JobStatus
  progress?: number
  error?: { code: string; message: string }
  result?: JobResult
}
