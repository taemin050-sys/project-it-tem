import type { Insight, ResearchResult, SourceType } from '../types/textSchema'

const SOURCE_BADGE: Record<SourceType, { label: string; tone: string }> = {
  '사용자 입력': { label: '사용자 입력', tone: 'neutral' },
  '검색 결과': { label: '검색 결과', tone: 'success' },
  'AI 추론': { label: 'AI 추론·의견', tone: 'warning' },
}

function ResearchLines({ lines }: { lines: Insight[] }) {
  return (
    <ul className="plain-list summary-list">
      {lines.map((line, index) => (
        <li key={index}>
          <span className={'badge badge-' + SOURCE_BADGE[line.source].tone}>
            {SOURCE_BADGE[line.source].label}
          </span> {line.text}
          {line.source === '검색 결과' && line.citations?.map((citation) => (
            <span key={citation.url}> · <a className="text-link" href={citation.url}
              target="_blank" rel="noreferrer">{citation.title ?? citation.url}</a></span>
          ))}
        </li>
      ))}
    </ul>
  )
}

export default function ResearchPanel({ research }: { research: ResearchResult }) {
  return (
    <section className="panel" aria-labelledby="research-title">
      <h2 id="research-title" className="panel-title">AI 사전 조사 요약</h2>
      {!research.research_performed && (
        <p className="notice notice-warning">
          외부 검색을 완료하지 못해 입력 정보와 AI 추론을 바탕으로 정리했습니다.
        </p>
      )}
      <ResearchLines lines={research.research.display_summary} />
      <p className="field-hint">
        AI 추론·의견은 근거가 확인되지 않은 내용입니다. 검색 자료는 연결된 문장의 출처를 확인하는 데 사용하세요.
      </p>
      {research.research.market_insights.length > 0 && <details className="source-group">
        <summary className="group-label">시장 조사와 출처</summary>
        <ResearchLines lines={research.research.market_insights} />
      </details>}
      {research.research.similar_products.length > 0 && <details className="source-group">
        <summary className="group-label">유사 제품 조사와 출처</summary>
        <ResearchLines lines={research.research.similar_products} />
      </details>}
    </section>
  )
}
