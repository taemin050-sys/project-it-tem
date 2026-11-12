/** These links describe independently approved revisions, never the original dual candidates. */
export default function RevisionResultLinks({completed}: {completed: {composed: boolean; freeform: boolean}}) {
  const count = Number(completed.composed) + Number(completed.freeform)
  if (!count) return null
  return <section className="notice notice-info stack" aria-label="승인된 수정본 저장">
    <p><strong>승인된 수정본 {count}개를 저장할 수 있습니다.</strong></p>
    <p className="field-hint">수정본은 별도로 검수·승인한 결과입니다. 원본 시안의 검토·거절 상태는 그대로 유지됩니다.</p>
    <nav className="button-row" aria-label="수정본 다운로드로 이동">
      {completed.composed && <a className="button small" href="#result-revisions-composed">승인된 합성형 수정본 저장</a>}
      {completed.freeform && <a className="button small" href="#result-revisions-freeform">승인된 자유형 수정본 저장</a>}
    </nav>
  </section>
}
