// 브라우저 다운로드 (blob URL·같은 출처 경로)
export function download(href: string, filename: string) {
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
}
