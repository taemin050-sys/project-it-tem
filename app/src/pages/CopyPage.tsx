import { Link, Navigate, useNavigate } from 'react-router-dom'
import { restorePrevious, review, reviseJob } from '../api/jobs'
import { approveCopyAndCreateImage, restoreCopy, reviseCopy } from '../api/liveFlow'
import { useState, useRef } from 'react'
import { advance, resetJob, useBlobUrl, useJob, useLiveSnapshot } from '../api/useJob'
import Icon from '../components/Icon'
import JobBadges from '../components/JobBadges'
import RunStatus from '../components/RunStatus'
import StepPage from '../components/StepPage'
import { StepCards } from '../components/Steps'
import { COPY_LIMITS, countChars, overLimits, SUBLINE_LINE_MAX, SUBLINE_MAX_LINES } from '../lib/copyLimits'
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

// 시안 2단계의 카피 칸 이름·아이콘
const FIELD_BOX = {
  headline: { icon: 'title', tone: 'text-primary', label: '메인 헤드라인' },
  subline: { icon: 'subtitles', tone: 'text-secondary', label: '서브 카피' },
  cta: { icon: 'touch_app', tone: 'text-tertiary', label: '인스타그램 프로필/스토리 CTA 버튼 문구' },
  caption: { icon: 'article', tone: 'text-primary', label: '인스타그램 피드 캡션 본문 (Emojis & Formatting)' },
} as const
// 인스타그램 게시글 본문 최대 길이
const CAPTION_MAX = 2200

// 색만으로 구분하지 않도록 배지에는 항상 위험도 글자를 함께 쓴다
const RISK_TONE: Record<RiskLevel, string> = { '위반 의심': 'danger', '근거 확인 필요': 'warning', 정상: 'success' }

// 사실(사용자 입력·검색 결과)과 의견(AI 추론)을 구분해 표시한다 (10/26 결정)
const SOURCE_BADGE: Record<SourceType, { label: string; tone: string }> = {
  '사용자 입력': { label: '사용자 입력', tone: 'neutral' },
  '검색 결과': { label: '검색 결과', tone: 'success' },
  'AI 추론': { label: 'AI 추론·의견', tone: 'warning' },
}

const QUICK_REQUESTS = ['친근한 인스타 말투', '촉촉함 강조', '더 짧고 간결하게']

const BACK = '/create/product'
// 검수 리포트가 있으면 서버 notice를 그대로 쓴다. 이 문구는 리포트가 없는 레거시 mock 카피용 (텍스트 모듈 기본 notice와 같은 문장)
const RESPONSIBILITY = '검수 결과는 참고용이며 법적 판단이 아닙니다. 게시 전 최종 확인 책임은 사용자에게 있습니다.'

// 화면에 보여주는 순서. 해시태그는 공백으로 이어 붙인 한 줄로 보여줘야 위치값이 맞는다
const REVIEW_FIELDS = ['headline', 'subline', 'cta', 'caption', 'hashtags'] as const

const tooltip = (i: ComplianceIssue) =>
  `${i.risk_level}: ${i.category}\n${i.reason}\n대체: ${i.suggestion ?? '삭제 권장'}\n근거: ${i.basis ?? '-'}`

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
  return <span className={n > limit ? 'count over' : 'count'}>{n}자 / {limit}자</span>
}

// 서버에 올라간 첫 번째 제품 사진 (1단계 원본)
function FirstPhoto({ job }: { job: Job }) {
  const asset = job.assets?.find((a) => a.role === 'product')
  const url = useBlobUrl(asset && `/api/v1/jobs/${job.job_id}/assets/${asset.asset_id}`)
  if (!url) return null
  return (
    <div className="photo-strip">
      <img src={url} alt="1단계에서 올린 제품 사진" />
      <span><Icon name="photo_camera" />1단계 업로드 기준 원본 이미지</span>
    </div>
  )
}

export default function CopyPage() {
  const navigate = useNavigate()
  const jobId = useProjectStore((s) => s.jobId)
  const busy = useProjectStore((s) => s.run.busy)
  const { data: job } = useJob()
  const mock=useProjectStore(s=>s.mock)
  const {data:live}=useLiveSnapshot()
  const [evidenceAck,setEvidenceAck]=useState(false)
  const approvalInFlight=useRef(false)
  const [instruction,setInstruction]=useState('')
  // 카피가 바뀌면(수정 요청·되돌리기) 확인 체크를 비운다. Live는 폴링마다 객체가 새로 와서 sha로 비교한다
  const copyKey=mock?JSON.stringify(job?.copy_output??null):live?.copy_sha
  const [seenCopy,setSeenCopy]=useState(copyKey)
  if(seenCopy!==copyKey){setSeenCopy(copyKey);setEvidenceAck(false)}

  if (jobId === null && !busy) return <Navigate to="/create/product" replace />

  const analysis = job?.product_analysis
  const copy = job?.copy_output
  const report = job?.compliance_report
  const research = job?.research_result
  const reviewing = job?.status === 'COPY_REVIEW_REQUIRED'
  const rejected = job?.status === 'COPY_REJECTED'
  const approved = job !== undefined && ['COPY_APPROVED', 'IMAGE_REVIEW_REQUIRED', 'IMAGE_APPROVED', 'IMAGE_REJECTED', 'COMPLETED'].includes(job.status)
  const canApprove = job !== undefined && canApproveCopy(job)
  const overs = copy ? overLimits(copy.ad_copy) : []
  // 되돌릴 이전 카피가 있는지: mock은 Job에, Live는 스냅샷 플래그로 온다
  const canRestore = mock ? job?.previous_copy_output !== undefined : live?.previous_copy_available === true
  const feedback = mock ? undefined : live?.revision_feedback ?? undefined

  // 글자 수를 넘었으면 줄여 달라는 요청을 칩으로 채울 수 있게 한다 (사용자가 기준을 몰라도 바로 보낼 수 있게)
  const quick = overs.length > 0
    ? [`글자 수를 줄여 주세요 (헤드 ${COPY_LIMITS.headline}자 1줄, 서브 ${COPY_LIMITS.subline}자·한 줄 ${SUBLINE_LINE_MAX}자·${SUBLINE_MAX_LINES}줄, CTA ${COPY_LIMITS.cta}자 1줄 이내)`, ...QUICK_REQUESTS]
    : QUICK_REQUESTS
  const addRequest = (text: string) => setInstruction((v) => (v.trim() ? `${v}, ${text}` : text))

  function onApprove() {
    if(!mock){
      if(!live || approvalInFlight.current)return
      approvalInFlight.current=true
      // 화면에서 본 검수본(live)과 클릭 시점 서버값을 비교하고, 승인이 성공한 뒤에만 이동한다. 실패 문구는 RunStatus가 보여준다
      void approveCopyAndCreateImage(live,evidenceAck,()=>navigate('/create/draft'))
        .catch(()=>{}).finally(()=>{approvalInFlight.current=false})
    }else{
      void advance(async () => { const j = await review(jobId!, 'copy', true); navigate('/create/draft'); return j })
    }
  }
  function sendRevision() {
    if (!jobId || !instruction.trim()) return
    const sent = mock
      ? advance(() => reviseJob(jobId, 'copy', instruction.trim()), 'ai/copy-review')
      : reviseCopy(jobId, instruction.trim())
    // 실패 문구는 RunStatus가 보여준다
    void sent.then(() => setInstruction(''), () => {})
  }
  function restore() {
    if (!jobId) return
    void (mock ? advance(() => restorePrevious(jobId, 'copy')) : restoreCopy(jobId)).catch(() => {})
  }

  const header = (
    <section className="head-card">
      <div className="head-row">
        <div className="head-title">
          <span className="tag tag-primary tag-upper">Step 2 of 4</span>
          <h1 className="headline-sm">광고 기획 및 카피 심층 검토</h1>
          {report && <span className="tag tag-tertiary"><Icon name="verified" />자체 검수 완료 (참고용)</span>}
        </div>
        {job && <JobBadges job={job} />}
      </div>
      <StepCards />
    </section>
  )

  if (analysis && !analysis.is_cosmetic) {
    return (
      <StepPage>
        {header}
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
      note={<>
        {reviewing && <label className="agree">
          <input type="checkbox" checked={evidenceAck} onChange={e=>setEvidenceAck(e.target.checked)}/>
          <span><strong>[필수]</strong> 자체 검수 결과(참고용)와 표현 근거를 확인했으며, 최종 광고 책임은 판매자에게 있음을 이해하고 승인합니다.</span>
        </label>}
        {reviewing && job && <ApprovalNote job={job} />}
        {reviewing && overs.length > 0 && <p className="field-error" role="alert">
          글자 수 기준을 넘어 이미지를 만들 수 없습니다: {overs.join(', ')}. AI 카피 수정 요청에서 글자 수 줄이기 요청을 눌러 보내 주세요.</p>}
      </>}
      actions={
        <div className="action-buttons">
          <Link className="button secondary" to={BACK}><Icon name="arrow_back" className="label-lg" />이전 단계</Link>
          {approved
            ? <Link className="button" to="/create/draft">다음: 이미지 검토<Icon name="arrow_forward" className="icon-forward" /></Link>
            : rejected
              ? <Link className="button" to="/create/product" onClick={resetJob}>제품 정보에서 다시 시작</Link>
              : <button className="button" disabled={!canApprove || !evidenceAck || overs.length > 0 || busy || (!mock && !live)} onClick={onApprove}>
                  이 카피로 이미지 만들기<Icon name="arrow_forward" className="icon-forward" />
                </button>}
        </div>
      }
    >
      {header}
      <RunStatus />
      {rejected && (
        <div className="notice notice-warning" role="status">
          <p className="notice-title">카피를 거절했습니다</p>
          <p>거절 후 수정·재승인은 아직 지원하지 않습니다. 새로 만들려면 제품 정보에서 다시 시작해 주세요.</p>
        </div>
      )}
      {job?.copy_candidate && <LegacyCopy job={job} />}

      {copy && report && <>
        {reviewing && (canRestore || feedback) && (
          <div className="banner" role="status">
            <span className="banner-text">
              <span className="banner-icon"><Icon name="history_toggle_off" /></span>
              <span><strong>수정된 카피입니다</strong>{feedback && <> — {feedback.note}{feedback.changed_fields.length > 0 &&
                ` (바뀐 항목: ${feedback.changed_fields.map((f) => FIELD_LABELS[f]).join(', ')})`}</>}</span>
            </span>
            {canRestore && <button type="button" className="button secondary small" disabled={busy} onClick={restore}>
              <Icon name="undo" className="label-lg" />이전 버전으로 되돌리기
            </button>}
          </div>
        )}
        <Diagnosis report={report} />

        <div className="copy-grid">
          <div className="stack">
            <section className="card md" aria-labelledby="copy-title">
              <div className="card-head">
                <div className="card-title">
                  <span className="icon-tile primary"><Icon name="feed" /></span>
                  <span>
                    <h2 id="copy-title" className="headline-sm">생성된 광고 카피 세트</h2>
                    <p className="body-sm text-variant">인스타그램 피드 및 스토리 스폰서드 규격 최적화</p>
                  </span>
                </div>
                <span className="tag tag-neutral">타깃: {copy.plan.target}</span>
              </div>
              {(['headline', 'subline', 'cta', 'caption'] as const).map((field) => {
                const text = copyFieldText(copy, field)!
                const issues = report.issues.filter((x) => x.field === field)
                const box = FIELD_BOX[field]
                const limit = field === 'caption' ? undefined : COPY_LIMITS[field]
                return (
                  <div key={field} className="fbox">
                    <div className="fbox-head">
                      <span className="label-md"><Icon name={box.icon} className={box.tone} />{box.label}</span>
                      {issues.some((i) => i.risk_level === '위반 의심')
                        ? <span className="fbox-warn" style={{ color: 'var(--error)' }}><Icon name="warning" />위반 의심 표현 포함</span>
                        : issues.length > 0 && <span className="fbox-warn text-secondary"><Icon name="info" />근거 확인 필요 표현 포함</span>}
                      {field === 'caption' && <span className="label-md">{countChars(text)} / {CAPTION_MAX.toLocaleString()}자</span>}
                    </div>
                    <p className={`fbox-body ${field}`}>
                      {text ? <Highlighted text={text} issues={issues} /> : <span className="muted">없음</span>}
                    </p>
                    {limit !== undefined && (
                      <div className="fbox-foot"><span>권장 길이: {limit}자 이내</span><CharCount field={field} text={text} /></div>
                    )}
                  </div>
                )
              })}
              <Hashtags text={copyFieldText(copy, 'hashtags') ?? ''} issues={report.issues.filter((x) => x.field === 'hashtags')} />
            </section>

            <section className="card md" aria-labelledby="review-title">
              <div className="card-title">
                <span className="icon-tile error"><Icon name="find_replace" /></span>
                <h2 id="review-title" className="headline-sm">검수에서 표시된 표현과 대체 제안</h2>
              </div>
              {report.issues.length > 0
                ? <ul className="issues">{report.issues.map((r) => <IssueItem key={`${r.field}-${r.start}`} issue={r} />)}</ul>
                : <p className="text-variant">검수에서 표시된 표현이 없습니다.</p>}
              {report.checklist.length > 0 && (
                <div className="checklist">
                  <h3 className="label-lg">게시 전 직접 확인할 것</h3>
                  <ul>{report.checklist.map((c) => <li key={c}>{c}</li>)}</ul>
                </div>
              )}
              <p className="field-hint">{report.notice}</p>
            </section>
          </div>

          <aside className="stack">
            <section className="card md" aria-labelledby="plan-title">
              <div className="card-title">
                <span className="icon-tile tertiary"><Icon name="psychology" /></span>
                <h2 id="plan-title" className="headline-sm">AI 기획 전략 및 근거 데이터</h2>
              </div>
              <ul className="strategy">
                <li><small>01. 캠페인 핵심 콘셉트</small><b>“{copy.plan.concept}”</b></li>
                <li><small>02. 핵심 메시지 (Key Message)</small><b>“{copy.plan.key_message}”</b></li>
                <li><small>03. 타깃 오디언스 프로파일</small><b>{copy.plan.target}</b></li>
                <li><small>04. 비주얼 톤앤매너 (Mood)</small><b>{copy.plan.mood.join(', ') || '없음'}</b><span className="body-sm text-variant">톤: {copy.plan.tone}</span></li>
              </ul>
              {research && <Research research={research} />}
              {job && <FirstPhoto job={job} />}
            </section>

            {reviewing && (
              <section className="card md" aria-labelledby="revise-title">
                <div className="card-title">
                  <span className="icon-tile secondary"><Icon name="draw" /></span>
                  <span>
                    <h2 id="revise-title" className="headline-sm">AI 카피 수정 요청</h2>
                    <p className="body-sm text-variant">원하는 톤이나 추가 소구점을 자유롭게 지시하세요</p>
                  </span>
                </div>
                <div className="field">
                  <textarea className="revise-input" rows={4} aria-labelledby="revise-title" value={instruction}
                    placeholder="예: 좀 더 20대 타깃의 친근한 말투로 바꿔줘, 인스타 릴스용 첫 문장을 더 짧게 다듬어줘"
                    onChange={e=>setInstruction(e.target.value)}/>
                  <div className="quick-chips">
                    {quick.map((q, i) => (
                      <button key={q} type="button" className="quick" onClick={() => addRequest(q)}>
                        + {i === 0 && overs.length > 0 ? '글자 수 줄이기' : q}
                      </button>
                    ))}
                  </div>
                  <p className="field-hint">AI가 카피를 다시 만들고 다시 검수합니다. 지금 카피는 이전 버전으로 남습니다.</p>
                </div>
                <button type="button" className="regen" disabled={!instruction.trim() || busy} onClick={sendRevision}>
                  <Icon name="magic_button" />AI 카피 재생성 요청
                </button>
              </section>
            )}
          </aside>
        </div>
      </>}
    </StepPage>
  )
}

// 위험도 요약은 카피보다 먼저 보여준다 (회의록: 규제 경고 우선)
function Diagnosis({ report }: { report: ComplianceReport }) {
  const danger = report.issues.filter((i) => i.risk_level === '위반 의심').length
  const warning = report.issues.filter((i) => i.risk_level === '근거 확인 필요').length
  const clean = REVIEW_FIELDS.filter((f) => !report.issues.some((i) => i.field === f)).length
  const status = !report.passed
    ? { title: '위반 표현 수정 필요', text: '위반 의심 표현이 있는 카피는 승인할 수 없습니다. 아래 대체 제안을 참고해 주세요.' }
    : warning > 0
      ? { title: '주의 표현 수정 권장', text: '표현을 뒷받침하는 근거가 있는지 확인한 뒤 승인해 주세요.' }
      : { title: '표시된 위험 표현 없음', text: '자동 검수는 모든 위험을 찾아내지 못할 수 있습니다.' }
  return (
    <section className="card md" aria-labelledby="diag-title">
      <div className="diag">
        <div className="diag-text">
          <h2 id="diag-title" className="card-title headline-sm"><Icon name="gavel" className="text-primary" />광고 문구 자체 검수 결과</h2>
          <p className="text-variant">화장품법 제13조 등을 참고한 자체 기준으로 의약품 오인, 절대적 표현, 효능 과장 표현을 찾습니다. 법적 판단이 아니며 모든 위험을 찾지는 못합니다.</p>
          <div className="diag-chips">
            <span className="count-chip danger"><i aria-hidden="true" />위반 의심 {danger}건</span>
            <span className="count-chip warning"><i aria-hidden="true" />근거 확인 필요 {warning}건</span>
            <span className="count-chip ok"><Icon name="check_circle" />표시 없음 {clean}건</span>
          </div>
        </div>
        <div className="diag-status" role={report.passed ? 'status' : 'alert'}>
          <span className="label-sm text-primary tag-upper">검수 상태 (참고용)</span>
          <b className="headline-sm">{status.title}</b>
          <p className="body-sm text-variant">{status.text} {report.notice}</p>
        </div>
      </div>
    </section>
  )
}

function IssueItem({ issue: r }: { issue: ComplianceIssue }) {
  const danger = r.risk_level === '위반 의심'
  return (
    <li className={danger ? 'issue danger' : 'issue warning'}>
      <div className="issue-head">
        <span className="risk-pill"><Icon name={danger ? 'cancel' : 'schedule'} />위험도: {danger ? '높음 (위반 의심)' : `보통 (${r.risk_level})`}</span>
        <span className="issue-meta">{FIELD_LABELS[r.field]}, {r.category}</span>
        {r.auto_fixed && <span className="badge badge-neutral">자동 수정됨</span>}
      </div>
      <div className="compare">
        <div>
          <span className="compare-label before">기존 원본 문구</span>
          <del>“{r.text}”</del>
        </div>
        <div>
          <span className="compare-label after">대체 문구 제안</span>
          {r.suggestion ? <ins>“{r.suggestion}”</ins> : <span className="muted">삭제 권장</span>}
        </div>
      </div>
      <p className="issue-reason">
        <Icon name={danger ? 'policy' : 'verified_user'} />
        <span><strong>{danger ? '검수 사유:' : '실증 요건:'}</strong> {r.reason}{r.basis && ` (근거: ${r.basis})`}</span>
      </p>
    </li>
  )
}

// 해시태그는 알약으로 나눠 보여주고, 검수 표현이 들어 있는 태그는 위험도 색으로 표시한다
function Hashtags({ text, issues }: { text: string; issues: ComplianceIssue[] }) {
  const tags = text.split(/\s+/).filter(Boolean)
  if (tags.length === 0) return null
  return (
    <div>
      <span className="card-title label-md"><Icon name="tag" className="text-secondary" />AI 추천 최적화 해시태그</span>
      <ul className="hashes">
        {tags.map((t, i) => {
          const hit = issues.find((x) => t.includes(x.text) || x.text.includes(t))
          return <li key={`${i}-${t}`} className={hit ? `hash risk-${RISK_TONE[hit.risk_level]}` : 'hash'} title={hit && tooltip(hit)}>{t}</li>
        })}
      </ul>
    </div>
  )
}

function Research({ research }: { research: ResearchResult }) {
  return (
    <div className="stack" style={{ gap: 8 }}>
      <h3 className="label-lg">AI 사전 조사 요약</h3>
      {!research.research_performed && (
        <p className="notice notice-warning">외부 검색을 하지 못해 조사 내용은 모두 AI 추론입니다.</p>
      )}
      <ul className="source-list">
        {research.research.display_summary.map((s) => (
          <li key={s.text}><span className={`badge badge-${SOURCE_BADGE[s.source].tone}`}>{SOURCE_BADGE[s.source].label}</span><span>{s.text}</span></li>
        ))}
      </ul>
      <p className="field-hint">AI 추론·의견은 근거가 확인되지 않은 내용입니다. 참고용으로만 봐 주세요.</p>
      {research.citations.length > 0 && (
        <ul className="plain-list">
          {research.citations.map((c) => (
            <li key={c.url}><a className="text-link" href={c.url} target="_blank" rel="noreferrer">{c.title ?? c.url}</a></li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ApprovalNote({ job }: { job: Job }) {
  const report = job.compliance_report
  if (report) {
    return report.passed
      ? <p className="field-hint">{report.notice}</p>
      : <p className="field-error">위반 의심 표현이 있어 이 카피는 승인할 수 없습니다. AI 카피 수정 요청으로 표현을 고쳐 주세요.</p>
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
      <div className="copy-grid">
        <section className="card md" aria-labelledby="legacy-copy-title">
          <h2 id="legacy-copy-title" className="headline-sm">광고 카피 {copy.mock && <span className="badge badge-warning">mock</span>}</h2>
          <p className="fbox-body headline">{copy.text}</p>
          <p className="field-hint">{copy.disclaimer}</p>
        </section>
        {job.plan && (
          <section className="card md" aria-labelledby="legacy-plan-title">
            <h2 id="legacy-plan-title" className="headline-sm">기획안 {job.plan.mock && <span className="badge badge-warning">mock</span>}</h2>
            <ul className="strategy">
              <li><small>타깃</small><b>{job.plan.audience}</b></li>
              <li><small>방향</small><b>{job.plan.direction}</b></li>
            </ul>
            <p className="field-hint">{job.plan.disclaimer}</p>
          </section>
        )}
      </div>
    </div>
  )
}
