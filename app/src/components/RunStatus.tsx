import { Link } from 'react-router-dom'
import { isUnreachable } from '../api/client'
import { getJob } from '../api/jobs'
import { advance, flowOf, refreshJob, useJob, useLiveProgress } from '../api/useJob'
import { nextStep, STEP_LABELS } from '../lib/pipeline'
import { useProjectStore } from '../store/projectStore'
import MockFallback from './MockFallback'

// 지금 보내고 있는 요청, 마지막 실패, 멈춘 진행만 보여준다. 진행률은 서버가 주지 않아 표시하지 않는다
export default function RunStatus() {
  const run = useProjectStore((s) => s.run)
  const jobId = useProjectStore((s) => s.jobId)
  const mock = useProjectStore((s) => s.mock)
  const { data: job, error: loadError } = useJob()
  const {data:liveTask}=useLiveProgress()

  if (run.busy) {
    return (
      <div className="notice notice-info" role="status" aria-busy="true">
        <p className="notice-title">{run.step ? STEP_LABELS[run.step] : '요청을 보내고 있습니다'}</p>
        <p>AI 단계는 길게는 몇 분까지 걸릴 수 있습니다. 이 화면을 그대로 두셔도 됩니다.</p>
        <div className="progress"><progress aria-label="진행 중" /></div>
      </div>
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
          <Link className="button secondary small" to="/create/product">제품 정보에서 다시 시작</Link>
        </div>
        {mock && isUnreachable(loadError) && <MockFallback />}
      </div>
    )
  }
  if(!mock){
    if(liveTask?.state==='BILLING_UNKNOWN')return <div className="notice notice-danger" role="alert">
      <p className="notice-title">AI Provider 청구 상태 불확실</p>
      <p>이 작업을 자동 재전송하지 않습니다. 서버 원장을 확인해야 합니다.</p>
    </div>
    if(liveTask && ['QUEUED','RUNNING'].includes(liveTask.state))
      return <div className="notice notice-info" role="status" aria-busy="true">
        <p className="notice-title">실제 AI {liveTask.stage} · {liveTask.state}</p>
        <p>작업은 서버에서 계속 처리됩니다. 새로고침해도 중복 요청하지 않습니다.</p>
        <div className="progress"><progress aria-label="실제 AI 처리 중" /></div>
      </div>
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
