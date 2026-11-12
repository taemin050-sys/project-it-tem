export type RevisionCostAttempt = {
  attempt_id: string; stage: string; state: string; model: string | null
  usage: Record<string, number> | null; billing_unknown: boolean; actual_usd: null
  receipt_sha?: string | null; provider_response_id?: string | null
}
export type RevisionCostGroup = {
  revision_id: string; kind: 'image_correction' | 'composed_copy_edit'; state: string
  provider_attempt_count: number; status: string; actual_usd: null; attempts: RevisionCostAttempt[]
}
export type RevisionCostSummary = {
  provider_attempt_count: number; status: string; actual_usd: null
  attempts: RevisionCostAttempt[]; revisions: RevisionCostGroup[]
  classification_status?: string; unclassified_uncertain_attempt_count?: number
}

const STATUS: Record<string, string> = {
  NO_NEW_PROVIDER_CALL: '원본 획 정밀 교정 · 추가 모델 호출 없음',
  NOT_DISPATCHED: '아직 모델을 호출하지 않았습니다.',
  AWAITING_RECEIPT: '요청을 전송했습니다. 사용량 영수증을 기다리고 있습니다.',
  UNPRICED: '사용량은 기록됐으며 실제 USD 청구액은 확인 전입니다.',
  BILLING_UNKNOWN: '과금 여부 확인이 필요합니다. 자동으로 다시 호출하지 않습니다.',
}
const LABEL = {image_correction: '자유형 오타 수정 · 이미지 편집', composed_copy_edit: '합성형 문구 수정 · LLM 검수'}
const COUNT = new Intl.NumberFormat('ko-KR')
const count = (n: number | undefined) => typeof n === 'number' && Number.isSafeInteger(n) && n >= 0 ? COUNT.format(n) : '확인 중'

export default function RevisionCostDetails({cost, revisionId}: {
  cost: RevisionCostSummary | undefined; revisionId?: string
}) {
  if (!cost) return null
  const groups = revisionId ? cost.revisions.filter(row => row.revision_id === revisionId) : cost.revisions
  const calls = groups.reduce((total, row) => total + row.provider_attempt_count, 0)
  return <details className="stack revision-cost-details" data-testid="revision-cost-details">
    <summary>수정 요청 사용량 · 모델 호출 {count(calls)}회</summary>
    <p className="field-hint">수정 요청의 사용량입니다. 최초 광고 생성 사용량과 구분하며 전체 Job 비용에 중복으로 더하지 않습니다.</p>
    {cost.classification_status && cost.classification_status !== 'COMPLETE' &&
      <p role="alert">일부 요청의 비용 원장 결속을 확인 중입니다. 확인되지 않은 금액을 0 USD로 처리하지 않습니다.</p>}
    {Boolean(cost.unclassified_uncertain_attempt_count) &&
      <p role="alert">이 Job의 다른 요청에도 과금·영수증 확인이 필요한 기록이 있습니다.</p>}
    {groups.length === 0 ? <p className="muted">수정 요청 기록이 없습니다.</p> : groups.map(group => <section className="stack" key={group.revision_id}>
      <h5>{LABEL[group.kind]}</h5>
      <p>모델 호출 {count(group.provider_attempt_count)}회 · {STATUS[group.status] ?? '사용량 기록을 확인하고 있습니다.'}</p>
      {group.attempts.map(attempt => <AttemptDetails key={attempt.attempt_id} attempt={attempt} />)}
    </section>)}
    <p className="field-hint">USD_UNRECONCILED · 실제 청구액 미대사. 표시된 토큰 수는 청구 금액이나 예산 잔액을 의미하지 않습니다.</p>
  </details>
}

function AttemptDetails({attempt}: {attempt: RevisionCostAttempt}) {
  const usage = attempt.usage
  return <details className="stack">
    <summary>{attempt.stage === 'image' ? '이미지 편집' : '카피 LLM 검수'} · {attempt.model ?? '모델 확인 중'}</summary>
    {(attempt.billing_unknown || attempt.state === 'BILLING_UNKNOWN') && <p role="alert">과금 미확정 · 자동 재호출 차단</p>}
    {usage ? <dl>
      <dt>입력 토큰</dt><dd>{count(usage.input_tokens)}</dd>
      <dt>출력 토큰</dt><dd>{count(usage.output_tokens)}</dd>
      <dt>전체 토큰</dt><dd>{count(usage.total_tokens)}</dd>
    </dl> : <p className="muted">Provider 사용량 영수증 대기</p>}
    <dl style={{overflowWrap: 'anywhere'}}>
      <dt>Attempt</dt><dd>{attempt.attempt_id}</dd>
      {attempt.receipt_sha && <><dt>Receipt SHA-256</dt><dd>{attempt.receipt_sha}</dd></>}
      {attempt.provider_response_id && <><dt>Provider 응답</dt><dd>{attempt.provider_response_id}</dd></>}
    </dl>
  </details>
}
