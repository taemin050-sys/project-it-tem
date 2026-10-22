import { toPng } from 'html-to-image'
import { CANVAS } from '../config'

// 미리보기 축소(transform)를 풀고 원본 크기 그대로 1:1 출력한다
export async function exportPng(node: HTMLElement, filename: string) {
  await document.fonts.ready
  const dataUrl = await toPng(node, {
    width: CANVAS.width,
    height: CANVAS.height,
    pixelRatio: 1,
    style: { transform: 'none' },
  })
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = filename
  a.click()
}
