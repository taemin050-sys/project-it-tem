import { request } from './client'
import type { Job } from '../types/draft'
import type { ProductInput,AdCopyOutput } from '../types/textSchema'
import { asProductJob,guardCopyApproval,guardImageApproval,
  type LiveSnapshot,type LiveTask,type LivePerformance } from './liveMapping'
import { getJob } from './jobs'

const prefix='/demo/api/live'
const url=(id:string)=>prefix+'/jobs/'+encodeURIComponent(id)
const json=(v:unknown)=>({method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify(v)})
export const getLiveSnapshot=(id:string)=>request<LiveSnapshot>(url(id))
export async function getProductLiveJob(id:string):Promise<Job>{
  const [snapshot,original]=await Promise.all([getLiveSnapshot(id),getJob(id)])
  return asProductJob(snapshot,original)
}
export function createLiveInput(b0:Job,product:ProductInput){
  return request<LiveSnapshot>(url(b0.job_id)+'/input',
    json({customer_request_id:'product-live-'+b0.job_id,product}))
}
export const queueLive=(id:string,stage:'text'|'prompt'|'image')=>
  request<{task_id:string;state:string;new:boolean}>(url(id)+'/queue-'+stage,
    {method:'POST'})
export const latestLiveTask=(id:string)=>request<{task:LiveTask|null}>(
  url(id)+'/task-status')
export const getLiveTask=(id:string)=>request<LiveTask>(
  prefix+'/tasks/'+encodeURIComponent(id))
export const editLiveCopy=(id:string,copy:AdCopyOutput)=>
  request<LiveSnapshot>(url(id)+'/copy',json({copy_output:copy}))
export const approveLiveCopy=(s:LiveSnapshot,acknowledgeEvidence:boolean)=>{
  guardCopyApproval(s)
  return request<LiveSnapshot>(url(s.job_id)+'/approve-copy',
    json({expected_generation:s.generation,expected_review_sha:s.review_sha,
      acknowledge_evidence:acknowledgeEvidence}))
}
export const rejectLiveCopy=(id:string)=>request<LiveSnapshot>(url(id)+'/reject-copy',{method:'POST'})
export const approveLiveImage=(s:LiveSnapshot)=>{
  guardImageApproval(s)
  return request<LiveSnapshot>(url(s.job_id)+'/approve-image',json({image_sha:s.image_sha}))
}
export const rejectLiveImage=(s:LiveSnapshot)=>{
  guardImageApproval(s)
  return request<LiveSnapshot>(url(s.job_id)+'/reject-image',json({image_sha:s.image_sha}))
}
export const composeLive=(id:string,layout?:unknown)=>request<LiveSnapshot>(
  url(id)+'/compose',json(layout===undefined?{}:{layout}))
export const shareLive=(id:string)=>request<{shared:boolean}>(url(id)+'/share',{method:'POST'})
export const listPublishedLive=()=>request<{mode:string;jobs:Array<{
  job_id:string;final_sha:string;shared_at:string}>}>(prefix+'/shared')
export const getLivePerformance=(id:string)=>request<LivePerformance>(url(id)+'/performance')
export async function waitLiveTask(id:string,taskId:string,success:LiveStateExpected,
  maxPoll=180):Promise<LiveSnapshot>{
  for(let i=0;i<maxPoll;i++){
    const task=await getLiveTask(taskId)
    if(task.job_id!==id)throw Error('LIVE_TASK_JOB_MISMATCH')
    if(task.state==='BILLING_UNKNOWN')throw Error('청구 여부 불명확: 자동 재호출 금지. 담당자 확인이 필요합니다.')
    if(task.state==='SUCCEEDED'){
      const current=await getLiveSnapshot(id)
      if(current.state===success)return current
      throw Error('LIVE_TASK_STATE_INTEGRITY_ERROR')
    }
    await new Promise(resolve=>setTimeout(resolve,1500))
  }
  throw Error('AI 작업 대기 시간이 길어졌습니다. 재호출하지 말고 새로고침 후 작업 상태를 확인하세요.')
}
type LiveStateExpected='COPY_REVIEW_REQUIRED'|'PROMPT_READY'|'IMAGE_REVIEW_REQUIRED'
