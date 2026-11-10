import {isMpoFile} from './mpo.ts'
import {A51D_MPO_FIXTURE,confirmedMpoChoice,requiresMpoFixtureSelection
} from './a51dMpoSelection.ts'

// 긴 변이 maxSide를 넘으면 비율을 유지해 줄인 크기
export function fitWithin(width: number, height: number, maxSide: number) {
  const scale = Math.min(1, maxSide / Math.max(width, height))
  return { width: Math.round(width * scale), height: Math.round(height * scale) }
}

// 큰 사진은 올리기 전에 브라우저에서 줄이고 다시 압축한다. 작은 사진은 원본 그대로 보낸다
// PNG는 투명도를 지키려고 PNG로, 나머지는 JPEG로 저장한다. EXIF 회전은 createImageBitmap이 반영한다
export async function shrinkImage(file: File, limits: { maxSide: number; maxBytes: number }): Promise<File> {
  if(A51D_MPO_FIXTURE){
    // Never silently decode/re-encode .jpg hidden MPO in browser; this would
    // discard the selected frame and break source/provenance SHA binding.
    if(confirmedMpoChoice(file)){
      if(file.size>limits.maxBytes)
        throw Error('선택한 MPO 원본의 크기가 업로드 제한을 초과했습니다.')
      return file
    }
    if(await requiresMpoFixtureSelection(file))
      throw Error('MPO 사진을 다시 선택하고 사용할 프레임을 확정해 주세요.')
    // The JPG MPF marker can be beyond the browser's bounded APP2 scan.
    // Never re-encode an unconfirmed .jpg/.jpeg in fixture mode: pass the
    // original bytes to B0, which rejects actual MPO-format-as-JPG. If the
    // browser resized it first it could silently lose the second frame.
    if(/\.jpe?g$/i.test(file.name)){
      if(file.size>limits.maxBytes)
        throw Error('원본 JPG가 업로드 제한보다 큽니다. 사진을 별도로 줄여서 올려 주세요.')
      return file
    }
  }
  if(isMpoFile(file)){
    if(file.size>limits.maxBytes)
      throw Error(file.name+': MPO 파일이 서버 업로드 제한보다 큽니다. JPEG로 변환해 올려 주세요.')
    return file
  }
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const size = fitWithin(bitmap.width, bitmap.height, limits.maxSide)
  if (size.width === bitmap.width && file.size <= limits.maxBytes) {
    bitmap.close()
    return file
  }
  const canvas = document.createElement('canvas')
  canvas.width = size.width
  canvas.height = size.height
  canvas.getContext('2d')!.drawImage(bitmap, 0, 0, size.width, size.height)
  bitmap.close()
  const type = file.type === 'image/png' ? 'image/png' : 'image/jpeg'
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, 0.9))
  if (!blob) throw new Error(`${file.name}: 사진을 줄이지 못했습니다.`)
  const name = type === 'image/jpeg' ? file.name.replace(/\.\w+$/, '.jpg') : file.name
  return new File([blob], name, { type })
}
