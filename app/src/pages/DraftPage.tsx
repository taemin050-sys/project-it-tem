import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { restorePrevious, review, reviseJob } from '../api/jobs'
import { advance, resetJob, useBlob, useBlobUrl, useJob, useLiveSnapshot, useLiveProgress } from '../api/useJob'
import {approveImageAndCompose,rejectImage,resumeImageFromApproved,retryCompose} from '../api/liveFlow'
import {getLiveSnapshot} from '../api/liveJobs'
import Icon from '../components/Icon'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { StepBars } from '../components/Steps'
import { RATIOS } from '../config'
import { download } from '../lib/download'
import { imagePath } from '../lib/pipeline'
import { useProjectStore } from '../store/projectStore'
import type { Asset } from '../types/draft'

const CIRCLED = ['①', '②', '③', '④', '⑤']
const PRESERVATION: Record<string, { label: string; tone: string }> = {
  pending: { label: '검토 전', tone: 'warning' },
  passed: { label: '통과', tone: 'success' },
  failed: { label: '실패', tone: 'danger' },
}

const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`

// 서버에 올라간 원본을 보여준다 (새로고침 뒤에도 같은 사진)
function Original({ jobId, asset, index }: { jobId: string; asset: Asset; index: number }) {
  const url = useBlobUrl(`/api/v1/jobs/${jobId}/assets/${asset.asset_id}`)
  return (
    <li>
      <span>{CIRCLED[index]} 사용자가 업로드한 원본 컷</span>
      <div className="original-frame">
        {url ? <img src={url} alt={`제품 사진 ${index + 1}`} /> : <p className="muted">불러오는 중…</p>}
        <span>입력 원본 #{index + 1}</span>
      </div>
    </li>
  )
}

export default function DraftPage() {
  const navigate = useNavigate()
  const jobId = useProjectStore((s) => s.jobId)
  const run = useProjectStore((s) => s.run)
  const ratio = useProjectStore((s) => s.ratio)
  const { data: job } = useJob()
  const mock=useProjectStore(s=>s.mock)
  const {data:live}=useLiveSnapshot()
  const {data:task}=useLiveProgress()
  const imageUrl = useBlobUrl(job && imagePath(job))
  const imageBlob = useBlob(job && imagePath(job))
  // 크기는 불러온 이미지 URL과 같이 저장해, 수정 요청·되돌리기로 이미지가 바뀌면 이전 크기를 쓰지 않는다
  const [loaded, setLoaded] = useState<{ url: string; width: number; height: number }>()
  const size = loaded?.url === imageUrl ? loaded : undefined
  // 원본 대조 확인도 지금 보이는 이미지에만 유효하다
  const [verifiedFor, setVerifiedFor] = useState<string>()
  const verified = imageUrl !== undefined && verifiedFor === imageUrl
  const [instruction, setInstruction] = useState('')

  const reviewing = job?.status === 'IMAGE_REVIEW_REQUIRED'
  const rejected = job?.status === 'IMAGE_REJECTED'
  const approved = job?.status === 'IMAGE_APPROVED' || job?.status === 'COMPLETED'
  const products = job?.assets?.filter((a) => a.role === 'product') ?? []
  const generating = task?.state === 'RUNNING' || task?.state === 'QUEUED'
  const ext = imageBlob?.type.includes('svg') ? 'svg' : 'png'
  const target = RATIOS[ratio]
  const preservation = job?.image_candidate?.preservation_review

  function sendRevision() {
    if (!jobId || !instruction.trim()) return
    void advance(() => reviseJob(jobId, 'image', instruction.trim()), 'ai/image').then(() => setInstruction(''))
  }

  // 합성 전 생성 이미지만 따로 저장 (svg는 mock 이미지)
  function saveImage() {
    download(imageUrl!, size ? `image_${size.width}x${size.height}.${ext}` : `image.${ext}`)
  }

  function onApprove() {
    // 화면에서 본 이미지(live.image_sha)와 클릭 시점 서버값을 비교하고, 합성까지 성공해야 최종 결과로 이동한다.
    // shortcut: 후보 이미지는 고정 주소(/artifacts/candidate)를 캐시해 그려 sha와 그림이 묶여 있지 않다. Live 이미지 수정이 생기면 주소에 sha를 붙인다
    if(!mock){
      if(!live)return
      void approveImageAndCompose(live,()=>navigate('/create/export')).catch(()=>{})
    }else{
      void advance(() => review(jobId!, 'image', true)).then(() => {
        if (!useProjectStore.getState().run.error) navigate('/create/export')
      })
    }
  }
  // 이미지 승인 뒤 합성만 실패한 상태: 이미지를 다시 만들지 않고 합성만 다시 보낸다
  const composeFailed = !mock && live?.state === 'IMAGE_APPROVED' && !run.busy
  function retry() {
    if (!live) return
    void retryCompose(live.job_id).then(() => navigate('/create/export'), () => {})
  }

  const primary = composeFailed
    ? <button className="button" onClick={retry}>합성만 다시 시도</button>
    : approved
      ? <Link className="button" to="/create/export">다음: 최종 결과<Icon name="arrow_forward" className="icon-forward" /></Link>
      : rejected
        ? <Link className="button" to="/create/product" onClick={resetJob}>제품 정보에서 다시 시작</Link>
        : <button className="button" disabled={!reviewing || !imageUrl || !verified || run.busy || (!mock && !live)} onClick={onApprove}>
            이 이미지로 광고 완성하기<Icon name="arrow_forward" className="icon-forward" />
          </button>

  return (
    <StepPage
      bar="card"
      note={(reviewing && !verified) || (!mock && live && ['COPY_APPROVED','PROMPT_READY'].includes(live.state)) ? <>
        {reviewing && !verified && <p className="field-hint">원본 비교 검증에서 왜곡이 없음을 확인해야 광고를 완성할 수 있습니다.</p>}
        {!mock && live && ['COPY_APPROVED','PROMPT_READY'].includes(live.state) &&
          <button type="button" className="button secondary small" disabled={run.busy || generating}
            onClick={()=>void resumeImageFromApproved(live.job_id).catch(()=>{})}>
            저장된 승인 상태에서 이미지 생성 진행
          </button>}
      </> : undefined}
      actions={
        <div className="action-buttons page-foot" style={{ width: '100%' }}>
          <Link className="button secondary" to="/create/copy"><Icon name="arrow_back" className="label-lg" />이전: 카피 다시 수정</Link>
          {!mock && reviewing && (
            <button className="button home" disabled={run.busy} onClick={() =>
              jobId && void getLiveSnapshot(jobId).then(rejectImage).catch(e=>
                useProjectStore.getState().setRun({error:String(e)}))}>
              <Icon name="block" className="label-lg" />이미지 거절
            </button>
          )}
          {primary}
        </div>
      }
    >
      <section className="head-card">
        <div className="head-row" style={{ marginBottom: 0 }}>
          <div className="card-title">
            <span className="icon-tile secondary"><Icon name="verified" /></span>
            <span>
              <h1 className="headline-md">3단계 : 인스타 비주얼 및 원본 정밀 검토</h1>
              <p className="body-sm text-variant">생성된 인스타그램 피드용 비주얼과 등록 원본 간의 제품 왜곡·식약처 라벨 가독성을 1:1 대조합니다.</p>
            </span>
          </div>
          {job && <JobBadges job={job} />}
        </div>
        <StepBars />
      </section>

      <RunStatus />
      {composeFailed && (
        <div className="state-card" role="status">
          <span className="state-icon"><Icon name="healing" /></span>
          <span className="tag tag-primary">합성 오류 감지</span>
          <h2 className="headline-sm">이미지는 승인됐고 합성만 남았습니다</h2>
          <p className="text-variant">이미지를 다시 만들지 않고, 승인한 이미지·카피 그대로 합성만 다시 요청합니다.</p>
        </div>
      )}
      {rejected && (
        <div className="notice notice-warning" role="status">
          <p className="notice-title">이미지를 거절했습니다</p>
          <p>거절 후 다시 만들기는 아직 지원하지 않습니다. 새로 만들려면 제품 정보에서 다시 시작해 주세요.</p>
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
        <div className="draft-grid">
          <section className="card md" aria-labelledby="image-title">
            <div className="card-head">
              <span className="button-row">
                <span id="image-title" className="tag tag-primary">AI 생성 광고 시안</span>
                <span className="label-lg">{ratio} 인스타그램 {target.desc} 규격 ({target.width} × {target.height})</span>
              </span>
              {imageUrl && <button type="button" className="button tonal small" onClick={saveImage}><Icon name="download" className="label-lg" />이미지만 저장 ({ext.toUpperCase()})</button>}
            </div>
            <div className="img-stage">
              {imageUrl
                ? <img className="result-image" src={imageUrl} alt="생성 이미지 (카피 합성 전)"
                    style={size && { aspectRatio: `${size.width} / ${size.height}` }}
                    onLoad={(e) => setLoaded({ url: imageUrl, width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })} />
                : <p className="muted" role="status" style={{ padding: 24 }}>이미지를 불러오는 중…</p>}
            </div>
            {size && (
              <div className="spec-row">
                <Icon name="photo_size_select_actual" />
                <span><strong>해상도:</strong> {size.width} × {size.height}px</span>
                {imageBlob && <><span className="spec-sep" aria-hidden="true">•</span><span><strong>용량:</strong> {formatSize(imageBlob.size)} {ext.toUpperCase()}</span></>}
                <span className="spec-sep" aria-hidden="true">•</span>
                <span>카피 합성 전 이미지</span>
              </div>
            )}
          </section>

          <aside className="stack">
            <section className="card md" aria-labelledby="originals-title">
              <div className="card-head">
                <span className="button-row">
                  <span id="originals-title" className="tag tag-neutral">원본 비교 검증</span>
                  <span className="label-lg">실제 촬영본 vs 생성물 일치도</span>
                </span>
                <Icon name="fact_check" className="text-secondary" />
              </div>
              {products.length > 0 && (
                <ul className="originals">
                  {products.map((a, i) => <Original key={a.asset_id} jobId={job.job_id} asset={a} index={i} />)}
                </ul>
              )}
              <div className="check-row">
                <span><Icon name="shape_line" />제품 보존 검토</span>
                <span className={`badge badge-${preservation ? PRESERVATION[preservation]?.tone ?? 'neutral' : 'neutral'}`}>
                  {preservation ? PRESERVATION[preservation]?.label ?? preservation : '정보 없음'}
                </span>
              </div>
              <div className="verify-box">
                <span className="verify-title"><Icon name="gavel" />식약처 규정 및 신뢰도 검증 체크</span>
                <p>실제 화장품법 제13조(부당한 표시·광고 행위 등의 금지)에 의거하여, 실제 제품의 용기 형태, 펌프 뚜껑 색상, 라벨 한글 표기 텍스트가 인위적으로 왜곡되거나 훼손되지 않았는지 최종 검수해주세요.</p>
                {reviewing && (
                  <label className="agree">
                    <input type="checkbox" checked={verified} onChange={(e) => setVerifiedFor(e.target.checked ? imageUrl : undefined)} />
                    <span>실물 화장품 패키지와 대조하여 왜곡이 없음을 확인했습니다.</span>
                  </label>
                )}
              </div>
              {mock && reviewing && job.previous_image_candidate && (
                <div className="banner" role="status">
                  <span className="banner-text">
                    <span className="banner-icon"><Icon name="history_toggle_off" /></span>
                    <span><strong>수정된 이미지입니다</strong> — 다시 누르면 지금 버전으로 돌아옵니다.</span>
                  </span>
                  <button type="button" className="button secondary small" disabled={run.busy}
                    onClick={() => void advance(() => restorePrevious(jobId!, 'image'))}>
                    <Icon name="undo" className="label-lg" />이전 버전으로 되돌리기
                  </button>
                </div>
              )}
            </section>

            {/* 이미지 수정은 Live API가 아직 없다 (서빙 11/06 답변): mock에서만 보인다 */}
            {mock && reviewing && (
              <section className="card md" aria-labelledby="revise-image-title">
                <h2 id="revise-image-title" className="card-title label-lg">
                  <Icon name="tune" className="text-secondary" />이미지 즉시 부분 수정 (Fine-Tune) <span className="badge badge-warning">mock</span>
                </h2>
                <p className="body-sm text-variant">배경 빛 방향이나 물방울 수분을 더 추가하고 싶다면 짧게 입력하세요.</p>
                <div className="inline-form">
                  <input aria-labelledby="revise-image-title" value={instruction} placeholder="예: 무지개 프리즘 빛을 우측 상단으로 조금 더 강하게 해줘"
                    onChange={(e) => setInstruction(e.target.value)} />
                  <button type="button" className="button tonal" disabled={!instruction.trim() || run.busy} onClick={sendRevision}>
                    <Icon name="auto_fix_high" className="label-lg" />조정 적용
                  </button>
                </div>
              </section>
            )}
          </aside>
        </div>
      )}
    </StepPage>
  )
}
