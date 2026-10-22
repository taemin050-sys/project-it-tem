type Limits = {
  minFiles: number
  maxFiles: number
  maxBytes: number
  acceptTypes: readonly string[]
}

// 클라이언트 1차 검사. 서버 측 검증(이형기)을 대체하지 않는다
export function validateImages(files: File[], limits: Limits): string[] {
  const errors: string[] = []
  if (files.length < limits.minFiles) errors.push(`제품 사진을 ${limits.minFiles}장 이상 올려 주세요.`)
  if (files.length > limits.maxFiles) errors.push(`제품 사진은 최대 ${limits.maxFiles}장까지 올릴 수 있습니다.`)
  const mb = Math.round(limits.maxBytes / 1024 / 1024)
  for (const f of files) {
    if (!limits.acceptTypes.includes(f.type)) errors.push(`${f.name}: JPG, PNG, WEBP 형식만 올릴 수 있습니다.`)
    else if (f.size > limits.maxBytes) errors.push(`${f.name}: ${mb}MB 이하 사진만 올릴 수 있습니다.`)
  }
  return errors
}
