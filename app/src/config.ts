// shortcut: 서비스명 미정이라 레포명(project-it-tem) 기준 가칭, 팀에서 이름 정하면 교체
export const SERVICE_NAME = 'IT-TEM'

// 비우면 같은 출처 /api (개발 중에는 vite proxy가 서버로 넘김)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
export const USE_MOCK = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true'
// 실제 서버는 지금 레거시 경로(mock/plan 등)만 구현돼 있고, 신규 v0.2 경로는 BLOCKED_WIRE라 MSW fixture로만 돌린다
// shortcut: v0.2 경로가 서버에 구현·동결되면 실제 서버도 'v2'로 바꾼다
export const API_FLOW: 'legacy' | 'v2' = USE_MOCK ? 'v2' : 'legacy'

// 사진 수는 10/23·10/26 회의 결정. 용량·해상도 제한은 두지 않고 큰 사진은 올리기 전에 줄인다
export const PRODUCT_PHOTOS = { minFiles: 2, maxFiles: 5, acceptTypes: ['image/jpeg', 'image/png', 'image/webp'] } as const
export const REFERENCE_PHOTOS = { ...PRODUCT_PHOTOS, minFiles: 0 } as const
// shortcut: 축소 기준은 미정(계약 7.4 BLOCKED_BY_DECISION), 레거시 서버 한도(파일당 10MiB·40MP) 안쪽으로 임시값
export const SHRINK = { maxSide: 2048, maxBytes: 10 * 1024 * 1024 } as const

export const REQUEST_TIMEOUT_MS = 30_000
// AI 호출은 서버 타임아웃 300초(10/26 결정)보다 조금 길게 기다린다
export const AI_REQUEST_TIMEOUT_MS = 330_000

// 인스타 피드 4:5
export const CANVAS = { width: 1080, height: 1350 } as const
// 카피는 바깥쪽 5% 여백 안이면 어디든 배치 가능 (10/26 결정)
export const SAFE_MARGIN = 0.05
