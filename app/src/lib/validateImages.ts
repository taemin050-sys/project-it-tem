import {isMpoFile} from './mpo.ts'

export type Limits = {
  minFiles: number
  maxFiles: number
  acceptTypes: readonly string[]
}

// 클라이언트 1차 검사. 서버 측 검증(이형기)을 대체하지 않는다. 용량은 제한하지 않는다 (큰 사진은 자동 축소)
export function validateImages(files: File[], limits: Limits, label: string): string[] {
  const errors: string[] = []
  if (files.length < limits.minFiles) errors.push(`${label}을 ${limits.minFiles}장 이상 올려 주세요.`)
  if (files.length > limits.maxFiles) errors.push(`${label}은 최대 ${limits.maxFiles}장까지 올릴 수 있습니다.`)
  for (const f of files) {
    if (!limits.acceptTypes.includes(f.type) && !(isMpoFile(f) && ['', 'image/mpo','image/jpeg','application/octet-stream'].includes(f.type))) errors.push(`${f.name}: JPG, PNG, WEBP 형식만 올릴 수 있습니다.`)
  }
  return errors
}
