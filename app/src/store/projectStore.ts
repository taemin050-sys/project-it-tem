import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { Step } from '../lib/pipeline'
import { AD_PURPOSES, type ProductInput } from '../types/textSchema'

// 사진 수는 보낼 때 실제 파일 수로 채운다
export type ProductForm = Omit<ProductInput, 'product_image_count' | 'reference_image_count'>

/** 지금 보내고 있는 요청과 마지막 실패. 화면 진행 표시는 이 값만 쓴다 (추정 진행률 없음) */
export type RunState = { busy: boolean; step: Step | null; error: string | null }

type ProjectState = {
  images: File[]
  references: File[]
  product: ProductForm
  jobId: string | null
  run: RunState
  setImages: (images: File[]) => void
  setReferences: (references: File[]) => void
  setProduct: (patch: Partial<ProductForm>) => void
  setJobId: (jobId: string | null) => void
  setRun: (patch: Partial<RunState>) => void
}

// 새로고침 뒤 서버 Job을 다시 읽을 수 있게 job_id와 입력 글자만 탭 세션에 둔다 (사진 파일은 저장 불가).
// 프로젝트 자동저장(🔶 미정)은 아니다. 저장소를 못 쓰는 환경이면 zustand가 메모리로만 동작한다
export const useProjectStore = create<ProjectState>()(persist((set) => ({
  images: [],
  references: [],
  product: {
    brand_name: null,
    product_name: '',
    product_category: null,
    features: '',
    ad_purpose: AD_PURPOSES[0],
    is_functional: false,
    photo_verified: false,
  },
  jobId: null,
  run: { busy: false, step: null, error: null },
  setImages: (images) => set({ images }),
  setReferences: (references) => set({ references }),
  setProduct: (patch) => set((s) => ({ product: { ...s.product, ...patch } })),
  setJobId: (jobId) => set({ jobId }),
  setRun: (patch) => set((s) => ({ run: { ...s.run, ...patch } })),
}), {
  name: 'it-tem-project',
  storage: createJSONStorage(() => sessionStorage),
  partialize: (s) => ({ jobId: s.jobId, product: s.product }),
}))
