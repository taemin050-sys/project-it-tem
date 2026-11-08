/** Explicit official-Owner DTO -> B0 view-model boundary; never cast a Live state to B0 status. */
import type { Job, JobStatus } from '../types/draft'
const QA_OFFLINE_FIXTURE=import.meta.env?.VITE_QA_OFFLINE_FIXTURE==='YES'
import type { AdCopyOutput, ComplianceReport, ProductAnalysis, ResearchResult } from '../types/textSchema'

export type LiveState='INPUT_STORED'|'COPY_REVIEW_REQUIRED'|'COPY_APPROVED'|'COPY_REJECTED'|
  'PROMPT_READY'|'IMAGE_REVIEW_REQUIRED'|'IMAGE_APPROVED'|'IMAGE_REJECTED'|'COMPLETED'
export type LiveSnapshot={
  job_id:string;state:LiveState;mode:string;generation:number;
  input_sha:string;copy_sha:string|null;review_sha:string|null;
  image_sha:string|null;final_sha:string|null;caption_sha:string|null;
  approval_current:boolean;previous_copy_available?:boolean;
  review_policy?:{status:'CURRENT'|'REVALIDATION_REQUIRED'|'LEGACY_UNBOUND'|
    'BINDING_TAMPERED'|'LEGACY_POLICY_MODE';version:string|null;sha:string|null};
  functional_types?:string[];
  functional_types_status?:'OWNER_TEXT_V010_APPLIED'|'OWNER_TEXT_DTO_PENDING'|'NO_SELECTION';
  emoji_level?:'없음'|'보통'|'많이';
  revision_feedback?:{note:string|null;changed_fields:string[];source:string}|null;
  analysis?:{analysis:ProductAnalysis;analysis_succeeded:boolean;error?:string|null};
  research_display?:ResearchResult;copy?:AdCopyOutput;compliance?:ComplianceReport;
  image_prompt?:unknown
  template_profile?:'A_CENTERED'|'LEGACY_PINNED'|'PRE_POLICY_LEGACY'|
    'OWNER_IMAGE_SIZE_3_4'|'OWNER_IMAGE_SIZE_4_5'|'OWNER_IMAGE_SIZE_9_16'
  image_size?:'3:4'|'4:5'|'9:16'
  generation_mode?:'composed'|'freeform'
  image_attempt_version?:number
  output_size?:{width:number;height:number}
  product_protection_status?:'MANUAL_REVIEW_REQUIRED'|'NOT_REVIEWED'
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
  if(snapshot.mode==='OFFLINE_FIXTURE'&&!QA_OFFLINE_FIXTURE)
    throw Error('LIVE_PROVENANCE_NOT_VERIFIED')
  const base=(snapshot.mode==='OFFLINE_FIXTURE' && QA_OFFLINE_FIXTURE
    ? '/demo/api/qa/jobs/' : '/demo/api/live/jobs/')+encodeURIComponent(snapshot.job_id)
  const candidate=snapshot.image_sha?{mock:snapshot.mode==='OFFLINE_FIXTURE'}:undefined
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
    live_revision_binding:{generation:snapshot.generation,
      copy_sha:snapshot.copy_sha,review_sha:snapshot.review_sha},
    ...(snapshot.analysis?.analysis_succeeded?{product_analysis:snapshot.analysis.analysis}:{}),
    research_result:snapshot.research_display,copy_output:snapshot.copy,
    compliance_report:snapshot.compliance,image_candidate:candidate,
    final_output:snapshot.state==='COMPLETED'?{mock:snapshot.mode==='OFFLINE_FIXTURE',
      width:snapshot.output_size?.width??1080,
      height:snapshot.output_size?.height??1350,format:'png'}:undefined
  }
}
/** Do not display an acknowledgement until the independently polled Job and
 * Live snapshot have the same exact copy/review/generation tuple.
 * Reviving an old copy SHA via restore never revives its previous approval.
 */
export function isCopyReviewHydrated(
  job:Job|undefined,s:LiveSnapshot|undefined,minGeneration=0
):boolean{
  const key=job?.live_revision_binding
  return Boolean(job && s && s.state==='COPY_REVIEW_REQUIRED' &&
    job.status==='COPY_REVIEW_REQUIRED' && job.job_id===s.job_id &&
    key && Number.isSafeInteger(key.generation) && key.generation>0 &&
    key.generation>=minGeneration &&
    key.generation===s.generation && key.copy_sha===s.copy_sha &&
    key.review_sha===s.review_sha && s.copy && s.copy_sha && s.review_sha &&
    s.compliance && job.copy_output && job.compliance_report &&
    job.compliance_report.passed===s.compliance.passed)
}
/** Revision/restore are remediation actions. Unlike approval they must
 * remain available for a failed compliance review; the server still binds
 * the authenticated actor, current Job, Generation and Review SHA via CAS.
 */
export function guardCopyReviewMutation(s:LiveSnapshot){
  if(!s.job_id || s.state!=='COPY_REVIEW_REQUIRED'||!s.review_sha||!s.copy_sha||
      !Number.isSafeInteger(s.generation)||s.generation<1)
    throw Error('COPY_REVIEW_REVISION_NOT_CURRENT')
}
// Owner #26 naming retained as a single alias, never a second/looser approval gate.
export const guardCopyRevision=guardCopyReviewMutation
export function guardCopyApproval(s:LiveSnapshot){
  if(s.state!=='COPY_REVIEW_REQUIRED'||!s.review_sha||!s.copy_sha||
      !Number.isSafeInteger(s.generation)||s.generation<1||!s.compliance?.passed||
      (s.review_policy && !['CURRENT','LEGACY_POLICY_MODE'].includes(s.review_policy.status)))
    throw Error('COPY_COMPLIANCE_OR_REVISION_NOT_APPROVED')
}
// Owner #26: bind approval to the exact copy/image the user saw, not merely fresh GET.
export const sameCopyReview=(seen:LiveSnapshot,current:LiveSnapshot)=>
  seen.job_id===current.job_id && seen.state==='COPY_REVIEW_REQUIRED' &&
  current.state==='COPY_REVIEW_REQUIRED' && seen.copy_sha!==null &&
  seen.copy_sha===current.copy_sha && seen.review_sha!==null &&
  seen.review_sha===current.review_sha && seen.generation===current.generation
export const sameImageCandidate=(seen:LiveSnapshot,current:LiveSnapshot)=>
  seen.job_id===current.job_id && seen.state==='IMAGE_REVIEW_REQUIRED' &&
  current.state==='IMAGE_REVIEW_REQUIRED' && seen.image_sha!==null &&
  seen.image_sha===current.image_sha && seen.generation===current.generation &&
  seen.copy_sha===current.copy_sha && seen.review_sha===current.review_sha &&
  current.approval_current
export function guardImageApproval(s:LiveSnapshot){
  if(s.state!=='IMAGE_REVIEW_REQUIRED'||!s.image_sha||!s.approval_current)
    throw Error('IMAGE_SHA_OR_COPY_APPROVAL_MISMATCH')
}

/** Verify the exact published final file, not merely a reused Job ID. */
export function isPublishedFinal(snapshot:LiveSnapshot|undefined,items:Array<{job_id:string;final_sha:string;integrity_status:'VERIFIED'|'UNAVAILABLE'}>):boolean{
  if(!snapshot?.final_sha || snapshot.state!=='COMPLETED')return false
  return items.some(x=>x.integrity_status==='VERIFIED' &&
    x.job_id===snapshot.job_id && x.final_sha===snapshot.final_sha)
}
