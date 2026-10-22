import { create } from 'zustand'
import { AD_PRESETS } from '../config'
import type { AdSettings, ProductInfo } from '../types/draft'

type ProjectState = {
  images: File[]
  product: ProductInfo
  settings: AdSettings
  jobId: string | null
  setImages: (images: File[]) => void
  setProduct: (patch: Partial<ProductInfo>) => void
  setSettings: (patch: Partial<AdSettings>) => void
  setJobId: (jobId: string | null) => void
}

// 브라우저 자동저장(IndexedDB)은 11/02 작업. 지금은 메모리에만 둔다
export const useProjectStore = create<ProjectState>((set) => ({
  images: [],
  product: {
    name: '',
    product_type: '',
    volume: '',
    is_functional: false,
    functional_items: [],
    photo_rights_confirmed: false,
  },
  settings: {
    purpose: AD_PRESETS.purpose[0],
    channel: AD_PRESETS.channel[0],
    tone: AD_PRESETS.tone[0],
    mood: AD_PRESETS.mood[0],
  },
  jobId: null,
  setImages: (images) => set({ images }),
  setProduct: (patch) => set((s) => ({ product: { ...s.product, ...patch } })),
  setSettings: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),
  setJobId: (jobId) => set({ jobId }),
}))
