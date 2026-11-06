import { useState } from 'react'
import { useObjectUrls } from '../lib/useObjectUrls'
import { validateImages, type Limits } from '../lib/validateImages'
import {hasMpoPrimarySignature,isMpoFile} from '../lib/mpo'

type Props = {
  id: string
  title: string
  limits: Limits
  hint: string
  files: File[]
  error?: string
  onChange: (files: File[]) => void
  onError: (message: string | undefined) => void
}

const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`

// 제품 사진·배경 참고 사진이 같이 쓰는 드롭존 + 썸네일 목록
export default function PhotoDrop({ id, title, limits, hint, files, error, onChange, onError }: Props) {
  const [dragOver, setDragOver] = useState(false)
  const previews = useObjectUrls(files)

  const full = files.length >= limits.maxFiles
  const required = limits.minFiles > 0

  async function add(list: FileList | null) {
    if (!list || list.length === 0) return
    const next = [...files, ...Array.from(list)]
    // 개수 미달은 제출 시점에만 알린다
    const errs = validateImages(next, { ...limits, minFiles: 0 }, title)
    onError(errs.length > 0 ? errs.join(' ') : undefined)
    if(errs.length)return
    for(const file of next){
      if(isMpoFile(file) && !(await hasMpoPrimarySignature(file))){
        onError(file.name+': MPO 사진의 MPF 구조가 올바르지 않습니다. JPEG로 변환해 주세요.')
        return
      }
    }
    onChange(next)
  }

  return (
    <section className="panel" aria-labelledby={`${id}-title`}>
      <div className="panel-head">
        <h2 id={`${id}-title`} className="panel-title">{title} <span className="field-tag">{required ? '필수' : '선택'}</span></h2>
        <span className="panel-meta">{files.length} / {limits.maxFiles}장</span>
      </div>
      <label
        htmlFor={id}
        className={['dropzone', dragOver && 'drag-over', full && 'is-full', error && 'has-error'].filter(Boolean).join(' ')}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); void add(e.dataTransfer.files) }}
      >
        <input
          id={id}
          type="file"
          className="visually-hidden"
          accept={limits.acceptTypes.join(',')}
          multiple
          disabled={full}
          aria-describedby={[`${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ')}
          aria-invalid={Boolean(error)}
          onChange={(e) => {
            void add(e.target.files)
            e.target.value = ''
          }}
        />
        <span className="dropzone-title">
          {full ? `사진 ${limits.maxFiles}장을 모두 올렸습니다` : '사진을 끌어다 놓거나 클릭해서 선택하세요'}
        </span>
        <span id={`${id}-hint`} className="field-hint">{hint}</span>
        {!full && <span className="button secondary small" aria-hidden="true">파일 선택</span>}
      </label>
      {error && <p id={`${id}-error`} className="field-error">{error}</p>}

      {files.length > 0 && (
        <ul className="thumbs" aria-label={`추가한 ${title}`}>
          {files.map((file, i) => (
            <li key={`${i}-${file.name}`} className="thumb">
              {previews[i] && !isMpoFile(file) && <img src={previews[i]} alt={`${title} ${i + 1}`} />}
              {isMpoFile(file) && <span className="muted" aria-label="MPO 첫 프레임 JPEG 변환">MPO · 서버에서 첫 프레임 변환</span>}
              <div className="thumb-info">
                <span className="thumb-name" title={file.name}>{file.name}</span>
                <span className="thumb-meta">✓ 추가됨 · {formatSize(file.size)}</span>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label={`${title} ${i + 1} 삭제`}
                onClick={() => onChange(files.filter((_, j) => j !== i))}
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
