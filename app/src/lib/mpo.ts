/** JPEG APP2 MPF signature preflight; the Server redecodes every frame safely.
 * This is only an early upload UX check, not cryptographic image validation. */
export function isMpoFile(file:Pick<File,'name'>):boolean {
  return /\.mpo$/i.test(file.name)
}
export async function hasMpoPrimarySignature(file:File):Promise<boolean> {
  if(!isMpoFile(file))return false
  return hasEmbeddedMpoSignature(file)
}

// Beta fixture only: detect actual MPO despite .JPG/.JPEG extension. This
// does not change the legacy v2 extension-only MPO branch or owner decoder.
export async function hasEmbeddedMpoSignature(file:File):Promise<boolean> {
  if(!/\.(?:jpe?g|mpo)$/i.test(file.name))return false
  if(file.size<20)return false
  const b=new Uint8Array(await file.slice(0,Math.min(file.size,256*1024)).arrayBuffer())
  if(b[0]!==255||b[1]!==216)return false
  let i=2
  while(i+4<=b.length){
    if(b[i]!==255)return false
    while(i<b.length && b[i]===255)i++
    if(i>=b.length)return false
    const marker=b[i++]
    if(marker===0xda||marker===0xd9)break
    if(marker===0x01||(marker>=0xd0&&marker<=0xd7))continue
    if(i+2>b.length)break
    const size=b[i]*256+b[i+1]
    if(size<2||i+size>b.length)break
    if(marker===0xe2 && size>=6 &&
       b[i+2]===77&&b[i+3]===80&&b[i+4]===70&&b[i+5]===0)return true
    i+=size
  }
  return false
}
