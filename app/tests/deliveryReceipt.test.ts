import test from 'node:test'
import assert from 'node:assert/strict'
import {assertLiveReceiptBinding} from '../src/api/deliveryReceipt.ts'

const jid='a'.repeat(32), image='b'.repeat(64)
const genuine=()=>({
  job_id:jid,
  image_provider_evidence:{
    owner_attempt_id:'attempt-1',provider_request_id:'resp-1',
    model:'image-model',image_sha256:image,usage:{total_tokens:1}
  }
})

test('completed genuine Job receipt binds the exact model response and bytes',()=>{
  assert.doesNotThrow(()=>assertLiveReceiptBinding(genuine(),jid,image))
  assert.throws(()=>assertLiveReceiptBinding(genuine(),'c'.repeat(32),image),
                /LIVE_RECEIPT_JOB_PROVIDER_BINDING_INVALID/)
  assert.throws(()=>assertLiveReceiptBinding(genuine(),jid,'d'.repeat(64)),
                /LIVE_RECEIPT_JOB_PROVIDER_BINDING_INVALID/)
})

test('offline/fixture and missing Usage cannot be sold as genuine model proof',()=>{
  assert.throws(()=>assertLiveReceiptBinding({job_id:jid},jid,image),
                /LIVE_RECEIPT_PROVIDER_EVIDENCE_MISSING/)
  const absent=genuine()
  absent.image_provider_evidence.usage={total_tokens:1}
  absent.image_provider_evidence.provider_request_id=''
  assert.throws(()=>assertLiveReceiptBinding(absent,jid,image),
                /LIVE_RECEIPT_JOB_PROVIDER_BINDING_INVALID/)
})
