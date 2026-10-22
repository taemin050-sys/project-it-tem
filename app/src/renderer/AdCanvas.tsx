import type { Ref } from 'react'
import { CANVAS } from '../config'
import { toPixelBox } from '../lib/geometry'
import type { AdCopy, ImageResult } from '../types/draft'

type Props = {
  image: ImageResult
  copy: Pick<AdCopy, 'headline' | 'subline' | 'cta'>
  previewScale: number
  canvasRef?: Ref<HTMLDivElement>
}

// 레이어 순서: 배경(scene_underlay) → 제품(product_rgba) → 스크림 → 문구. 순서는 pi와 합의 필요
export default function AdCanvas({ image, copy, previewScale, canvasRef }: Props) {
  const { width, height } = CANVAS
  const product = toPixelBox(image.product_box, width, height)
  const zone = toPixelBox(image.text_safe_zone, width, height)

  return (
    <div className="ad-preview" style={{ width: width * previewScale, height: height * previewScale }}>
      <div
        ref={canvasRef}
        className="ad-canvas"
        style={{ width, height, transform: `scale(${previewScale})` }}
      >
        <img className="layer" src={image.scene_underlay} alt="" style={{ inset: 0, width, height }} />
        <img className="layer" src={image.product_rgba} alt="" style={product} />
        <div className="scrim" style={{ top: zone.top - 120, height: height - zone.top + 120 }} />
        <div className="text-zone" style={zone}>
          <p className="ad-headline">{copy.headline}</p>
          <p className="ad-subline">{copy.subline}</p>
          <span className="ad-cta">{copy.cta}</span>
        </div>
      </div>
    </div>
  )
}
