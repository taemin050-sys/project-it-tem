import { Link, Navigate } from 'react-router-dom'
import { useJob } from '../api/useJob'
import JobStatusView from '../components/JobStatusView'
import { useProjectStore } from '../store/projectStore'

export default function CopyPage() {
  const jobId = useProjectStore((s) => s.jobId)
  const { data: job, error, isPending } = useJob()

  if (jobId === null) return <Navigate to="/product" replace />
  if (error) return <p className="errors" role="alert">{error.message}</p>
  if (isPending) return <p>불러오는 중…</p>

  const result = job.result
  return (
    <section>
      <h1>기획·카피</h1>
      <JobStatusView job={job} />

      {result && (
        <>
          <h2>제품 분석</h2>
          <dl className="kv">
            <dt>제품 유형</dt><dd>{result.analysis.product_type}</dd>
            <dt>용기</dt><dd>{result.analysis.container}</dd>
            <dt>색상</dt><dd>{result.analysis.colors.join(', ')}</dd>
            <dt>라벨</dt><dd>{result.analysis.label_text}</dd>
            <dt>무드</dt><dd>{result.analysis.mood}</dd>
          </dl>

          <h2>광고 문구</h2>
          <dl className="kv">
            <dt>헤드라인</dt><dd>{result.copy.headline}</dd>
            <dt>서브</dt><dd>{result.copy.subline}</dd>
            <dt>CTA</dt><dd>{result.copy.cta}</dd>
            <dt>캡션</dt><dd>{result.copy.caption}</dd>
            <dt>해시태그</dt><dd>{result.copy.hashtags.join(' ')}</dd>
          </dl>

          {result.review.length > 0 && (
            <>
              <h2>표현 검수 (참고용, 법률 검토를 대체하지 않습니다)</h2>
              <ul>
                {result.review.map((r) => (
                  <li key={r.expression}>
                    <mark>{r.expression}</mark> — {r.reason} → 제안: {r.suggestion}
                  </li>
                ))}
              </ul>
            </>
          )}

          <Link className="button" to="/draft">다음: 이미지 시안</Link>
        </>
      )}
    </section>
  )
}
