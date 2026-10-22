export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
export const USE_MOCK = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true'

// shortcut: 서버 업로드 제한(이형기) 미확정이라 임시값, 서버 명세 수신 시 맞춘다
export const UPLOAD = {
  minFiles: 1,
  maxFiles: 3,
  maxBytes: 10 * 1024 * 1024,
  acceptTypes: ['image/jpeg', 'image/png', 'image/webp'],
} as const

export const POLL_INTERVAL_MS = 1500
export const REQUEST_TIMEOUT_MS = 30_000

// 인스타 피드 4:5 (MVP 채널 범위는 PM 확인 중)
export const CANVAS = { width: 1080, height: 1350 } as const

export const PRODUCT_TYPES = ['스킨/토너', '세럼/에센스', '크림', '클렌저', '선크림', '기타']
export const FUNCTIONAL_ITEMS = ['미백', '주름 개선', '자외선 차단', '여드름성 피부 완화', '탈모 증상 완화']

// shortcut: 목적·채널·톤·무드 프리셋은 10/26 합의 회의 전 임시값, 합의 결과로 교체
export const AD_PRESETS = {
  purpose: ['신제품 출시', '시즌 프로모션', 'SNS 홍보'],
  channel: ['인스타그램 피드'],
  tone: ['친근한', '고급스러운', '차분한'],
  mood: ['내추럴', '미니멀', '비비드'],
} as const
