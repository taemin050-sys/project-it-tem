/** Explicit official-Owner DTO -> B0 view-model boundary; never cast a Live state to B0 status. */
import type { Job, JobStatus } from '../types/draft'
import type { AdCopyOutput, ComplianceReport, ProductAnalysis, ResearchResult } from '../types/textSchema'

export type LiveState='INPUT_STORED'|'COPY_REVIEW_REQUIRED'|'COPY_APPROVED'|'COPY_REJECTED'|
  'PROMPT_READY'|'IMAGE_REVIEW_REQUIRED'|'IMAGE_APPROVED'|'IMAGE_REJECTED'|'COMPLETED'
export type LiveSnapshot={
  job_id:string;state:LiveState;mode:string;generation:number;
  input_sha:string;copy_sha:string|null;review_sha:string|null;
  image_sha:string|null;final_sha:string|null;caption_sha:string|null;
  approval_current:boolean;analysis?:{analysis:ProductAnalysis;analysis_succeeded:boolean;error?:string|null};
  research_display?:ResearchResult;copy?:AdCopyOutput;compliance?:ComplianceReport;
  image_prompt?:unknown
}
export type LiveTask={task_id:string;job_id:string;stage:string;state:
  'QUEUED'|'RUNNING'|'SUCCEEDED'|'BILLING_UNKNOWN';error_code?:string|null}
export type LivePerformance={
  mode:'LIVE';timings:Array<{stage:string;state:string;server_elapsed_s:number|null}>;
  provider_attempts:Array<{stage:string;state:string;model:string|null;
    usage:Record<string,number>|null;billing_unknown:boolean}>;
  project_spend_status:string;application_cost_policy:string
}
const stateMap:Record<LiveState,JobStatus>={
  INPUT_STORED:'INPUTS_VALIDATED',COPY_REVIEW_REQUIRED:'COPY_REVIEW_REQUIRED',
  COPY_APPROVED:'COPY_APPROVED',COPY_REJECTED:'COPY_REJECTED',
  PROMPT_READY:'COPY_APPROVED',IMAGE_REVIEW_REQUIRED:'IMAGE_REVIEW_REQUIRED',
  IMAGE_APPROVED:'IMAGE_APPROVED',IMAGE_REJECTED:'IMAGE_REJECTED',COMPLETED:'COMPLETED'
}
export function asProductJob(snapshot:LiveSnapshot,b0:Job):Job{
  if(snapshot.job_id!==b0.job_id)throw Error('LIVE_JOB_ID_MISMATCH')
  if(snapshot.mode==='OFFLINE_FIXTURE')throw Error('LIVE_PROVENANCE_NOT_VERIFIED')
  const base='/demo/api/live/jobs/'+encodeURIComponent(snapshot.job_id)
  const candidate=snapshot.image_sha?{mock:false}:undefined
  const artifacts={...b0.artifacts,
    ...(snapshot.image_sha?{image:{kind:'image' as const,content_type:'image/png',
      size_bytes:0,download_url:base+'/artifacts/candidate'}}:{}),
    ...(snapshot.state==='COMPLETED'?{
      final:{kind:'final' as const,content_type:'image/png',size_bytes:0,
        download_url:base+'/artifacts/final'},
      caption:{kind:'caption' as const,content_type:'text/plain;charset=utf-8',size_bytes:0,
        download_url:base+'/artifacts/caption'}}:{})
  }
  return {...b0,status:stateMap[snapshot.state],artifacts,
    ...(snapshot.analysis?.analysis_succeeded?{product_analysis:snapshot.analysis.analysis}:{}),
    research_result:snapshot.research_display,copy_output:snapshot.copy,
    compliance_report:snapshot.compliance,image_candidate:candidate,
    final_output:snapshot.state==='COMPLETED'?{mock:false,width:1080,height:1350,format:'png'}:undefined
  }
}
export function guardCopyApproval(s:LiveSnapshot){
  if(s.state!=='COPY_REVIEW_REQUIRED'||!s.review_sha||!s.copy_sha||
      !Number.isSafeInteger(s.generation)||s.generation<1||!s.compliance?.passed)
    throw Error('COPY_COMPLIANCE_OR_REVISION_NOT_APPROVED')
}
export function guardImageApproval(s:LiveSnapshot){
  if(s.state!=='IMAGE_REVIEW_REQUIRED'||!s.image_sha||!s.approval_current)
    throw Error('IMAGE_SHA_OR_COPY_APPROVAL_MISMATCH')
}
