import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { restorePrevious, review, reviseJob } from '../api/jobs'
import { advance, resetJob, useBlobQuery, useBlobUrl, useJob, useLiveSnapshot, useLiveProgress } from '../api/useJob'
import {approveImageAndCompose,rejectImage,resumeImageFromApproved,retryCompose,regenerateRejectedImage} from '../api/liveFlow'
import {getLiveSnapshot} from '../api/liveJobs'
import {candidateArtifactPath,isImageReviewHydrated,sameImageCandidate} from '../api/liveMapping'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { download } from '../lib/download'
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
  const mock=useProjectStore(s=>s.mock)
  const {data:live}=useLiveSnapshot()
  const {data:task}=useLiveProgress()
  const reviewing = job?.status === 'IMAGE_REVIEW_REQUIRED'
  const jobImagePath = job && imagePath(job)
  const liveImagePath = live && candidateArtifactPath(live)
  const previewPath = !mock && reviewing && liveImagePath !== jobImagePath ? undefined : jobImagePath
  const imageFile = useBlobQuery(previewPath)
  const imageUrl = useBlobUrl(previewPath)
  // 크기는 불러온 이미지 URL과 같이 저장해, 수정 요청·되돌리기로 이미지가 바뀌면 이전 크기를 쓰지 않는다
  const [loaded, setLoaded] = useState<{ url: string; width: number; height: number }>()
  const size = loaded?.url === imageUrl ? loaded : undefined
  const [revising, setRevising] = useState(false)
  const [instruction, setInstruction] = useState('')

  const reviewReady = reviewing && Boolean(size) && (mock || isImageReviewHydrated(job, live))
  const rejected = job?.status === 'IMAGE_REJECTED'
  const approved = job?.status === 'IMAGE_APPROVED' || job?.status === 'COMPLETED'
  const composeFailed = !mock && live?.state==='IMAGE_APPROVED' && !run.busy
  const products = job?.assets?.filter((a) => a.role === 'product') ?? []
  const generating = task?.state === 'RUNNING' || task?.state === 'QUEUED'

  function sendRevision() {
    if (!jobId || !instruction.trim()) return
    setRevising(false)
    void advance(() => reviseJob(jobId, 'image', instruction.trim()), 'ai/image').then(() => setInstruction(''))
  }

  // 합성 전 생성 이미지만 따로 저장 (svg는 mock 이미지)
  function saveImage() {
    const ext = imageFile.data?.type.includes('svg') ? 'svg' : 'png'
    download(imageUrl!, size ? `image_${size.width}x${size.height}.${ext}` : `image.${ext}`)
  }

  function onImageDecision(approve: boolean) {
    if (!reviewReady || !jobId || run.busy) return
    if(!mock){
      if(!live)return
      void getLiveSnapshot(jobId).then(current=>{
        if(!sameImageCandidate(live,current))
          throw Error('이미지 검토 버전이 변경됐습니다. 최신 이미지를 다시 확인해 주세요.')
        return approve ? approveImageAndCompose(current,()=>navigate('/create/export')) : rejectImage(current)
      }).catch(e=>useProjectStore.getState().setRun({
        error:e instanceof Error?e.message:'이미지 검토 상태를 확인하지 못했습니다.'
      }))
    }else{
      navigate('/create/export')
      void advance(() => review(jobId, 'image', true))
    }
  }

  return (
    <StepPage
      title="이미지 검토"
      description="승인한 카피로 만든 이미지입니다. 제품이 원본 사진과 같은지 확인하고 승인해 주세요."
      wide
      back={BACK}
      actions={composeFailed
        ? <button className="button" onClick={()=>{
            if(live) void retryCompose(live.job_id).then(()=>navigate('/create/export'),()=>{})
          }}>합성만 다시 시도</button>
        : approved
        ? <Link className="button" to="/create/export">다음: 최종 결과</Link>
        : rejected
          ? <div className="button-row">
              {!mock && live?.state==='IMAGE_REJECTED' && <button className="button"
                disabled={run.busy} onClick={()=>void regenerateRejectedImage(live).catch(()=>{})}>
                승인 카피 유지하고 이미지 다시 만들기
              </button>}
              <Link className="button secondary" to="/create/product" onClick={resetJob}>처음부터 다시 시작</Link>
            </div>
          : (
            <div className="button-row">
              {mock
                ? <button className="button secondary" disabled={!reviewing || run.busy} onClick={() => setRevising(true)}>
                    {/* 이미지 수정·되돌리기는 Live API가 아직 없다 (서빙 11/06 답변): mock 전용임을 표시 */}
                    수정 요청 <span className="badge badge-warning">mock</span>
                  </button>
                : <button className="button secondary" disabled={!reviewReady || run.busy}
                    onClick={() => onImageDecision(false)}>
                    이미지 거절
                  </button>}
              <button className="button" disabled={!reviewReady || run.busy}
                onClick={() => onImageDecision(true)}>이 이미지로 광고 완성하기</button>
            </div>
          )}
      actionsNote={<>
        {reviewing && <p className="field-hint">원본 제품·브랜드·라벨 보존을 직접 확인하세요. {mock ? '고칠 점이 있으면 수정 요청으로 다시 만들 수 있습니다.' : '거절하면 자동 유료 재생성은 하지 않습니다.'}</p>}
        {!mock && live && ['COPY_APPROVED','PROMPT_READY'].includes(live.state) &&
        <button type="button" className="button secondary small"
          disabled={run.busy || generating}
          onClick={()=>void resumeImageFromApproved(live.job_id).catch(()=>{})}>
          저장된 승인 상태에서 이미지 생성 진행
        </button>}
      </>}
    >
      {job && <JobBadges job={job} />}
      {!mock && ((live?.template_profile==='A_CENTERED') || Boolean(live?.template_profile?.startsWith('OWNER_IMAGE_SIZE_'))) && <div className="notice notice-warning" role="status">
        <p className="notice-title">제품 보호 영역 미확인 · 수동 검토 필요</p>
        <p>Owner A의 안전 영역은 카피 배치용입니다. 실제 제품·라벨을 보호한다는 의미가 아닙니다.
          원본 사진과 생성 후보를 직접 비교하여 확인해 주세요.</p>
      </div>}
      <RunStatus />
      {composeFailed && <div className="notice notice-warning" role="status">
        <p className="notice-title">이미지는 승인됐고 합성만 남았습니다</p>
        <p>이미지를 다시 만들지 않고 승인된 결과로 합성만 재시도합니다.</p>
      </div>}
      {rejected && (
        <div className="notice notice-warning" role="status">
          <p className="notice-title">이미지를 거절했습니다</p>
          <p>{mock
            ? '현재 Mock에서는 이미지 수정 요청이나 새 광고 만들기를 이용할 수 있습니다.'
            : '이전 승인 카피·분석·리서치·프롬프트를 유지한 채 아래 버튼으로 새 이미지 1장을 명시적으로 생성할 수 있습니다. 유료 생성 여부는 실행 전에 확인하세요.'}</p>
        </div>
      )}

      {!job?.image_candidate && !run.busy && !run.error && !generating && (
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
              ? <img key={imageUrl} className="result-image" src={imageUrl} alt="생성 이미지 (카피 합성 전)"
                  style={size && { aspectRatio: `${size.width} / ${size.height}` }}
                  onLoad={(e) => setLoaded({ url: imageUrl, width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })} />
              : imageFile.isError
                ? <div role="alert">
                    <p>검토할 이미지를 불러오지 못했습니다.</p>
                    <button type="button" className="button secondary small" disabled={imageFile.isFetching}
                      onClick={() => void imageFile.refetch()}>이미지 다시 불러오기</button>
                  </div>
                : <p className="muted" role="status">이미지를 불러오는 중…</p>}
            {imageUrl && (
              <figcaption className="button-row">
                <button type="button" className="button secondary small" onClick={saveImage}>이미지만 저장</button>
                {size && <span className="muted">{size.width}×{size.height}px · 카피 합성 전</span>}
              </figcaption>
            )}
          </figure>

          <aside className="stack">
            {reviewing && revising && (
              <section className="panel" aria-labelledby="revise-image-title">
                <h2 id="revise-image-title" className="panel-title">이미지 수정 요청 <span className="badge badge-warning">mock</span></h2>
                <label className="field">
                  <span className="field-hint">어떻게 바꾸고 싶은지 적어 주세요. AI가 이미지를 다시 만듭니다. 지금 이미지는 이전 버전으로 남습니다.</span>
                  <textarea className="revise-input" rows={7} value={instruction} placeholder="예: 배경을 더 밝게, 제품을 조금 더 크게"
                    onChange={(e) => setInstruction(e.target.value)} />
                </label>
                <div className="button-row">
                  <button type="button" className="button" disabled={!instruction.trim() || run.busy} onClick={sendRevision}>수정 요청 보내기</button>
                  <button type="button" className="button secondary" onClick={() => setRevising(false)}>취소</button>
                </div>
              </section>
            )}
            {mock && reviewing && job.previous_image_candidate && (
              <div className="notice notice-info" role="status">
                <p className="notice-title">수정된 이미지입니다</p>
                <p>마음에 들지 않으면 이전 버전으로 되돌릴 수 있습니다. 다시 누르면 지금 버전으로 돌아옵니다.</p>
                <button type="button" className="button secondary small" disabled={run.busy}
                  onClick={() => void advance(() => restorePrevious(jobId!, 'image'))}>이전 버전으로 되돌리기</button>
              </div>
            )}
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
