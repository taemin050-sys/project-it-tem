import { useBlobUrl } from '../api/useJob'
import type { Asset } from '../types/draft'

export default function AssetThumb({ jobId, asset, index, openFull }: { jobId: string; asset: Asset; index: number; openFull?: boolean }) {
  const url = useBlobUrl(`/api/v1/jobs/${jobId}/assets/${asset.asset_id}`)
  if (!url) return <li><span className="muted">불러오는 중…</span></li>
  const image = <img src={url} alt={`제품 사진 ${index + 1}`} />
  return <li>{openFull ? <a href={url} target="_blank" rel="noreferrer">{image}</a> : image}</li>
}
