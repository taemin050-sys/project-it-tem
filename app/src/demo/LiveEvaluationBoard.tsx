import { useCallback, useEffect, useState } from 'react'
import './LiveEvaluationBoard.css'
import { formatSharedAtKST } from './sharedTime'
import {displayActualArtwork} from './sharedArtworkDisplay'

type Shared = {job_id: string; final_sha: string; shared_at: string; shared_at_utc: string | null;
  integrity_status: 'VERIFIED' | 'UNAVAILABLE';
  image_size: '3:4' | '4:5' | '9:16' | null;
  output_size: {width:number;height:number} | null;
  dimensions_source: 'VERIFIED_FINAL_PNG' | 'UNAVAILABLE'}
type Rated = {score: number; comment: string; category: string; artifact_sha256: string; revision: number}
const categories = [
  ['product_recognition', '제품 분석 정확도'],
  ['plan_copy_compliance', '기획·카피·규제 적절성'],
  ['image_fidelity', '제품 이미지 보존'],
  ['final_layout_korean', '한국어 합성·가독성'],
  ['speed_reliability', '속도·안정성'],
  ['ui_ux', 'UI/UX'],
] as const
const api = '/demo/api/live'

async function json<T>(url: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    ...(body === undefined ? {} : {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  })
  if (!response.ok) throw new Error('요청에 실패했습니다. (HTTP ' + response.status + ')')
  return response.json() as Promise<T>
}

const categoryLabel = (category: string) =>
  categories.find(([key]) => key === category)?.[1] ?? category

export default function LiveEvaluationBoard() {
  const [items, setItems] = useState<Shared[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [category, setCategory] = useState<string>(categories[0][0])
  const [score, setScore] = useState(3)
  const [comment, setComment] = useState('')
  const [reviews, setReviews] = useState<Rated[]>([])
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    const data = await json<{jobs: Shared[]}>(api + '/shared')
    setItems(data.jobs)
    setSelected(old => old && data.jobs.some(x => x.job_id === old && x.integrity_status === 'VERIFIED')
      ? old : null)
  }, [])

  useEffect(() => {
    let active = true
    void json<{jobs: Shared[]}>(api + '/shared')
      .then(data => { if (active) setItems(data.jobs) })
      .catch(() => { if (active) setError('공유 광고 목록을 불러오지 못했습니다.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function choose(jobId: string) {
    if (items.find(item=>item.job_id===jobId)?.integrity_status !== 'VERIFIED') {
      setSelected(null)
      setError('산출물 무결성을 확인할 수 없어 평가할 수 없습니다.')
      return
    }
    setSelected(jobId)
    setReviews([])
    setMessage('')
    setError('')
    try {
      const data = await json<{reviews: Rated[]}>(api + '/shared/' + jobId + '/evaluations')
      setReviews(data.reviews)
    } catch {
      setError('본인 평가 기록을 불러오지 못했습니다. 다시 선택해 주세요.')
    }
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected || saving || items.find(x=>x.job_id===selected)?.integrity_status !== 'VERIFIED'
      || !Number.isInteger(score) || score < 1 || score > 5) return
    setSaving(true)
    setMessage('')
    setError('')
    try {
      const result = await json<{saved: boolean}>(api + '/shared/' + selected + '/evaluations', 'POST', {
        job_id: selected,
        scenario_id: 'UC-01',
        category,
        score,
        comment,
        needs_improvement: score <= 2,
      })
      if (result.saved) {
        setMessage('이 광고의 최종 파일 버전에 평가가 저장됐습니다.')
        const data = await json<{reviews: Rated[]}>(api + '/shared/' + selected + '/evaluations')
        setReviews(data.reviews)
      } else {
        setError('평가가 저장되지 않았습니다. 다시 확인해 주세요.')
      }
    } catch {
      setError('평가 저장에 실패했습니다. 로그인 및 네트워크 연결을 확인해 주세요.')
    } finally {
      setSaving(false)
    }
  }

  const chosen = items.find(item => item.job_id === selected && item.integrity_status === 'VERIFIED')
  const artwork = chosen ? displayActualArtwork(chosen) : null

  return (
    <main className="live-eval">
      <div className="step-width wide live-eval-wrap">
        <header className="live-eval-intro">
          <p className="eyebrow">TEAM REVIEW / LIVE AI</p>
          <h1>팀 공동 품질 평가</h1>
          <p className="step-desc">실제 AI로 완성한 광고를 함께 검토해 주세요. 작성자가 공개를 승인한 최종 이미지와 Caption만 보이며, 원본 제품 사진과 개별 작업 기록은 공유되지 않습니다.</p>
          <div className="notice notice-info" role="note">
            <p>평가는 실제 사람의 독립적인 판단으로 진행합니다. 1점은 개선 필요, 5점은 매우 우수입니다. AI가 표시한 1차 규칙 검수 통과는 법률 적합성 확정을 의미하지 않습니다.</p>
          </div>
        </header>

        <section className="panel live-eval-list" aria-labelledby="live-eval-list-title">
          <div className="panel-head">
            <h2 id="live-eval-list-title" className="panel-title">공유된 광고</h2>
            <button type="button" className="button secondary small" onClick={() => void refresh().then(() => setError('')).catch(() => setError('목록 갱신 실패'))}>
              목록 새로고침
            </button>
          </div>
          {loading && <p className="muted" role="status">평가 대상을 불러오는 중입니다…</p>}
          {!loading && items.length === 0 && <div className="empty"><p className="empty-title">아직 공유된 광고가 없습니다.</p><p>광고 작성자가 최종 결과 화면에서 ‘팀 품질 평가에 명시적으로 공유’를 선택하면 여기에 표시됩니다.</p></div>}
          <ul className="live-eval-items">
            {items.map((item, i) => (
              <li key={item.job_id}>
                <button type="button" className={'live-eval-item' + (selected === item.job_id ? ' is-active' : '')}
                  aria-pressed={selected === item.job_id && item.integrity_status === 'VERIFIED'}
                  disabled={item.integrity_status !== 'VERIFIED'}
                  onClick={() => void choose(item.job_id)}>
                  <span className="live-eval-index">{String(i + 1).padStart(2, '0')}</span>
                  <span className="live-eval-item-details"><strong>{item.integrity_status === 'VERIFIED' ? '실제 AI 광고' : '검증 불가 · 평가 중지'} · {item.job_id.slice(0, 8)}</strong><small>{formatSharedAtKST(item.shared_at_utc)}</small></span>
                  <span className="live-eval-item-action">{item.integrity_status !== 'VERIFIED' ? '검증 불가' :
                      selected === item.job_id ? '선택됨' : '평가하기'}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        {chosen && selected && (
          <div className="live-eval-grid">
            <section className="panel live-eval-artwork" aria-labelledby="live-eval-artwork-title">
              <p className="eyebrow">CREATIVE / {artwork?.ratioLabel ?? '화면비 확인 불가'}</p>
              {artwork?.pixels && <p className="field-hint">
                실제 최종 광고: {artwork.pixels}
                {' · '}최종 PNG SHA 검증
              </p>}
              <h2 id="live-eval-artwork-title" className="panel-title">평가 광고 · {selected.slice(0, 8)}</h2>
              <img src={api + '/shared/' + selected + '/artifacts/final'}
                style={artwork?.aspectRatio?{aspectRatio:artwork.aspectRatio}:undefined}
                alt="팀에 명시적으로 공유된 실제 AI 광고 시안" />
              <a className="text-link" href={api + '/shared/' + selected + '/artifacts/caption'} target="_blank" rel="noopener noreferrer">Caption 확인</a>
              {chosen && <p className="field-hint">광고 파일 버전: {chosen.final_sha.slice(0, 12)}…</p>}
            </section>

            <section className="panel live-eval-review" aria-labelledby="live-eval-review-title">
              <p className="eyebrow">YOUR INDEPENDENT REVIEW</p>
              <h2 id="live-eval-review-title" className="panel-title">평가 작성</h2>
              <p className="field-hint">평가 항목별로 점수와 개선 의견을 제출할 수 있습니다.</p>
              <form className="stack live-eval-form" onSubmit={event => void submit(event)}>
                <label className="field" htmlFor="live-eval-category">
                  <span className="field-label">평가 영역</span>
                  <select id="live-eval-category" value={category} onChange={event => setCategory(event.target.value)}>
                    {categories.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
                  </select>
                </label>
                <label className="field" htmlFor="live-eval-score">
                  <span className="field-label">평가 점수 (1~5)</span>
                  <select id="live-eval-score" value={score} onChange={event => setScore(Number(event.target.value))}>
                    {[1, 2, 3, 4, 5].map(value => <option key={value} value={value}>{value}점{value === 1 ? ' · 개선 필요' : value === 5 ? ' · 매우 우수' : ''}</option>)}
                  </select>
                </label>
                <label className="field" htmlFor="live-eval-comment">
                  <span className="field-label">개선 의견 <span className="field-tag">선택</span></span>
                  <textarea id="live-eval-comment" rows={5} maxLength={1800} value={comment} onChange={event => setComment(event.target.value)} placeholder="좋았던 점, 수정이 필요한 표현 또는 이미지 요소를 적어 주세요." />
                  <span className="field-hint">{comment.length} / 1800자</span>
                </label>
                <button type="submit" className="button" disabled={saving}>{saving ? '평가 저장 중…' : '평가 저장'}</button>
              </form>
              {message && <div className="notice notice-success" role="status"><p>{message}</p></div>}
              {error && <div className="notice notice-danger" role="alert"><p>{error}</p></div>}
              <div className="live-eval-records">
                <h3>본인 평가 기록</h3>
                {reviews.length === 0 ? <p className="field-hint">이 광고에 저장한 평가 기록이 아직 없습니다.</p> : (
                  <ul>{reviews.map((review, i) => (
                    <li key={i}>
                      <div><strong>{categoryLabel(review.category)}</strong><span className="badge badge-neutral">{review.score}점</span></div>
                      {review.comment && <p>{review.comment}</p>}
                      <small>Revision {review.revision}</small>
                    </li>
                  ))}</ul>
                )}
              </div>
            </section>
          </div>
        )}
      </div>
    </main>
  )
}
