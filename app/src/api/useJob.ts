import { useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { toOwnerEmojiLevel } from '../lib/emojiLevel'
import { nextStep, type Flow, type Step } from '../lib/pipeline'
import { useObjectUrls } from '../lib/useObjectUrls'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'
import { ApiError, isUnreachable } from './client'
import { getBlob, getJob, runStep } from './jobs'
import { queryClient } from './queryClient'
import {getProductLiveJob,createLiveInput,queueLive,getLiveSnapshot,getLiveTask,latestLiveTask,qaText} from './liveJobs'
import {QA_OFFLINE_FIXTURE} from '../config'
import type {ProductInput} from '../types/textSchema'

const jobKey = (jobId: string | null) => ['job', jobId]

// 실서버는 지금 레거시 경로(mock/plan 등)만 있고, 신규 v0.2 경로는 BLOCKED_WIRE라 mock에서만 돌린다
// shortcut: v0.2 경로가 서버에 구현·동결되면 실서버도 'v2'로 바꾼다
export const flowOf = (mock: boolean): Flow => (mock ? 'v2' : 'legacy')

// 단계 POST가 Job을 돌려주므로 폴링하지 않는다. 새로고침 뒤에는 저장해 둔 job_id로 서버 상태를 다시 읽는다
export function useJob() {
  const jobId = useProjectStore((s) => s.jobId)
  const mock = useProjectStore((s) => s.mock)
  const busy = useProjectStore((s) => s.run.busy)
  return useQuery({
    queryKey: jobKey(jobId),
    queryFn: () => mock ? getJob(jobId!) : getProductLiveJob(jobId!),
    // An uploaded B0 job exists before the Live input snapshot. Never GET the
    // latter in the middle of the input transaction; busy also disables
    // reads during explicitly approved POST transitions.
    enabled: jobId !== null && (mock || !busy),
    staleTime: mock ? Infinity : 0,
    refetchInterval: mock ? false : 1800,
    retry: false,
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

// 새로 시작할 때 이전 작업의 상태와 결과 캐시를 비운다 (입력값·사진은 유지).
// shortcut: 서버에 Job 삭제 API가 없어 서버 저장본은 남는다, 서빙에 삭제 API가 생기면 여기서 호출한다
export function resetJob() {
  const { setJobId, setRun } = useProjectStore.getState()
  setJobId(null)
  setRun({ error: null, offline: false })
  queryClient.clear()
}

// Match Owner Text #25's exact v0.10 DTO; keep the original user ad_purpose
// free of stealth instructions and bind the emoji preference to the Job hash.
export function productPayload() {
  const { product, emoji } = useProjectStore.getState()
  return { ...product, functional_types:product.functional_types,
    // Owner Text v0.10 automatically considers selected types functional.
    is_functional:product.is_functional || product.functional_types.length>0,
    emoji_level:toOwnerEmojiLevel(emoji) }
}

// first(업로드·승인)를 보낸 뒤 사용자 승인이 필요한 곳까지 단계를 차례로 보낸다.
// 사용자 클릭에서만 부른다: 화면 effect에서 부르면 유료 AI 호출이 중복될 수 있다. 실패해도 자동 재시도하지 않는다
// step: first 요청 중 로딩 문구 (수정 요청처럼 AI가 다시 만드는 요청)
export async function advance(first: () => Promise<Job>, step: Step | null = null) {
  const { setRun, setJobId, mock } = useProjectStore.getState()
  const flow = flowOf(mock)
  setRun({ busy: true, step, error: null, offline: false })
  let jobId: string | null = useProjectStore.getState().jobId
  try {
    let job = await first()
    jobId = job.job_id
    setJobId(jobId)
    if(!mock){
      const product=productPayload()
      const imageCount=job.assets?.filter(a=>a.role==='product').length
      const refCount=job.assets?.filter(a=>a.role==='reference').length
      if(imageCount===undefined || refCount===undefined)throw Error('원본 사진 메타데이터를 확인하지 못했습니다.')
      const input:ProductInput={...product,brand_name:product.brand_name?.trim()||null,
        product_image_count:imageCount,reference_image_count:refCount}
      const selectedSize=useProjectStore.getState().ratio
      const current=await createLiveInput(job,input,selectedSize)
      if(current.state==='INPUT_STORED'){
        setRun({step:'ai/analyze'})
        if(QA_OFFLINE_FIXTURE){
          await qaText(jobId)
        }else{
          const task=await queueLive(jobId,'text')
          useProjectStore.getState().setLiveTask(task.task_id)
        }
      } else if(current.state!=='COPY_REVIEW_REQUIRED'){
        throw Error('기존 Live Job이 다른 단계입니다. 작업 상태부터 확인해 주세요.')
      }
      await queryClient.invalidateQueries({queryKey:jobKey(jobId)})
      setRun({busy:false,step:null})
      return
    }
    queryClient.setQueryData(jobKey(jobId), job)
    for (let step = nextStep(job, flow); step; step = nextStep(job, flow)) {
      setRun({ step })
      job = await runStep(jobId, step, stepBody(step))
      queryClient.setQueryData(jobKey(jobId), job)
    }
    setRun({ busy: false, step: null })
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) await queryClient.invalidateQueries({ queryKey: jobKey(jobId) })
    setRun({ busy: false, step: null, error: e instanceof Error ? e.message : '요청에 실패했습니다.', offline: isUnreachable(e) })
  }
}

// shortcut: 비율은 mock(v2 ai/image)에만 보낸다. 이미지·서빙이 비율을 받으면 Live 입력에도 넣는다
function stepBody(step: Step) {
  if (step === 'mock/plan') return legacyPlanBody()
  if (step === 'ai/image') return { aspect_ratio: useProjectStore.getState().ratio }
}

// 레거시 mock/plan은 brand_name·product_name을 둘 다 필수(빈 값 거절)로 받는다. v0.5는 브랜드가 선택 항목이라 표시용 값을 보낸다
// shortcut: 레거시 mock 전용. 서빙(이형기)에 brand_name nullable 불일치 전달함, v2 경로로 바뀌면 삭제
function legacyPlanBody() {
  const { brand_name, product_name } = useProjectStore.getState().product
  return { brand_name: brand_name?.trim() || '브랜드 미입력', product_name: product_name.trim() }
}

/** Recover a committed B0 upload without uploading photos or resubmitting a provider call. */
export async function recoverLiveInput(){
  const {jobId,setRun}=useProjectStore.getState()
  if(!jobId)throw Error('복구할 작업이 없습니다.')
  setRun({busy:true,error:null})
  try{
    const original=await getJob(jobId)
    const product_image_count=original.assets?.filter(a=>a.role==='product').length
    const reference_image_count=original.assets?.filter(a=>a.role==='reference').length
    if(product_image_count===undefined||reference_image_count===undefined)
      throw Error('기존 사진 기록이 없습니다.')
    const selectedSize=useProjectStore.getState().ratio
    const current=await createLiveInput(original,
      {...productPayload(),product_image_count,reference_image_count},selectedSize)
    if(current.state==='INPUT_STORED'){
      const s=await getLiveSnapshot(jobId)
      if(s.state==='INPUT_STORED'){
        if(QA_OFFLINE_FIXTURE) await qaText(jobId)
        else{
          const task=await queueLive(jobId,'text')
          useProjectStore.getState().setLiveTask(task.task_id)
        }
      }
    }
    await queryClient.invalidateQueries({queryKey:jobKey(jobId)})
  }catch(e){setRun({error:e instanceof Error?e.message:'Live 입력 복구 실패'});throw e}
  finally{setRun({busy:false,step:null})}
}

/** GET-only realtime status for a queued paid attempt. Reloads never POST. */
export function useLiveProgress(){
  const id=useProjectStore(s=>s.jobId)
  const mock=useProjectStore(s=>s.mock)
  const taskId=useProjectStore(s=>s.liveTaskId)
  return useQuery({
    queryKey:['live-task',id,taskId],
    queryFn:async()=>{
      // Only read a saved task; never POST from polling or component effects.
      if(taskId){
        try{return await getLiveTask(taskId)}
        catch{return (await latestLiveTask(id!)).task}
      }
      return (await latestLiveTask(id!)).task
    },
    enabled:!mock && !!id,refetchInterval:!mock?1800:false,retry:false,
  })
}
export function useLiveSnapshot(){
  const id=useProjectStore(s=>s.jobId)
  const mock=useProjectStore(s=>s.mock)
  return useQuery({
    queryKey:['live-snapshot',id],queryFn:()=>getLiveSnapshot(id!),
    enabled:!mock && !!id,refetchInterval:!mock?1800:false,retry:false,
  })
}
