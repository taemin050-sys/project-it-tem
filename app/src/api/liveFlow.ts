/** User initiated only: never called from React effects/poll hooks. No auto paid retries. */
import {queryClient} from './queryClient'
import {useProjectStore} from '../store/projectStore'
import {approveLiveCopy,rejectLiveCopy,queueLive,waitLiveTask,approveLiveImage,
  rejectLiveImage,composeLive,getLiveSnapshot,reviseLiveCopy,restoreLiveCopy} from './liveJobs'
import {guardCopyApproval,guardImageApproval,sameCopyReview,sameImageCandidate,type LiveSnapshot} from './liveMapping'
import {AD_LAYOUT} from '../config'
import {ApiError} from './client'
// The generic HTTP messages (e.g. 422 = photo input) are wrong for a compose failure; the image is kept.
const compose=(id:string)=>composeLive(id,AD_LAYOUT,true).catch(e=>{
  throw Error('광고 합성에 실패했습니다. 승인한 이미지는 그대로 있으니 원인을 확인한 뒤 합성만 다시 시도하세요.'+
    (e instanceof ApiError&&e.status>0?` (오류 ${e.status})`:''))
})
const refresh=async(id:string)=>{
  await queryClient.invalidateQueries({queryKey:['job',id]})
  await queryClient.invalidateQueries({queryKey:['live-snapshot',id]})
}
async function run(id:string,step:'ai/image'|'ai/copy-review'|'compose',action:()=>Promise<unknown>){
  const {setRun}=useProjectStore.getState()
  if(useProjectStore.getState().run.busy)throw Error('이미 작업을 진행 중입니다.')
  setRun({busy:true,step,error:null})
  try{await action();await refresh(id)}
  catch(e){
    await refresh(id)
    setRun({error:e instanceof Error?e.message:'Live 작업 실패. 재호출 전에 현재 상태를 확인하세요.'})
    throw e
  }finally{setRun({busy:false,step:null})}
}
async function queuePromptAndImage(id:string){
  const task=await queueLive(id,'prompt')
  useProjectStore.getState().setLiveTask(task.task_id)
  await waitLiveTask(id,task.task_id,'PROMPT_READY')
  // This only executes as a continuation of the explicit user's "generate image"
  // click. Re-mounting after a crash never resumes POST.
  const image=await queueLive(id,'image')
  useProjectStore.getState().setLiveTask(image.task_id)
}
// seen: 사용자가 화면에서 본 스냅샷. 클릭 시점 서버값이 다르면 승인하지 않는다 (run이 새로고침·오류 표시).
// onApproved: 승인 POST가 성공한 뒤에만 부른다 (화면 이동). 이후 이미지 생성 실패는 이미지 화면에서 재개한다
export async function approveCopyAndCreateImage(seen:LiveSnapshot,ack:boolean,onApproved:()=>void){
  await run(seen.job_id,'ai/image',async()=>{
    const s=await getLiveSnapshot(seen.job_id)
    if(!sameCopyReview(seen,s))throw Error('카피가 바뀌었습니다. 최신 카피를 다시 확인한 뒤 승인해 주세요.')
    guardCopyApproval(s)
    await approveLiveCopy(s,ack)
    onApproved()
    await queuePromptAndImage(s.job_id)
  })
}
export async function resumeImageFromApproved(id:string){
  await run(id,'ai/image',async()=>{
    const s=await getLiveSnapshot(id)
    if(s.state==='COPY_APPROVED')await queuePromptAndImage(id)
    else if(s.state==='PROMPT_READY'){
      const task=await queueLive(id,'image')
      useProjectStore.getState().setLiveTask(task.task_id)
    }else throw Error('이미 진행 중이거나 완료된 상태입니다. 상태를 새로고침하세요.')
  })
}
// 수정 요청·되돌리기: 클릭 시점의 최신 스냅샷 해시로 보낸다. Task면 끝날 때까지 기다린다 (자동 재시도 없음)
async function untilReviewed(id:string,res:{task_id?:string}){
  if(!res.task_id)return
  useProjectStore.getState().setLiveTask(res.task_id)
  await waitLiveTask(id,res.task_id,'COPY_REVIEW_REQUIRED')
}
export async function reviseCopy(id:string,instruction:string){
  await run(id,'ai/copy-review',async()=>untilReviewed(id,await reviseLiveCopy(await getLiveSnapshot(id),instruction)))
}
export async function restoreCopy(id:string){
  await run(id,'ai/copy-review',async()=>untilReviewed(id,await restoreLiveCopy(await getLiveSnapshot(id))))
}
export async function rejectCopy(s:LiveSnapshot){
  if(s.state!=='COPY_REVIEW_REQUIRED')throw Error('카피 거절 상태 오류')
  await run(s.job_id,'ai/image',async()=>{await rejectLiveCopy(s.job_id)})
}
// 합성까지 성공해야 onDone(최종 결과로 이동). 합성만 실패하면 이미지 화면에서 retryCompose로 다시 시도한다
export async function approveImageAndCompose(seen:LiveSnapshot,onDone:()=>void){
  await run(seen.job_id,'compose',async()=>{
    const s=await getLiveSnapshot(seen.job_id)
    if(!sameImageCandidate(seen,s))throw Error('이미지가 바뀌었습니다. 최신 이미지를 다시 확인한 뒤 승인해 주세요.')
    guardImageApproval(s)
    await approveLiveImage(s)
    await compose(s.job_id)
    onDone()
  })
}
/** Compose failed after image approval: resend compose only, never regenerate or re-approve the image. */
export async function retryCompose(id:string){
  await run(id,'compose',async()=>{
    const s=await getLiveSnapshot(id)
    if(s.state!=='IMAGE_APPROVED')throw Error('합성 대기 상태가 아닙니다. 새로고침 후 현재 상태를 확인하세요.')
    await compose(id)
  })
}
export async function rejectImage(s:LiveSnapshot){
  guardImageApproval(s)
  await run(s.job_id,'ai/image',async()=>{await rejectLiveImage(s)})
}
