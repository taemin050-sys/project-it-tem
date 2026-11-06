import { useEffect,useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { isUnreachable } from '../api/client'
import { createJob } from '../api/jobs'
import {getTextCostEstimate,getTotalCostEstimate,
  type TextCostEstimate,type CombinedCostEstimate} from '../api/liveJobs'
import { advance,hasUnfinishedJob,productPayload,recoverLiveInput,resetJob } from '../api/useJob'
import Field from '../components/Field'
import MockFallback from '../components/MockFallback'
import OptionGroup from '../components/OptionGroup'
import PhotoDrop from '../components/PhotoDrop'
import StepPage from '../components/StepPage'
import { PRODUCT_PHOTOS, RATIOS, REFERENCE_PHOTOS, SHRINK, type Ratio } from '../config'
import { shrinkImage } from '../lib/shrinkImage'
import { validateProduct, type ProductErrors } from '../lib/validateProduct'
import { useProjectStore } from '../store/projectStore'
import { AD_PURPOSES, EMOJI_LEVELS, FUNCTIONAL_TYPES, PRODUCT_TYPES, type EmojiLevel, type FunctionalType } from '../types/textSchema'

const LIMITS = { product: PRODUCT_PHOTOS, reference: REFERENCE_PHOTOS }

// 제출 시 첫 오류 항목으로 포커스를 옮기기 위한 순서와 대상 id
const FOCUS_ORDER: [keyof ProductErrors, string][] = [
  ['images', 'photos'],
  ['references', 'references'],
  ['product_name', 'product_name'],
  ['features', 'features'],
  ['functional_types', 'functional_types'],
  ['photo_verified', 'photo_verified'],
]

// 텍스트 schemas.py emoji_level 설명과 같은 뜻
const EMOJI_DESC: Record<EmojiLevel, string> = {
  없음: '이모티콘 없이 차분하게',
  보통: '문단마다 1~2개',
  많이: '거의 모든 줄 + 친근한 말투',
}

// 기능성 종류 목록 순서를 유지한 채 켜고 끈다
const toggle = (list: FunctionalType[], t: FunctionalType, on: boolean) =>
  FUNCTIONAL_TYPES.filter((x) => (x === t ? on : list.includes(x)))

const describedBy = (...ids: (string | false | undefined)[]) => ids.filter(Boolean).join(' ') || undefined

export default function ProductPage() {
  const navigate = useNavigate()
  const { images, references, product, ratio, generationMode, mock, run, jobId, setImages, setReferences, setRatio, setGenerationMode, setProduct: saveProduct } = useProjectStore()
  const [errors, setErrors] = useState<ProductErrors>({})
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<{ message: string; offline: boolean }>()
  const [textEstimate,setTextEstimate]=useState<{photoCount:number;estimate:TextCostEstimate}>()
  const [combinedEstimate,setCombinedEstimate]=useState<{key:string;estimate:CombinedCostEstimate}>()
  useEffect(()=>{
    let active=true
    if(!mock && images.length>=2 && images.length<=5){
      void getTextCostEstimate(images.length).then(value=>{
        if(active)setTextEstimate({photoCount:images.length,estimate:value})
      }).catch(()=>{})
    }
    return ()=>{active=false}
  },[images.length,mock])
  const currentEstimate=(!mock && images.length===textEstimate?.photoCount)
    ? textEstimate.estimate:undefined
  const estimateKey=images.length+':'+ratio+':'+generationMode
  useEffect(()=>{
    let active=true
    if(!mock && images.length>=2 && images.length<=5){
      void getTotalCostEstimate(images.length,ratio,generationMode).then(value=>{
        if(active)setCombinedEstimate({key:estimateKey,estimate:value})
      }).catch(()=>{if(active)setCombinedEstimate(undefined)})
    }
    return ()=>{active=false}
  },[estimateKey,images.length,mock,ratio,generationMode])
  const currentCombined=!mock && combinedEstimate?.key===estimateKey
    ? combinedEstimate.estimate:undefined

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
  // All three ratios are accepted by the Owner #23 size-only contract.
  const ratioBlocked = false

  return (
    <StepPage
      title="제품 정보"
      description="광고에 사용할 제품 사진과 정보를 입력해 주세요."
      back={{ to: '/', label: '처음으로' }}
      actions={
        <button className="button" type="submit" form="product-form"
          disabled={busy || ratioBlocked} aria-busy={uploading}>
          {uploading ? '사진을 올리는 중…' : '다음: 기획·카피 만들기'}
        </button>
      }
      actionsNote={
        <>
          {!mock && <p className="field-hint" role="status">
            {currentEstimate
              ? <>텍스트 AI 예상 비용: <strong>{currentEstimate.display}</strong>
                  {' '}({images.length}장 기준)</>
              : '텍스트 AI 예상 비용: 제품 사진 2~5장을 선택하면 서버에서 조회합니다.'}
            {currentCombined && <>
              {' '}이미지 1장 참고 비용:{' '}
              {currentCombined.image.reference_median_usd===null
                ? '동일 생성 방식의 표본 부족으로 산출 불가'
                : <strong>${currentCombined.image.reference_median_usd.toFixed(4)}</strong>}
              {currentCombined.total_display && <>
                {' '}텍스트+이미지 참고 합계: <strong>{currentCombined.total_display}</strong>
              </>}
              {' '}(<span>{currentCombined.image.sample_count}건 관측 표본, 실제 청구액·상한 보장 아님</span>)
            </>}
            {' '}선택한 모델·품질·화면비·방식이 관측값과 다르면 비용을 추정하지 않습니다.
          </p>}
        {!import.meta.env.DEV && jobId && !run.busy &&
          <button type="button" className="button secondary small"
            onClick={()=>void recoverLiveInput().then(()=>navigate('/create/copy')).catch(()=>{})}>
            기존 업로드 이어서 처리하기 (재업로드 없음)
          </button>}
        {uploadError
          ? (
            <>
              <p className="field-error" role="alert">{uploadError.message}</p>
              {import.meta.env.DEV && uploadError.offline && <MockFallback onSwitch={() => setUploadError(undefined)} />}
            </>
          )
          : Object.values(errors).some(Boolean) && <p className="field-error">입력하지 않았거나 확인이 필요한 항목이 있습니다.</p>}
        {run.error && <p className="field-error" role="alert">{run.error}</p>}
        </>
      }
    >
      {/* noValidate: 브라우저 기본 말풍선 대신 각 항목 아래에 한국어 오류를 보여준다 */}
      <form id="product-form" className="stack" onSubmit={onSubmit} noValidate>
        <PhotoDrop
          id="photos"
          title="제품 사진"
          limits={PRODUCT_PHOTOS}
          hint={`같은 제품을 정면·후면·측면 등 여러 각도에서 찍은 사진 ${PRODUCT_PHOTOS.minFiles}~${PRODUCT_PHOTOS.maxFiles}장. JPG·PNG·WEBP, 큰 사진은 자동으로 줄여서 올립니다.`}
          files={images}
          error={errors.images}
          onChange={(files) => { setImages(files); setError('images') }}
          onError={(m) => setError('images', m)}
        />
        <PhotoDrop
          id="references"
          title="배경 참고 사진"
          limits={REFERENCE_PHOTOS}
          hint={`원하는 배경·구도가 담긴 사진 최대 ${REFERENCE_PHOTOS.maxFiles}장. 없으면 비워 두세요.`}
          files={references}
          error={errors.references}
          onChange={(files) => { setReferences(files); setError('references') }}
          onError={(m) => setError('references', m)}
        />

        <section className="panel" aria-labelledby="basic-title">
          <h2 id="basic-title" className="panel-title">기본 정보</h2>
          <div className="field-grid">
            <Field id="brand_name" label="브랜드명">
              <input
                id="brand_name"
                placeholder="예: 라움"
                autoComplete="off"
                value={product.brand_name ?? ''}
                onChange={(e) => setProduct({ brand_name: e.target.value || null })}
              />
            </Field>
            <Field id="product_name" label="제품명" required error={errors.product_name}>
              <input
                id="product_name"
                placeholder="예: 글로우 보습 세럼"
                autoComplete="off"
                value={product.product_name}
                aria-invalid={Boolean(errors.product_name)}
                aria-describedby={describedBy(errors.product_name && 'product_name-error')}
                onChange={(e) => setProduct({ product_name: e.target.value })}
              />
            </Field>
            {/* shortcut: v0.5 product_category는 자유 문자열·필수 여부 미정이라 ProductType 목록을 선택 항목으로 둔다 */}
            <Field id="product_category" label="제품 카테고리">
              <select
                id="product_category"
                value={product.product_category ?? ''}
                onChange={(e) => setProduct({ product_category: e.target.value || null })}
              >
                <option value="">선택 안 함</option>
                {PRODUCT_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Field>
            <div className="span-2">
              <Field id="features" label="제품 특징" required hint="성분, 사용감, 용량, 가격·혜택 등 광고에 담고 싶은 내용을 자유롭게 적어 주세요." error={errors.features}>
                <textarea
                  id="features"
                  rows={5}
                  placeholder="예: 히알루론산이 들어간 30ml 보습 세럼. 끈적임 없이 가볍게 스며듭니다."
                  value={product.features}
                  aria-invalid={Boolean(errors.features)}
                  aria-describedby={describedBy('features-hint', errors.features && 'features-error')}
                  onChange={(e) => setProduct({ features: e.target.value })}
                />
              </Field>
            </div>
          </div>
        </section>

        <section className="panel" aria-label="광고 목적">
          <OptionGroup
            legend="광고 목적"
            name="ad_purpose"
            value={product.ad_purpose}
            options={AD_PURPOSES.map((p) => ({ value: p, label: p }))}
            onChange={(v) => setProduct({ ad_purpose: v })}
          />
        </section>

        <section className="panel" aria-label="이모티콘">
          <OptionGroup
            legend="게시글 이모티콘"
            name="emoji_level"
            value={product.emoji_level}
            options={EMOJI_LEVELS.map((v) => ({ value: v, label: v, desc: EMOJI_DESC[v] }))}
            onChange={(v) => setProduct({ emoji_level: v })}
          />
          <p className="field-hint panel-footnote">게시글 본문에만 들어갑니다. 이미지 위 문구·해시태그에는 넣지 않습니다.</p>
        </section>

        <section className="panel" aria-label="화장품 구분">
          <OptionGroup
            legend="화장품 구분"
            name="is_functional"
            value={product.is_functional ? 'functional' : 'general'}
            options={[
              { value: 'general', label: '일반 화장품', desc: '기능성 인증을 받지 않은 제품' },
              { value: 'functional', label: '기능성 화장품', desc: '식약처 심사·보고를 마친 기능성화장품' },
            ]}
            onChange={(v) => setProduct({ is_functional: v === 'functional', functional_types: [] })}
          />
          {product.is_functional && (
            <fieldset id="functional_types" className="subgroup check-group" tabIndex={-1}
              aria-describedby={describedBy('functional_types-hint', errors.functional_types && 'functional_types-error')}>
              <legend className="group-label">기능성 종류</legend>
              <p id="functional_types-hint" className="field-hint">
                심사·보고받은 기능성 종류를 선택하세요. 종류를 확실히 모르면 선택하지 않아도
                진행할 수 있지만 모든 기능성 효능 표현에 '근거 확인 필요' 경고가 표시됩니다.
                여드름완화는 인체세정용 제품만 해당합니다.
              </p>
              {!mock && <p className="field-hint" role="status">
                선택한 종류는 Text Owner v0.10의 생성·규제 검수에 전달됩니다.
                선택만으로 실제 심사·보고 여부나 효능 광고 근거가 증명되지는 않습니다.
              </p>}
              <div className="check-grid">
                {FUNCTIONAL_TYPES.map((t) => (
                  <label key={t} className="check-item">
                    <input type="checkbox" checked={product.functional_types.includes(t)}
                      onChange={(e) => setProduct({ functional_types: toggle(product.functional_types, t, e.target.checked) })} />
                    {t}
                  </label>
                ))}
              </div>
              {errors.functional_types && <p id="functional_types-error" className="field-error">{errors.functional_types}</p>}
            </fieldset>
          )}
        </section>

        <section className="panel" aria-label="이미지 생성 방식">
          <OptionGroup legend="이미지 생성 방식 · 이미지 1장" name="generation-mode"
            value={generationMode} onChange={setGenerationMode}
            disabled={Boolean(jobId) && hasUnfinishedJob()}
            options={[
              {value:'composed' as const,label:'합성형',desc:'AI로 제품·배경을 생성하고 서버가 승인 문구를 한글 폰트로 합성'},
              {value:'freeform' as const,label:'자유형',desc:'AI가 승인 문구와 제품을 이미지에 직접 그림 · 정확도 수동 검수 필요'},
            ]} />
          <p className="field-hint">생성 방식은 서버 Job에 고정됩니다. 자유형의 한글·제품 형태·라벨 정확도는 보장되지 않습니다.</p>
        </section>
        <section className="panel" aria-label="이미지 비율">
          <OptionGroup
            legend="이미지 비율"
            name="ratio"
            value={ratio}
            options={(Object.keys(RATIOS) as Ratio[]).map((r) => ({ value: r, label: RATIOS[r].label, desc: `${RATIOS[r].desc} · ${RATIOS[r].width}×${RATIOS[r].height}` }))}
            onChange={setRatio}
          />
          {!mock && <p className="field-hint" role="status">
            선택한 최종 크기는 Server Job에 저장되어 Image Owner의 생성·합성 프로필로 전달됩니다.
            3:4·4:5·9:16의 실제 모델 품질은 아직 검증되지 않았습니다.
          </p>}
        </section>

        <div className={errors.photo_verified ? 'consent has-error' : 'consent'}>
          <label className="consent-label">
            <input
              id="photo_verified"
              type="checkbox"
              checked={product.photo_verified}
              aria-invalid={Boolean(errors.photo_verified)}
              aria-describedby={describedBy(errors.photo_verified && 'photo_verified-error')}
              onChange={(e) => setProduct({ photo_verified: e.target.checked })}
            />
            <span>
              <strong>사진 사용 권한을 확인했습니다</strong>
              <span className="field-hint">직접 촬영했거나 광고에 사용할 권한이 있는 사진입니다.</span>
            </span>
          </label>
          {errors.photo_verified && <p id="photo_verified-error" className="field-error">{errors.photo_verified}</p>}
        </div>
      </form>
    </StepPage>
  )
}
