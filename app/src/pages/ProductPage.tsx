import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { isUnreachable } from '../api/client'
import { createJob } from '../api/jobs'
import { advance, hasUnfinishedJob, productPayload, recoverLiveInput, resetJob, startNewAd } from '../api/useJob'
import Icon from '../components/Icon'
import MockFallback from '../components/MockFallback'
import PhotoDrop from '../components/PhotoDrop'
import StepPage from '../components/StepPage'
import { StepPills } from '../components/Steps'
import { PRODUCT_PHOTOS, RATIOS, REFERENCE_PHOTOS, SHRINK, type Ratio } from '../config'
import { shrinkImage } from '../lib/shrinkImage'
import { validateProduct, type ProductErrors } from '../lib/validateProduct'
import { useProjectStore } from '../store/projectStore'
import { AD_PURPOSES, EMOJI_LEVELS, FUNCTIONAL_TYPES, PRODUCT_TYPES, type EmojiLevel, type FunctionalType, type ProductType } from '../types/textSchema'

const LIMITS = { product: PRODUCT_PHOTOS, reference: REFERENCE_PHOTOS }

// 제출 시 첫 오류 항목으로 포커스를 옮기기 위한 순서와 대상 id
const FOCUS_ORDER: [keyof ProductErrors, string][] = [
  ['images', 'photos'],
  ['references', 'references'],
  ['product_name', 'product_name'],
  ['features', 'features'],
  ['functional_types', 'functional_types'],
  ['photo_verified', 'photo_verified'],
  ['ai_consent', 'ai_consent'],
]

// 화면 표시 이름만 시안을 따르고, 서버로 보내는 값은 텍스트 스키마 값 그대로다
const CATEGORY_LABEL: Partial<Record<ProductType, string>> = { 색조: '색조 립&아이', 바디: '바디케어', 헤어: '헤어케어' }
const PURPOSE_TILE: Record<(typeof AD_PURPOSES)[number], { icon: string; desc: string }> = {
  '신제품 홍보': { icon: 'campaign', desc: '첫인상 극대화' },
  '할인 프로모션': { icon: 'shopping_cart', desc: '혜택/할인 강조' },
  '효능 강조': { icon: 'science', desc: '성분/효과 강조' },
  '감성 브랜딩': { icon: 'award_star', desc: '철학/비건스토리' },
}
const EMOJI_LABEL: Record<EmojiLevel, string> = { 없음: '없음', 보통: '보통 ✨🌿', 많이: '많이 🔥😍' }
const RATIO_TILE: Record<Ratio, { label: string; w: number; h: number }> = {
  '3:4': { label: '3:4 피드', w: 16, h: 20 },
  '4:5': { label: '4:5 인스타 최적', w: 16, h: 20 },
  '9:16': { label: '9:16 스토리/릴스', w: 14, h: 24 },
}

// 기능성 종류 목록 순서를 유지한 채 켜고 끈다
const toggle = (list: FunctionalType[], t: FunctionalType, on: boolean) =>
  FUNCTIONAL_TYPES.filter((x) => (x === t ? on : list.includes(x)))

const describedBy = (...ids: (string | false | undefined)[]) => ids.filter(Boolean).join(' ') || undefined

export default function ProductPage() {
  const navigate = useNavigate()
  const { images, references, product, ratio, run, jobId, setImages, setReferences, setRatio, setProduct: saveProduct } = useProjectStore()
  const [errors, setErrors] = useState<ProductErrors>({})
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<{ message: string; offline: boolean }>()
  // AI 생성 직전 권한 재확인(PM 11/11). 매 제출마다 다시 받으려고 store·서버 값에 넣지 않는다
  const [aiConsent, setAiConsent] = useState(false)

  // 사용자가 항목을 고치면 그 항목의 오류는 바로 지운다 (나머지는 다음 제출 때 다시 검사)
  const setError = (key: keyof ProductErrors, message?: string) => setErrors((e) => ({ ...e, [key]: message }))
  function setProduct(patch: Parameters<typeof saveProduct>[0]) {
    saveProduct(patch)
    for (const key of ['product_name', 'features', 'functional_types', 'photo_verified'] as const) {
      if (key in patch) setError(key)
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    const errs = validateProduct(images, references, product, LIMITS)
    if (!aiConsent) errs.ai_consent = '광고 활용과 외부 AI 전송 권한을 확인해 주세요.'
    setErrors(errs)
    const first = FOCUS_ORDER.find(([key]) => errs[key])
    if (first) {
      document.getElementById(first[1])?.focus()
      return
    }
    // 진행 중인 작업이 있는데 새로 제출하면 그 작업은 이 화면에서 사라진다 (서버 Job은 남음)
    if (hasUnfinishedJob() && !window.confirm('진행 중인 광고가 있습니다. 이 정보로 새로 만들면 진행 중인 광고는 이 화면에서 사라집니다. 이전 작업은 서버에 남습니다. 새로 만들까요?')) return
    setUploading(true)
    setUploadError(undefined)
    try {
      const [productFiles, referenceFiles] = await Promise.all([
        Promise.all(images.map((f) => shrinkImage(f, SHRINK))),
        Promise.all(references.map((f) => shrinkImage(f, SHRINK))),
      ])
      const job = await createJob(productFiles, referenceFiles, {
        ...productPayload(),
        brand_name: product.brand_name?.trim() || null,
        product_image_count: productFiles.length,
        reference_image_count: referenceFiles.length,
      })
      // 업로드가 성공한 뒤에 비워야 실패해도 이전 작업으로 돌아갈 수 있다
      resetJob()
      navigate('/create/copy')
      void advance(async () => job)
    } catch (err) {
      setUploadError({ message: err instanceof Error ? err.message : '사진을 올리지 못했습니다.', offline: isUnreachable(err) })
    } finally {
      setUploading(false)
    }
  }

  const busy = uploading || run.busy
  const complete = !Object.values(validateProduct(images, references, product, LIMITS)).some(Boolean)

  return (
    <StepPage
      top={
        <section className="pillbar">
          <div className="pillbar-inner">
            <StepPills />
            <div className="button-row">
              <span className="tag tag-primary"><Icon name="auto_awesome" />광고 문구 자체 검수 (참고용)</span>
              <button type="button" className="button secondary small" disabled={run.busy}
                onClick={() => { if (startNewAd()) navigate('/create/product') }}>
                <Icon name="refresh" className="label-lg" />새 광고
              </button>
            </div>
          </div>
        </section>
      }
    >
      <div className="page-head">
        <div>
          <span className="tag tag-soft"><Icon name="verified" />1단계 · 제품 정보</span>
          <h1 className="headline-lg">광고할 뷰티 제품 정보를 입력해 주세요</h1>
          <p>입력한 정보와 사진으로 광고 카피와 이미지를 만듭니다. 카피는 자체 기준으로 표현을 검수하며, 결과는 참고용입니다.</p>
        </div>
      </div>

      {/* noValidate: 브라우저 기본 말풍선 대신 각 항목 아래에 한국어 오류를 보여준다 */}
      <form id="product-form" className="product-grid" onSubmit={onSubmit} noValidate>
        <div className="stack">
          <PhotoDrop
            id="photos"
            variant="product"
            title="제품 사진 업로드"
            limits={PRODUCT_PHOTOS}
            hint={`정면 누끼 컷, 45도 앵글, 제형 스와치 컷처럼 같은 제품을 여러 각도에서 찍은 사진 ${PRODUCT_PHOTOS.minFiles}~${PRODUCT_PHOTOS.maxFiles}장을 업로드해 주세요.${import.meta.env.VITE_A51E_SIGNED_BETA_CANDIDATE === 'YES' ? ' 이번 베타에서 MPO 형식은 업로드할 수 없습니다. 휴대폰 갤러리에서 원하는 사진을 일반 JPG 또는 PNG 파일로 저장한 뒤 다시 업로드해 주세요.' : ''}`}
            files={images}
            error={errors.images}
            onChange={(files) => { setImages(files); setError('images') }}
            onError={(m) => setError('images', m)}
          />
          <PhotoDrop
            id="references"
            variant="reference"
            title="배경 레퍼런스 사진 업로드"
            limits={REFERENCE_PHOTOS}
            hint="원하시는 톤앤매너, 조명, 공간 인테리어 감성 이미지를 지정하시면 AI 모델이 조명 셋업을 모방합니다."
            files={references}
            error={errors.references}
            onChange={(files) => { setReferences(files); setError('references') }}
            onError={(m) => setError('references', m)}
          />
        </div>

        <div className="stack">
          <div className="card form-card">
            {/* 브랜드명 아래에 제품명: 한 줄 폭을 다 써서 예시 문구가 오른쪽 아이콘에 가리지 않는다 */}
            <div className="name-fields">
              <div className="field">
                <label htmlFor="brand_name" className="field-label"><span>브랜드명</span><span className="field-tag">영문 병기 추천</span></label>
                <div className="input-wrap">
                  <input id="brand_name" placeholder="예: 로즈마리 코스메틱 (Rosemary Lab)" autoComplete="off"
                    value={product.brand_name ?? ''} onChange={(e) => setProduct({ brand_name: e.target.value || null })} />
                  <Icon name="domain" />
                </div>
              </div>
              <div className="field">
                <label htmlFor="product_name" className="field-label">
                  <span>제품명 <span className="req" aria-hidden="true">*</span></span><span className="field-tag req-tag">필수</span>
                </label>
                <div className="input-wrap">
                  <input id="product_name" placeholder="예: 트리플 히알루론산 딥 모이스처 비건 앰플" autoComplete="off"
                    value={product.product_name} aria-invalid={Boolean(errors.product_name)}
                    aria-describedby={describedBy(errors.product_name && 'product_name-error')}
                    onChange={(e) => setProduct({ product_name: e.target.value })} />
                  <Icon name="verified_user" className="text-primary" />
                </div>
                {errors.product_name && <p id="product_name-error" className="field-error">{errors.product_name}</p>}
              </div>
            </div>

            {/* shortcut: v0.5 product_category는 자유 문자열·필수 여부 미정이라 선택 항목으로 둔다. 다시 누르면 선택을 해제한다 */}
            <fieldset id="product_category" className="chip-group">
              <legend className="field-label"><span>제품 카테고리</span><span className="field-tag">정확한 카테고리 선택 시 특화 카피 추천</span></legend>
              <div className="chips">
                {PRODUCT_TYPES.map((t) => {
                  const on = product.product_category === t
                  return (
                    <button key={t} type="button" className="chip" aria-pressed={on}
                      onClick={() => setProduct({ product_category: on ? null : t })}>
                      {on && <Icon name="check" />}{CATEGORY_LABEL[t] ?? t}
                    </button>
                  )
                })}
              </div>
            </fieldset>

            <div className="field">
              <div className="field-label">
                <label htmlFor="features">제품 핵심 특장점 &amp; 원료 USP <span className="req" aria-hidden="true">*</span></label>
                <span className="field-tag">{product.features.length}자</span>
              </div>
              <textarea id="features" rows={4}
                placeholder="예: 히알루론산이 들어간 30ml 보습 세럼. 끈적임 없이 가볍게 스며듭니다."
                value={product.features} aria-invalid={Boolean(errors.features)}
                aria-describedby={describedBy(errors.features && 'features-error')}
                onChange={(e) => setProduct({ features: e.target.value })} />
              {errors.features && <p id="features-error" className="field-error">{errors.features}</p>}
            </div>

            <fieldset className="chip-group">
              <legend className="field-label">광고 캠페인 목표</legend>
              <div className="tiles">
                {AD_PURPOSES.map((p) => (
                  <label key={p} className={product.ad_purpose === p ? 'tile is-on' : 'tile'}>
                    <input type="radio" className="visually-hidden" name="ad_purpose" checked={product.ad_purpose === p}
                      onChange={() => setProduct({ ad_purpose: p })} />
                    <Icon name={PURPOSE_TILE[p].icon} />
                    <b>{p}</b>
                    <small>{PURPOSE_TILE[p].desc}</small>
                  </label>
                ))}
              </div>
            </fieldset>

            <div className="func-box">
              <div className="func-head">
                <div className="func-title">
                  <Icon name="health_and_safety" />
                  <span>
                    <b>기능성 화장품 심사 보고 품목인가요?</b>
                    <span className="body-sm text-variant">식약처 심사·보고를 마친 기능성 효능만 광고에 표현할 수 있습니다.</span>
                  </span>
                </div>
                <label className="switch">
                  <input type="checkbox" role="switch" className="visually-hidden" checked={product.is_functional}
                    onChange={(e) => setProduct({ is_functional: e.target.checked, functional_types: [] })} />
                  <span className="switch-track" aria-hidden="true"><span className="switch-knob" /></span>
                  {product.is_functional ? '여 (기능성 인정)' : '부 (일반 화장품)'}
                </label>
              </div>
              {product.is_functional && (
                <fieldset id="functional_types" className="func-pills" tabIndex={-1}
                  aria-describedby={describedBy('functional_types-hint', errors.functional_types && 'functional_types-error')}>
                  <legend className="visually-hidden">기능성 종류</legend>
                  {FUNCTIONAL_TYPES.map((t) => {
                    const on = product.functional_types.includes(t)
                    return (
                      <label key={t} className="func-pill">
                        <input type="checkbox" checked={on}
                          onChange={(e) => setProduct({ functional_types: toggle(product.functional_types, t, e.target.checked) })} />
                        <span>{t}{on && ' (선택됨)'}</span>
                      </label>
                    )
                  })}
                  <p id="functional_types-hint" className="field-hint" style={{ width: '100%' }}>심사·보고를 마친 기능성 효능을 모두 골라 주세요. 여드름완화는 인체세정용 제품만 해당합니다.</p>
                  {errors.functional_types && <p id="functional_types-error" className="field-error">{errors.functional_types}</p>}
                </fieldset>
              )}
            </div>

            <div className="two-col">
              <fieldset className="chip-group">
                <legend className="field-label">광고 카피 이모티콘 정도</legend>
                <div className="seg">
                  {EMOJI_LEVELS.map((v) => (
                    <label key={v} className={product.emoji_level === v ? 'is-on' : undefined}>
                      <input type="radio" className="visually-hidden" name="emoji_level" checked={product.emoji_level === v}
                        onChange={() => setProduct({ emoji_level: v })} />
                      {EMOJI_LABEL[v]}
                    </label>
                  ))}
                </div>
              </fieldset>
              <fieldset className="chip-group">
                <legend className="field-label">인스타그램 광고 규격 (비율)</legend>
                <div className="ratios">
                  {(Object.keys(RATIOS) as Ratio[]).map((r) => (
                    <label key={r} className={ratio === r ? 'ratio is-on' : 'ratio'}>
                      <input type="radio" className="visually-hidden" name="ratio" value={r} checked={ratio === r} onChange={() => setRatio(r)} />
                      <span className="ratio-shape" style={{ width: RATIO_TILE[r].w, height: RATIO_TILE[r].h }} aria-hidden="true" />
                      {RATIO_TILE[r].label}
                    </label>
                  ))}
                </div>
              </fieldset>
            </div>

            <div className={errors.photo_verified ? 'consent-box has-error' : 'consent-box'}>
              <label>
                <input id="photo_verified" type="checkbox" checked={product.photo_verified}
                  aria-invalid={Boolean(errors.photo_verified)}
                  aria-describedby={describedBy(errors.photo_verified && 'photo_verified-error')}
                  onChange={(e) => setProduct({ photo_verified: e.target.checked })} />
                <span><strong>[필수]</strong> 직접 촬영했거나 광고에 사용할 권한이 있는 사진임을 확인했습니다.</span>
              </label>
              {errors.photo_verified && <p id="photo_verified-error" className="field-error">{errors.photo_verified}</p>}
              {complete && (
                <p className="ok-line"><Icon name="check_circle" />필수 입력 항목(제품 사진 {images.length}장, 제품명, 특장점, 저작권 동의)이 모두 완벽히 충족되었습니다.</p>
              )}
            </div>
          </div>

          <div className={errors.ai_consent ? 'consent-box has-error' : 'consent-box'}>
            <label>
              <input id="ai_consent" type="checkbox" checked={aiConsent}
                aria-invalid={Boolean(errors.ai_consent)}
                aria-describedby={describedBy('ai_consent-hint', errors.ai_consent && 'ai_consent-error')}
                onChange={(e) => { setAiConsent(e.target.checked); setError('ai_consent') }} />
              <span><strong>[필수]</strong> 이 사진과 브랜드·로고를 광고에 쓰고, 광고 제작을 위해 외부 AI 서비스로 보낼 권한이 있음을 확인했습니다.</span>
            </label>
            <p id="ai_consent-hint" className="field-hint">판매자의 확인이며, 서비스가 실제 사용권을 검증하지는 않습니다.</p>
            {errors.ai_consent && <p id="ai_consent-error" className="field-error">{errors.ai_consent}</p>}
          </div>

          {!import.meta.env.DEV && jobId && !run.busy &&
            <button type="button" className="button secondary small"
              onClick={() => void recoverLiveInput().then(() => navigate('/create/copy')).catch(() => {})}>
              기존 업로드 이어서 처리하기 (재업로드 없음)
            </button>}
          {uploadError
            ? <>
              <p className="field-error" role="alert">{uploadError.message}</p>
              {import.meta.env.DEV && uploadError.offline && <MockFallback onSwitch={() => setUploadError(undefined)} />}
            </>
            : Object.values(errors).some(Boolean) && <p className="field-error">입력하지 않았거나 확인이 필요한 항목이 있습니다.</p>}
          {run.error && <p className="field-error" role="alert">{run.error}</p>}

          <div className="action-bar plain">
            <Link className="button secondary" to="/"><Icon name="arrow_back" className="label-lg" />처음으로</Link>
            <button className="button lg" type="submit" disabled={busy} aria-busy={uploading}>
              {uploading ? '사진을 올리는 중…' : '다음: 기획·카피 검토하기'}
              <Icon name="arrow_forward" className="icon-forward" />
            </button>
          </div>
        </div>
      </form>
    </StepPage>
  )
}
