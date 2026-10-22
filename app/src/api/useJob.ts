import { useQuery } from '@tanstack/react-query'
import { POLL_INTERVAL_MS } from '../config'
import { useProjectStore } from '../store/projectStore'
import { getJob } from './jobs'

// shortcut: 폴링으로 구현. 이형기 님이 SSE로 정하면 이 훅만 바꾼다
export function useJob() {
  const jobId = useProjectStore((s) => s.jobId)
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (q) => {
      const status = q.state.data?.status
      return status === 'done' || status === 'failed' ? false : POLL_INTERVAL_MS
    },
  })
}
