/** Visual labels derived ONLY from the SHA-verified final PNG dimensions.
 * Requested Job ratio and browser CSS must never override actual file shape.
 * Gracefully accepts an older server response with no dimension fields.
 */
export type SharedArtworkSize = {
  image_size?:'3:4'|'4:5'|'9:16'|null
  output_size?:{width:number;height:number}|null
  dimensions_source?:'VERIFIED_FINAL_PNG'|'UNAVAILABLE'
}
export type ActualArtworkDisplay={
  ratioLabel:string
  pixels:string|null
  aspectRatio:string|undefined
  verified:boolean
}
const expected=new Map<string,string>([
  ['1080x1440','3:4'],['1080x1350','4:5'],['1080x1920','9:16']
])
export function displayActualArtwork(src:SharedArtworkSize):ActualArtworkDisplay{
  const s=src.output_size
  if(src.dimensions_source!=='VERIFIED_FINAL_PNG'||!s||
     !Number.isSafeInteger(s.width)||!Number.isSafeInteger(s.height)||
     s.width<=0||s.height<=0||s.width*s.height>12_000_000)
    return {ratioLabel:'화면비 확인 불가',pixels:null,aspectRatio:undefined,verified:false}
  const measured=expected.get(s.width+'x'+s.height)
  const ratioLabel=measured
     ? (measured===src.image_size?measured:'화면비 메타데이터 불일치')
     : '기타 화면비'
  return {ratioLabel,pixels:s.width+'×'+s.height+'px',
    aspectRatio:s.width+' / '+s.height,verified:true}
}
