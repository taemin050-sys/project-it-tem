import { QueryClient } from '@tanstack/react-query'

// 화면 밖(advance)에서도 Job 캐시를 갱신해야 해서 모듈로 둔다
export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } })
