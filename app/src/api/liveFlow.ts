/** User initiated only: never called from React effects/poll hooks. No auto paid retries. */
import {queryClient} from './queryClient'
import {useProjectStore} from '../store/projectStore'
import {approveLiveCopy,rejectLiveCopy,queueLive,waitLiveTask,approveLiveImage,
    rejectLiveImage,composeLive,getLiveSnapshot,qaPromptImage,qaCompose,
  reviseLiveCopy,restoreLiveCopy} from './liveJobs'
import { AD_LAYOUT, QA_OFFLINE_FIXTURE } from '../config'
import {guardCopyApproval,guardImageApproval,type LiveSnapshot} from './liveMapping'
// Legacy-only composition layout. Managed A Jobs NEVER receive this value.
// The server records each Job's layout version/hash and composes from it.
export const LEGACY_LAYOUT={text_regions:{
  headline:{left:.07,top:.055,right:.93,bottom:.17,min_font_size:44,max_font_size:62,
    padding:9,align:'center',color:'#26352B',background:null},
  subline:{left:.06,top:.835,right:.94,bottom:.905,min_font_size:26,max_font_size:42,
    padding:9,align:'center',color:'#25342C',background:'#F8F7F3'},
  cta:{left:.62,top:.91,right:.94,bottom:.95,min_font_size:19,max_font_size:26,
    padding:4,align:'center',color:'#FFFFFF',background:'#305141'},
},protected_regions:[{left:.31,top:.23,right:.73,bottom:.82}]}
import {ApiError} from './client'
// Send FE Owner A v1 unchanged; Backend validates the SHA against the
// frozen per-Job Image Owner policy and rejects any mismatch.
const composePinned=(s:LiveSnapshot)=>{
  const operation=QA_OFFLINE_FIXTURE
    ? qaCompose(s.job_id)
    : composeLive(s.job_id,s.template_profile?.startsWith('OWNER_IMAGE_SIZE_')
       ? undefined : s.template_profile==='A_CENTERED'?AD_LAYOUT:LEGACY_LAYOUT)
  return operation.catch(e=>{
    throw Error('광고 합성에 실패했습니다. 승인 이미지는 유지됩니다. 합성만 재시도하세요.'+
      (e instanceof ApiError&&e.status>0?' (오류 '+e.status+')':''))
  })
}
const refresh=async(id:string)=>{
  await queryClient.invalidateQueries({queryKey:['job',id]})
  await queryClient.invalidateQueries({queryKey:['live-snapshot',id]})
}
async function run(id:string,step:'ai/image'|'ai/copy-review'|'compose',
                   action:()=>Promise<unknown>){
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
  if(QA_OFFLINE_FIXTURE){
    await qaPromptImage(id)
    return
  }
  const task=await queueLive(id,'prompt')
  useProjectStore.getState().setLiveTask(task.task_id)
  await waitLiveTask(id,task.task_id,'PROMPT_READY')
  // This only executes as a continuation of the explicit user's "generate image"
  // click. Re-mounting after a crash never resumes POST.
  const image=await queueLive(id,'image')
  useProjectStore.getState().setLiveTask(image.task_id)
}
export async function approveCopyAndCreateImage(s:LiveSnapshot,ack:boolean,onApproved:()=>void=()=>{}){
  guardCopyApproval(s)
  await run(s.job_id,'ai/image',async()=>{
    await approveLiveCopy(s,ack)
    // Owner #26: navigate only after actual approval POST success.
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
export async function reviseCopyFromInstruction(s:LiveSnapshot,instruction:string){
  if(!instruction.trim())throw Error('수정 요청을 입력해 주세요.')
  await run(s.job_id,'ai/copy-review',async()=>{
    const result=await reviseLiveCopy(s,instruction.trim())
    if('task_id' in result){
      useProjectStore.getState().setLiveTask(result.task_id)
      const updated=await waitLiveTask(s.job_id,result.task_id,'COPY_REVIEW_REQUIRED')
      if(updated.generation<=s.generation || updated.review_sha===s.review_sha)
        throw Error('TEXT_REVISION_NOT_COMMITTED')
    }
  })
}
export async function restorePreviousLiveCopy(s:LiveSnapshot){
  if(!s.previous_copy_available)throw Error('복원 가능한 이전 버전이 없습니다.')
  await run(s.job_id,'ai/copy-review',async()=>{await restoreLiveCopy(s)})
}
export async function rejectCopy(s:LiveSnapshot){
  if(s.state!=='COPY_REVIEW_REQUIRED')throw Error('카피 거절 상태 오류')
  await run(s.job_id,'ai/image',async()=>{await rejectLiveCopy(s.job_id)})
}
export async function approveImageAndCompose(s:LiveSnapshot,onComposed:()=>void=()=>{}){
  guardImageApproval(s)
  await run(s.job_id,'compose',async()=>{
    await approveLiveImage(s)
    await composePinned(s)
    // Only show final result after a successful composition response.
    onComposed()
  })
}
/** FE Owner alias: a manual retry is composition-only, never image regeneration. */
export const retryCompose=(id:string)=>retryApprovedComposition(id)
export async function rejectImage(s:LiveSnapshot){
  guardImageApproval(s)
  await run(s.job_id,'ai/image',async()=>{await rejectLiveImage(s)})
}

/** Explicit, cost-free retry only for a previously approved candidate.
 * No image/prompt queue, no Provider attempt, same pinned server policy.
 */
export async function retryApprovedComposition(id:string){
  await run(id,'compose',async()=>{
    const current=await getLiveSnapshot(id)
    if(current.state!=='IMAGE_APPROVED'||!current.image_sha||!current.approval_current)
      throw Error('IMAGE_APPROVAL_STALE_OR_COMPLETED')
    await composePinned(current)
  })
}
