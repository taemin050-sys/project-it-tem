import test from 'node:test'
import assert from 'node:assert/strict'
import {frozenSingleImageInput,SINGLE_IMAGE_MODES,SINGLE_IMAGE_RATIOS} from '../src/api/singleImageContract.ts'
import type {ProductInput} from '../src/types/textSchema.ts'

const id='a'.repeat(32)
const product={product_name:'데일리 크림'} as ProductInput

test('FE Owner #26 input accepts two modes times three ratios and no candidate count/mix',()=>{
  assert.deepEqual(SINGLE_IMAGE_MODES,['composed','freeform'])
  assert.deepEqual(SINGLE_IMAGE_RATIOS,['3:4','4:5','9:16'])
  for(const mode of SINGLE_IMAGE_MODES)for(const ratio of SINGLE_IMAGE_RATIOS){
    const value=frozenSingleImageInput(id,product,ratio,mode)
    assert.deepEqual(Object.keys(value).sort(),
      ['customer_request_id','product','image_size','generation_mode'].sort())
    assert.equal(value.generation_mode,mode)
    assert.equal(value.image_size,ratio)
    assert.equal(value.customer_request_id,'product-live-'+id)
    assert.equal('candidate_count' in value,false)
    assert.equal('modes' in value,false)
    assert.equal('batch' in value,false)
  }
})

test('Invalid/mixed mode, ratio, or job id is rejected before a POST',()=>{
  for(const mode of ['batch','free-1+composed-1','freeform+composed',null,2]){
    assert.throws(()=>frozenSingleImageInput(id,product,'4:5',mode as never),
      /PM_IMAGE_SINGLE_MODE_RATIO_INVALID/)
  }
  for(const ratio of ['1:1','2:3','4x5',null]){
    assert.throws(()=>frozenSingleImageInput(id,product,ratio as never,'composed'),
      /PM_IMAGE_SINGLE_MODE_RATIO_INVALID/)
  }
  assert.throws(()=>frozenSingleImageInput('other',product,'4:5','freeform'),
    /PM_IMAGE_SINGLE_MODE_RATIO_INVALID/)
})
