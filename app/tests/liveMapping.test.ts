import test from 'node:test'
import assert from 'node:assert/strict'
import {asProductJob,guardCopyApproval,guardImageApproval,isPublishedFinal,isCopyReviewHydrated,type LiveSnapshot} from '../src/api/liveMapping.ts'
import type {Job} from '../src/types/draft.ts'
const raw:Job={job_id:'a'.repeat(32),status:'INPUTS_VALIDATED',assets:[{
  asset_id:'A',role:'product',original_filename:'a.png',content_type:'image/png',
  size_bytes:1024,width:720,height:960,sha256:'b'.repeat(64)
}]}
const example:LiveSnapshot={job_id:raw.job_id,state:'INPUT_STORED',mode:'INPUT_ONLY',
  generation:0,input_sha:'c'.repeat(64),copy_sha:null,review_sha:null,
  image_sha:null,final_sha:null,caption_sha:null,approval_current:false}
test('Live snapshot remains independently typed; no synthetic mock stage',()=>{
  const input=asProductJob(example,raw)
  assert.equal(input.status,'INPUTS_VALIDATED')
  assert.deepEqual(input.assets,raw.assets)
  assert.equal(input.plan,undefined)
  assert.equal(input.copy_candidate,undefined)
})
test('copy approval locks generation, compliance and review SHA',()=>{
  assert.throws(()=>guardCopyApproval(example))
  const review={...example,state:'COPY_REVIEW_REQUIRED' as const,
    generation:2,review_sha:'d'.repeat(64),copy_sha:'e'.repeat(64),
    compliance:{passed:true,issues:[],revised_fields:{},checklist:[],notice:'review'}}
  assert.doesNotThrow(()=>guardCopyApproval(review))
  assert.throws(()=>guardCopyApproval({...review,compliance:{...review.compliance,passed:false}}))
  assert.throws(()=>guardCopyApproval({...review,review_sha:null}))
})
test('image approval requires an active copy approval and candidate SHA',()=>{
  const candidate={...example,state:'IMAGE_REVIEW_REQUIRED' as const,image_sha:'a'.repeat(64),
    approval_current:true,mode:'LIVE'}
  assert.doesNotThrow(()=>guardImageApproval(candidate))
  assert.throws(()=>guardImageApproval({...candidate,approval_current:false}))
})
test('real final download maps to the owner-scoped server, no offline artifacts',()=>{
  const job=asProductJob({...example,state:'COMPLETED',mode:'LIVE',
    image_sha:'d'.repeat(64),final_sha:'e'.repeat(64),caption_sha:'f'.repeat(64)},raw)
  assert.equal(job.status,'COMPLETED')
  assert.equal(job.final_output?.mock,false)
  assert.equal(job.artifacts?.final?.download_url,
    '/demo/api/live/jobs/'+raw.job_id+'/artifacts/final')
})
test('offline fixture and cross-job DTOs never pass as live',()=>{
  assert.throws(()=>asProductJob({...example,mode:'OFFLINE_FIXTURE'},raw))
  assert.throws(()=>asProductJob({...example,job_id:'other'},raw))
})

test('published status is bound to completed immutable file sha, not job id alone',()=>{
 const s={...example,state:'COMPLETED' as const,final_sha:'a'.repeat(64)}
 const entries=[{job_id:raw.job_id,final_sha:'a'.repeat(64),integrity_status:'VERIFIED' as const}]
 assert.equal(isPublishedFinal(s,entries),true)
 assert.equal(isPublishedFinal({...s,final_sha:'f'.repeat(64)},entries),false)
 assert.equal(isPublishedFinal({...s,state:'IMAGE_APPROVED'},entries),false)
 assert.equal(isPublishedFinal(s,[{job_id:'other',final_sha:'a'.repeat(64),integrity_status:'VERIFIED'}]),false)
 assert.equal(isPublishedFinal(s,[{...entries[0],integrity_status:'UNAVAILABLE'}]),false)
 assert.equal(isPublishedFinal(s,[{job_id:raw.job_id,final_sha:'a'.repeat(64),
   integrity_status:'UNAVAILABLE'}]),false)
})

test('copy review acknowledgement hydrates only when Job and Live tuple agree',()=>{
  const compliance={passed:true,issues:[],revised_fields:{},checklist:[],notice:'review'}
  const copy={
    plan:{concept:'',target_audience:'',tone:'',key_message:'',differentiation:'',cta_strategy:''},
    ad_copy:{headline:'a',subline:'b',cta:'c'},caption:'abc',hashtags:[]
  } as unknown as NonNullable<LiveSnapshot['copy']>
  const r2={...example,state:'COPY_REVIEW_REQUIRED' as const,generation:2,
    review_sha:'d'.repeat(64),copy_sha:'e'.repeat(64),mode:'LIVE',
    compliance,copy}
  const display2=asProductJob(r2,raw)
  assert.equal(isCopyReviewHydrated(display2,r2),true)
  const r3={...r2,generation:3,review_sha:'f'.repeat(64)}
  assert.equal(isCopyReviewHydrated(display2,r3),false)
  const display3=asProductJob(r3,raw)
  assert.equal(isCopyReviewHydrated(display3,r2),false)
  assert.equal(isCopyReviewHydrated(display3,r3),true)
  assert.equal(isCopyReviewHydrated(display2,r2,3),false)
  assert.equal(isCopyReviewHydrated(display3,r3,3),true)
  assert.equal(isCopyReviewHydrated(display3,r3,4),false)
  assert.equal(isCopyReviewHydrated(display3,{...r3,copy_sha:'a'.repeat(64)}),false)
  assert.equal(isCopyReviewHydrated(undefined,r3),false)
})
