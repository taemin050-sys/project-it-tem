export const STEPS = [
  { path: '/create/product', label: '제품 정보' },
  { path: '/create/copy', label: '기획·카피 검토' },
  { path: '/create/draft', label: '이미지 검토' },
  { path: '/create/export', label: '최종 결과' },
] as const

export const stepIndex = (pathname: string) => STEPS.findIndex((s) => s.path === pathname)
