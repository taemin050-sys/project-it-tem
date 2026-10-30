import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { API_FLOW } from '../config'
import { nextStep } from '../lib/pipeline'
import { useObjectUrls } from '../lib/useObjectUrls'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'
import { ApiError } from './client'
import { getBlob, getJob, runStep } from './jobs'
import { queryClient } from './queryClient'

const jobKey = (jobId: string | null) => ['job', jobId]

// 단계 POST가 Job을 돌려주므로 폴링하지 않는다. 새로고침 뒤에는 저장해 둔 job_id로 서버 상태를 다시 읽는다
export function useJob() {
  const jobId = useProjectStore((s) => s.jobId)
  return useQuery({
    queryKey: jobKey(jobId),
    queryFn: () => getJob(jobId!),
    enabled: jobId !== null,
    staleTime: Infinity,
  })
}

// 서버 파일(이미지 Asset·산출물)을 blob으로 받는다. 경로가 바뀌지 않는 한 다시 받지 않는다
export function useBlob(path: string | undefined) {
  return useQuery({
    queryKey: ['blob', path],
    queryFn: () => getBlob(path!),
    enabled: path !== undefined,
    staleTime: Infinity,
  }).data
}

// blob URL로 그린다: 다른 출처 이미지나 인증이 필요한 경로도 같은 방식으로 받기 위해
export function useBlobUrl(path: string | undefined) {
  const blob = useBlob(path)
  const blobs = useMemo(() => (blob ? [blob] : []), [blob])
  return useObjectUrls(blobs)[0] as string | undefined
}

// 서버 Job 상태를 다시 읽는다 (재전송 없음)
export async function refreshJob() {
  const { jobId, setRun } = useProjectStore.getState()
  if (!jobId) return
  setRun({ error: null })
  await queryClient.invalidateQueries({ queryKey: jobKey(jobId) })
}

// first(업로드·승인)를 보낸 뒤 사용자 승인이 필요한 곳까지 단계를 차례로 보낸다.
// 사용자 클릭에서만 부른다: 화면 effect에서 부르면 유료 AI 호출이 중복될 수 있다. 실패해도 자동 재시도하지 않는다
export async function advance(first: () => Promise<Job>) {
  const { setRun, setJobId } = useProjectStore.getState()
  setRun({ busy: true, step: null, error: null })
  let jobId: string | null = useProjectStore.getState().jobId
  try {
    let job = await first()
    jobId = job.job_id
    setJobId(jobId)
    queryClient.setQueryData(jobKey(jobId), job)
    for (let step = nextStep(job, API_FLOW); step; step = nextStep(job, API_FLOW)) {
      setRun({ step })
      job = await runStep(jobId, step, step === 'mock/plan' ? legacyPlanBody() : undefined)
      queryClient.setQueryData(jobKey(jobId), job)
    }
    setRun({ busy: false, step: null })
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await queryClient.invalidateQueries({ queryKey: jobKey(jobId) })
    setRun({ busy: false, step: null, error: e instanceof Error ? e.message : '요청에 실패했습니다.' })
  }
}

// 레거시 mock/plan은 brand_name·product_name을 둘 다 필수(빈 값 거절)로 받는다. v0.5는 브랜드가 선택 항목이라 표시용 값을 보낸다
// shortcut: 레거시 mock 전용. 서빙(이형기)에 brand_name nullable 불일치 전달함, v2 경로로 바뀌면 삭제
function legacyPlanBody() {
  const { brand_name, product_name } = useProjectStore.getState().product
  return { brand_name: brand_name?.trim() || '브랜드 미입력', product_name: product_name.trim() }
}
