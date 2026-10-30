// 긴 변이 maxSide를 넘으면 비율을 유지해 줄인 크기
export function fitWithin(width: number, height: number, maxSide: number) {
  const scale = Math.min(1, maxSide / Math.max(width, height))
  return { width: Math.round(width * scale), height: Math.round(height * scale) }
}

// 큰 사진은 올리기 전에 브라우저에서 줄이고 다시 압축한다. 작은 사진은 원본 그대로 보낸다
// PNG는 투명도를 지키려고 PNG로, 나머지는 JPEG로 저장한다. EXIF 회전은 createImageBitmap이 반영한다
export async function shrinkImage(file: File, limits: { maxSide: number; maxBytes: number }): Promise<File> {
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
