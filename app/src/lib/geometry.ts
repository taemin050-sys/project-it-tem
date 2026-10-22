import type { NormBox } from '../types/draft'

// shortcut: [x, y, w, h] 0~1 좌상단 원점 가정, pi와 변환 규칙 합의 후 맞춘다
export function toPixelBox([x, y, w, h]: NormBox, width: number, height: number) {
  return {
    left: Math.round(x * width),
    top: Math.round(y * height),
    width: Math.round(w * width),
    height: Math.round(h * height),
  }
}
