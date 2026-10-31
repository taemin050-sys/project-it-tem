import test from 'node:test'
import assert from 'node:assert/strict'
import {asProductJob,guardCopyApproval,guardImageApproval,type LiveSnapshot} from '../src/api/liveMapping.ts'
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
