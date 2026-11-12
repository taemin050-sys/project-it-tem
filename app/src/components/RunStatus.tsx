import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { isUnreachable } from '../api/client'
import { getJob } from '../api/jobs'
import { advance, flowOf, refreshJob, resetJob, useJob, useLiveProgress } from '../api/useJob'
import { nextStep, STEP_LABELS } from '../lib/pipeline'
import { useProjectStore } from '../store/projectStore'
import MockFallback from './MockFallback'

function Loading({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="loading" role="status" aria-busy="true">
      <span className="spinner" aria-hidden="true" />
      <p className="notice-title">{title}</p>
      <p>{children}</p>
    </div>
  )
}

// 지금 보내고 있는 요청, 마지막 실패, 멈춘 진행만 보여준다. 진행률은 서버가 주지 않아 표시하지 않는다
export default function RunStatus() {
  const run = useProjectStore((s) => s.run)
  const jobId = useProjectStore((s) => s.jobId)
  const mock = useProjectStore((s) => s.mock)
  const { data: job, error: loadError } = useJob()
  const {data:liveTask}=useLiveProgress()

  // Server terminal states override a stale local busy spinner.
  // In particular, an inactive Worker must never look like active AI work.
  if (!mock && liveTask?.state==='BILLING_UNKNOWN')return (
    <div className="notice notice-danger" role="alert">
      <p className="notice-title">서버 작업이 안전하게 중단됐습니다</p>
      <p>실행 증빙 확인이 필요합니다. 자동 재호출하지 마세요. 다른 작업은 내 작업 목록에서 확인할 수 있습니다.</p>
      <Link className="button secondary small" to="/my/jobs">내 작업 목록</Link>
    </div>
  )
  if (!mock && liveTask?.state==='FAILED_PRE_DISPATCH')return (
    <div className="notice notice-warning" role="alert">
      <p className="notice-title">요청 처리 전 검증 실패</p>
      <p>외부 AI 호출 전에 작업을 중단했습니다. 새로 생성하지 말고 담당자에게 현재 Job을 알려주세요.</p>
      <Link className="button secondary small" to="/my/jobs">내 작업 목록</Link>
    </div>
  )
  const age=liveTask?.age_seconds??0
  if (!mock && liveTask?.state==='QUEUED' && age>=90)return (
    <div className="notice notice-warning" role="status">
      <p className="notice-title">AI 작업이 예상보다 오래 대기 중입니다</p>
      <p>접수된 작업은 보존돼 있습니다. 새 요청을 보내지 말고 잠시 후 목록에서 상태를 확인해 주세요.</p>
      <Link className="button secondary small" to="/my/jobs">내 작업 확인</Link>
    </div>
  )
  if (run.busy) {
    return (
      <Loading title={run.step ? STEP_LABELS[run.step] : '요청을 보내고 있습니다'}>
        AI 단계는 길게는 몇 분까지 걸릴 수 있습니다. 이 화면을 그대로 두셔도 됩니다.
      </Loading>
    )
  }
  if (run.error) {
    // 실패한 요청을 다시 보내지 않고 서버 상태부터 확인한다 (응답만 놓쳤을 수 있음)
    return (
      <div className="notice notice-danger" role="alert">
        <p className="notice-title">진행하지 못했습니다</p>
        <p>{run.error}</p>
        <button className="button secondary small" onClick={refreshJob}>상태 다시 확인</button>
        {mock && run.offline && <MockFallback />}
      </div>
    )
  }
  if (loadError) {
    return (
      <div className="notice notice-danger" role="alert">
        <p className="notice-title">작업 정보를 불러오지 못했습니다</p>
        <p>{loadError.message}</p>
        <div className="button-row">
          <button className="button secondary small" onClick={refreshJob}>다시 불러오기</button>
          <Link className="button secondary small" to="/create/product" onClick={resetJob}>제품 정보에서 다시 시작</Link>
        </div>
        {mock && isUnreachable(loadError) && <MockFallback />}
      </div>
    )
  }
  if(!mock){
    if(liveTask && ['QUEUED','RUNNING'].includes(liveTask.state))
      return <Loading title={STEP_LABELS[liveTask.stage.startsWith('image')?'ai/image':'ai/copy-review']}>
        작업은 서버에서 계속 처리됩니다. 새로고침해도 중복 요청하지 않습니다.
      </Loading>
    return null
  }
  // 새로고침·상태 확인 뒤 남은 단계가 있으면 사용자가 눌러야 이어서 보낸다
  const step = job && nextStep(job, flowOf(mock))
  if (!jobId || !step) return null
  return (
    <div className="notice notice-warning" role="status">
      <p className="notice-title">진행이 멈춰 있습니다</p>
      <p>다음 단계: {STEP_LABELS[step]}. 이어서 진행하면 이 단계 요청을 한 번 보냅니다.</p>
      <button className="button secondary small" onClick={() => advance(() => getJob(jobId))}>이어서 진행</button>
    </div>
  )
}
