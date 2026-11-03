import { isMockJob } from '../lib/pipeline'
import { QA_OFFLINE_FIXTURE } from '../config'
import { useProjectStore } from '../store/projectStore'
import type { Job } from '../types/draft'

type Badge = { label: string; value: string; tone: 'success' | 'warning' | 'danger' | 'neutral' }

const PRESERVATION: Record<string, string> = { pending: '검토 전', passed: '통과', failed: '실패' }

// Mock/Live·조사 수행·검수 통과·제품 보존 검토를 서로 섞지 않고 각각 표시한다 (FRONTEND.md 4장)
export default function JobBadges({ job }: { job: Job }) {
  const mock = useProjectStore((s) => s.mock)
  const badges: Badge[] = []
  badges.push(QA_OFFLINE_FIXTURE || mock || isMockJob(job)
    ? { label: '생성', value: 'OFFLINE_FIXTURE · 실제 AI 아님', tone: 'warning' }
    : { label: '생성', value: 'Live', tone: 'neutral' })

  const searched = job.research_result?.research_performed ?? job.plan?.research_performed
  if (searched !== undefined) {
    badges.push(searched
      ? { label: '조사', value: '검색 수행', tone: 'success' }
      : { label: '조사', value: '검색 안 함 · AI 추론', tone: 'warning' })
  }

  if (job.compliance_report) {
    badges.push(job.compliance_report.passed
      ? { label: '검수', value: '통과(참고용)', tone: 'success' }
      : { label: '검수', value: '위반 의심 · 승인 불가', tone: 'danger' })
  } else if (job.copy_candidate) {
    badges.push({ label: '검수', value: '미실시', tone: 'warning' })
  }

  if (job.image_candidate) {
    const review = job.image_candidate.preservation_review
    badges.push({ label: '제품 보존 검토', value: review ? PRESERVATION[review] ?? review : '정보 없음', tone: review === 'passed' ? 'success' : 'warning' })
  }

  return (
    <ul className="job-badges" aria-label="작업 상태">
      {badges.map((b) => (
        <li key={b.label}><span className="job-badge-label">{b.label}</span> <span className={`badge badge-${b.tone}`}>{b.value}</span></li>
      ))}
    </ul>
  )
}
