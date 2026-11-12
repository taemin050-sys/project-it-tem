import { useQuery } from '@tanstack/react-query'
import { useId, useMemo, useRef, useState } from 'react'
import {
  belongsToDerivedContext, canRevokeDerivedAdmission, configureDerivedProposal, decideDerivedRender, derivedArtifactPath, derivedFinalizeReady,
  derivedModeLabel, derivedProposalReady, derivedQueryKey, derivedReviewReady,
  finalizeDerivedRender, getDerivedJob, parseDerivedGeometry, prepareDerivedRender, revokeDerivedAdmission, selectDerivedRender, uploadDerivedMask,
  type DerivedArtifactKind, type DerivedRender, type DerivedSnapshot, type DerivedVisualReview,
} from '../api/derivedJobs'
import { getBlob } from '../api/jobs'
import { queryClient } from '../api/queryClient'
import { download } from '../lib/download'
import { useObjectUrls } from '../lib/useObjectUrls'
import type { AdCopy } from '../types/textSchema'

type OutputSize = {width: number; height: number}
const STATUS: Record<DerivedRender['state'], string> = {
  QUEUED: '원본 제품 보호 시안 준비 대기', RENDERING: '원본 제품 보호 시안 준비 중',
  REVIEW_REQUIRED: '원본 제품 보호 시안 검수 필요', APPROVED: '시안 승인됨 · 파일 발급 가능',
  COMPLETED: '원본 제품 보호 시안 완료', REJECTED: '시안 거절됨', HOLD: '시각 품질·승인 확인 보류',
  FAILED: '시안을 준비하지 못했습니다', STALE: '이 보호 시안은 현재 사용할 수 없습니다',
}
const CHECKS = [
  ['source_pixels_preserved', '원본 사진의 제품·용기·브랜드·라벨이 보존됐는지 확대해 대조했습니다.'],
  ['edges_acceptable', '제품 경계·물보라·그림자·반사와 조명이 자연스럽습니다.'],
  ['no_duplicate_product', '용기나 펌프가 중복으로 보이지 않습니다.'],
  ['no_ghost_product', '모델이 그린 제품·라벨·그림자의 잔상이 남아 있지 않습니다.'],
  ['no_copy_occlusion', '제품이 광고 문구를 가리지 않고 오탈자·누락·중복·추가 문구가 없습니다.'],
  ['cta_policy_matches', 'CTA의 문구와 위치를 확인했고 제품·문구를 가리지 않습니다.'],
  ['label_ground_truth_confirmed', '실물 또는 확인된 패키지 원본으로 작은 라벨 문자까지 대조했습니다.'],
  ['mobile_readable', '사용할 모바일 화면에서 제목·서브·CTA의 가독성을 확인했습니다.'],
] as const

function emptyReview(): DerivedVisualReview {
  return {source_pixels_preserved: false, edges_acceptable: false, no_duplicate_product: false,
    no_ghost_product: false, no_copy_occlusion: false, cta_policy_matches: false,
    label_ground_truth_confirmed: false, mobile_readable: false,
    observed_copy: {headline: '', subline: '', cta: ''}}
}

function useDerivedArtifact(render: DerivedRender, kind: DerivedArtifactKind, enabled: boolean) {
  const path = enabled ? derivedArtifactPath(render, kind) : undefined
  const sha = kind === 'preview' ? render.preview_sha : render[`${kind}_sha`]
  const query = useQuery({
    queryKey: ['derived-artifact', path], enabled: Boolean(path), retry: false,
    staleTime: Infinity, refetchOnWindowFocus: false,
    queryFn: async () => {
      const blob = await getBlob(path!)
      const digest = await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())
      const actual = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
      if (actual !== sha) throw Error('제품 보호 시안 파일의 SHA-256이 일치하지 않습니다.')
      return {blob, text: kind === 'caption' ? await blob.text() : undefined}
    },
  })
  const blob = query.data?.blob
  const blobs = useMemo(() => blob ? [blob] : [], [blob])
  const [url] = useObjectUrls(blobs)
  return {url, query}
}

function RenderReview({snapshot, render, approvedCopy, target, canMutate}: {
  snapshot: DerivedSnapshot; render: DerivedRender; approvedCopy: AdCopy | undefined
  target: OutputSize; canMutate: boolean
}) {
  const [review, setReview] = useState(emptyReview)
  const [loaded, setLoaded] = useState<{url: string; width: number; height: number}>()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  const current = belongsToDerivedContext(snapshot, render) && !['STALE', 'HOLD'].includes(render.state)
  const complete = render.state === 'COMPLETED' && current
  const imageKind = complete ? 'final' : 'preview'
  const image = useDerivedArtifact(render, imageKind, current && Boolean(complete ? render.final_sha : render.preview_sha))
  const caption = useDerivedArtifact(render, 'caption', complete)
  const receipt = useDerivedArtifact(render, 'receipt', complete)
  const actualSize = loaded?.url === image.url ? loaded : undefined
  const sizeReady = actualSize?.width === target.width && actualSize?.height === target.height
  const canApprove = canMutate && sizeReady && derivedReviewReady(snapshot, render, review, approvedCopy)
  const canFinalize = canMutate && sizeReady && derivedFinalizeReady(snapshot, render)
  const canDecide = canMutate && current && snapshot.can_review && render.state === 'REVIEW_REQUIRED'
  const selected = snapshot.selected_derived_id === render.derived_id

  async function change(action: () => Promise<unknown>) {
    if (!canMutate || inFlight.current) return
    inFlight.current = true
    setPending(true)
    setError('')
    try {
      await action()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '제품 보호 시안 상태를 저장하지 못했습니다.')
    } finally {
      await queryClient.invalidateQueries({queryKey: derivedQueryKey(render.job_id)})
      inFlight.current = false
      setPending(false)
    }
  }

  return <section className="derived-render stack" aria-label={derivedModeLabel(render.render_mode)}>
    <header>
      <h4>{derivedModeLabel(render.render_mode)}</h4>
      <p className="muted" role="status">{STATUS[render.state]}</p>
    </header>
    {render.hold_code && <p className="notice notice-warning" role="alert">
      {render.hold_code === 'PROTECTED_PRODUCT_RECIPE_REVALIDATION_REQUIRED'
        ? '이전 합성은 제품 전체 형태를 보장하지 못해 사용을 중단했습니다. 원본과 전체 윤곽을 확인한 새 배치가 필요합니다.'
        : '제품·시각 품질 또는 승인 근거의 추가 확인이 필요합니다.'}
      <small style={{display: 'block', overflowWrap: 'anywhere'}}>{render.hold_code}</small>
    </p>}
    {image.url && <figure className="dual-preview">
      <img className="result-image" src={image.url} alt={`${derivedModeLabel(render.render_mode)} ${complete ? '최종 이미지' : '검토 이미지'}`}
        style={{aspectRatio: `${target.width} / ${target.height}`}}
        onLoad={event => setLoaded({url: image.url, width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight})} />
      <figcaption>
        {actualSize ? `${actualSize.width}×${actualSize.height}px` : '이미지 크기 확인 중…'}
        {' · '}<a href={image.url} target="_blank" rel="noreferrer">원본 크기로 보기</a>
        {actualSize && !sizeReady && <p className="field-error" role="alert">선택한 출력 크기와 일치하지 않습니다.</p>}
      </figcaption>
    </figure>}
    {image.query.isError && <div role="alert">
      <p>제품 보호 이미지를 확인하지 못했습니다.</p>
      <button className="button secondary small" type="button" disabled={image.query.isFetching}
        onClick={() => void image.query.refetch()}>이미지 다시 가져오기</button>
    </div>}
    {current && render.preview_sha && !image.url && !image.query.isError &&
      <p className={image.query.fetchStatus === 'idle' ? 'field-error' : 'muted'}
        role={image.query.fetchStatus === 'idle' ? 'alert' : 'status'}>
        {image.query.fetchStatus === 'idle' ? '검토 파일의 경로·해시를 확인할 수 없습니다.' : '검토 파일 확인 중…'}
      </p>}
    {render.state === 'REVIEW_REQUIRED' && <>
      <fieldset className="stack" disabled={!canDecide || !sizeReady || pending}>
        <legend>보호 합성 결과를 따로 검수해 주세요</legend>
        <p className="field-hint">원본 픽셀 보존과 작은 라벨 문자의 실제 판독을 각각 확인하세요. 확인할 수 없는 항목은 체크하지 않습니다.</p>
        {CHECKS.map(([field,label]) => <label className="consent-label" key={field}>
          <input type="checkbox" checked={review[field]}
            onChange={event => setReview(previous => ({...previous, [field]: event.target.checked}))} />
          <span>{label}</span>
        </label>)}
        <p className="field-hint">완성 이미지를 직접 읽은 광고 문구를 입력해 승인 카피와 대조하세요.</p>
        {([['headline','헤드라인'], ['subline','서브 문구'], ['cta','CTA']] as const).map(([field,label]) =>
          <label key={field}>{label}<textarea rows={field === 'subline' ? 2 : 1}
            value={review.observed_copy[field]} autoComplete="off" spellCheck={false}
            onChange={event => setReview(previous => ({...previous,
              observed_copy: {...previous.observed_copy, [field]: event.target.value}}))} />
          </label>)}
      </fieldset>
      <div className="button-row">
        <button className="button secondary" type="button" disabled={!canDecide || pending}
          onClick={() => void change(() => decideDerivedRender(snapshot, render, false, review, approvedCopy))}>
          보호 시안 거절
        </button>
        <button className="button" type="button" disabled={!canApprove || pending}
          onClick={() => void change(() => decideDerivedRender(snapshot, render, true, review, approvedCopy))}>
          이 보호 시안 승인
        </button>
      </div>
    </>}
    {render.state === 'APPROVED' && <button className="button" type="button" disabled={!canFinalize || pending}
      onClick={() => void change(() => finalizeDerivedRender(snapshot, render))}>
      {pending ? '파일 발급 중…' : '승인한 보호 시안 파일 발급'}
    </button>}
    {complete && <>
      <div className="button-row">
        <button className="button" type="button" disabled={pending || !image.url || !sizeReady}
          onClick={() => download(image.url!, `ad_${render.render_mode}_${target.width}x${target.height}.png`)}>보호 시안 PNG 저장</button>
        <button className="button secondary" type="button" disabled={pending || !caption.url}
          onClick={() => download(caption.url!, 'caption_protected_product.txt')}>본문 TXT 저장</button>
        <button className="button secondary" type="button" disabled={pending || !receipt.url}
          onClick={() => download(receipt.url!, 'receipt_protected_product.json')}>Receipt 저장</button>
      </div>
      {(caption.query.isError || receipt.query.isError) && <div role="alert">
        <p>본문 또는 Receipt를 확인하지 못했습니다.</p>
        <button className="button secondary small" type="button" onClick={() => {
          void caption.query.refetch()
          void receipt.query.refetch()
        }}>저장 파일 다시 가져오기</button>
      </div>}
      <details><summary>게시글 본문과 해시태그</summary><p className="post-text">{caption.query.data?.text}</p></details>
      <button className="button secondary" type="button" aria-pressed={selected}
        disabled={!canMutate || pending || selected || !sizeReady || !caption.url || !receipt.url}
        onClick={() => void change(() => selectDerivedRender(snapshot, render))}>
        {selected ? '선택한 보호 시안' : '이 보호 시안 선택'}
      </button>
    </>}
    <details className="derived-provenance"><summary>원본·보호 합성의 검수 기록</summary>
      <dl>
        <dt>생성 방식</dt><dd>{derivedModeLabel(render.render_mode)}</dd>
        <dt>파생 시안</dt><dd>{render.derived_id}</dd>
        <dt>Recipe SHA-256</dt><dd>{render.recipe_sha}</dd>
        <dt>Recipe 수용 기록</dt><dd>{render.admission_sha}</dd>
        <dt>검토 이미지 SHA-256</dt><dd>{render.preview_sha ?? '준비 대기'}</dd>
        <dt>파생 승인 SHA-256</dt><dd>{render.approval_sha ?? '승인 대기'}</dd>
        <dt>최종 PNG SHA-256</dt><dd>{render.final_sha ?? '발급 대기'}</dd>
        <dt>Caption SHA-256</dt><dd>{render.caption_sha ?? '발급 대기'}</dd>
        <dt>Receipt SHA-256</dt><dd>{render.receipt_sha ?? '발급 대기'}</dd>
      </dl>
    </details>
    {canMutate && canRevokeDerivedAdmission(snapshot, render) && <details className="derived-access">
      <summary>보호 시안 사용 권한 관리</summary>
      <div className="stack derived-prepare">
        <p>이 시안의 Recipe 수용 권한을 철회합니다. 같은 수용 기록을 공유하는 보호 시안들도 서버에서 조회·저장할 수 없게 되며 선택이 해제됩니다.</p>
        <p className="field-hint">원본 합성형·자유형 결과와 Provider 기록은 유지됩니다. 이미 기기에 저장한 파일은 삭제되지 않습니다.</p>
        <button className="button secondary" type="button" disabled={pending}
          onClick={() => void change(() => revokeDerivedAdmission(snapshot, render))}>
          {pending ? '보호 시안 사용 중지 중…' : '이 보호 시안 사용 중지'}
        </button>
      </div>
    </details>}
    {pending && <p className="muted" role="status">보호 시안 상태 저장 중…</p>}
    {error && <p className="field-error" role="alert">{error}</p>}
  </section>
}

const EMPTY_GEOMETRY = JSON.stringify({source_crop: null, registered_size: null, output_offset: null,
  protected_rois: null, source_product_outline: null, model_regions: [], copy_exclusions: []}, null, 2)

function DerivedConfigurationForm({snapshot, canMutate, refresh}: {
  snapshot: DerivedSnapshot; canMutate: boolean; refresh: () => Promise<unknown>
}) {
  const formId = useId()
  const [sourceId, setSourceId] = useState(snapshot.source_assets?.[0]?.asset_id ?? '')
  const [mask, setMask] = useState<File | null>(null)
  const [geometry, setGeometry] = useState(EMPTY_GEOMETRY)
  const [acknowledged, setAcknowledged] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  const enabled = canMutate && snapshot.can_admit && !pending
  async function configure() {
    if (!enabled || !acknowledged || inFlight.current) return
    inFlight.current = true
    setPending(true)
    setError('')
    try {
      const values = parseDerivedGeometry(geometry)
      const maskRef = mask ? await uploadDerivedMask(snapshot.job_id, mask) : null
      await configureDerivedProposal(snapshot, {...values, source_asset_id: sourceId,
        mask_ref: maskRef, acknowledge_regions: true})
      setAcknowledged(false)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '합성 배치 설정을 저장하지 못했습니다.')
    } finally {
      inFlight.current = false
      setPending(false)
    }
  }
  return <details className="derived-config">
    <summary>원본 제품·마스크·합성 배치 설정</summary>
    <div className="stack derived-prepare">
      <label htmlFor={`${formId}-source`}>보호할 제품 원본</label>
      <select id={`${formId}-source`} value={sourceId} disabled={!enabled} onChange={event => {
        setSourceId(event.target.value)
        setAcknowledged(false)
        setMask(null)
      }}>
        {snapshot.source_assets?.map((asset,index) => <option key={asset.asset_id} value={asset.asset_id}>
          {asset.name || `제품 사진 ${index + 1}`} · {asset.width}×{asset.height}px
        </option>)}
      </select>
      <label htmlFor={`${formId}-mask`}>제품 마스크 PNG <span className="field-hint">선택</span></label>
      <input key={sourceId} id={`${formId}-mask`} type="file" accept="image/png,.png" disabled={!enabled}
        onChange={event => {setMask(event.target.files?.[0] ?? null); setAcknowledged(false)}} />
      <p className="field-hint">펌프부터 용기 바닥까지 전부 포함한 마스크가 필요합니다. 라벨만 보존하거나 제품 하단을 제거한 마스크는 사용할 수 없습니다.</p>
      <label htmlFor={`${formId}-geometry`}>크롭·배치·보호 영역</label>
      <textarea id={`${formId}-geometry`} className="derived-geometry" rows={12} value={geometry}
        spellCheck={false} autoComplete="off" disabled={!enabled} maxLength={64000}
        onChange={event => {setGeometry(event.target.value); setAcknowledged(false)}} />
      <p className="field-hint">크롭과 라벨 보호 영역은 제품 원본 좌표입니다. 출력 크기·위치, 모델 제품 제거 영역과 광고 문구 보호 영역은 최종 PNG 좌표를 사용합니다. 좌표 상자는 [왼쪽, 위, 오른쪽, 아래] 순서입니다. 자동 배치는 null로 둡니다.</p>
      <label className="consent-label">
        <input type="checkbox" checked={acknowledged} disabled={!enabled}
          onChange={event => setAcknowledged(event.target.checked)} />
        <span>사용 권한이 있는 원본을 골랐고, 제품·펌프·반사·그림자와 광고 문구의 검토 영역을 확인했습니다.</span>
      </label>
      <button className="button secondary" type="button" disabled={!enabled || !sourceId || !acknowledged}
        onClick={() => void configure()}>{pending ? '배치 확인 중…' : '이 배치로 보호 합성 제안 만들기'}</button>
      {error && <p className="field-error" role="alert">{error}</p>}
    </div>
  </details>
}

export default function DerivedArtifactPanel({jobId, approvedCopy, target, canMutate}: {
  jobId: string; approvedCopy: AdCopy | undefined; target: OutputSize; canMutate: boolean
}) {
  const query = useQuery({
    queryKey: derivedQueryKey(jobId), queryFn: () => getDerivedJob(jobId), retry: false,
    refetchInterval: current => current.state.data?.renders.some(render =>
      ['QUEUED', 'RENDERING'].includes(render.state)) ? 1500 : false,
  })
  const [sourceConsent, setSourceConsent] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  const snapshot = query.data?.job_id === jobId && query.data.available ? query.data : undefined
  const sourceConsentContext = snapshot ? `${snapshot.context_sha}:${snapshot.revision}` : null
  const sourceChecked = Boolean(sourceConsentContext && sourceConsent === sourceConsentContext)
  if (!snapshot && !query.isError) return null
  if (query.isError) return <details className="derived-panel">
    <summary>원본 제품 보호 시안</summary>
    <p role="alert">제품 보호 시안 상태를 확인하지 못했습니다.</p>
    <button className="button secondary small" type="button" disabled={query.isFetching}
      onClick={() => void query.refetch()}>보호 시안 상태 다시 확인</button>
  </details>
  if (!snapshot) return null

  async function prepare(proposal: DerivedSnapshot['proposals'][number]) {
    if (!snapshot || !canMutate || !sourceChecked || inFlight.current) return
    inFlight.current = true
    setPending(true)
    setError('')
    try {
      await prepareDerivedRender(snapshot, proposal)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '보호 시안을 준비하지 못했습니다.')
    } finally {
      await query.refetch()
      inFlight.current = false
      setPending(false)
    }
  }

  return <section className="derived-panel stack" aria-label="원본 제품 보호 시안">
    <header>
      <h3>원본 제품 보호 시안</h3>
      <p className="field-hint">올린 사진의 용기·라벨을 보존한 결과를 비교하고, 완성 이미지를 별도로 검수하세요.</p>
    </header>
    {snapshot.hold_code && <p className="notice notice-warning" role="alert">
      제품·승인 또는 과금 상태를 먼저 확인해야 합니다. <small>{snapshot.hold_code}</small>
    </p>}
    {snapshot.source_assets && snapshot.source_assets.length > 0 && <DerivedConfigurationForm
      key={`${snapshot.job_id}:${snapshot.context_sha}`} snapshot={snapshot}
      canMutate={canMutate} refresh={() => query.refetch()} />}
    {snapshot.proposals.length > 0 && <details>
      <summary>보호 합성 방식 선택</summary>
      <div className="stack derived-prepare">
        <label className="consent-label">
          <input type="checkbox" checked={sourceChecked} disabled={!canMutate || pending || !snapshot.can_admit}
            onChange={event => setSourceConsent(event.target.checked ? sourceConsentContext : null)} />
          <span>선택한 원본 제품·라벨과 사용 권한을 확인했습니다.</span>
        </label>
        {snapshot.proposals.map(proposal => <div className="derived-proposal" key={proposal.proposal_id}>
          <strong>{proposal.title}</strong>
          <p className="field-hint">{derivedModeLabel(proposal.render_mode)}</p>
          {proposal.requires_ground_truth && <p className="field-hint">최종 광고 승인에는 실물 라벨과 문자 판독 근거가 필요합니다.</p>}
          {proposal.hold_code && <p className="field-error" role="alert">이 방식은 추가 확인이 필요합니다. {proposal.hold_code}</p>}
          <button className="button secondary" type="button"
            disabled={!canMutate || pending || !sourceChecked || !derivedProposalReady(snapshot, proposal)}
            onClick={() => void prepare(proposal)}>{pending ? '보호 시안 준비 중…' : '이 방식으로 보호 시안 준비'}</button>
        </div>)}
      </div>
    </details>}
    {!snapshot.can_admit && !snapshot.renders.length && <p className="field-hint">원본·Recipe를 확인할 권한이 있는 담당자의 검토를 기다리고 있습니다.</p>}
    {snapshot.renders.map(render => <RenderReview key={`${render.derived_id}:${render.preview_sha}:${render.context_sha}:${render.state}`}
      snapshot={snapshot} render={render} approvedCopy={approvedCopy} target={target}
      canMutate={canMutate && !query.isError} />)}
    {error && <p className="field-error" role="alert">{error}</p>}
  </section>
}
