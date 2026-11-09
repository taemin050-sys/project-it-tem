import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getBlob } from '../api/jobs'
import { startNewAdLink, useBlobUrl, useJob, useLiveSnapshot } from '../api/useJob'
import {retryCompose} from '../api/liveFlow'
import {shareLive,listPublishedLive} from '../api/liveJobs'
import {isPublishedFinal} from '../api/liveMapping'
import {queryClient} from '../api/queryClient'
import Icon from '../components/Icon'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { StepChecks } from '../components/Steps'
import { CANVAS, RATIOS, SERVICE_NAME } from '../config'
import { download } from '../lib/download'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'

// 승인한 카피가 서버 본문 파일에 그대로 들어갔는지 (v0.5는 caption, 레거시는 문구 1개)
const approvedText = (job: Job) => job.copy_output?.caption ?? job.copy_candidate?.text

// 최종 결과: 서버가 합성한 광고 PNG(artifacts/final) + 게시글 본문·해시태그(artifacts/caption)
export default function ExportPage() {
  const run = useProjectStore((s) => s.run)
  const brand = useProjectStore((s) => s.product.brand_name)
  const { data: job } = useJob()
  // 결과까지 끝난 작업을 기억해 둔다: 이후 홈·광고 만들기에서 확인 없이 새 광고로 시작한다 (새로고침 뒤에도 유지)
  const completedId = job?.status === 'COMPLETED' ? job.job_id : null
  useEffect(() => { if (completedId) useProjectStore.getState().setFinishedJob(completedId) }, [completedId])
  const mock=useProjectStore(s=>s.mock)
  const [shared,setShared]=useState(false)
  const [sharing,setSharing]=useState(false)
  const [shareError,setShareError]=useState('')
  const live=useLiveSnapshot()
  const publications=useQuery({
    queryKey:['live-shared-results'],
    queryFn:listPublishedLive,
    enabled:!mock && job?.status==='COMPLETED',
    staleTime:0,retry:false
  })
  const alreadyShared=shared||isPublishedFinal(live.data,publications.data?.jobs??[])
  // 이미지 승인까지 끝났는데 합성만 실패한 상태 (합성 중에는 busy라 숨긴다)
  const composeFailed=!mock && live.data?.state==='IMAGE_APPROVED' && !run.busy
  async function publish(){
    if(!job || job.status!=='COMPLETED')return
    setSharing(true);setShareError('')
    try{
      await shareLive(job.job_id)
      setShared(true)
      await queryClient.invalidateQueries({queryKey:['live-shared-results']})
    }
    catch(e){setShareError(e instanceof Error?e.message:'공유 실패')}
    finally{setSharing(false)}
  }
  const final = job?.artifacts?.final
  const captionPath = job?.artifacts?.caption?.download_url
  const finalUrl = useBlobUrl(final?.download_url)
  const { data: caption } = useQuery({
    queryKey: ['text', captionPath],
    queryFn: async () => (await getBlob(captionPath!)).text(),
    enabled: captionPath !== undefined,
    staleTime: Infinity,
  })
  const [size, setSize] = useState<{ width: number; height: number }>()
  const [copied, setCopied] = useState<'idle' | 'done' | 'error'>('idle')

  const finished = job?.status === 'COMPLETED'
  const ready = finished && finalUrl !== undefined && caption !== undefined
  // 서버가 알려준 최종 크기(mock은 고른 비율, Live는 스냅샷 output_size) 기준으로 확인한다
  const target = job?.final_output ?? CANVAS
  const sizeOk = size?.width === target.width && size?.height === target.height
  const ratioName = Object.entries(RATIOS).find(([, r]) => r.width === target.width && r.height === target.height)?.[0]
  const expected = job && approvedText(job)
  const captionOk = caption !== undefined && expected !== undefined && caption.includes(expected)
  const ext = final?.content_type.includes('svg') ? 'svg' : 'png'
  const handle = brand?.trim() || SERVICE_NAME

  async function copyPost() {
    try {
      await navigator.clipboard.writeText(caption!)
      setCopied('done')
    } catch {
      setCopied('error')
    }
  }

  function saveCaption() {
    const url = URL.createObjectURL(new Blob([caption!], { type: 'text/plain;charset=utf-8' }))
    download(url, 'caption.txt')
    // 바로 해제하면 일부 브라우저에서 다운로드가 시작되기 전에 끊긴다
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <StepPage
      bar="plain"
      actions={
        <div className="page-foot" style={{ width: '100%' }}>
          {finished
            ? <Link className="button home" to="/" onClick={startNewAdLink}><Icon name="home" className="label-lg" />홈으로 이동</Link>
            : <span />}
          <div className="action-buttons">
            <Link className="button secondary" to="/create/draft">이전 (비주얼 검토)</Link>
            {composeFailed && <button className="button secondary" onClick={() => void retryCompose(live.data!.job_id).catch(() => {})}>합성만 다시 시도</button>}
            {finished && <Link className="button" to="/create/product" onClick={startNewAdLink}><Icon name="auto_fix_high" />새 광고 만들기</Link>}
          </div>
        </div>
      }
    >
      <section className="page-head">
        <div>
          <span className="tag tag-primary"><span className="ping" style={{ background: 'var(--primary)' }} aria-hidden="true" />{finished ? '생성 파이프라인 완료' : '생성 파이프라인 진행 중'}</span>
          <h1 className="display">최종 소재 검토 및 배포 {finished && <span aria-hidden="true">✨</span>}</h1>
          {finished && <p>식약처 광고 가이드 준수 검수와 인스타그램 핏 최적화가 완료되었습니다. 소재를 즉시 다운로드하거나 팀원과 공유하세요.</p>}
        </div>
        {job && <JobBadges job={job} />}
      </section>
      <StepChecks finished={finished} />

      <RunStatus />
      {composeFailed && (
        <div className="state-card" role="status">
          <span className="state-icon"><Icon name="healing" /></span>
          <span className="tag tag-primary">합성 오류 감지</span>
          <h2 className="headline-sm">이미지는 승인됐고 합성만 남았습니다</h2>
          <p className="text-variant">이미지를 다시 만들지 않고, 승인한 이미지·카피 그대로 합성만 다시 요청합니다.</p>
        </div>
      )}

      {!finished && !run.busy && !run.error && !composeFailed && (
        <div className="empty">
          <p className="empty-title">아직 완성된 광고가 없습니다</p>
          <p>이미지 검토에서 이미지를 승인하면 최종 광고를 만듭니다.</p>
          <Link className="button small" to="/create/draft">이미지 검토로 가기</Link>
        </div>
      )}

      {ready && (
        <div className="export-grid">
          <section aria-labelledby="visual-title">
            <div className="sec-title">
              <h2 id="visual-title" className="headline-sm">최종 인스타그램 광고 비주얼</h2>
              <span className="tag tag-secondary">FEED {ratioName ?? `${target.width}×${target.height}`}</span>
            </div>
            <div className="stack" style={{ gap: 12 }}>
              <figure className="insta">
                <div className="insta-head">
                  <span className="avatar" aria-hidden="true">{handle.slice(0, 1).toUpperCase()}</span>
                  <span className="insta-name">
                    <b>{handle}<Icon name="verified" /></b>
                    <span>Sponsored · 유료 광고</span>
                  </span>
                </div>
                <img className="result-image" src={finalUrl} alt="최종 광고 이미지"
                  style={size && { aspectRatio: `${size.width} / ${size.height}` }}
                  onLoad={(e) => setSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })} />
                <figcaption className="insta-spec">
                  <span><Icon name="aspect_ratio" />
                    {!size ? '크기 확인 중…' : sizeOk
                      ? `${size.width} x ${size.height}px${ratioName ? ` (${ratioName})` : ''}`
                      : <span className="field-error">크기가 {size.width}×{size.height}px입니다 (기대값 {target.width}×{target.height})</span>}
                  </span>
                  <span><Icon name="high_quality" />{ext.toUpperCase()}</span>
                </figcaption>
              </figure>
              <button className="button block" onClick={() => download(finalUrl!, `ad_${target.width}x${target.height}.${ext}`)}>
                <Icon name="download" />광고 이미지 저장 ({ext.toUpperCase()})
              </button>
            </div>
          </section>

          <div className="stack">
            <section aria-labelledby="post-title">
              <div className="sec-title violet">
                <h2 id="post-title" className="headline-sm">인스타그램 게시글 본문 &amp; 운영 가이드</h2>
              </div>
              <div className="card md">
                <div className="caption-head">
                  <span><Icon name="article" />피드 캡션 최종안</span>
                  <span className="button-row">
                    <button type="button" className="mini" onClick={copyPost}><Icon name="content_copy" />본문 복사</button>
                    <button type="button" className="mini" onClick={saveCaption}><Icon name="download" />텍스트 (.txt)</button>
                  </span>
                </div>
                <p className="caption-body">{caption}</p>
                {!captionOk && <p className="field-error">본문 파일에 승인한 카피가 그대로 들어 있지 않습니다. 게시 전에 확인해 주세요.</p>}
                <p className="field-hint" role="status">
                  {copied === 'done' ? '✓ 본문과 해시태그를 복사했습니다.' : copied === 'error' ? '복사하지 못했습니다. 텍스트를 직접 선택해 복사해 주세요.' : ''}
                </p>
              </div>
            </section>

            {job.compliance_report && (
              <section className="card md" aria-labelledby="final-check-title">
                <h3 id="final-check-title" className="card-title headline-sm"><Icon name="policy" className="text-primary" />게시 전 필수 체크리스트 &amp; 법적 고지</h3>
                {job.compliance_report.checklist.length > 0 && (
                  <ul className="todo-list">
                    {job.compliance_report.checklist.map((c) => (
                      <li key={c}><label><input type="checkbox" />{c}</label></li>
                    ))}
                  </ul>
                )}
                <p className="legal"><Icon name="info" /><span><strong>식약처 화장품 표시·광고 법률 고지:</strong> {job.compliance_report.notice}</span></p>
              </section>
            )}
          </div>
        </div>
      )}

      {!mock && ready && (
        <section className="hub" aria-labelledby="hub-title">
          <div className="hub-text">
            <span className="tag tag-secondary"><Icon name="groups" />Team Hub</span>
            <h3 id="hub-title" className="headline-sm">최종 광고를 팀원과 실시간 공유</h3>
            <p className="text-variant">최종 광고 이미지와 Caption만 다른 인증된 팀원과 공유합니다. 원본 제품 사진과 비공개 Job 정보는 공유하지 않습니다.</p>
            {shareError && <p role="alert" className="field-error">{shareError}</p>}
          </div>
          <div className="button-row">
            <button className="button secondary" type="button" disabled={sharing||alreadyShared||publications.isLoading}
              onClick={()=>void publish()}>{alreadyShared?'공동 평가 공유 완료':
                publications.isLoading?'공유 상태 확인 중…':'최종 광고를 팀원과 공유'}</button>
            {alreadyShared && <Link className="button" to="/team/evaluations">팀 공동 품질 평가로 이동<Icon name="arrow_forward" className="icon-forward" /></Link>}
          </div>
        </section>
      )}
    </StepPage>
  )
}
