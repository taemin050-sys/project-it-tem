import { Link, Navigate, useNavigate } from 'react-router-dom'
import { review } from '../api/jobs'
import { approveCopyAndCreateImage, rejectCopy } from '../api/liveFlow'
import {editLiveCopy,getLiveSnapshot} from '../api/liveJobs'
import {queryClient} from '../api/queryClient'
import { useState, useEffect, useRef } from 'react'
import { advance, resetJob, useJob, useLiveProgress, useLiveSnapshot } from '../api/useJob'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { copyFieldText, splitByIssues } from '../lib/highlight'
import { canApproveCopy } from '../lib/pipeline'
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

// 텍스트·이미지 담당 기준: 공백 포함, 줄바꿈 제외 (서브는 \n으로 최대 2줄)
const charCount = (s: string) => `${Array.from(s.replace(/\n/g, '')).length}자`

export default function CopyPage() {
  const navigate = useNavigate()
  const jobId = useProjectStore((s) => s.jobId)
  const busy = useProjectStore((s) => s.run.busy)
  const { data: job } = useJob()
  const mock=useProjectStore(s=>s.mock)
  const {data:live}=useLiveSnapshot()
  const {data:task}=useLiveProgress()
  const [evidenceAck,setEvidenceAck]=useState(false)
  const [editError,setEditError]=useState('')
  const [saving,setSaving]=useState(false)
  const seenCopy=useRef<string|null>(null)
  const copyFormRef=useRef<HTMLElement|null>(null)
  const approvalInFlight=useRef(false)
  const [draft,setDraft]=useState({headline:'',subline:'',cta:'',caption:'',hashtags:''})
  const [draftDirty,setDraftDirty]=useState(false)
  const [editorHydratedKey,setEditorHydratedKey]=useState<string|null>(null)
  // A server GET may arrive AFTER the review screen has mounted. Until
  // the exact (job, copy SHA) is hydrated, no editing or approval is offered.
  const editorKey=jobId && live?.copy_sha ? jobId+':'+live.copy_sha : null
  const copyConflict=Boolean(draftDirty && editorHydratedKey && editorKey!==editorHydratedKey)
  const editorReady=Boolean(editorKey && editorHydratedKey===editorKey && !copyConflict)
  useEffect(()=>{
    if(!live?.copy || !editorKey || seenCopy.current===editorKey)return
    // Do not erase unsaved text when another session revises the same Job.
    if(draftDirty)return
    seenCopy.current=editorKey
    setDraft({headline:live.copy.ad_copy.headline,subline:live.copy.ad_copy.subline,
      cta:live.copy.ad_copy.cta,caption:live.copy.caption,
      hashtags:live.copy.hashtags.join(' ')})
    setEditorHydratedKey(editorKey)
    setEvidenceAck(false)
  },[live,editorKey,draftDirty])
  function discardDraftAndLoadCurrent(){
    setDraftDirty(false)
    setEditorHydratedKey(null)
    seenCopy.current=null
    setEditError('')
  }

  if (jobId === null && !busy) return <Navigate to="/create/product" replace />

  const analysis = job?.product_analysis
  const copy = job?.copy_output
  const report = job?.compliance_report
  const research = job?.research_result
  const reviewing = job?.status === 'COPY_REVIEW_REQUIRED'
  const rejected = job?.status === 'COPY_REJECTED'
  const approved = job !== undefined && ['COPY_APPROVED', 'IMAGE_REVIEW_REQUIRED', 'IMAGE_APPROVED', 'IMAGE_REJECTED', 'COMPLETED'].includes(job.status)
  // FE Owner #21 requests an explicit confirmation for every Copy approval.
  // Do not render this control until the current Live copy revision has hydrated,
  // otherwise the late GET resets a user's early acknowledgement.
  const canApprove = job !== undefined && canApproveCopy(job) && evidenceAck &&
    (mock || (editorReady && !draftDirty && !copyConflict && !saving &&
      live?.state===job.status && live?.compliance?.passed===job.compliance_report?.passed))

  function onApprove() {
    if(!mock){
      if(!jobId || approvalInFlight.current || !canApprove || !evidenceAck || !editorReady ||
          draftDirty || copyConflict || saving)return
      approvalInFlight.current=true
      // Always read the current server review hash at the click boundary.
      // Stale React Query data cannot silently discard approval clicks.
      void getLiveSnapshot(jobId).then(current=>{
        if(current.copy_sha!==live?.copy_sha || current.review_sha!==live?.review_sha ||
            current.state!=='COPY_REVIEW_REQUIRED' || current.compliance?.passed!==true)
          throw Error('COPY_APPROVAL_SERVER_REVISION_CHANGED')
        navigate('/create/draft')
        return approveCopyAndCreateImage(current,evidenceAck)
      }).catch(e=>useProjectStore.getState().setRun({
        error:e instanceof Error?e.message:'승인 상태 조회 실패. 재호출하지 마세요.'
      })).finally(()=>{approvalInFlight.current=false})
    }else{
      navigate('/create/draft')
      void advance(() => review(jobId!, 'copy', true))
    }
  }
  async function saveLiveCopy(){
    if(!jobId || !job?.copy_output || !editorReady || !draftDirty ||
        copyConflict || saving)return
    // Snapshot the actual visible values synchronously at the save click.
    const submitted={...draft}
    for(const key of ['headline','subline','cta','caption','hashtags'] as const){
      const area=copyFormRef.current?.querySelector<HTMLTextAreaElement>(
        'textarea[data-copy-field="'+key+'"]')
      if(!area) {
        setEditError('COPY_EDIT_VISIBLE_INPUT_UNAVAILABLE')
        return
      }
      submitted[key]=area.value
    }
    setSaving(true);setEditError('')
    try{
      const current=await getLiveSnapshot(jobId)
      if(!current.copy || !current.copy_sha || editorKey!==jobId+':'+current.copy_sha ||
          current.state!=='COPY_REVIEW_REQUIRED')
        throw Error('서버 카피가 변경되었습니다. 미저장 내용을 확인한 뒤 다시 불러와 주세요.')
      const saved=await editLiveCopy(jobId,{...current.copy,
        ad_copy:{headline:submitted.headline,subline:submitted.subline,cta:submitted.cta},
        caption:submitted.caption,hashtags:submitted.hashtags.split(/[\s,]+/).filter(Boolean)})
      queryClient.setQueryData(['live-snapshot',jobId],saved)
      setDraftDirty(false)
      setEditorHydratedKey(null)
      seenCopy.current=null
      await Promise.all([
        queryClient.invalidateQueries({queryKey:['live-snapshot',jobId]}),
        queryClient.invalidateQueries({queryKey:['job',jobId]})
      ])
    }catch(e){setEditError(e instanceof Error?e.message:'카피 수정 실패')}
    finally{setSaving(false)}
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
              <button className="button secondary" disabled={!reviewing || busy} onClick={() => mock
                ? void advance(() => review(jobId!, 'copy', false))
                : jobId && void getLiveSnapshot(jobId).then(rejectCopy).catch(e=>
                    useProjectStore.getState().setRun({error:String(e)}))}>
                카피 거절
              </button>
              <button className="button" disabled={!canApprove || busy} onClick={onApprove}>이 카피로 이미지 만들기</button>
            </div>
          )}
      actionsNote={<>
        {reviewing && job && <ApprovalNote job={job} />}
        {/* Never expose the checkbox before this Job's current copy SHA has
            hydrated; a late copy GET deliberately resets the acknowledgement. */}
        {reviewing && (mock || editorReady) && <label className="field-hint">
          <input type="checkbox" checked={evidenceAck}
            onChange={e=>setEvidenceAck(e.target.checked)}/>
          근거 확인 필요 표현과 제품 정보의 근거를 직접 확인하겠습니다.
          (1차 규칙 검수는 법적 적합성 확정이 아닙니다)
        </label>}
        {!mock && task?.state==='BILLING_UNKNOWN' && <div role="alert" className="notice notice-warning">
          <p>AI 작업의 과금 여부를 확인할 수 없습니다. 자동으로 다시 실행하지 마세요. 담당자 확인 후 진행하세요.</p>
        </div>}
      </>}
    >
      {job && <JobBadges job={job} />}
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
          {!mock && reviewing && !editorReady && !copyConflict &&
            <p role="status">검수 버전과 카피 입력값을 확인하고 있습니다…</p>}
          {!mock && reviewing && copyConflict && <div className="notice notice-warning" role="alert">
            <p>다른 요청에서 카피 버전이 변경되었습니다. 미저장 편집은 자동으로 덮어쓰지 않습니다.</p>
            <button type="button" className="button secondary" onClick={discardDraftAndLoadCurrent}>
              서버의 최신 카피 다시 불러오기
            </button>
          </div>}
          {!mock && reviewing && editorReady && <section className="panel" ref={copyFormRef}>
            <h2 className="panel-title">카피 수정·재검수</h2>
            <p className="field-hint">수정하면 서버에서 새 Revision으로 재검수합니다.
              원문으로 되돌려도 이전 승인은 재활성화되지 않습니다.</p>
            {(['headline','subline','cta','caption','hashtags'] as const).map(k=>
              <label key={k} className="field">
                <span className="copy-label">{k}</span>
                <textarea data-copy-field={k} rows={k==='caption'?3:2} value={draft[k]}
                  disabled={saving}
                  onChange={e=>{
                    const value=e.currentTarget.value
                    setDraft(x=>({...x,[k]:value}))
                    setDraftDirty(true)
                    setEditError('')
                  }}/>
              </label>)}
            <button type="button" className="button secondary"
              disabled={saving||busy||!draftDirty||!job?.copy_output}
              onClick={()=>void saveLiveCopy()}>{saving?'저장 중…':'수정하고 다시 검수'}</button>
            {draftDirty && <p className="field-hint" role="status">
              편집 내용이 아직 검수되지 않았습니다. 저장·재검수 전에는 카피 승인이 불가능합니다.
            </p>}
            {editError&&<p role="alert" className="field-error">{editError}</p>}
          </section>}
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
                        {FIELD_LABELS[field]} {field !== 'hashtags' && <span className="count">{charCount(text)}</span>}
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
      : <p className="field-error">위반 의심 표현이 있어 이 카피는 승인할 수 없습니다. 카피 수정·재생성은 아직 지원하지 않습니다.</p>
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
