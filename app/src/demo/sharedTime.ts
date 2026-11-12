/** The API supplies explicit UTC ISO-8601 only. Never parse legacy naive shared_at. */
const missing = '공유 시각 확인 불가'

export function formatSharedAtKST(utc: string | null | undefined): string {
  if (typeof utc !== 'string' ||
      !/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|\+00:00)$/.test(utc)) {
    return missing
  }
  const time = new Date(utc)
  if (!Number.isFinite(time.getTime()) ||
      time.toISOString().slice(0, 19) !== utc.slice(0, 19)) return missing
  return '공유 시각: ' + new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hourCycle: 'h23',
  }).format(time) + ' KST'
}
