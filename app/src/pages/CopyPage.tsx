import { Link, Navigate, useNavigate } from 'react-router-dom'
import { restorePrevious, review, reviseJob } from '../api/jobs'
import { approveCopyAndCreateImage, reviseCopyFromInstruction, restorePreviousLiveCopy } from '../api/liveFlow'
import {getLiveSnapshot,getTextCostEstimate,revalidateLiveReviewPolicy,type TextCostEstimate} from '../api/liveJobs'
import { useState, useRef,useEffect } from 'react'
import { advance, resetJob, useJob, useLiveProgress, useLiveSnapshot } from '../api/useJob'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { COPY_LIMITS, countChars, overLimits, SUBLINE_LINE_MAX, SUBLINE_MAX_LINES } from '../lib/copyLimits'
import { copyFieldText, splitByIssues } from '../lib/highlight'
import { canApproveCopy } from '../lib/pipeline'
import { isCopyReviewHydrated } from '../api/liveMapping'
import { queryClient } from '../api/queryClient'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'
import type { ComplianceIssue, ComplianceReport, CopyField, ResearchResult, RiskLevel, SourceType } from '../types/textSchema'

const FIELD_LABELS: Record<CopyField, string> = {
  product_name: '제품명',
  headline: '헤드라인',
  subline: '서브 문구',
  cta: 'CTA',
  caption: '게시글 본문',
  hashtags: '해시태그',
  user_text: '직접 입력 문구',
}

// 색만으로 구분하지 않도록 배지에는 항상 위험도 글자를 함께 쓴다
const RISK_TONE: Record<RiskLevel, string> = { '위반 의심': 'danger', '근거 확인 필요': 'warning', 정상: 'success' }

// 사실(사용자 입력·검색 결과)과 의견(AI 추론)을 구분해 표시한다 (10/26 결정)
const SOURCE_BADGE: Record<SourceType, { label: string; tone: string }> = {
  '사용자 입력': { label: '사용자 입력', tone: 'neutral' },
  '검색 결과': { label: '검색 결과', tone: 'success' },
  'AI 추론': { label: 'AI 추론·의견', tone: 'warning' },
}

const BACK = { to: '/create/product', label: '제품 정보' }
// 검수 리포트가 있으면 서버 notice를 그대로 쓴다. 이 문구는 리포트가 없는 레거시 mock 카피용 (텍스트 모듈 기본 notice와 같은 문장)
const RESPONSIBILITY = '검수 결과는 참고용이며 법적 판단이 아닙니다. 게시 전 최종 확인 책임은 사용자에게 있습니다.'

// 화면에 보여주는 순서. 해시태그는 공백으로 이어 붙인 한 줄로 보여줘야 위치값이 맞는다
const REVIEW_FIELDS = ['headline', 'subline', 'cta', 'caption', 'hashtags'] as const

const tooltip = (i: ComplianceIssue) =>
  `${i.risk_level} · ${i.category}\n${i.reason}\n대체: ${i.suggestion ?? '삭제 권장'}\n근거: ${i.basis ?? '-'}`

function Highlighted({ text, issues }: { text: string; issues: ComplianceIssue[] }) {
  return (
    <>
      {splitByIssues(text, issues).map((seg, i) =>
        seg.issue
          ? <mark key={i} className={`risk risk-${RISK_TONE[seg.issue.risk_level]}`} title={tooltip(seg.issue)}>{seg.text}</mark>
          : seg.text)}
    </>
  )
}

// 헤드·서브·CTA는 기준 글자 수와 같이 보여주고 넘으면 빨갛게 (공백 포함, 줄바꿈 제외)
function CharCount({ field, text }: { field: string; text: string }) {
  const n = countChars(text)
  const limit = field in COPY_LIMITS ? COPY_LIMITS[field as keyof typeof COPY_LIMITS] : undefined
  if (limit === undefined) return <span className="count">{n}자</span>
  return <span className={n > limit ? 'count over' : 'count'}>{n}/{limit}자</span>
}

export default function CopyPage() {
  const navigate = useNavigate()
  const jobId = useProjectStore((s) => s.jobId)
  const busy = useProjectStore((s) => s.run.busy)
  const { data: job } = useJob()
  const mock=useProjectStore(s=>s.mock)
  const {data:live}=useLiveSnapshot()
  const {data:task}=useLiveProgress()
  const approvalInFlight=useRef(false)
  const revisionInFlight=useRef(false)
  const [revising,setRevising]=useState(false)
  const [instruction,setInstruction]=useState('')
  const [revisionEstimate,setRevisionEstimate]=useState<TextCostEstimate>()
  useEffect(()=>{
    let active=true
    if(!mock && revising){
      void getTextCostEstimate(5,'copy').then(value=>{
        if(active)setRevisionEstimate(value)
      }).catch(()=>{if(active)setRevisionEstimate(undefined)})
    }
    return ()=>{active=false}
  },[mock,revising])
  // An acknowledgement is valid only for the exact published copy revision.
  // Nothing is offered during a late Live GET or unhydrated Job display.
  const copyKey=mock?JSON.stringify(job?.copy_output??null):
    jobId && live?.copy_sha && live?.review_sha && Number.isSafeInteger(live?.generation)
      ? [jobId,live.generation,live.review_sha,live.copy_sha].join(':') : null
  const [ackKey,setAckKey]=useState<string|null>(null)
  // Once a revision/restore is requested, a still-matching *old* pair
  // of React Query caches cannot expose the acknowledgement again.
  const [revisionFence,setRevisionFence]=useState<{
    jobId:string;minGeneration:number
  }|null>(null)
  const minGeneration=revisionFence?.jobId===jobId?revisionFence.minGeneration:0
  const liveReady=mock || isCopyReviewHydrated(job,live,minGeneration)
  const evidenceAck=Boolean(copyKey && ackKey===copyKey && liveReady)

  if (jobId === null && !busy) return <Navigate to="/create/product" replace />

  const analysis = job?.product_analysis
  const copy = job?.copy_output
  const report = job?.compliance_report
  const research = job?.research_result
  const reviewing = job?.status === 'COPY_REVIEW_REQUIRED'
  const rejected = job?.status === 'COPY_REJECTED'
  const approved = job !== undefined && ['COPY_APPROVED', 'IMAGE_REVIEW_REQUIRED', 'IMAGE_APPROVED', 'IMAGE_REJECTED', 'COMPLETED'].includes(job.status)
  const canApprove = job !== undefined && canApproveCopy(job) && liveReady &&
    !(['REVALIDATION_REQUIRED','LEGACY_UNBOUND','BINDING_TAMPERED']
      .includes(live?.review_policy?.status??'CURRENT'))
  const overs = copy ? overLimits(copy.ad_copy) : []
  const captionChars=copy ? countChars(copy.caption):0
  const captionMin=250
  const captionMax=(!mock && live?.emoji_level==='많이')?350:400
  const captionOutOfRange=Boolean(copy && (captionChars<captionMin || captionChars>captionMax))
  const revisionFeedback=(!mock && liveReady)?live?.revision_feedback:null
  const policyMustRevalidate=!mock && live && live.state !== 'COMPLETED' &&
    ['REVALIDATION_REQUIRED','LEGACY_UNBOUND','BINDING_TAMPERED']
      .includes(live.review_policy?.status??'CURRENT')
  const policyBlocked=Boolean(policyMustRevalidate)
  async function resetCurrentReviewQueries(){
    await queryClient.invalidateQueries({queryKey:['live-snapshot',jobId]})
    await queryClient.invalidateQueries({queryKey:['job',jobId]})
  }
  function requestPolicyRevalidation(){
    if(!jobId || !live || busy)return
    void getLiveSnapshot(jobId).then(current=>{
      if(current.generation!==live.generation ||
        current.review_sha!==live.review_sha ||
        current.copy_sha!==live.copy_sha)
        throw Error('POLICY_REVIEW_CHANGED_BEFORE_REVALIDATION')
      return revalidateLiveReviewPolicy(current)
    }).then(()=>{
      setAckKey(null)
      setRevisionFence(null)
      void resetCurrentReviewQueries()
    }).catch(error=>useProjectStore.getState().setRun({
      error:error instanceof Error?error.message:'정책 재검수 실패'
    }))
  }

  // 글자 수를 넘었으면 줄여 달라는 요청을 미리 채워 둔다 (사용자가 기준을 몰라도 바로 보낼 수 있게)
  function openRevision() {
    if (overs.length > 0 && !instruction.trim()) {
      setInstruction(`글자 수를 줄여 주세요 (헤드 ${COPY_LIMITS.headline}자 1줄, 서브 ${COPY_LIMITS.subline}자·한 줄 ${SUBLINE_LINE_MAX}자·${SUBLINE_MAX_LINES}줄, CTA ${COPY_LIMITS.cta}자 1줄 이내)`)
    }
    setRevising(true)
  }

  function onApprove() {
    if(!mock){
      if(!jobId || approvalInFlight.current || !canApprove || !evidenceAck || overs.length>0 || !liveReady)return
      approvalInFlight.current=true
      // Always read the current server review hash at the click boundary.
      // Stale React Query data cannot silently discard approval clicks.
      void getLiveSnapshot(jobId).then(current=>{
        if(current.copy_sha!==live?.copy_sha || current.review_sha!==live?.review_sha ||
           current.generation!==live?.generation ||
           current.state!=='COPY_REVIEW_REQUIRED' || current.compliance?.passed!==true)
          throw Error('COPY_APPROVAL_SERVER_REVISION_CHANGED')
        return approveCopyAndCreateImage(current,evidenceAck,()=>navigate('/create/draft'))
      }).catch(e=>useProjectStore.getState().setRun({
        error:e instanceof Error?e.message:'승인 상태 조회 실패. 재호출하지 마세요.'
      })).finally(()=>{approvalInFlight.current=false})
    }else{
      navigate('/create/draft')
      void advance(() => review(jobId!, 'copy', true))
    }
  }
  function sendRevision() {
    if (!jobId || !instruction.trim() || revisionInFlight.current ||
        (!mock && !liveReady)) return
    if(mock){
      setRevising(false)
      void advance(() => reviseJob(jobId, 'copy', instruction.trim()), 'ai/copy-review')
        .then(()=>setInstruction(''))
      return
    }
    if(!live || !liveReady)return
    const requested=instruction.trim()
    const beforeGeneration=live.generation
    // Use a revision floor before any network request, not only after success.
    setRevisionFence({jobId,minGeneration:beforeGeneration+1})
    revisionInFlight.current=true
    void getLiveSnapshot(jobId).then(current=>{
      if(current.state!=='COPY_REVIEW_REQUIRED' ||
        current.generation!==live.generation ||
        current.review_sha!==live.review_sha || current.copy_sha!==live.copy_sha)
        throw Error('서버 카피가 변경됐습니다. 현재 검수 버전을 다시 확인해 주세요.')
      return reviseCopyFromInstruction(current,requested)
    }).then(()=>{setRevising(false);setInstruction('')})
      .catch(e=>{
        // Clear the fence only if a fresh authoritative read proves that
        // the server did not move to a new generation.
        void getLiveSnapshot(jobId).then(current=>{
          if(current.generation===beforeGeneration)setRevisionFence(null)
        }).catch(()=>{})
        useProjectStore.getState().setRun({
          error:e instanceof Error?e.message:'수정 요청을 처리하지 못했습니다. 자동 재시도하지 않습니다.'
        })
      }).finally(()=>{revisionInFlight.current=false})
  }
  function restoreLivePrevious(){
    if(!jobId || !liveReady || !live?.previous_copy_available ||
       revisionInFlight.current)return
    const beforeGeneration=live.generation
    setRevisionFence({jobId,minGeneration:beforeGeneration+1})
    revisionInFlight.current=true
    void getLiveSnapshot(jobId).then(current=>{
      if(current.generation!==live.generation || current.review_sha!==live.review_sha)
        throw Error('서버 카피 버전이 변경되었습니다.')
      return restorePreviousLiveCopy(current)
    }).then(()=>{setRevising(false);setInstruction('')})
      .catch(e=>{
        void getLiveSnapshot(jobId).then(current=>{
          if(current.generation===beforeGeneration)setRevisionFence(null)
        }).catch(()=>{})
        useProjectStore.getState().setRun({
          error:e instanceof Error?e.message:'이전 버전 복원 실패'
        })
      }).finally(()=>{revisionInFlight.current=false})
  }

  if (analysis && !analysis.is_cosmetic) {
    return (
      <StepPage title="기획·카피 검토" back={BACK}>
        <div className="notice notice-danger" role="alert">
          <p className="notice-title">화장품 사진이 아닌 것 같습니다</p>
          <p>사진 분석에서 화장품을 찾지 못해 다음 단계를 진행하지 않았습니다. 제품이 잘 보이는 사진으로 다시 올려 주세요.</p>
          <Link className="button small" to="/create/product" onClick={resetJob}>사진 다시 올리기</Link>
        </div>
      </StepPage>
    )
  }

  return (
    <StepPage
      title="기획·카피 검토"
      description="AI가 조사한 내용과 광고 카피, 표현 검수 결과를 확인하고 카피를 승인해 주세요."
      wide
      back={BACK}
      actions={approved
        ? <Link className="button" to="/create/draft">다음: 이미지 검토</Link>
        : rejected
          ? <Link className="button" to="/create/product" onClick={resetJob}>제품 정보에서 다시 시작</Link>
          : (
            <div className="button-row">
              <button className="button secondary" disabled={!reviewing || busy || !liveReady || policyBlocked} onClick={openRevision}>수정 요청</button>
              <button className="button" disabled={!canApprove || !evidenceAck || overs.length > 0 || busy || policyBlocked} onClick={onApprove}>이 카피로 이미지 만들기</button>
            </div>
          )}
      actionsNote={<>
        {policyBlocked && <div className="notice notice-warning" role="alert">
          <strong>카피 검수 정책이 변경되었거나 정책 결속이 확인되지 않았습니다.</strong>
          <p>기존 승인·이미지 생성은 차단됩니다. 정책 재검수는 현재 원문 카피를 바꾸지 않고 새 검수 버전으로 시작하며, 이전 승인을 복구하지 않습니다.</p>
          <button type="button" className="button secondary small" disabled={busy}
            onClick={requestPolicyRevalidation}>현재 정책으로 재검수</button>
        </div>}
        {reviewing && job && <ApprovalNote job={job} />}
        {reviewing && overs.length > 0 && <p className="field-error" role="alert">
          글자 수 기준을 넘어 이미지를 만들 수 없습니다: {overs.join(', ')}.
          수정 요청에서 짧은 카피를 요청해 주세요.</p>}
        {reviewing && captionOutOfRange && <p className="field-hint" role="status">
          게시글 본문 {captionChars}자 · Text Owner 권장 범위
          {' '}{captionMin}~{captionMax}자입니다.
          권장 길이와 다르면 수정 요청으로 보완할 수 있습니다.
          이 길이 안내 자체가 법적 검수 결과나 승인 차단은 아닙니다.
        </p>}
        {reviewing && !liveReady && !mock && <p role="status" className="field-hint">
          현재 카피·검수 버전을 동기화하고 있습니다. 확인·승인 전에 잠시 상태를 확인해 주세요.
        </p>}
        {reviewing && liveReady && <label className="field-hint">
          <input type="checkbox" checked={evidenceAck}
            onChange={e=>setAckKey(e.target.checked?copyKey:null)}/>
          근거 확인 필요 표현과 제품 정보의 근거를 직접 확인하겠습니다.
          (1차 규칙 검수는 법적 적합성 확정이 아닙니다)
        </label>}
        {!mock && task?.state==='BILLING_UNKNOWN' && <p role="alert" className="notice notice-warning">
          AI 작업의 과금 여부가 불확실합니다. 재호출하지 말고 담당자에게 확인하세요.
        </p>}
      </>}
    >
      {job && <JobBadges job={job} />}
      {revisionFeedback && <div className="notice" role="status">
        <strong>텍스트 AI 수정 요청 결과</strong>
        <p>변경된 항목: {revisionFeedback.changed_fields.length
          ? revisionFeedback.changed_fields.map((f) => FIELD_LABELS[f as CopyField] ?? f).join(', ') : '수정된 항목 없음'}</p>
        {revisionFeedback.note && <p>{revisionFeedback.note}</p>}
        <p>새 검수 버전의 승인·근거 확인은 다시 진행해야 합니다.</p>
      </div>}
      <RunStatus />
      {rejected && (
        <div className="notice notice-warning" role="status">
          <p className="notice-title">카피를 거절했습니다</p>
          <p>거절 후 수정·재승인은 아직 지원하지 않습니다. 새로 만들려면 제품 정보에서 다시 시작해 주세요.</p>
        </div>
      )}
      {job?.copy_candidate && <LegacyCopy job={job} />}

      {copy && report && (
        <div className="stack">
          {reviewing && revising && <section className="panel" aria-labelledby="revise-title">
            <h2 id="revise-title" className="panel-title">수정 요청</h2>
            <label className="field">
              <span className="field-hint">어떻게 바꾸고 싶은지 적어 주세요. AI가 카피를 다시 만들고 다시 검수합니다. 지금 카피는 이전 버전으로 남습니다.</span>
              <textarea rows={3} maxLength={300} value={instruction} placeholder="예: 헤드라인을 더 짧고 산뜻하게, 할인 이벤트 느낌으로"
                onChange={e=>setInstruction(e.target.value)}/>
            </label>
            {!mock && <p className="field-hint" role="status">
              QA Fixture는 유료 모델을 호출하지 않습니다.
              실제 Text Owner v0.10 수정은 관리자가 승인한 Live Worker에서만 실행됩니다.
              {revisionEstimate
                ? <> 텍스트 수정 1회 예상 비용: <strong>{revisionEstimate.display}</strong>.</>
                : ' 텍스트 수정 예상 비용을 확인 중이거나 조회할 수 없습니다.'}
              {' '}추정액은 이미지 재생성 비용이나 실제 청구 금액이 아닙니다.
            </p>}
            <div className="button-row">
              <button type="button" className="button"
                disabled={!instruction.trim() || busy || (!mock && !liveReady)}
                onClick={sendRevision}>수정 요청 보내기</button>
              <button type="button" className="button secondary" onClick={()=>setRevising(false)}>취소</button>
            </div>
          </section>}
          {!mock && reviewing && live?.previous_copy_available && <div className="notice notice-info" role="status">
            <p className="notice-title">이전 카피 버전이 보존돼 있습니다</p>
            <p>되돌리면 새 Generation으로 재검수하며 과거 승인·확인은 재활성화되지 않습니다.</p>
            <button type="button" className="button secondary small"
              disabled={busy || !liveReady || policyBlocked} onClick={restoreLivePrevious}>이전 버전으로 되돌리기</button>
          </div>}
          {mock && reviewing && job?.previous_copy_output && <div className="notice notice-info" role="status">
            <p className="notice-title">수정된 카피입니다</p>
            <p>마음에 들지 않으면 이전 버전으로 되돌릴 수 있습니다. 다시 누르면 지금 버전으로 돌아옵니다.</p>
            <button type="button" className="button secondary small" disabled={busy}
              onClick={()=>void advance(()=>restorePrevious(jobId!,'copy'))}>이전 버전으로 되돌리기</button>
          </div>}
          <ReviewSummary report={report} />

          <div className="copy-layout">
            <div className="stack">
              <section className="panel" aria-labelledby="copy-title">
                <div className="panel-head">
                  <h2 id="copy-title" className="panel-title">광고 카피</h2>
                  <span className="panel-meta">톤 · {copy.plan.tone}</span>
                </div>
                <p className="field-hint">표시된 표현에 마우스를 올리면 이유·대체 문구가 보입니다. 전체 목록은 아래 표현 검수에 있습니다.</p>
                {REVIEW_FIELDS.map((field) => {
                  const text = copyFieldText(copy, field)!
                  return (
                    <div key={field} className="copy-field">
                      <span className="copy-label">
                        {FIELD_LABELS[field]} {field !== 'hashtags' && <CharCount field={field} text={text} />}
                      </span>
                      <p className={`copy-${field}`}>
                        {text
                          ? <Highlighted text={text} issues={report.issues.filter((x) => x.field === field)} />
                          : <span className="muted">없음</span>}
                      </p>
                    </div>
                  )
                })}
              </section>

              <section className="panel" aria-labelledby="review-title">
                <div className="panel-head">
                  <h2 id="review-title" className="panel-title">표현 검수</h2>
                  <span className="panel-meta">참고용</span>
                </div>
                {report.issues.length > 0
                  ? (
                    <ul className="issues">
                      {report.issues.map((r) => (
                        <li key={`${r.field}-${r.start}`} className={`issue issue-${RISK_TONE[r.risk_level]}`}>
                          <div className="issue-head">
                            <span className={`badge badge-${RISK_TONE[r.risk_level]}`}>{r.risk_level}</span>
                            <span className="issue-where">{FIELD_LABELS[r.field]} · {r.category}</span>
                            {r.auto_fixed && <span className="badge badge-neutral">자동 수정됨</span>}
                          </div>
                          <div className="compare">
                            <div>
                              <span className="compare-label">원문</span>
                              <del>{r.text}</del>
                            </div>
                            <div>
                              <span className="compare-label">대체 제안</span>
                              {r.suggestion ? <ins>{r.suggestion}</ins> : <span className="muted">삭제 권장</span>}
                            </div>
                          </div>
                          <p className="issue-reason">{r.reason}</p>
                          {r.basis && <p className="field-hint">근거: {r.basis}</p>}
                        </li>
                      ))}
                    </ul>
                  )
                  : <p className="muted">검수에서 표시된 표현이 없습니다.</p>}
                {report.checklist.length > 0 && (
                  <div className="checklist">
                    <h3 className="group-label">게시 전 직접 확인할 것</h3>
                    <ul>{report.checklist.map((c) => <li key={c}>{c}</li>)}</ul>
                  </div>
                )}
                <p className="field-hint panel-footnote">{report.notice}</p>
              </section>
            </div>

            <aside className="stack">
              {research && <ResearchPanel research={research} />}
              <section className="panel" aria-labelledby="plan-title">
                <h2 id="plan-title" className="panel-title">AI 기획안</h2>
                <div className="plan-key">
                  <span className="copy-label">콘셉트</span>
                  <p className="plan-strong">{copy.plan.concept}</p>
                  <span className="copy-label">핵심 메시지</span>
                  <p className="plan-strong">{copy.plan.key_message}</p>
                </div>
                <dl className="info-list">
                  <dt>타깃</dt><dd>{copy.plan.target}</dd>
                  <dt>무드</dt><dd>{copy.plan.mood.join(', ') || '없음'}</dd>
                </dl>
              </section>
            </aside>
          </div>
        </div>
      )}
    </StepPage>
  )
}

function ApprovalNote({ job }: { job: Job }) {
  const report = job.compliance_report
  if (report) {
    return report.passed
      ? <p className="field-hint">{report.notice}</p>
      : <p className="field-error">위반 의심 표현이 있어 이 카피는 승인할 수 없습니다. 수정하기로 표현을 고쳐 주세요.</p>
  }
  return canApproveCopy(job)
    ? <p className="field-hint">mock 카피는 규제 검수 없이 흐름 확인용으로만 승인할 수 있습니다. 실제 광고에 쓰지 마세요.</p>
    : <p className="field-error">규제 검수 결과가 없어 이 카피는 승인할 수 없습니다.</p>
}

// 레거시 서버(mock/plan·mock/copy) 결과: 구조 없는 문구 1개, 실제 조사·규제 검수 없음
function LegacyCopy({ job }: { job: Job }) {
  const copy = job.copy_candidate!
  return (
    <div className="stack">
      {!copy.compliance_checked && (
        <div className="notice notice-warning">
          <p className="notice-title">규제 검수를 하지 않은 카피입니다</p>
          <p>{RESPONSIBILITY}</p>
        </div>
      )}
      <div className="copy-layout">
        <section className="panel" aria-labelledby="legacy-copy-title">
          <h2 id="legacy-copy-title" className="panel-title">광고 카피 {copy.mock && <span className="badge badge-warning">mock</span>}</h2>
          <p className="copy-headline">{copy.text}</p>
          <p className="field-hint panel-footnote">{copy.disclaimer}</p>
        </section>
        {job.plan && (
          <section className="panel" aria-labelledby="legacy-plan-title">
            <h2 id="legacy-plan-title" className="panel-title">기획안 {job.plan.mock && <span className="badge badge-warning">mock</span>}</h2>
            <dl className="info-list">
              <dt>타깃</dt><dd>{job.plan.audience}</dd>
              <dt>방향</dt><dd>{job.plan.direction}</dd>
            </dl>
            <p className="field-hint panel-footnote">{job.plan.disclaimer}</p>
          </section>
        )}
      </div>
    </div>
  )
}

// 위험도 요약은 카피보다 먼저 보여준다 (회의록: 규제 경고 우선)
function ReviewSummary({ report }: { report: ComplianceReport }) {
  const danger = report.issues.filter((i) => i.risk_level === '위반 의심').length
  const warning = report.issues.filter((i) => i.risk_level === '근거 확인 필요').length
  if (!report.passed) {
    return (
      <div className="notice notice-danger" role="alert">
        <p className="notice-title">위반 의심 표현 {danger}건{warning > 0 && ` · 근거 확인 필요 ${warning}건`}</p>
        <p>위반 의심 표현이 있는 카피는 승인할 수 없습니다. 아래 대체 제안을 참고해 주세요.</p>
        <p>{report.notice}</p>
      </div>
    )
  }
  if (warning > 0) {
    return (
      <div className="notice notice-warning">
        <p className="notice-title">근거 확인이 필요한 표현 {warning}건</p>
        <p>표현을 뒷받침하는 근거가 있는지 확인한 뒤 승인해 주세요.</p>
        <p>{report.notice}</p>
      </div>
    )
  }
  return (
    <div className="notice notice-success">
      <p className="notice-title">✓ 검수에서 주의할 표현을 찾지 못했습니다</p>
      <p>자동 검수는 모든 위험을 찾아내지 못할 수 있습니다. {report.notice}</p>
    </div>
  )
}

function ResearchPanel({ research }: { research: ResearchResult }) {
  return (
    <section className="panel" aria-labelledby="research-title">
      <h2 id="research-title" className="panel-title">AI 사전 조사 요약</h2>
      {!research.research_performed && (
        <p className="notice notice-warning">외부 검색을 하지 못해 조사 내용은 모두 AI 추론입니다.</p>
      )}
      <ul className="plain-list summary-list">
        {research.research.display_summary.map((s) => (
          <li key={s.text}>
            <span className={`badge badge-${SOURCE_BADGE[s.source].tone}`}>{SOURCE_BADGE[s.source].label}</span> {s.text}
          </li>
        ))}
      </ul>
      <p className="field-hint">AI 추론·의견은 근거가 확인되지 않은 내용입니다. 참고용으로만 봐 주세요.</p>
      {research.citations.length > 0 && (
        <div className="source-group">
          <h3 className="group-label">검색 출처</h3>
          <ul className="plain-list">
            {research.citations.map((c) => (
              <li key={c.url}><a className="text-link" href={c.url} target="_blank" rel="noreferrer">{c.title ?? c.url}</a></li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
