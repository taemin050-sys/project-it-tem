import { useState, type DragEvent } from 'react'
import { useObjectUrls } from '../lib/useObjectUrls'
import { validateImages, type Limits } from '../lib/validateImages'
import Icon from './Icon'

type Props = {
  id: string
  title: string
  /** product: 드롭존 + 정사각 썸네일, reference: 추가 줄 + 4:3 썸네일 (시안 1단계) */
  variant: 'product' | 'reference'
  limits: Limits
  hint: string
  files: File[]
  error?: string
  onChange: (files: File[]) => void
  onError: (message: string | undefined) => void
}

// 제품 사진·배경 참고 사진이 같이 쓰는 업로드 카드
export default function PhotoDrop({ id, title, variant, limits, hint, files, error, onChange, onError }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const previews = useObjectUrls(files)
  const full = files.length >= limits.maxFiles
  const product = variant === 'product'

  function add(list: FileList | null) {
    if (!list || list.length === 0) return
    const next = [...files, ...Array.from(list)]
    // 개수 미달은 제출 시점에만 알린다
    const errs = validateImages(next, { ...limits, minFiles: 0 }, title)
    onError(errs.length > 0 ? errs.join(' ') : undefined)
    if (errs.length === 0) onChange(next)
  }
  const drop = {
    onDragOver: (e: DragEvent) => { e.preventDefault(); setDragOver(true) },
    onDragLeave: () => setDragOver(false),
    onDrop: (e: DragEvent) => { e.preventDefault(); setDragOver(false); add(e.dataTransfer.files) },
  }
  const input = (
    <input id={id} type="file" className="visually-hidden" accept={limits.acceptTypes.join(',')} multiple disabled={full}
      aria-describedby={[`${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ')} aria-invalid={Boolean(error)}
      onChange={(e) => { add(e.target.files); e.target.value = '' }} />
  )

  return (
    <section className="card" aria-labelledby={`${id}-title`}>
      <div className="card-head">
        <h2 id={`${id}-title`} className="card-title headline-sm">
          <Icon name={product ? 'photo_library' : 'palette'} className={product ? 'text-primary' : 'text-secondary'} />
          {title}{product && <span className="req" aria-label="필수">*</span>}
        </h2>
        <span className={product ? 'tag tag-primary' : 'tag tag-secondary'}>
          {files.length} / {limits.maxFiles}장 {product ? `(필수 ${limits.minFiles}장 이상)` : '(선택)'}
        </span>
      </div>
      <p id={`${id}-hint`} className="body-sm text-variant">{hint}</p>

      {product
        ? (
          <label htmlFor={id} className={['dropzone', dragOver && 'drag-over', full && 'is-full', error && 'has-error'].filter(Boolean).join(' ')} {...drop}>
            {input}
            <span className="drop-icon"><Icon name="cloud_upload" /></span>
            <span className="label-md">
              {full ? `사진 ${limits.maxFiles}장을 모두 올렸습니다` : <>제품 사진 끌어다 놓기 또는 <span className="drop-link">파일 찾기</span></>}
            </span>
            <span className="body-sm text-variant">JPG, PNG, WEBP (큰 사진은 자동으로 줄여서 올립니다)</span>
          </label>
        )
        : (
          <label htmlFor={id} className={['ref-row', error && 'has-error'].filter(Boolean).join(' ')} {...drop}>
            {input}
            <span className="ref-row-label"><Icon name="add_photo_alternate" />{full ? `사진 ${limits.maxFiles}장을 모두 올렸습니다` : '무드보드 레퍼런스 추가하기'}</span>
            {!full && <span className="ref-row-btn" aria-hidden="true">+ 파일 선택</span>}
          </label>
        )}
      {error && <p id={`${id}-error`} className="field-error">{error}</p>}

      {files.length > 0 && (
        <ul className={product ? 'thumb-grid' : 'thumb-grid ref'} aria-label={`추가한 ${title}`}>
          {files.map((file, i) => (
            <li key={`${i}-${file.name}`} className="thumb">
              {previews[i] && <img src={previews[i]} alt={`${title} ${i + 1}`} />}
              {product && i === 0 && <span className="thumb-badge">대표 이미지</span>}
              <button type="button" className="thumb-del" aria-label={`${title} ${i + 1} 삭제`}
                onClick={() => onChange(files.filter((_, j) => j !== i))}>
                <Icon name="close" />
              </button>
              <span className="thumb-name" title={file.name}>{file.name}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
