import type { Ref } from 'react'
import { CANVAS, SAFE_MARGIN } from '../config'
import type { AdCopy } from '../types/textSchema'

type Props = {
  imageUrl: string
  /** 없으면 이미지만 그린다 (이미지 검토 단계) */
  copy?: AdCopy
  previewScale: number
  canvasRef?: Ref<HTMLDivElement>
}

// 생성 이미지(4:5 한 장) 위에 카피를 글자 레이어로 올린다. 카피는 바깥쪽 5% 여백 안쪽 하단에 둔다.
// shortcut: 합성 방식(이미지 합성 vs 텍스트 레이어)·카피 위치는 실험 중(10/26), 결정되면 맞춘다
export default function AdCanvas({ imageUrl, copy, previewScale, canvasRef }: Props) {
  const { width, height } = CANVAS
  const margin = { paddingInline: width * SAFE_MARGIN, paddingBottom: height * SAFE_MARGIN }

  return (
    <div className="ad-preview" style={{ width: width * previewScale, height: height * previewScale }}>
      <div
        ref={canvasRef}
        className="ad-canvas"
        style={{ width, height, transform: `scale(${previewScale})` }}
      >
        <img className="layer" src={imageUrl} alt="" style={{ inset: 0, width, height }} />
        {copy && (
          <div className="text-zone" style={margin}>
            <p className="ad-headline">{copy.headline}</p>
            <p className="ad-subline">{copy.subline}</p>
            <span className="ad-cta">{copy.cta}</span>
          </div>
        )}
      </div>
    </div>
  )
}
