import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useRef, useState } from 'react'
import { request } from '../api/client'
import { getBlob } from '../api/jobs'
import { queryClient } from '../api/queryClient'
import { revisionArtifactPath, revisionPath, revisionSourcePath, validTextRegion,
  type CopyFields, type RevisionKind, type TextRegion } from '../api/resultRevisionContract'
import { download } from '../lib/download'
import { useObjectUrls } from '../lib/useObjectUrls'
import RevisionCostDetails, { type RevisionCostSummary } from './RevisionCostDetails'

type Revision = {
  edit_id?: string; correction_id?: string; state: string; revision: number
  copy?: {ad_copy: CopyFields}; approved_copy?: CopyFields; copy_sha: string; review_sha: string | null
  preview_sha: string | null; final_sha: string | null; caption_sha: string | null; receipt_sha: string | null
  error_code?: string | null; report?: {passed?: boolean; issues?: Array<{reason?: string}>}
  region?: TextRegion; source_size?: [number, number] | null
  render_mode?: string; edit_prompt_version?: string | null
  artifacts: Partial<Record<'preview' | 'final' | 'caption' | 'receipt', string>>
}
type Snapshot = {
  job_id: string; available: boolean; source_image_sha: string; source_artifact?: string; source_size?: [number, number]
  approved_copy: CopyFields; copy_sha: string; approval_sha: string
  source_copy_sha?: string; source_approval_sha?: string; corrections?: Revision[]; edits?: Revision[]
  cost_summary?: RevisionCostSummary
}
const FIELDS = [['headline', '헤드라인'], ['subline', '서브 문구'], ['cta', 'CTA']] as const
const STATES: Record<string, string> = {
  QUEUED: '오타 영역 수정 대기', RUNNING: '오타 영역 수정 중', QUEUED_REVIEW: '수정 카피 검수 대기',
  COPY_REVIEW_REQUIRED: '수정 카피 승인 필요', IMAGE_REVIEW_REQUIRED: '새 합성본 검수 필요',
  REVIEW_REQUIRED: '수정 이미지 검수 필요', COMPLETED: '수정본 승인 완료', REJECTED: '수정본 거절됨',
  RULE_BLOCKED: '수정 카피 규칙 검수 불합격 · 문구를 바꿔 다시 요청하세요',
  BILLING_UNKNOWN: '요청 과금 확인 필요 · 자동 재호출 중지', HOLD: '안전 확인 보류',
}
const EMPTY_COPY: CopyFields = {headline: '', subline: '', cta: ''}
const EMPTY_REVIEW = {product_matches: false, label_matches: false, cta_policy_matches: false, no_extra_text: false}

function useFile(path: string | undefined, sha: string | null | undefined) {
  const query = useQuery({queryKey: ['revision-artifact', path], enabled: Boolean(path && sha),
    retry: false, staleTime: Infinity, refetchOnWindowFocus: false, queryFn: async () => {
      const blob = await getBlob(path!)
      const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
      const actual = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('')
      if (actual !== sha) throw Error('수정본 파일의 SHA-256이 일치하지 않습니다.')
      return blob
    }})
  const blobs = useMemo(() => query.data ? [query.data] : [], [query.data])
  const [url] = useObjectUrls(blobs)
  return {url, query}
}

export default function ResultRevisionPanel({jobId, mode, canMutate, onCompletedChange, showRequestForm = true}: {
  jobId: string; mode: 'composed' | 'freeform'; canMutate: boolean; onCompletedChange?: (completed: boolean) => void
  showRequestForm?: boolean
}) {
  const [expanded, setExpanded] = useState<boolean | null>(null)
  const kind: RevisionKind = mode === 'freeform' ? 'image-corrections' : 'composed-copy-edits'
  const base = revisionPath(jobId, kind)
  const query = useQuery({queryKey: ['result-revisions', jobId, kind],
    queryFn: () => request<Snapshot>(base), retry: false, refetchInterval: q =>
      [...q.state.data?.corrections ?? [], ...q.state.data?.edits ?? []].some(
        item => ['QUEUED', 'RUNNING', 'QUEUED_REVIEW'].includes(item.state)) ? 2500 : false})
  const completed = [...query.data?.corrections ?? [], ...query.data?.edits ?? []].some(row => row.state === 'COMPLETED')
  const open = expanded ?? completed
  useEffect(() => {onCompletedChange?.(completed)}, [completed, onCompletedChange])
  return <details className="stack" style={{borderTop:'1px solid #ddd',paddingBlock:16}}
    id={`result-revisions-${mode}`} data-testid={`revision-panel-${mode}`} open={open}
    onToggle={event => setExpanded(event.currentTarget.open)}>
    <summary>{showRequestForm ? mode === 'freeform' ? '자유형 오타 부분만 수정 요청' : '합성형 문구 직접 수정'
      : `${mode === 'freeform' ? '자유형' : '합성형'} 수정본 확인·다운로드`}</summary>
    {open && <div className="stack">
      {showRequestForm && <p className="field-hint">{mode === 'freeform'
        ? '교정 방식을 선택하세요. AI 확대 교정은 모델을 1회 호출하며, 원본 획 정밀 교정은 추가 모델 호출 없이 처리합니다. 두 방식 모두 새 수정본을 별도로 검수해야 합니다.'
        : '문구를 직접 고친 뒤 규칙·LLM 검수와 새 카피 승인을 거칩니다. 기존 배경으로 다시 합성하며 이미지 AI는 호출하지 않습니다.'}</p>}
      {query.isPending ? <p role="status">수정 기능 확인 중…</p> : query.isError
        ? <div role="alert"><p>수정 상태를 확인하지 못했습니다.</p><button className="button secondary" onClick={() => void query.refetch()}>상태 다시 확인</button></div>
        : query.data?.available ? <RevisionWorkspace key={`${base}:${query.data.source_image_sha}`}
          snapshot={query.data} kind={kind} base={base} canMutate={canMutate} showRequestForm={showRequestForm}
          refresh={() => queryClient.invalidateQueries({queryKey: ['result-revisions', jobId, kind]})} />
          : <p>현재 서버에서 이 수정 기능을 사용할 수 없습니다.</p>}
    </div>}
  </details>
}

function RevisionWorkspace({snapshot, kind, base, canMutate, refresh, showRequestForm}: {
  snapshot: Snapshot; kind: RevisionKind; base: string; canMutate: boolean; refresh: () => Promise<void>
  showRequestForm: boolean
}) {
  const [copy, setCopy] = useState<CopyFields>(snapshot.approved_copy ?? EMPTY_COPY)
  const [field, setField] = useState<keyof CopyFields>('subline')
  const [observed, setObserved] = useState('')
  // No inferred rectangle: the user deliberately selects an area before a paid call.
  const [region, setRegion] = useState<TextRegion>([0, 0, 0, 0])
  const [paid, setPaid] = useState(false)
  const [localStroke,setLocalStroke]=useState(false)
  const [strokeText,setStrokeText]=useState('[]')
  const strokeBox=useMemo(()=>{try{const v=JSON.parse(strokeText);return Array.isArray(v)&&v.length===4&&v.every(Number.isInteger)?v:null}catch{return null}},[strokeText])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState('')
  const flight = useRef(false)
  const requestKey = useRef<string | null>(null)
  const source = useFile(revisionSourcePath(snapshot.job_id, snapshot.source_artifact, snapshot.source_image_sha), snapshot.source_image_sha)
  const freeform = kind === 'image-corrections'
  const unchanged = FIELDS.every(([key]) => copy[key] === snapshot.approved_copy?.[key])
  const records = snapshot.corrections ?? snapshot.edits ?? []
  const formFingerprint = JSON.stringify(freeform ? {field, observed, region, localStroke, strokeBox} : copy)
  const waiting = records.some(row => ['QUEUED', 'RUNNING', 'QUEUED_REVIEW', 'BILLING_UNKNOWN'].includes(row.state))
  async function submit() {
    if (flight.current || !canMutate || waiting) return
    flight.current = true; setPending(true); setError('')
    requestKey.current ??= crypto.randomUUID().replaceAll('-', '')
    try {
      await request(base, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        expected_image_sha: snapshot.source_image_sha,
        expected_copy_sha: snapshot.source_copy_sha ?? snapshot.copy_sha,
        expected_approval_sha: snapshot.source_approval_sha ?? snapshot.approval_sha,
        request_key: requestKey.current,
        ...(freeform ? {field, observed_text: observed, region, acknowledge_paid_edit: localStroke ? false : paid, ...(localStroke ? {stroke_source_box:strokeBox} : {matte_style_context:true})} : {ad_copy: copy}),
      })})
      requestKey.current = null; setPaid(false); setSubmitted(formFingerprint)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '수정 요청을 저장하지 못했습니다.')
      // Keep the same idempotency key after an uncertain HTTP response.
    } finally {await refresh(); flight.current = false; setPending(false)}
  }
  const review = (row: Revision) => <RevisionReview key={row.correction_id ?? row.edit_id} row={row} base={base}
    kind={kind} jobId={snapshot.job_id} canMutate={canMutate} approvedCopy={snapshot.approved_copy}
    sourceUrl={source.url} sourceSize={snapshot.source_size} cost={snapshot.cost_summary} refresh={refresh} />
  return <div className="stack">
    {records.filter(row => row.state === 'COMPLETED').map(review)}
    {showRequestForm && <>
    {freeform ? <>
      <label>교정 방식<select value={localStroke?'stroke':'model'} onChange={e=>{setLocalStroke(e.target.value==='stroke');setPaid(false)}}>
        <option value="model">AI 글자 분리 교정 · 모델 호출 1회</option><option value="stroke">원본 획 정밀 교정 · 추가 모델 호출 없음</option>
      </select></label>
      {localStroke && <label>기준 획 원본 좌표 [왼쪽, 위, 오른쪽, 아래]<input value={strokeText} onChange={e=>setStrokeText(e.target.value)} spellCheck={false}/>
        <span className="field-hint">ㅈ→ㅊ 초성 교정용입니다. 원본의 짧은 가로 획을 1:1로 복사하며 교정 영역과 크기가 같아야 합니다. 새 글꼴이나 AI 문구를 덧쓰지 않습니다.</span></label>}
      {source.url && <TextAreaSelector src={source.url} region={region} setRegion={setRegion} />}
      {source.query.isError && <div role="alert"><p>수정 영역을 고를 원본 이미지를 가져오지 못했습니다.</p>
        <button className="button secondary" type="button" onClick={() => void source.query.refetch()}>원본 이미지 다시 가져오기</button></div>}
      <label>수정할 문구<select value={field} onChange={e => {setField(e.target.value as keyof CopyFields); setObserved('')}}>
        {FIELDS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
      </select></label>
      <label>이미지에 잘못 표시된 문구<input value={observed} maxLength={600} spellCheck={false}
        placeholder="이미지에서 직접 읽은 문구" onChange={e => setObserved(e.target.value)} /></label>
      <p>수정할 승인 원문: <strong>{snapshot.approved_copy?.[field]}</strong></p>
      <fieldset className="stack"><legend>수정 영역 (%)</legend>
        <p className="field-hint">이미지에서 잘못된 문구를 드래그해 감싸거나 아래 좌표를 입력하세요. 제품과 다른 문구를 포함하지 않도록 좁게 지정합니다.</p>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(2,minmax(0,1fr))', gap: 8}}>
          {['왼쪽', '위', '오른쪽', '아래'].map((name, index) => <label key={name}>{name}
            <input type="number" min={0} max={100} step={0.1} value={Math.round(region[index] * 1000) / 10}
              onChange={e => setRegion(previous => previous.map((n, i) => i === index ? Number(e.target.value) / 100 : n) as TextRegion)} />
          </label>)}
        </div>
        {!validTextRegion(region) && <p className="field-hint">전체 면적의 25% 이하인 사각 영역을 지정해 주세요.</p>}
      </fieldset>
      <label className="consent-label"><input type="checkbox" checked={paid} onChange={e => setPaid(e.target.checked)} />
        <span>{localStroke?'원본 획과 교정 영역을 확인했습니다. 추가 모델 호출 없이 별도 수정본을 만듭니다.':'선택 영역과 승인 원문을 확인했습니다. 이미지 모델 수정 호출 1건을 요청합니다.'}</span></label>
    </> : <>
      {FIELDS.map(([key, label]) => <label key={key}>{label}<textarea rows={key === 'subline' ? 2 : 1}
        maxLength={key === 'headline' ? 100 : 600} value={copy[key]} spellCheck={false}
        onChange={e => setCopy(previous => ({...previous, [key]: e.target.value}))} /></label>)}
      <p className="field-hint">기존 시안과 자유형은 그대로 보존됩니다. 수정본은 새 카피 승인과 이미지 검수 후 저장할 수 있습니다. LLM 검수 호출 1건이 발생합니다.</p>
    </>}
    <button className="button secondary" type="button" onClick={() => void submit()}
      disabled={!canMutate || pending || waiting || submitted === formFingerprint || (freeform
        ? !paid || (localStroke && !strokeBox) || !validTextRegion(region) || !observed.trim() || observed === snapshot.approved_copy?.[field]
        : unchanged || FIELDS.some(([key]) => !copy[key].trim()))}>
      {pending ? '요청 저장 중…' : freeform ? localStroke ? '원본 획으로 비과금 교정' : '이 오타 영역만 수정 요청' : '수정 카피 검수 요청'}
    </button>
    {error && <p className="field-error" role="alert">{error}</p>}
    </>}
    {records.filter(row => row.state !== 'COMPLETED').map(review)}
  </div>
}

function TextAreaSelector({src, region, setRegion}: {src: string; region: TextRegion; setRegion: (region: TextRegion) => void}) {
  const start = useRef<[number, number] | null>(null)
  return <div style={{position: 'relative', touchAction: 'none', width:'100%', maxWidth:560, marginInline:'auto'}}
    onPointerDown={e => {const b = e.currentTarget.getBoundingClientRect(); start.current = [(e.clientX-b.left)/b.width, (e.clientY-b.top)/b.height]; e.currentTarget.setPointerCapture(e.pointerId)}}
    onPointerMove={e => {if (!start.current) return; const b=e.currentTarget.getBoundingClientRect();
      const x=Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)), y=Math.max(0,Math.min(1,(e.clientY-b.top)/b.height));
      setRegion([Math.min(start.current[0],x),Math.min(start.current[1],y),Math.max(start.current[0],x),Math.max(start.current[1],y)])}}
    onPointerUp={() => {start.current=null}} onPointerCancel={() => {start.current=null}}>
    <img className="result-image" src={src} alt="오타 수정 영역을 선택할 원본 · 승인 광고가 아닙니다" draggable={false}
      style={{display:'block', width:'100%', maxWidth:'none', height:'auto', aspectRatio:'auto'}} />
    <div aria-hidden="true" style={{position:'absolute',pointerEvents:'none',border:'2px solid #d63838',background:'#e8383826',
      left:`${region[0]*100}%`,top:`${region[1]*100}%`,width:`${(region[2]-region[0])*100}%`,height:`${(region[3]-region[1])*100}%`}} />
  </div>
}

function RevisionReview({row, base, kind, jobId, canMutate, approvedCopy, sourceUrl, sourceSize, cost, refresh}: {
  row: Revision; base: string; kind: RevisionKind; jobId: string; canMutate: boolean; approvedCopy: CopyFields; refresh: () => Promise<void>
  sourceUrl?: string; sourceSize?: [number, number]; cost?: RevisionCostSummary
}) {
  const id = row.correction_id ?? row.edit_id ?? ''
  const [observed, setObserved] = useState<CopyFields>(EMPTY_COPY)
  const [checks, setChecks] = useState(EMPTY_REVIEW)
  const [ack, setAck] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const complete = row.state === 'COMPLETED'
  const current = !['REJECTED', 'HOLD', 'BILLING_UNKNOWN'].includes(row.state)
  const artifact = (name: 'preview' | 'final' | 'caption' | 'receipt') => revisionArtifactPath(jobId, kind, id, name, row.artifacts?.[name], row[`${name}_sha`])
  const image = useFile(current ? artifact(complete ? 'final' : 'preview') : undefined, complete ? row.final_sha : row.preview_sha)
  const caption = useFile(complete ? artifact('caption') : undefined, row.caption_sha)
  const receipt = useFile(complete ? artifact('receipt') : undefined, row.receipt_sha)
  const copy = row.copy?.ad_copy ?? row.approved_copy ?? approvedCopy
  const reviewed = Object.values(checks).every(Boolean) && FIELDS.every(([field]) => observed[field] === copy?.[field])
  async function mutate(action: string, body: unknown) {
    if (pending || !canMutate) return
    setPending(true); setError('')
    try {await request(`${base}/${id}/${action}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
    catch (cause) {setError(cause instanceof Error ? cause.message : '상태를 저장하지 못했습니다.')}
    finally {await refresh(); setPending(false)}
  }
  const decision = (approve: boolean) => void mutate('decision', {expected_revision:row.revision,
    expected_preview_sha:row.preview_sha,approve,visual_review:{...checks,observed_copy:observed}})
  return <article className={complete ? 'stack' : 'panel stack'} data-testid="result-revision">
    <h4 style={{margin:0}}>{kind === 'image-corrections' ? row.render_mode === 'freeform_source_stroke_corrected_v1' ? '자유형 · 원본 획 정밀 교정본' : row.render_mode === 'freeform_model_matte_corrected_v1' ? '자유형 · AI 글자 분리 교정본' : '자유형 · 텍스트 영역 수정본' : '합성형 · 직접 수정본'}</h4>
    <p role="status">{STATES[row.state] ?? row.state}</p>
    {row.error_code && <p role="alert" style={{overflowWrap:'anywhere'}}>확인 코드: {row.error_code}</p>}
    {image.url && <a href={image.url} target="_blank" rel="noreferrer"><img className="result-image" src={image.url} alt="새 수정본 · 별도 검수 대상" /></a>}
    {kind === 'image-corrections' && image.url && sourceUrl && row.region && (row.source_size ?? sourceSize) &&
      <CorrectionComparison before={sourceUrl} after={image.url} region={row.region} size={(row.source_size ?? sourceSize)!} />}
    <RevisionCostDetails cost={cost} revisionId={id} />
    {row.state === 'COPY_REVIEW_REQUIRED' && <>
      {FIELDS.map(([field,label]) => <p key={field}>{label}: {copy?.[field]}</p>)}
      {row.report?.issues?.map((issue,index) => <p className="field-error" key={index}>{issue.reason}</p>)}
      <label className="consent-label"><input type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)} />
        <span>수정 문구와 검수 근거를 확인했습니다. 이 수정본의 새 카피를 승인합니다.</span></label>
      <button className="button" disabled={!canMutate || pending || !ack || row.report?.passed === false}
        onClick={() => void mutate('copy-approval',{expected_revision:row.revision,expected_copy_sha:row.copy_sha,
          expected_review_sha:row.review_sha,acknowledge_evidence:ack})}>수정 카피 승인 후 합성</button>
    </>}
    {['REVIEW_REQUIRED','IMAGE_REVIEW_REQUIRED'].includes(row.state) && <fieldset className="stack">
      <legend>수정본을 새로 검수해 주세요</legend>
      {([['product_matches','제품 전체 형태와 브랜드가 원본과 일치합니다.'],['label_matches','라벨의 작은 문자까지 판독해 원본과 대조했습니다.'],
        ['cta_policy_matches','CTA가 정확히 한 번 표시되고 제품을 가리지 않습니다.'],['no_extra_text','오탈자·누락·중복·추가 문구가 없습니다.']] as const).map(([key,label]) =>
        <label className="consent-label" key={key}><input type="checkbox" checked={checks[key]}
          onChange={e=>setChecks(previous=>({...previous,[key]:e.target.checked}))} /><span>{label}</span></label>)}
      {FIELDS.map(([field,label]) => <label key={field}>이미지에서 직접 읽은 {label}<input value={observed[field]} spellCheck={false}
        onChange={e=>setObserved(previous=>({...previous,[field]:e.target.value}))} /></label>)}
      <div className="button-row"><button className="button secondary" disabled={!canMutate || pending} onClick={()=>decision(false)}>수정본 거절</button>
        <button className="button" disabled={!canMutate || pending || !image.url || !reviewed} onClick={()=>decision(true)}>수정본 승인</button></div>
    </fieldset>}
    {complete && <div className="button-row">
      <button className="button" disabled={!image.url} onClick={()=>download(image.url!,`ad_${id}.png`)}>수정 PNG 저장</button>
      <button className="button secondary" disabled={!caption.url} onClick={()=>download(caption.url!,`caption_${id}.txt`)}>본문 TXT 저장</button>
      <button className="button secondary" disabled={!receipt.url} onClick={()=>download(receipt.url!,`receipt_${id}.json`)}>Receipt 저장</button>
    </div>}
    {error && <p role="alert" className="field-error">{error}</p>}
  </article>
}

function CorrectionComparison({before, after, region, size}: {
  before: string; after: string; region: TextRegion; size: [number, number]
}) {
  if (!validTextRegion(region) || size.some(n => !Number.isSafeInteger(n) || n < 1)) return null
  const [width, height] = size
  // Show neighbouring strokes as context at the same magnification in both panels.
  const x = Math.max(0, region[0] * width - 32), y = Math.max(0, region[1] * height - 16)
  const w = Math.min(width - x, (region[2] - region[0]) * width + 64)
  const h = Math.min(height - y, (region[3] - region[1]) * height + 32)
  return <section className="stack" aria-label="오타 수정 전후 확대 비교">
    <p className="field-hint">같은 영역을 같은 배율로 비교하세요. 맞춤법 외에도 글씨 크기·굵기·간격과 정보 위계를 확인해야 합니다. 영역 밖 픽셀 보존은 영역 안의 디자인 품질 승인을 대신하지 않습니다.</p>
    <div style={{display:'grid',gridTemplateColumns:'repeat(2,minmax(0,1fr))',gap:8}}>
      {[[before,'수정 전'],[after,'수정 후']].map(([src,label]) => <figure key={label} style={{margin:0,minWidth:0}}>
        <figcaption>{label}</figcaption>
        <svg role="img" aria-label={`${label} 글자 영역 확대`} viewBox={`${x} ${y} ${w} ${h}`}
          style={{display:'block',width:'100%',height:150,border:'1px solid #ddd'}}>
          <image href={src} width={width} height={height} />
        </svg>
      </figure>)}
    </div>
  </section>
}
