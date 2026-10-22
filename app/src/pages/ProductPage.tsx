import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { FUNCTIONAL_ITEMS, PRODUCT_TYPES, UPLOAD } from '../config'
import { validateImages } from '../lib/validateImages'
import { useProjectStore } from '../store/projectStore'

export default function ProductPage() {
  const navigate = useNavigate()
  const { images, product, setImages, setProduct } = useProjectStore()
  const [errors, setErrors] = useState<string[]>([])

  const previews = useMemo(() => images.map((f) => URL.createObjectURL(f)), [images])
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews])

  function onFiles(list: FileList | null) {
    const next = [...images, ...Array.from(list ?? [])]
    // 개수 미달은 제출 시점에만 알린다
    const errs = validateImages(next, { ...UPLOAD, minFiles: 0 })
    setErrors(errs)
    if (errs.length === 0) setImages(next)
  }

  function toggleItem(item: string) {
    const items = product.functional_items
    setProduct({ functional_items: items.includes(item) ? items.filter((i) => i !== item) : [...items, item] })
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    const errs = validateImages(images, UPLOAD)
    if (product.is_functional && product.functional_items.length === 0) errs.push('기능성 인증 항목을 1개 이상 선택해 주세요.')
    if (!product.photo_rights_confirmed) errs.push('사진 사용 권리를 확인해 주세요.')
    setErrors(errs)
    if (errs.length === 0) navigate('/settings')
  }

  return (
    <form className="form" onSubmit={onSubmit}>
      <h1>제품 정보</h1>

      <fieldset>
        <legend>제품 사진 ({images.length}/{UPLOAD.maxFiles})</legend>
        <input
          type="file"
          accept={UPLOAD.acceptTypes.join(',')}
          multiple
          disabled={images.length >= UPLOAD.maxFiles}
          onChange={(e) => {
            onFiles(e.target.files)
            e.target.value = ''
          }}
        />
        <ul className="thumbs">
          {previews.map((src, i) => (
            <li key={src}>
              <img src={src} alt={`제품 사진 ${i + 1}`} />
              <button type="button" onClick={() => setImages(images.filter((_, j) => j !== i))}>삭제</button>
            </li>
          ))}
        </ul>
      </fieldset>

      <label>
        제품명
        <input required value={product.name} onChange={(e) => setProduct({ name: e.target.value })} />
      </label>

      <label>
        제품 유형
        <select required value={product.product_type} onChange={(e) => setProduct({ product_type: e.target.value })}>
          <option value="" disabled>선택하세요</option>
          {PRODUCT_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </label>

      <label>
        용량
        <input required placeholder="예: 50ml" value={product.volume} onChange={(e) => setProduct({ volume: e.target.value })} />
      </label>

      <fieldset>
        <legend>화장품 구분</legend>
        <label className="inline">
          <input type="radio" checked={!product.is_functional} onChange={() => setProduct({ is_functional: false, functional_items: [] })} />
          일반 화장품
        </label>
        <label className="inline">
          <input type="radio" checked={product.is_functional} onChange={() => setProduct({ is_functional: true })} />
          기능성 화장품
        </label>
      </fieldset>

      {product.is_functional && (
        <fieldset>
          <legend>기능성 인증 항목</legend>
          {FUNCTIONAL_ITEMS.map((item) => (
            <label key={item} className="inline">
              <input type="checkbox" checked={product.functional_items.includes(item)} onChange={() => toggleItem(item)} />
              {item}
            </label>
          ))}
        </fieldset>
      )}

      <label className="inline">
        <input
          type="checkbox"
          checked={product.photo_rights_confirmed}
          onChange={(e) => setProduct({ photo_rights_confirmed: e.target.checked })}
        />
        직접 촬영했거나 사용 권리가 있는 사진입니다.
      </label>

      {errors.length > 0 && (
        <ul className="errors" role="alert">
          {errors.map((m) => <li key={m}>{m}</li>)}
        </ul>
      )}

      <button className="button" type="submit">다음: 광고 설정</button>
    </form>
  )
}
