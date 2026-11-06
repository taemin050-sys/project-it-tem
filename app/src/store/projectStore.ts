import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import { MOCK_DEFAULT, type Ratio } from '../config'
import type { Step } from '../lib/pipeline'
import { AD_PURPOSES, type ProductInput } from '../types/textSchema'

// 사진 수는 보낼 때 실제 파일 수로 채운다
export type ProductForm = Omit<ProductInput, 'product_image_count' | 'reference_image_count'>

/** 지금 보내고 있는 요청과 마지막 실패. 화면 진행 표시는 이 값만 쓴다 (추정 진행률 없음) */
export type RunState = { busy: boolean; step: Step | null; error: string | null; offline?: boolean }

// 처음 화면의 입력값. 새 광고를 시작하면 이 값으로 되돌린다 (이모티콘은 가운데 값을 기본으로)
const INITIAL_PRODUCT: ProductForm = {
  brand_name: null,
  product_name: '',
  product_category: null,
  features: '',
  ad_purpose: AD_PURPOSES[0],
  is_functional: false,
  functional_types: [],
  emoji_level: '보통',
  photo_verified: false,
}
const INITIAL_RATIO: Ratio = '4:5'

type ProjectState = {
  images: File[]
  references: File[]
  product: ProductForm
  ratio: Ratio
  setRatio: (ratio: Ratio) => void
  jobId: string | null
  /** 결과(COMPLETED)까지 끝난 작업. 지금 작업이 이 값이면 새 광고를 확인 없이 시작한다 */
  finishedJobId: string | null
  setFinishedJob: (jobId: string) => void
  identityScope: string | null
  liveTaskId: string | null
  setIdentityScope: (scope: string | null) => void
  setLiveTask: (task: string | null) => void
  run: RunState
  /** 개발 중 mock 사용 여부. 서버가 없을 때 사용자가 직접 켠다 (조용히 mock으로 바꾸지 않음) */
  mock: boolean
  setImages: (images: File[]) => void
  setReferences: (references: File[]) => void
  setProduct: (patch: Partial<ProductForm>) => void
  /** 사진·제품 정보·선택값을 처음 화면 값으로 되돌린다 (로그인 정보·mock 설정은 그대로) */
  clearInputs: () => void
  setJobId: (jobId: string | null) => void
  setRun: (patch: Partial<RunState>) => void
  /** 서버가 바뀌면 이전 작업은 쓸 수 없어 작업·진행 상태를 비운다 (입력값·사진은 유지) */
  setMock: (mock: boolean) => void
}

// 새로고침 뒤 서버 Job을 다시 읽을 수 있게 job_id와 입력 글자만 탭 세션에 둔다 (사진 파일은 저장 불가).
// 프로젝트 자동저장(🔶 미정)은 아니다. 저장소를 못 쓰는 환경이면 zustand가 메모리로만 동작한다
export const useProjectStore = create<ProjectState>()(persist((set) => ({
  images: [],
  references: [],
  product: INITIAL_PRODUCT,
  ratio: INITIAL_RATIO,
  setRatio: (ratio) => set({ ratio }),
  jobId: null,
  finishedJobId: null,
  setFinishedJob: (finishedJobId) => set({ finishedJobId }),
  identityScope: null,
  liveTaskId: null,
  setIdentityScope: (scope) => set((s)=>s.identityScope===scope?{}:
    {identityScope:scope,jobId:null,liveTaskId:null,run:{busy:false,step:null,error:null}}),
  setLiveTask: (liveTaskId) => set({liveTaskId}),
  run: { busy: false, step: null, error: null },
  mock: MOCK_DEFAULT,
  setImages: (images) => set({ images }),
  setReferences: (references) => set({ references }),
  setProduct: (patch) => set((s) => ({ product: { ...s.product, ...patch } })),
  clearInputs: () => set({ images: [], references: [], product: INITIAL_PRODUCT, ratio: INITIAL_RATIO }),
  setJobId: (jobId) => set({ jobId,liveTaskId:null }),
  setRun: (patch) => set((s) => ({ run: { ...s.run, ...patch } })),
  setMock: (mock) => set({ mock: import.meta.env.DEV && mock, jobId: null, run: { busy: false, step: null, error: null } }),
}), {
  name: 'it-tem-project',
  storage: createJSONStorage(() => sessionStorage),
  partialize: (s) => ({ jobId: s.jobId, finishedJobId: s.finishedJobId, product: s.product, ratio: s.ratio, mock: s.mock,
    identityScope:s.identityScope,liveTaskId:s.liveTaskId }),
  // 이전 버전에 저장된 product에는 새 항목(functional_types·emoji_level)이 없어 기본값 위에 덮는다
  merge: (saved, current) => {
    const s = saved as Partial<ProjectState> | undefined
    return { ...current, ...s, product: { ...current.product, ...s?.product } }
  },
}))
