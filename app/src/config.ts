// shortcut: 서비스명 미정이라 레포명(project-it-tem) 기준 가칭, 팀에서 이름 정하면 교체
export const SERVICE_NAME = 'IT-TEM'

// 비우면 같은 출처 /api (개발 중에는 vite proxy가 서버로 넘김)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''
// mock 시작값. 개발 중에는 화면에서 바꿀 수 있다 (store의 mock, 배포 빌드는 항상 실서버)
export const MOCK_DEFAULT = import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true'

// 사진 수는 10/23·10/26 회의 결정. 용량·해상도 제한은 두지 않고 큰 사진은 올리기 전에 줄인다
export const PRODUCT_PHOTOS = { minFiles: 2, maxFiles: 5, acceptTypes: ['image/jpeg', 'image/png', 'image/webp', '.mpo', '.MPO'] } as const
export const REFERENCE_PHOTOS = { ...PRODUCT_PHOTOS, minFiles: 0 } as const
// shortcut: 축소 기준은 미정(계약 7.4 BLOCKED_BY_DECISION), 레거시 서버 한도(파일당 10MiB·40MP) 안쪽으로 임시값
export const SHRINK = { maxSide: 2048, maxBytes: 10 * 1024 * 1024 } as const

export const REQUEST_TIMEOUT_MS = 30_000
// AI 호출은 서버 타임아웃 300초(10/26 결정)보다 조금 길게 기다린다
export const AI_REQUEST_TIMEOUT_MS = 330_000

// 인스타 피드 4:5
export const CANVAS = { width: 1080, height: 1350 } as const
// 사용자가 고르는 결과 이미지 비율 (인스타 기준, 가로 1080 고정)
export const RATIOS = {
  '3:4': { width: 1080, height: 1440, label: '3:4', desc: '세로형 피드' },
  '4:5': { width: 1080, height: 1350, label: '4:5', desc: '기본 피드' },
  '9:16': { width: 1080, height: 1920, label: '9:16', desc: '스토리·릴스' },
} as const
export type Ratio = keyof typeof RATIOS
// 카피는 바깥쪽 5% 여백 안이면 어디든 배치 가능 (10/26 결정)
export const SAFE_MARGIN = 0.05

// 합성 배치 A (이미지 담당 a_template.py 값, 11/02 연결 가이드): 헤드·서브 상단 중앙, CTA 하단 중앙
// 좌표는 1080×1350 대비 0~1 비율, 글자 크기·padding은 최종 PNG 픽셀. 처음 합성과 합성 재시도 모두 이 값만 쓴다
const A_REGION = { left: 0.08, right: 0.92, padding: 16, align: 'center', color: '#151515', background: null } as const
// shortcut: CTA 좌표는 이미지 쪽 검증 전 임시값(제품 보호 영역과 겹침 확인됨), 확정 좌표를 받으면 cta만 교체한다
export const AD_LAYOUT = {
  text_regions: {
    headline: { ...A_REGION, top: 0.06, bottom: 0.14, min_font_size: 48, max_font_size: 64 },
    subline: { ...A_REGION, top: 0.15, bottom: 0.25, min_font_size: 45, max_font_size: 48 },
    cta: { ...A_REGION, top: 0.85, bottom: 0.94, min_font_size: 48, max_font_size: 54 },
  },
  // 제품 보호 영역은 후보 이미지마다 확인한 좌표만 넣는다. 모든 제품에 같은 사각형을 넣지 않고, 비우면 서버가 미검증 경고를 남긴다
  protected_regions: [],
}

// Explicit build-time QA label only. Authentication and Fixture access are
// independently controlled by the backend; this is not an auth bypass.
export const QA_OFFLINE_FIXTURE = import.meta.env?.VITE_QA_OFFLINE_FIXTURE === 'YES'
export const DUAL_QA = QA_OFFLINE_FIXTURE && import.meta.env?.VITE_BP18_DUAL_QA === 'YES'
