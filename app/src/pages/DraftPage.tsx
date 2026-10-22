import { useRef, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useJob } from '../api/useJob'
import AdCanvas from '../renderer/AdCanvas'
import { exportPng } from '../renderer/exportPng'

export default function DraftPage() {
  const { data: job } = useJob()
  const canvasRef = useRef<HTMLDivElement>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  if (!job?.result) return <Navigate to="/copy" replace />
  const { image, copy } = job.result

  async function onExport() {
    setExportError(null)
    try {
      await exportPng(canvasRef.current!, 'ad_1080x1350.png')
    } catch {
      setExportError('이미지 저장에 실패했습니다. 다른 브라우저에서 다시 시도해 주세요.')
    }
  }

  return (
    <section>
      <h1>이미지 시안</h1>
      {image.needs_manual_check && <p className="errors">제품 영역 확인이 필요합니다.</p>}
      {image.warnings.map((w) => <p key={w} className="errors">{w}</p>)}

      <AdCanvas image={image} copy={copy} previewScale={0.4} canvasRef={canvasRef} />

      {exportError && <p className="errors" role="alert">{exportError}</p>}
      <div className="actions">
        <button className="button" onClick={onExport}>PNG 저장 (1080×1350)</button>
        <Link className="button secondary" to="/export">다음: 검증·내보내기</Link>
      </div>
    </section>
  )
}
