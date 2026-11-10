import { useState } from 'react'
import { useObjectUrls } from '../lib/useObjectUrls'
import { validateImages, type Limits } from '../lib/validateImages'
import {hasMpoPrimarySignature,isMpoFile} from '../lib/mpo'
import {A51D_MPO_FIXTURE, requiresMpoFixtureSelection, inspectMpoFixture,
  confirmMpoFixtureFrame, confirmedMpoChoice, type PreviewReceipt
} from '../lib/a51dMpoSelection'

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
  const [confirmBusy, setConfirmBusy] = useState(false)
  // In this *OFFLINE_FIXTURE* build an MPO source requires an actual preview
  // selection before appearing in the product input. No silent frame-zero.
  const [pending, setPending] = useState<{
    next: File[]
    items: { file: File; receipt: PreviewReceipt }[]
    selected: Record<number, number>
  }>()
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
    if (A51D_MPO_FIXTURE) {
      try {
        const items: { file: File; receipt: PreviewReceipt }[] = []
        for (const f of next) {
          if (await requiresMpoFixtureSelection(f) && !confirmedMpoChoice(f)) {
            items.push({file: f, receipt: await inspectMpoFixture(f)})
          }
        }
        if (items.length) {
          setPending({next, items, selected: {}})
          return
        }
      } catch {
        onError('MPO 프레임 미리보기를 가져오지 못했습니다. 다시 선택해 주세요.')
        return
      }
    }
    setPending(undefined)
    onChange(next)
  }

  async function confirmPending() {
    if (!pending || confirmBusy ||
        pending.items.some((_, i) => pending.selected[i] === undefined)) return
    setConfirmBusy(true)
    try {
      for (let i=0;i<pending.items.length;i++) {
        const {file,receipt}=pending.items[i]
        await confirmMpoFixtureFrame(file,receipt,pending.selected[i])
      }
      onError(undefined)
      onChange(pending.next)
      setPending(undefined)
    } catch {
      onError('서버에서 MPO 프레임 선택을 확인하지 못했습니다. 사진을 다시 선택해 주세요.')
      setPending(undefined)
    } finally {
      setConfirmBusy(false)
    }
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
      {A51D_MPO_FIXTURE && pending && (
        <section aria-label="MPO 프레임 직접 선택" className="panel">
          <p>이 사진은 여러 프레임이 있는 MPO입니다. 광고에 사용할 프레임을 직접 확인하고 선택하세요.</p>
          {pending.items.map(({file, receipt}, i) => (
            <div key={i}>
              <p>{file.name} — {receipt.source_frame_count}개 프레임</p>
              <div className="thumbs">
                {receipt.frames.map(frame => (
                  <button key={frame.index} type="button" className="button secondary small"
                    aria-pressed={pending.selected[i] === frame.index}
                    onClick={() => setPending(prev => prev
                      ? {...prev, selected: {...prev.selected, [i]: frame.index}} : prev)}>
                    <img src={frame.preview_data_uri}
                      alt={`${file.name} 프레임 ${frame.index+1} 선택 미리보기`}
                      width={140} height={140} style={{objectFit:'contain'}}/>
                    <span>프레임 {frame.index+1}{pending.selected[i]===frame.index ? ' · 선택됨' : ''}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          <button type="button" className="button"
            disabled={confirmBusy || pending.items.some((_, i) => pending.selected[i] === undefined)}
            onClick={() => void confirmPending()}>
            {confirmBusy ? '선택 확인 중…' : '선택한 프레임 확정'}
          </button>
          <button type="button" className="button secondary"
            onClick={() => setPending(undefined)}>취소</button>
        </section>
      )}

      {files.length > 0 && (
        <ul className="thumbs" aria-label={`추가한 ${title}`}>
          {files.map((file, i) => (
            <li key={`${i}-${file.name}`} className="thumb">
              {A51D_MPO_FIXTURE && confirmedMpoChoice(file) &&
                <img src={confirmedMpoChoice(file)!.preview_data_uri} alt={`${title} ${i + 1} — 선택한 프레임`}/>}
              {previews[i] && !confirmedMpoChoice(file) && !isMpoFile(file) &&
                <img src={previews[i]} alt={`${title} ${i + 1}`}/>}
              {isMpoFile(file) && !confirmedMpoChoice(file) &&
                <span className="muted" aria-label="레거시 MPO 첫 프레임 변환">MPO · 서버에서 첫 프레임 변환</span>}
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
