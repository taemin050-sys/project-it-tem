import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { getBlob } from '../api/jobs'
import { useBlobUrl, useJob, useLiveSnapshot } from '../api/useJob'
import {getLivePerformance,shareLive,listPublishedLive} from '../api/liveJobs'
import {retryApprovedComposition} from '../api/liveFlow'
import {isPublishedFinal} from '../api/liveMapping'
import {queryClient} from '../api/queryClient'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { CANVAS } from '../config'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'

function download(href: string, filename: string) {
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
}

// 승인한 카피가 서버 본문 파일에 그대로 들어갔는지 (v0.5는 caption, 레거시는 문구 1개)
const approvedText = (job: Job) => job.copy_output?.caption ?? job.copy_candidate?.text

// 최종 결과: 서버가 합성한 광고 PNG(artifacts/final) + 게시글 본문·해시태그(artifacts/caption)
export default function ExportPage() {
  const run = useProjectStore((s) => s.run)
  const { data: job } = useJob()
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
  const perf=useQuery({
    queryKey:['live-perf',job?.job_id],
    queryFn:()=>getLivePerformance(job!.job_id),
    enabled:!mock && !!job?.job_id,refetchInterval:job?.status==='COMPLETED'?false:3000,
    retry:false
  })
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

  const ready = job?.status === 'COMPLETED' && finalUrl !== undefined && caption !== undefined
  const sizeOk = size?.width === CANVAS.width && size?.height === CANVAS.height
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
    const url = URL.createObjectURL(new Blob([caption!], { type: 'text/plain;charset=utf-8' }))
    download(url, 'caption.txt')
    // 바로 해제하면 일부 브라우저에서 다운로드가 시작되기 전에 끊긴다
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return (
    <StepPage
      title="최종 결과"
      description="완성된 광고 이미지와 게시글 본문·해시태그를 확인하고 저장하세요."
      wide
      back={{ to: '/create/draft', label: '이미지 검토' }}
      actions={
        <button className="button" disabled={!ready} onClick={() => download(finalUrl!, `ad_${CANVAS.width}x${CANVAS.height}.${ext}`)}>
          광고 이미지 저장 ({ext.toUpperCase()})
        </button>
      }
    >
      {job && <JobBadges job={job} />}
      {!mock && live.data?.template_profile==='A_CENTERED' && <div className="notice notice-warning" role="status">
        <p className="notice-title">제품 보호·게시 적합성: 수동 검토 필요</p>
        <p>A 템플릿의 합성 완료는 제품 보호 검증 PASS가 아닙니다.
          원본 제품·라벨·법률 표시사항을 사람 검토 후 게시해 주세요.</p>
      </div>}
      <RunStatus />

      {job?.status !== 'COMPLETED' && !run.busy && !run.error && (
        <div className="empty">
          <p className="empty-title">아직 완성된 광고가 없습니다</p>
          <p>이미지 검토에서 이미지를 승인하면 최종 광고를 만듭니다.</p>
          <Link className="button small" to="/create/draft">이미지 검토로 가기</Link>
        </div>
      )}

      {!mock && live.data?.state==='IMAGE_APPROVED' && <section className="panel">
        <h2 className="panel-title">승인된 이미지 합성 복구</h2>
        <p>승인된 이미지·카피·서버에 저장된 레이아웃만으로 합성을 다시 시도합니다.
          Image AI 추가 호출이나 자동 과금 재시도는 하지 않습니다.</p>
        <button type="button" className="button secondary" disabled={run.busy}
          onClick={()=>void retryApprovedComposition(live.data!.job_id).catch(()=>{})}>
          기존 승인 이미지로 합성 복구
        </button>
      </section>}
      {!mock && perf.data && <section className="panel">
        <h2 className="panel-title">실제 AI 실행 기록</h2>
        <p>비용 정책: {perf.data.application_cost_policy} ·
          프로젝트 전체 사용액: {perf.data.project_spend_status}</p>
        <ul className="plain-list">{perf.data.provider_attempts.map((a,i)=><li key={i}>
          {a.stage} · {a.state} · {a.model||'모델 미확인'} ·
          {a.usage ? JSON.stringify(a.usage) : '사용량 미확인'}
        </li>)}</ul>
        <p className="field-hint">실제 API 기록이며 Mock 처리시간이 아닙니다. 규칙 검수는 법적 적합성 확정이 아닙니다.</p>
      </section>}
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
                onLoad={(e) => setSize({ width: e.currentTarget.naturalWidth, height: e.currentTarget.naturalHeight })}
              />
              <figcaption>
                {!size ? '크기 확인 중…' : sizeOk
                  ? `✓ ${size.width}×${size.height}px (4:5)`
                  : <span className="field-error">크기가 {size.width}×{size.height}px입니다 (기대값 {CANVAS.width}×{CANVAS.height})</span>}
              </figcaption>
            </figure>
          </aside>
        </div>
      )}
    </StepPage>
  )
}
