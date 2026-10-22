import type { Job } from '../types/draft'

const STATUS_TEXT: Record<Job['status'], string> = {
  queued: '순서를 기다리고 있습니다',
  running: '광고를 만들고 있습니다',
  needs_review: '확인이 필요한 항목이 있습니다',
  done: '완료되었습니다',
  failed: '생성에 실패했습니다',
}

export default function JobStatusView({ job }: { job: Job }) {
  return (
    <div className={`status status-${job.status}`} role="status">
      <strong>{STATUS_TEXT[job.status]}</strong>
      {job.status === 'running' && job.progress !== undefined && (
        <progress max={100} value={job.progress}>{job.progress}%</progress>
      )}
      {job.error && <p>{job.error.message}</p>}
    </div>
  )
}
