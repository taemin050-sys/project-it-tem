import test from 'node:test'
import assert from 'node:assert/strict'

import {A51E_SIGNED_BETA_CANDIDATE,isPendingMpo,newUploadRequestId
} from '../src/lib/a51eSignedBeta.ts'

test('A51E signed beta client candidate is OFF unless built explicitly',async()=>{
  assert.equal(A51E_SIGNED_BETA_CANDIDATE,false)
  const file=new File([new Uint8Array([255,216,255,217])],
    'hidden_mpo.jpg',{type:'image/jpeg'})
  assert.equal(await isPendingMpo(file),false)
})

test('A51E upload request IDs are fresh 32-hex random UUID v4',()=>{
  const ids=new Set<string>()
  for(let i=0;i<64;i++){
    const id=newUploadRequestId()
    assert.match(id,/^[0-9a-f]{32}$/)
    assert.equal(id[12],'4')
    ids.add(id)
  }
  assert.equal(ids.size,64)
})
