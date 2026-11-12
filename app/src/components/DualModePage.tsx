import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { dualArtifactPath, matchesDualImageSize, type DualArtifactKind } from '../api/dualArtifacts'
import { canResumeDualJob, decideDualVariant, dualQueryKey, getDualJob, resumeDualJob, selectDualVariant,
  snapshotDualProvenance, type DualMode, type DualSnapshot, type DualVariant, type DualCost } from '../api/dualJobs'
import { getBlob, getJob } from '../api/jobs'
import type { AdCopy } from '../types/textSchema'
import type { LiveSnapshot } from '../api/liveMapping'
import { queryClient } from '../api/queryClient'
import { startNewAdLink } from '../api/useJob'
import { DUAL_QA, RATIOS } from '../config'
import { download } from '../lib/download'
import { useObjectUrls } from '../lib/useObjectUrls'
import { useProjectStore } from '../store/projectStore'
import AssetThumb from './AssetThumb'
import DerivedArtifactPanel from './DerivedArtifactPanel'
import ResultRevisionPanel from './ResultRevisionPanel'
import RevisionResultLinks from './RevisionResultLinks'
import { derivedQueryKey } from '../api/derivedJobs'
import StepPage from './StepPage'

type Stage = 'draft' | 'export'
const MODES = ['composed', 'freeform'] as const
const FinalInpaintingPanel = lazy(() => import('./FinalInpaintingPanel'))
const LABELS = {composed: '시안 A · 합성형 (Composed)', freeform: '시안 B · 자유형 (Freeform)'}
const GROUP_STATUS: Record<DualSnapshot['state'], string> = {
  READY: '카피 승인 대기', GENERATING: '두 시안 준비 중', REVIEW_REQUIRED: '시안 검토 필요',
  HOLD: '안전 확인 보류', PARTIAL: '부분 완료', COMPLETED: '두 시안 완료', FAILED: '완성된 시안 없음',
}
const VARIANT_STATUS: Partial<Record<DualVariant['state'], string>> = {
  IMAGE_REVIEW_REQUIRED: '이미지 검토 필요', IMAGE_APPROVED: '이미지 승인됨 · 파일 준비 중',
  HOLD: '생성 안전 확인 보류', IMAGE_REJECTED: '이미지 거절됨', COMPLETED: '완료 · 이미지 검수 기록 있음', FAILED: '시안 준비 실패',
}

function useVerifiedArtifact(path: string | undefined, sha: string | null | undefined, readText = false) {
  const query = useQuery({
    queryKey: ['dual-artifact', path],
    queryFn: async () => {
      const blob = await getBlob(path!)
      const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
      const actual = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
      if (actual !== sha) throw Error('다운로드 파일의 SHA-256이 일치하지 않습니다.')
      return {blob, text: readText ? await blob.text() : undefined}
    },
    enabled: Boolean(path), staleTime: Infinity, retry: false, refetchOnWindowFocus: false,
  })
  const blob = query.data?.blob
  const blobs = useMemo(() => blob ? [blob] : [], [blob])
  const [url] = useObjectUrls(blobs)
  return {query, url}
}

function VariantCard({group, mode, stage, variant, canMutate, approvedCopy, onRevisionCompletedChange}: {
  group: DualSnapshot; mode: DualMode; stage: Stage; variant: DualVariant | null; canMutate: boolean; approvedCopy: AdCopy | undefined
  onRevisionCompletedChange: (completed: boolean) => void
}) {
  const live=group.provenance==='LIVE_DUAL'
  const [checks,setChecks]=useState({product_matches:false,label_matches:false,cta_policy_matches:false,no_extra_text:false})
  const [observedCopy,setObservedCopy]=useState({headline:'',subline:'',cta:''})
  const observedMatches=Boolean(approvedCopy && Object.keys(observedCopy).every(
    field=>observedCopy[field as keyof AdCopy]===approvedCopy[field as keyof AdCopy]))
  const liveReviewReady=checks.product_matches && checks.label_matches && checks.cta_policy_matches &&
    (mode==='composed' || (checks.no_extra_text && observedMatches))
  const [checked, setChecked] = useState(false)
  const [loaded, setLoaded] = useState<{url: string; width: number; height: number}>()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  const title = LABELS[mode]
  const complete = variant?.state === 'COMPLETED' && variant.verification_state === (live ? 'LIVE_REVIEWED' : 'FIXTURE_REVIEWED')
  const reviewing = stage === 'draft' && variant?.state === 'IMAGE_REVIEW_REQUIRED'
  const composing = variant?.state === 'IMAGE_APPROVED' && variant.verification_state === (live ? 'LIVE_REVIEWED' : 'FIXTURE_REVIEWED')
  const selected = group.preferred_variant === mode
  const target = RATIOS[group.image_size]
  const artifact = (kind: DualArtifactKind, sha: string | null | undefined) =>
    dualArtifactPath(group.job_id, mode, kind, variant?.artifacts[kind], sha, group.provenance)
  const composedPreview = live && mode === 'composed' && reviewing
  const imageKind = complete ? 'final' : composedPreview ? 'preview' : 'candidate'
  const imageSha = complete ? variant.final_sha : reviewing ? composedPreview ? variant.preview_sha : variant.candidate_sha : undefined
  const image = useVerifiedArtifact(artifact(imageKind, imageSha), imageSha)
  const captionSha = complete ? variant.caption_sha : undefined
  const caption = useVerifiedArtifact(artifact('caption', captionSha), captionSha, true)
  const receiptSha = complete ? variant.receipt_sha : undefined
  const receipt = useVerifiedArtifact(artifact('receipt', receiptSha), receiptSha)
  const actualSize = loaded?.url === image.url ? loaded : undefined
  const sizeOk = matchesDualImageSize(actualSize, target, 'final')
  const candidateReady = matchesDualImageSize(actualSize, target, 'candidate')

  async function change(action: () => Promise<DualSnapshot>) {
    if (!canMutate || inFlight.current) return
    inFlight.current = true
    setPending(true)
    setError('')
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '시안 상태를 저장하지 못했습니다.')
    } finally {
      await queryClient.invalidateQueries({queryKey: dualQueryKey(group.job_id,group.provenance)})
      if (variant?.variant_job_id) await queryClient.invalidateQueries({queryKey: derivedQueryKey(variant.variant_job_id)})
      inFlight.current = false
      setPending(false)
    }
  }

  function decide(approve: boolean) {
    if (!reviewing || !variant.candidate_sha || !candidateReady || (approve && !(live?liveReviewReady:checked))) return
    const sha = variant.candidate_sha
    void change(() => decideDualVariant(group, mode, sha, approve,
      live && approve ? {product_matches:checks.product_matches,label_matches:checks.label_matches,
        cta_policy_matches:checks.cta_policy_matches,
        ...(mode==='freeform'?{observed_copy:observedCopy,no_extra_text:checks.no_extra_text}:{})} : undefined))
  }

  const stem = `ad_${mode}_${target.width}x${target.height}`
  return <article className="panel dual-variant stack" id={`dual-variant-${mode}`} tabIndex={-1}
    data-testid={`dual-variant-${mode}`} aria-labelledby={`dual-title-${mode}`}>
    <header>
      <h2 className="panel-title" id={`dual-title-${mode}`}>{title}</h2>
      <p className="muted" data-testid={`dual-state-${mode}`}>{variant ? VARIANT_STATUS[variant.state] ?? '시안 준비 중' : '시안 준비 대기'}</p>
    </header>
    {variant?.error_code && <p className="field-error" role="alert">이 시안에 문제가 발생했습니다. 코드 {variant.error_code}</p>}
    {variant?.state === 'IMAGE_REJECTED' && <p>이 시안은 최종 광고로 제공되지 않습니다. 다른 시안의 상태는 유지됩니다.</p>}
    {stage === 'export' && variant?.state === 'IMAGE_REVIEW_REQUIRED' &&
      <Link to="/create/draft">이 시안 검토하기</Link>}
    {(complete || reviewing) && <>
      {image.url ? <figure className="dual-preview">
        <img className="result-image" src={image.url} alt={`${title} ${complete ? '최종 광고' : '검토 이미지'}`}
          style={actualSize && {aspectRatio: `${actualSize.width} / ${actualSize.height}`}}
          onLoad={event => setLoaded({url: image.url, width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight})} />
        <figcaption>
          {composedPreview && <p>승인 카피를 합성한 검토용 광고 · 이미지 승인 전</p>}
          {actualSize ? `${actualSize.width}×${actualSize.height}px` : '크기 확인 중…'}
          {actualSize && <> · <a href={image.url} target="_blank" rel="noreferrer">원본 크기로 보기</a></>}
          {complete && actualSize && !sizeOk && <p className="field-error" role="alert">선택한 출력 크기와 일치하지 않습니다.</p>}
          {reviewing && actualSize && !candidateReady && <p className="field-error" role="alert">선택한 출력 비율과 일치하지 않습니다.</p>}
        </figcaption>
      </figure> : <ArtifactStatus artifact={image} name="이미지" />}
      {composedPreview && <details><summary>카피 합성 전 모델 원본 확인</summary>
        <p className="field-hint">모델 원본에는 광고 문구가 없습니다. 위 광고는 승인된 문구를 서버에서 한 번 합성한 검토용 이미지이며 최종 승인은 별도입니다.</p>
        <RawCandidate group={group} mode={mode} variant={variant} />
      </details>}
    </>}
    {reviewing && <details className="dual-review">
      <summary>이 원본 시안 검수하기</summary>
      <div className="stack dual-review-body">
      {live ? <fieldset className="stack">
        <legend>원본과 후보의 시각 검수</legend>
        {([
          ['product_matches','용기 형태·색상·제품과 브랜드가 원본과 일치합니다.'],
          ['label_matches','로고·라벨과 작은 표식의 문자를 확대해 원본과 대조했습니다. 판독 불가 항목이 없습니다.'],
          ['cta_policy_matches',mode==='composed' ? '승인 CTA의 합성 위치가 제품을 가리지 않는지 확인했습니다.' : '승인 CTA가 이미지에 정확히 한 번 보이며 제품을 가리지 않습니다.'],
          ...(mode==='freeform' ? [['no_extra_text','승인 외 문구·효능·가격·배지가 추가되지 않았고, 오탈자·누락·중복이 없습니다.']] : []),
        ] as Array<[keyof typeof checks,string]>).map(([field,label])=><label className="consent-label" key={field}>
          <input type="checkbox" checked={checks[field]} disabled={!canMutate || !candidateReady || pending}
            onChange={event=>setChecks(previous=>({...previous,[field]:event.target.checked}))} />
          <span>{label}</span>
        </label>)}
        {mode==='freeform' && <div className="stack">
          <p className="field-hint">후보 이미지에서 직접 읽은 문구를 입력해 승인 원문과 대조하세요.</p>
          {([['headline','헤드라인'],['subline','서브 문구'],['cta','CTA']] as const).map(([field,label])=><label key={field}>
            {label}<textarea rows={field==='subline'?2:1} value={observedCopy[field]} disabled={!canMutate || !candidateReady || pending}
              onChange={event=>setObservedCopy(previous=>({...previous,[field]:event.target.value}))}
              autoComplete="off" spellCheck={false} />
          </label>)}
          {!observedMatches && <p className="field-hint">입력한 세 문구가 승인 원문과 정확히 일치해야 승인할 수 있습니다.</p>}
        </div>}
      </fieldset> : <label className="consent-label">
        <input type="checkbox" checked={checked} disabled={!canMutate || !candidateReady || pending}
          onChange={event => setChecked(event.target.checked)} />
        <span>{mode === 'composed'
          ? '원본 사진을 기준으로 용기, 브랜드, 라벨의 검토 항목을 확인했습니다.'
          : '원본 제품과 라벨, 승인 문구의 오탈자·누락·중복 검토 항목을 확인했습니다.'}</span>
      </label>}
      <div className="button-row">
        <button className="button secondary" type="button" disabled={!canMutate || !candidateReady || pending} onClick={() => decide(false)}>이 시안 거절</button>
        <button className="button" type="button" disabled={!canMutate || !candidateReady || pending || !(live?liveReviewReady:checked)} onClick={() => decide(true)}>이 시안 승인</button>
      </div>
      </div>
    </details>}
    {composing && variant.candidate_sha && <button className="button secondary" type="button" disabled={!canMutate || pending}
      onClick={() => void change(() => decideDualVariant(group, mode, variant.candidate_sha!, true))}>
      승인된 이미지로 파일 준비 다시 시도
    </button>}
    {complete && <>
      <div className="button-row">
        <button className="button" type="button" disabled={!image.url || !sizeOk}
          onClick={() => download(image.url!, `${stem}.png`)}>PNG 저장</button>
        <button className="button secondary" type="button" disabled={!caption.url}
          onClick={() => download(caption.url!, `caption_${mode}.txt`)}>본문 TXT 저장</button>
        <button className="button secondary" type="button" disabled={!receipt.url}
          onClick={() => download(receipt.url!, `receipt_${mode}.json`)}>Receipt 저장</button>
      </div>
      {!caption.url && <ArtifactStatus artifact={caption} name="본문" />}
      {!receipt.url && <ArtifactStatus artifact={receipt} name="Receipt" />}
      <details>
        <summary>게시글 본문과 해시태그</summary>
        <p className="post-text">{caption.query.data?.text}</p>
      </details>
      <button className="button secondary" type="button" aria-pressed={selected}
        disabled={!canMutate || pending || selected || !sizeOk || !caption.url || !receipt.url || !variant.final_sha}
        onClick={() => void change(() => selectDualVariant(group, mode, variant.final_sha!))}>
        {selected ? '선택한 시안' : '이 시안 선택'}
      </button>
      {live && variant.variant_job_id && <Suspense fallback={<p>부분 수정 도구 준비 중…</p>}>
        <FinalInpaintingPanel key={variant.variant_job_id} jobId={variant.variant_job_id} mode={mode} canMutate={canMutate} />
      </Suspense>}
      <details className="dual-provenance">
        <summary>파일 무결성과 검수 기록</summary>
        <dl>
          <dt>시안 Job</dt><dd>{variant.variant_job_id}</dd>
          <dt>공통 카피 SHA-256</dt><dd>{group.copy_sha}</dd>
          <dt>카피 검수 SHA-256</dt><dd>{variant.review_sha}</dd>
          <dt>카피 승인 SHA-256</dt><dd>{variant.approval_sha}</dd>
          <dt>이미지 검수 SHA-256</dt><dd>{variant.image_review_sha}</dd>
          <dt>후보 SHA-256</dt><dd>{variant.candidate_sha}</dd>
          <dt>PNG SHA-256</dt><dd>{variant.final_sha}</dd>
          <dt>Caption SHA-256</dt><dd>{variant.caption_sha}</dd>
          <dt>Receipt SHA-256</dt><dd>{variant.receipt_sha}</dd>
          <dt>검수 범위</dt><dd>{variant.verification_state}</dd>
          {variant.provider_evidence && <>
            <dt>공통 기획 Prompt SHA-256</dt><dd>{variant.provider_evidence.shared_prompt_sha}</dd>
            <dt>모드별 Provider Prompt SHA-256</dt><dd>{variant.provider_evidence.provider_prompt_sha}</dd>
            <dt>모드별 Provider 요청 SHA-256</dt><dd>{variant.provider_evidence.provider_request_sha}</dd>
            <dt>Owner Attempt ID</dt><dd>{variant.provider_evidence.owner_attempt_id}</dd>
            <dt>비용 원장 Attempt ID</dt><dd>{variant.provider_evidence.cost_attempt_id}</dd>
          </>}
        </dl>
      </details>
    </>}
    {live && variant?.variant_job_id && <ResultRevisionPanel key={`${variant.variant_job_id}:${variant.candidate_sha}`}
      jobId={variant.variant_job_id} mode={mode} canMutate={canMutate} showRequestForm={stage === 'draft'}
      onCompletedChange={onRevisionCompletedChange} />}
    {live && variant?.variant_job_id && (variant.state === 'IMAGE_REJECTED'
      ? <p role="status">원본 시안이 거절되어 이 원본을 사용한 제품 보호 합성본도 승인·저장할 수 없습니다. 오타 수정은 별도의 수정본으로 요청하세요.</p>
      : <DerivedArtifactPanel jobId={variant.variant_job_id} approvedCopy={approvedCopy} target={target} canMutate={canMutate} />)}
    {variant && <CostDetails cost={variant.cost} live={live} />}
    {pending && <p className="muted" role="status">시안 상태 저장 중…</p>}
    {error && <p className="field-error" role="alert">{error}</p>}
  </article>
}

function RawCandidate({group, mode, variant}: {group: DualSnapshot; mode: DualMode; variant: DualVariant}) {
  const path = dualArtifactPath(group.job_id, mode, 'candidate', variant.artifacts.candidate, variant.candidate_sha, group.provenance)
  const raw = useVerifiedArtifact(path, variant.candidate_sha)
  return raw.url ? <a href={raw.url} target="_blank" rel="noreferrer">모델 원본 크기로 보기</a> : <ArtifactStatus artifact={raw} name="모델 원본" />
}

function ArtifactStatus({artifact, name}: {artifact: ReturnType<typeof useVerifiedArtifact>; name: string}) {
  if (artifact.query.isError) return <div role="alert">
    <p>{name} 파일을 확인하지 못했습니다.</p>
    <button className="button secondary small" type="button" disabled={artifact.query.isFetching}
      onClick={() => void artifact.query.refetch()}>{name} 파일 다시 가져오기</button>
  </div>
  return <p className="muted" role="status">
    {artifact.query.isPending && artifact.query.fetchStatus === 'idle' ? `${name} 파일을 확인할 수 없습니다.` : `${name} 파일을 확인하는 중…`}
  </p>
}

export function DualModeLoading({failed, retry}: {failed: boolean; retry: () => void}) {
  return <StepPage title="광고 시안 확인" wide stickyActions={false}>
    {failed ? <div className="notice notice-danger" role="alert">
      <p>저장된 광고 상태를 확인하지 못했습니다.</p>
      <button className="button secondary small" type="button" onClick={retry}>상태 다시 확인</button>
    </div> : <p className="muted" role="status">저장된 광고 상태를 확인 중…</p>}
  </StepPage>
}

export default function DualModePage({snapshot, stage}: {snapshot: LiveSnapshot; stage: Stage}) {
  const {job_id: jobId} = snapshot
  const [resuming, setResuming] = useState(false)
  const [resumeError, setResumeError] = useState('')
  const [revisionCompletion, setRevisionCompletion] = useState({jobId, composed: false, freeform: false})
  const onComposedCompleted = useCallback((completed: boolean) => setRevisionCompletion(previous =>
    previous.jobId === jobId && previous.composed === completed ? previous : {
      jobId, composed: completed, freeform: previous.jobId === jobId && previous.freeform,
    }), [jobId])
  const onFreeformCompleted = useCallback((completed: boolean) => setRevisionCompletion(previous =>
    previous.jobId === jobId && previous.freeform === completed ? previous : {
      jobId, freeform: completed, composed: previous.jobId === jobId && previous.composed,
    }), [jobId])
  const resumeInFlight = useRef(false)
  const provenance=snapshotDualProvenance(snapshot)
  const live=provenance==='LIVE_DUAL'
  const enabled = live ? snapshot.mode==='LIVE' : DUAL_QA && snapshot.mode === 'OFFLINE_FIXTURE'
  const groupQuery = useQuery({
    queryKey: dualQueryKey(jobId,provenance), queryFn: () => getDualJob(jobId,provenance), enabled, retry: false,
    refetchInterval: query => ['COMPLETED', 'FAILED'].includes(query.state.data?.state ?? '') ? false : 1800,
  })
  const originals = useQuery({
    queryKey: ['dual-originals', jobId], queryFn: () => getJob(jobId), enabled: enabled && stage === 'draft',
    staleTime: Infinity, retry: false,
  })
  const group = groupQuery.data?.job_id === jobId && groupQuery.data.provenance === provenance ? groupQuery.data : undefined
  const completedRevisions = revisionCompletion.jobId === jobId && live
    ? {composed: revisionCompletion.composed, freeform: revisionCompletion.freeform}
    : {composed: false, freeform: false}
  // Customer completion can use an independently approved revision. This does
  // not mutate or relabel the original dual group's partial/rejected state.
  const complete = group?.state === 'COMPLETED' || Boolean(group &&
    (completedRevisions.composed || completedRevisions.freeform))
  const canExport = group && (MODES.some(mode => group.variants[mode]?.state === 'COMPLETED') ||
    completedRevisions.composed || completedRevisions.freeform)
  const products = originals.data?.assets?.filter(asset => asset.role === 'product') ?? []
  const copy = group?.copy_sha && group.copy_sha === snapshot.copy_sha ? snapshot.copy?.ad_copy : undefined
  const canResume = enabled && stage === 'draft' && group && !groupQuery.isError && canResumeDualJob(snapshot, group)
  useEffect(() => {
    if (enabled && complete && stage === 'export') useProjectStore.getState().setFinishedJob(jobId)
  }, [complete, enabled, jobId, stage])

  async function resume() {
    if (!group || !canResume || resumeInFlight.current) return
    resumeInFlight.current = true
    setResuming(true)
    setResumeError('')
    try {
      await resumeDualJob(snapshot, group)
    } catch (cause) {
      setResumeError(cause instanceof Error ? cause.message : '시안 준비를 이어가지 못했습니다.')
    } finally {
      await groupQuery.refetch()
      resumeInFlight.current = false
      setResuming(false)
    }
  }

  return <StepPage title={stage === 'draft' ? '두 광고 시안 검토' : '최종 광고 시안'}
    description="같은 카피와 비율로 준비한 합성형과 자유형을 비교하세요. 각 시안의 승인과 저장은 개별적으로 진행합니다."
    back={stage === 'draft' ? {to: '/create/copy', label: '기획·카피 검토'} : {to: '/create/draft', label: '이미지 검토'}}
    wide stickyActions={false}
    actions={stage === 'draft'
      ? canExport && <Link className="button" to="/create/export">최종 시안 보기</Link>
      : complete && <Link className="button secondary" to="/create/product" onClick={startNewAdLink}>새 광고 만들기</Link>}>
    {!enabled ? <p role="alert">이 두 시안 작업의 실행 환경을 확인해야 합니다.</p> : <>
      {groupQuery.isError && <div className="notice notice-danger" role="alert">
        <p>두 시안의 최신 상태를 확인하지 못했습니다.</p>
        <button className="button secondary small" type="button" disabled={groupQuery.isFetching}
          onClick={() => void groupQuery.refetch()}>상태 다시 확인</button>
      </div>}
      {!group && !groupQuery.isError && <p className="muted" role="status">시안 상태를 확인 중…</p>}
      {group && <>
        <p className="notice notice-info" role="status" data-testid="dual-job-state">
          <strong>{GROUP_STATUS[group.state]}</strong> · {group.image_size}
          {group.state === 'PARTIAL' && ' · 완성된 시안은 계속 사용할 수 있습니다.'}
        </p>
        <RevisionResultLinks completed={completedRevisions} />
        {group.hold_code && <div className="notice notice-warning" role="alert">
          <p>실행 결과 또는 과금 상태를 확인하고 있습니다. 기존에 완료된 시안은 계속 저장할 수 있습니다.</p>
          <small>{group.hold_code}</small>
        </div>}
        <nav className="dual-jump" aria-label="광고 시안으로 이동">
          <a className="button secondary small" href="#dual-variant-composed">합성형 시안 보기</a>
          <a className="button secondary small" href="#dual-variant-freeform">자유형 시안 보기</a>
        </nav>
        {live && group.shared_text_cost && <details className="panel dual-common-cost">
          <summary>공통 AI 사용량 확인</summary>
          <p className="field-hint">두 이미지 시안의 사용량과 별도로 한 번만 집계됩니다.</p>
          <CostDetails cost={group.shared_text_cost} live />
        </details>}
        {canResume && <button className="button secondary" type="button" disabled={resuming} onClick={() => void resume()}>
          {resuming ? '시안 준비 중…' : '승인된 카피로 시안 준비 이어가기'}
        </button>}
        {resumeError && <p className="field-error" role="alert">{resumeError}</p>}
        {stage === 'draft' && <details className="panel dual-common-review">
          <summary>승인 카피·제품 원본 확인</summary>
          <div className="stack dual-review-body">
          {copy && <dl className="dual-copy">
            <dt>헤드라인</dt><dd>{copy.headline}</dd>
            <dt>서브 문구</dt><dd>{copy.subline}</dd>
            <dt>CTA</dt><dd>{copy.cta}</dd>
          </dl>}
          {products.length > 0 && <ul className="compare-thumbs" aria-label="올린 제품 사진">
            {products.map((asset, index) => <AssetThumb key={asset.asset_id} jobId={jobId} asset={asset} index={index} openFull />)}
          </ul>}
          {originals.isError && <button className="button secondary small" type="button" onClick={() => void originals.refetch()}>원본 사진 다시 확인</button>}
          <p className="field-hint">{live ? '원본 사진과 승인 카피를 두 시안에 각각 대조하세요. 확인하기 어려운 라벨이나 글자는 승인 전에 보완해야 합니다.' : '시험 이미지의 용기와 라벨은 예시입니다. 한글 가독성, 제품 충실도, 광고 매력도, 브랜드 적합성, CTA를 같은 기준으로 살펴보세요.'}</p>
          </div>
        </details>}
        <div className="dual-grid">
          {MODES.map(mode => {
            const variant = group.variants[mode]
            return <VariantCard key={`${mode}:${variant?.candidate_sha}:${variant?.state}`}
              group={group} approvedCopy={copy} mode={mode} stage={stage} variant={variant}
              onRevisionCompletedChange={mode === 'composed' ? onComposedCompleted : onFreeformCompleted}
              canMutate={!groupQuery.isError && (variant?.state !== 'IMAGE_REVIEW_REQUIRED' || Boolean(copy && products.length >= 2))} />
          })}
        </div>
        {stage === 'export' && canExport && <p className="field-hint">
          선호 시안은 이 작업에 기록됩니다. Owner·PM의 실제 광고 평가는 한글 가독성, 제품 충실도, 광고 매력도, 브랜드 적합성과 CTA를 기준으로 별도로 기록합니다.
        </p>}
      </>}
    </>}
  </StepPage>
}

function CostDetails({cost,live}: {cost:DualCost;live:boolean}) {
  return <div className="field-hint">
    <p>Provider 시도 {cost.provider_attempt_count}건 · {live ? (
      cost.status==='BILLING_UNKNOWN' ? '과금 상태 확인 필요 · 자동 재호출 차단' :
      cost.status==='NOT_DISPATCHED' ? '전송 전' :
      cost.status==='AWAITING_RECEIPT' ? '응답 사용량 확인 중' :
      '실제 청구액 UNPRICED'
    ) : '실제 청구액 대사 대상 없음'}</p>
    {live && cost.attempts && cost.attempts.length>0 && <details>
      <summary>모델 사용량과 Attempt</summary>
      {cost.attempts.map(attempt=><p key={attempt.attempt_id}>
        {attempt.stage} · {attempt.model || '모델 응답 대기'} · {attempt.state}
        {attempt.usage?.total_tokens!==undefined && <> · {attempt.usage.total_tokens} tokens</>}
        <br /><small>{attempt.attempt_id}</small>
      </p>)}
    </details>}
  </div>
}
