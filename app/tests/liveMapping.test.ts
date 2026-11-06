import test from 'node:test'
import assert from 'node:assert/strict'
import {asProductJob,guardCopyApproval,guardCopyReviewMutation,guardCopyRevision,sameCopyReview,sameImageCandidate,guardImageApproval,isPublishedFinal,isCopyReviewHydrated,type LiveSnapshot} from '../src/api/liveMapping.ts'
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
test('failed compliance copy can be revised/restored but never approved; stale CAS guard stays closed',()=>{
  const review:LiveSnapshot={...example,state:'COPY_REVIEW_REQUIRED',mode:'LIVE',
    generation:2,copy_sha:'e'.repeat(64),review_sha:'f'.repeat(64),
    compliance:{passed:false,issues:[],revised_fields:{},checklist:[],notice:'failed'} }
  assert.doesNotThrow(()=>guardCopyReviewMutation(review))
  assert.throws(()=>guardCopyApproval(review))
  assert.doesNotThrow(()=>guardCopyReviewMutation({...review,compliance:undefined}))
  assert.throws(()=>guardCopyReviewMutation({...review,review_sha:null}))
  assert.throws(()=>guardCopyReviewMutation({...review,copy_sha:null}))
  assert.throws(()=>guardCopyReviewMutation({...review,generation:0}))
  assert.throws(()=>guardCopyReviewMutation({...review,generation:2.5}))
  assert.throws(()=>guardCopyReviewMutation({...review,state:'COPY_APPROVED'}))
  assert.throws(()=>guardCopyReviewMutation({...review,job_id:''}))
  assert.doesNotThrow(()=>guardCopyReviewMutation({...review,compliance:{...review.compliance!,passed:true}}))
  assert.doesNotThrow(()=>guardCopyApproval({...review,compliance:{...review.compliance!,passed:true}}))
})

test('Owner FE #26 guard name uses the identical BP11 failed-review repair fence',()=>{
  assert.equal(guardCopyRevision,guardCopyReviewMutation)
})
test('Owner #26 subsequent approval requires unchanged seen generation/review/image',()=>{
  const s={...example,state:'COPY_REVIEW_REQUIRED' as const,generation:2,
    copy_sha:'c'.repeat(64),review_sha:'r'.repeat(64)}
  assert.equal(sameCopyReview(s,{...s}),true)
  assert.equal(sameCopyReview(s,{...s,generation:3}),false)
  assert.equal(sameCopyReview(s,{...s,review_sha:'new'}),false)
  const img={...s,state:'IMAGE_REVIEW_REQUIRED' as const,image_sha:'i'.repeat(64),approval_current:true}
  assert.equal(sameImageCandidate(img,{...img}),true)
  assert.equal(sameImageCandidate(img,{...img,image_sha:'j'.repeat(64)}),false)
  assert.equal(sameImageCandidate(img,{...img,approval_current:false}),false)
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

test('Owner Image #23 final dimensions are server-bound, not silently forced to 4:5',()=>{
  const supported=[
    {image_size:'3:4' as const,output_size:{width:1080,height:1440},
      template_profile:'OWNER_IMAGE_SIZE_3_4' as const},
    {image_size:'4:5' as const,output_size:{width:1080,height:1350},
      template_profile:'OWNER_IMAGE_SIZE_4_5' as const},
    {image_size:'9:16' as const,output_size:{width:1080,height:1920},
      template_profile:'OWNER_IMAGE_SIZE_9_16' as const}
  ]
  for(const fields of supported){
    const s:LiveSnapshot={...example,...fields,state:'COMPLETED',mode:'LIVE',
      image_sha:'e'.repeat(64),final_sha:'f'.repeat(64),caption_sha:'a'.repeat(64)}
    const job=asProductJob(s,raw)
    assert.equal(job.final_output?.width,fields.output_size.width)
    assert.equal(job.final_output?.height,fields.output_size.height)
    assert.equal(job.final_output?.mock,false)
    assert.equal(job.artifacts?.final?.download_url,
      '/demo/api/live/jobs/'+raw.job_id+'/artifacts/final')
  }
})
