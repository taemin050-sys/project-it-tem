import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getBlob } from '../api/jobs'
import { startNewAdLink, useBlobQuery, useBlobUrl, useJob, useLiveSnapshot } from '../api/useJob'
import {retryCompose} from '../api/liveFlow'
import {shareLive,listPublishedLive} from '../api/liveJobs'
import {isPublishedFinal} from '../api/liveMapping'
import {queryClient} from '../api/queryClient'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { CANVAS } from '../config'
import { download } from '../lib/download'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'

// 승인한 카피가 서버 본문 파일에 그대로 들어갔는지 (v0.5는 caption, 레거시는 문구 1개)
const approvedText = (job: Job) => job.copy_output?.caption ?? job.copy_candidate?.text

// 최종 결과: 서버가 합성한 광고 PNG(artifacts/final) + 게시글 본문·해시태그(artifacts/caption)
export default function ExportPage() {
  const run = useProjectStore((s) => s.run)
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
  const finalFile = useBlobQuery(final?.download_url)
  const finalUrl = useBlobUrl(final?.download_url)
  const captionFile = useQuery({
    queryKey: ['text', captionPath],
    queryFn: async () => {
      const blob = await getBlob(captionPath!)
      return { blob, text: await blob.text() }
    },
    enabled: captionPath !== undefined,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  })
  const caption = captionFile.data?.text
  const [size, setSize] = useState<{ width: number; height: number }>()
  const [copied, setCopied] = useState<'idle' | 'done' | 'error'>('idle')

  const ready = job?.status === 'COMPLETED' && finalUrl !== undefined && caption !== undefined
  // Owner #26: 서버에 고정된 Live output_size와 최종 PNG 실제 크기를 대조한다.
  const target = job?.final_output ?? CANVAS
  const sizeOk = size?.width === target.width && size?.height === target.height
  const expected = job && approvedText(job)
  const captionOk = caption !== undefined && expected !== undefined && caption.includes(expected)
  const ext = final?.content_type.includes('svg') ? 'svg' : 'png'

  async function copyPost() {
    try {
      await navigator.clipboard.writeText(caption!)
      setCopied('done')
    } catch {
      setCopied('error')
    }
  }

  function saveCaption() {
    if (!captionFile.data) return
    const url = URL.createObjectURL(captionFile.data.blob)
    download(url, 'caption.txt')
    // 바로 해제하면 일부 브라우저에서 다운로드가 시작되기 전에 끊긴다
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <StepPage
      title="최종 결과"
      description="완성된 광고 이미지와 게시글 본문·해시태그를 확인하고 저장하세요."
      wide
      stickyActions={false}
      back={{ to: '/create/draft', label: '이미지 검토' }}
      actions={
        <div className="button-row">
          {job?.status === 'COMPLETED' && <>
            <Link className="button secondary" to="/" onClick={startNewAdLink}>홈으로</Link>
            <Link className="button secondary" to="/create/product" onClick={startNewAdLink}>새 광고 만들기</Link>
          </>}
          {composeFailed && <button className="button secondary" onClick={() => void retryCompose(live.data!.job_id).catch(() => {})}>합성만 다시 시도</button>}
          <button className="button" disabled={!ready} onClick={() => download(finalUrl!, `ad_${target.width}x${target.height}.${ext}`)}>
            광고 이미지 저장 ({ext.toUpperCase()})
          </button>
        </div>
      }
    >
      {job && <JobBadges job={job} />}
      {!mock && ((live.data?.template_profile==='A_CENTERED') || Boolean(live.data?.template_profile?.startsWith('OWNER_IMAGE_SIZE_')) || Boolean(live.data?.template_profile?.startsWith('BP18_PROVISIONAL_SIZE_'))) && <div className="notice notice-warning" role="status">
        <p className="notice-title">제품 보호·게시 적합성: 수동 검토 필요</p>
        <p>이미지 합성 완료는 제품·브랜드·라벨 보존 검증 PASS가 아닙니다.
          원본 사진과 법률 표시사항을 사람이 확인한 뒤 게시해 주세요.</p>
      </div>}
      <RunStatus />

      {job?.status==='COMPLETED' && (finalFile.isError || captionFile.isError) && (
        <div className="notice notice-danger" role="alert">
          <p className="notice-title">완료된 광고 파일을 불러오지 못했습니다</p>
          <p>완료한 광고와 승인 기록은 서버에 유지됩니다. 아래 버튼은 파일을 GET으로 다시 가져오기만 하며 이미지 생성이나 유료 AI 호출을 재시작하지 않습니다.</p>
          <div className="button-row">
            {finalFile.isError && <button type="button" className="button secondary small"
              disabled={finalFile.isFetching}
              onClick={() => void finalFile.refetch()}>
              {finalFile.isFetching ? '이미지 다시 조회 중…' : '이미지 파일 다시 가져오기'}
            </button>}
            {captionFile.isError && <button type="button" className="button secondary small"
              disabled={captionFile.isFetching}
              onClick={() => void captionFile.refetch()}>
              {captionFile.isFetching ? '본문 다시 조회 중…' : '본문 파일 다시 가져오기'}
            </button>}
          </div>
        </div>
      )}

      {composeFailed && (
        <div className="notice notice-warning" role="status">
          <p className="notice-title">이미지는 승인됐고 합성만 남았습니다</p>
          <p>이미지를 다시 만들지 않고, 승인한 이미지·카피 그대로 합성만 다시 요청합니다.</p>
        </div>
      )}

      {job?.status !== 'COMPLETED' && !run.busy && !run.error && !composeFailed && (
        <div className="empty">
          <p className="empty-title">아직 완성된 광고가 없습니다</p>
          <p>이미지 검토에서 이미지를 승인하면 최종 광고를 만듭니다.</p>
          <Link className="button small" to="/create/draft">이미지 검토로 가기</Link>
        </div>
      )}

      {!mock && ready && <section className="panel">
        <h2 className="panel-title">팀 공동 품질 평가</h2>
        <p>최종 광고 이미지와 Caption만 다른 인증된 팀원과 공유합니다. 원본 제품 사진과 비공개 Job 정보는 공유하지 않습니다.</p>
        <button className="button secondary" type="button" disabled={sharing||alreadyShared||publications.isLoading}
          onClick={()=>void publish()}>{alreadyShared?'공동 평가 공유 완료':
            publications.isLoading?'공유 상태 확인 중…':'최종 광고를 팀원과 공유'}</button>
        {shareError && <p role="alert" className="field-error">{shareError}</p>}
        {alreadyShared && <Link className="button small" to="/team/evaluations">팀 평가 화면</Link>}
      </section>}
      {ready && (
        <div className="export-layout">
          <div className="stack">
            <section className="panel" aria-labelledby="post-title">
              <h2 id="post-title" className="panel-title">게시글 본문·해시태그</h2>
              <p className="post-text">{caption}</p>
              {!captionOk && <p className="field-error">본문 파일에 승인한 카피가 그대로 들어 있지 않습니다. 게시 전에 확인해 주세요.</p>}
              <div className="button-row">
                <button className="button secondary small" onClick={copyPost}>본문 복사</button>
                <button className="button secondary small" onClick={saveCaption}>텍스트 저장 (.txt)</button>
              </div>
              <p className="field-hint" role="status">
                {copied === 'done' ? '✓ 본문과 해시태그를 복사했습니다.' : copied === 'error' ? '복사하지 못했습니다. 텍스트를 직접 선택해 복사해 주세요.' : ''}
              </p>
            </section>

            {job.compliance_report && (
              <section className="panel" aria-labelledby="final-check-title">
                <h2 id="final-check-title" className="panel-title">게시 전 확인</h2>
                {job.compliance_report.checklist.length > 0 && (
                  <ul className="plain-list">{job.compliance_report.checklist.map((c) => <li key={c}>{c}</li>)}</ul>
                )}
                <p className="field-hint panel-footnote">{job.compliance_report.notice}</p>
              </section>
            )}
          </div>

          <aside>
            <figure className="export-preview">
              <img
                className="result-image"
                src={finalUrl}
                alt="최종 광고 이미지"
                style={size && { aspectRatio: `${size.width} / ${size.height}` }}
                onLoad={(e) => setSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
              />
              <figcaption>
                {!size ? '크기 확인 중…' : sizeOk
                  ? `✓ ${size.width}×${size.height}px`
                  : <span className="field-error">크기가 {size.width}×{size.height}px입니다 (기대값 {target.width}×{target.height})</span>}
              </figcaption>
            </figure>
          </aside>
        </div>
      )}
    </StepPage>
  )
}
