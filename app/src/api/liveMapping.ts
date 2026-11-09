/** Explicit official-Owner DTO -> B0 view-model boundary; never cast a Live state to B0 status. */
import type { Job, JobStatus } from '../types/draft'
import type { AdCopyOutput, ComplianceReport, CopyField, ProductAnalysis, ResearchResult } from '../types/textSchema'

export type LiveState='INPUT_STORED'|'COPY_REVIEW_REQUIRED'|'COPY_APPROVED'|'COPY_REJECTED'|
  'PROMPT_READY'|'IMAGE_REVIEW_REQUIRED'|'IMAGE_APPROVED'|'IMAGE_REJECTED'|'COMPLETED'
export type LiveSnapshot={
  job_id:string;state:LiveState;mode:string;generation:number;
  input_sha:string;copy_sha:string|null;review_sha:string|null;
  image_sha:string|null;final_sha:string|null;caption_sha:string|null;
  approval_current:boolean;analysis?:{analysis:ProductAnalysis;analysis_succeeded:boolean;error?:string|null};
  research_display?:ResearchResult;copy?:AdCopyOutput;compliance?:ComplianceReport;
  image_prompt?:unknown
  output_size?:{width:number;height:number}
  revision_feedback?:{changed_fields:CopyField[];note:string}|null
  previous_copy_available?:boolean
}
export type LiveTask={task_id:string;job_id:string;stage:string;state:
  'QUEUED'|'RUNNING'|'SUCCEEDED'|'BILLING_UNKNOWN';error_code?:string|null}
export type LivePerformance={
  mode:'LIVE';job_id:string;timings:Array<{stage:string;state:string;server_elapsed_s:number|null}>;
  provider_attempts:Array<{stage:string;state:string;model:string|null;
    usage:Record<string,number|null>|null;billing_unknown:boolean;
    estimated_cost_usd?:string|null;estimate_rate_version?:string|null}>;
  image_cost_summary?:{
    known_estimated_cost_usd:string|null;
    estimated_total_usd?:string|null;
    priced_attempt_count:number;
    unpriced_attempt_count:number;
  };
  image_savings_estimate?:{
    reference_usage:{
      input_text_tokens:number;
      input_image_tokens:number;
      output_tokens:number;
      total_tokens:number;
    };
    reference_cost_usd:string;
    direct_attempt_count:number;
    direct_baseline_stages?:Array<{label:string;attempt_count:number}>;
    service_attempt_count:number;
    service_attempt_count_is_estimated:boolean;
    direct_estimated_cost_usd:string;
    service_estimated_cost_usd:string;
    estimated_savings_usd:string;
    estimated_savings_tokens:number;
    dimension_experiment?:{
      variant_count:number;
      initial_attempt_count:number;
      refinement_attempt_count:number;
      total_tokens:number;
      estimated_cost_usd:string;
    };
  }|null;
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
    // shortcut: output_size 형태({width,height})는 서빙 답변서 기준, GCP 응답으로 확인되면 주석 삭제. 없으면 예전 기본 4:5
    final_output:snapshot.state==='COMPLETED'?{mock:false,width:snapshot.output_size?.width??1080,
      height:snapshot.output_size?.height??1350,format:'png'}:undefined
  }
}
export function guardCopyApproval(s:LiveSnapshot){
  if(s.state!=='COPY_REVIEW_REQUIRED'||!s.review_sha||!s.copy_sha||
      !Number.isSafeInteger(s.generation)||s.generation<1||!s.compliance?.passed)
    throw Error('COPY_COMPLIANCE_OR_REVISION_NOT_APPROVED')
}
// 수정 요청·되돌리기는 규제 미통과 카피에도 허용한다 (승인만 PASS 필요). 지금 보고 있는 검수본인지만 잠근다
export function guardCopyRevision(s:LiveSnapshot){
  if(s.state!=='COPY_REVIEW_REQUIRED'||!s.review_sha||!s.copy_sha||
      !Number.isSafeInteger(s.generation)||s.generation<1)
    throw Error('COPY_REVISION_STATE_MISMATCH')
}
// 승인 직전 서버 최신값이 사용자가 화면에서 본 검수본·이미지와 같은지 (다른 탭 수정·폴링 지연으로 바뀌었으면 승인하지 않는다)
export const sameCopyReview=(seen:LiveSnapshot,current:LiveSnapshot)=>
  seen.generation===current.generation&&seen.review_sha===current.review_sha&&seen.copy_sha===current.copy_sha
export const sameImageCandidate=(seen:LiveSnapshot,current:LiveSnapshot)=>
  seen.image_sha!==null&&seen.image_sha===current.image_sha
export function guardImageApproval(s:LiveSnapshot){
  if(s.state!=='IMAGE_REVIEW_REQUIRED'||!s.image_sha||!s.approval_current)
    throw Error('IMAGE_SHA_OR_COPY_APPROVAL_MISMATCH')
}

/** Verify the exact published final file, not merely a reused Job ID. */
export function isPublishedFinal(snapshot:LiveSnapshot|undefined,items:Array<{job_id:string;final_sha:string}>):boolean{
  if(!snapshot?.final_sha || snapshot.state!=='COMPLETED')return false
  return items.some(x=>x.job_id===snapshot.job_id && x.final_sha===snapshot.final_sha)
}
