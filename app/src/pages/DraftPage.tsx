import { Link, useNavigate } from 'react-router-dom'
import { review } from '../api/jobs'
import { advance, useBlobUrl, useJob } from '../api/useJob'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { imagePath } from '../lib/pipeline'
import { useProjectStore } from '../store/projectStore'
import type { Asset } from '../types/draft'

const BACK = { to: '/create/copy', label: '기획·카피 검토' }

// 서버에 올라간 원본을 보여준다 (새로고침 뒤에도 같은 사진)
function AssetThumb({ jobId, asset, index }: { jobId: string; asset: Asset; index: number }) {
  const url = useBlobUrl(`/api/v1/jobs/${jobId}/assets/${asset.asset_id}`)
  return <li>{url ? <img src={url} alt={`제품 사진 ${index + 1}`} /> : <span className="muted">불러오는 중…</span>}</li>
}

export default function DraftPage() {
  const navigate = useNavigate()
  const jobId = useProjectStore((s) => s.jobId)
  const run = useProjectStore((s) => s.run)
  const { data: job } = useJob()
  const imageUrl = useBlobUrl(job && imagePath(job))

  const reviewing = job?.status === 'IMAGE_REVIEW_REQUIRED'
  const rejected = job?.status === 'IMAGE_REJECTED'
  const approved = job?.status === 'IMAGE_APPROVED' || job?.status === 'COMPLETED'
  const products = job?.assets?.filter((a) => a.role === 'product') ?? []

  function onApprove() {
    navigate('/create/export')
    void advance(() => review(jobId!, 'image', true))
  }

  return (
    <StepPage
      title="이미지 검토"
      description="승인한 카피로 만든 이미지입니다. 제품이 원본 사진과 같은지 확인하고 승인해 주세요."
      wide
      back={BACK}
      actions={approved
        ? <Link className="button" to="/create/export">다음: 최종 결과</Link>
        : rejected
          ? <Link className="button" to="/create/product">제품 정보에서 다시 시작</Link>
          : (
            <div className="button-row">
              <button className="button secondary" disabled={!reviewing || run.busy} onClick={() => advance(() => review(jobId!, 'image', false))}>
                이미지 거절
              </button>
              <button className="button" disabled={!reviewing || !imageUrl || run.busy} onClick={onApprove}>이 이미지로 광고 완성하기</button>
            </div>
          )}
      actionsNote={reviewing && <p className="field-hint">이미지 다시 만들기·부분 수정은 아직 지원하지 않습니다.</p>}
    >
      {job && <JobBadges job={job} />}
      <RunStatus />
      {rejected && (
        <div className="notice notice-warning" role="status">
          <p className="notice-title">이미지를 거절했습니다</p>
          <p>거절 후 다시 만들기는 아직 지원하지 않습니다. 새로 만들려면 제품 정보에서 다시 시작해 주세요.</p>
        </div>
      )}

      {!job?.image_candidate && !run.busy && !run.error && (
        <div className="empty">
          <p className="empty-title">아직 만든 이미지가 없습니다</p>
          <p>기획·카피 검토에서 카피를 승인하면 이미지를 만듭니다.</p>
          <Link className="button small" to="/create/copy">카피 검토로 가기</Link>
        </div>
      )}

      {job?.image_candidate && (
        <div className="draft-layout">
          <figure className="draft-stage">
            {imageUrl
              ? <img className="result-image" src={imageUrl} alt="생성 이미지 (카피 합성 전)" />
              : <p className="muted" role="status">이미지를 불러오는 중…</p>}
          </figure>

          <aside className="stack">
            <div className="notice notice-warning">
              <p className="notice-title">제품을 직접 확인해 주세요</p>
              <p>AI가 만든 이미지라 제품 모양·색·라벨 글자가 원본과 다를 수 있습니다.</p>
            </div>

            {products.length > 0 && (
              <section className="panel" aria-labelledby="originals-title">
                <h2 id="originals-title" className="panel-title">올린 제품 사진</h2>
                <ul className="compare-thumbs">
                  {products.map((a, i) => <AssetThumb key={a.asset_id} jobId={job.job_id} asset={a} index={i} />)}
                </ul>
              </section>
            )}
          </aside>
        </div>
      )}
    </StepPage>
  )
}
