import test from 'node:test'
import assert from 'node:assert/strict'
import {displayActualArtwork} from '../src/demo/sharedArtworkDisplay.ts'

const meta=(width:number,height:number,image_size:'3:4'|'4:5'|'9:16'|null)=>({
  dimensions_source:'VERIFIED_FINAL_PNG' as const,
  output_size:{width,height},image_size
})
test('actual final PNG pixel dimensions drive all three supported ratios',()=>{
  for(const [w,h,ratio] of [[1080,1440,'3:4'],[1080,1350,'4:5'],[1080,1920,'9:16']] as const){
    const x=displayActualArtwork(meta(w,h,ratio))
    assert.equal(x.ratioLabel,ratio)
    assert.equal(x.pixels,w+'×'+h+'px')
    assert.equal(x.aspectRatio,w+' / '+h)
    assert.equal(x.verified,true)
  }
})
test('wrong 4:5 metadata never mislabels a verified 9:16 file',()=>{
 const x=displayActualArtwork(meta(1080,1920,'4:5'))
 assert.equal(x.ratioLabel,'화면비 메타데이터 불일치')
 assert.equal(x.aspectRatio,'1080 / 1920')
})
test('unknown legacy dimensions show actual pixels without inventing a ratio',()=>{
 const x=displayActualArtwork(meta(135,175,null))
 assert.equal(x.ratioLabel,'기타 화면비')
 assert.equal(x.pixels,'135×175px')
})
test('missing, corrupted or unverified metadata fails closed',()=>{
 for(const x of [
  {},
  {dimensions_source:'UNAVAILABLE' as const,output_size:{width:1080,height:1920},image_size:'9:16' as const},
  {dimensions_source:'VERIFIED_FINAL_PNG' as const,output_size:{width:0,height:1920},image_size:'9:16' as const},
  {dimensions_source:'VERIFIED_FINAL_PNG' as const,output_size:{width:1080.25,height:1920},image_size:'9:16' as const},
  {dimensions_source:'VERIFIED_FINAL_PNG' as const,output_size:{width:9000,height:9000},image_size:'9:16' as const}
 ]){
  const r=displayActualArtwork(x)
  assert.equal(r.verified,false)
  assert.equal(r.pixels,null)
  assert.equal(r.ratioLabel,'화면비 확인 불가')
 }
})
