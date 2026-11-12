import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getJob } from '../api/jobs'
import { startNewAdLink } from '../api/useJob'
import { getLiveSnapshot, listMyLiveJobs, type MyLiveJob } from '../api/liveJobs'
import { queryClient } from '../api/queryClient'
import { resumeLabel, resumePath } from '../lib/resumeRoute'
import { useProjectStore, INITIAL_RATIO, INITIAL_GENERATION_MODE } from '../store/projectStore'
import '../demo/LiveEvaluationBoard.css'

function localTime(value:string){
  const d=new Date(value.endsWith('Z') || value.includes('+') ? value : value.replace(' ','T')+'Z')
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})
}
export default function MyJobsPage(){
  const navigate=useNavigate()
  const [jobs,setJobs]=useState<MyLiveJob[]>([])
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')
  const [selecting,setSelecting]=useState<string|null>(null)
  const busy=useProjectStore(s=>s.run.busy)
  const refresh=useCallback(async()=>{
    setError('')
    try{
      const data=await listMyLiveJobs()
      setJobs(data.jobs)
    }catch{
      setError('내 작업 목록을 불러오지 못했습니다. Tailscale 연결을 확인해 주세요.')
    }finally{
      setLoading(false)
    }
  },[])
  useEffect(()=>{
    let active=true
    void listMyLiveJobs()
      .then(data=>{if(active)setJobs(data.jobs)})
      .catch(()=>{if(active)setError('내 작업 목록을 불러오지 못했습니다. Tailscale 연결을 확인해 주세요.')})
      .finally(()=>{if(active)setLoading(false)})
    return ()=>{active=false}
  },[])

  async function openJob(item:MyLiveJob){
    if(selecting||useProjectStore.getState().run.busy)return
    const previous=useProjectStore.getState()
    const changed=previous.jobId!==item.job_id &&
      (previous.jobId!==null || previous.images.length>0 || previous.references.length>0 ||
       Boolean(previous.product.product_name.trim()) || Boolean(previous.product.features.trim()))
    if(changed && !window.confirm('다른 작업으로 전환하면 현재 화면에 남아 있는 미저장 입력이 지워집니다. 기존 서버 작업은 삭제되지 않습니다. 계속할까요?'))return
    setSelecting(item.job_id)
    setError('')
    try{
      // Recheck both existing Actor-owned endpoints before modifying browser state.
      const [live,original]=await Promise.all([getLiveSnapshot(item.job_id),getJob(item.job_id)])
      if(live.job_id!==item.job_id || original.job_id!==item.job_id)
        throw Error('JOB_ID_MISMATCH')
      const before=useProjectStore.getState()
      if(before.run.busy || before.identityScope!==previous.identityScope)
        throw Error('SESSION_OR_BUSY_CHANGED')
      const target=resumePath(live.state)
      const ratio=live.image_size==='3:4'||live.image_size==='4:5'||live.image_size==='9:16'
        ?live.image_size:INITIAL_RATIO
      const mode=live.generation_mode==='freeform'?'freeform':INITIAL_GENERATION_MODE
      queryClient.clear()
      before.clearInputs()
      before.setRatio(ratio)
      before.setGenerationMode(mode)
      before.setFinishedJob(live.state==='COMPLETED'?item.job_id:null)
      before.setJobId(item.job_id)
      before.setRun({busy:false,step:null,error:null,offline:false})
      navigate(target)
    }catch{
      setError('이 작업의 현재 상태를 확인하지 못했습니다. 권한 또는 네트워크 상태를 확인하고 다시 시도해 주세요.')
    }finally{
      setSelecting(null)
    }
  }

  return <main className="live-eval">
    <div className="step-width wide live-eval-wrap">
      <header className="live-eval-intro">
        <p className="eyebrow">MY WORK / LIVE AI</p>
        <h1>내 광고 작업</h1>
        <p className="step-desc">진행 중인 내 광고를 이어 만들거나, 완료된 광고의 결과를 볼 수 있습니다. 다른 팀원의 작업과 팀 공유 광고는 여기에 표시되지 않습니다.</p>
        <div className="button-row">
          <Link className="button" to="/create/product" onClick={startNewAdLink}>새 광고 만들기</Link>
          <Link className="button secondary" to="/team/evaluations">팀 공동 품질 평가</Link>
          <Link className="text-link" to="/">홈으로</Link>
        </div>
      </header>
      <section className="panel live-eval-list" aria-labelledby="my-work-title">
        <div className="panel-head">
          <h2 id="my-work-title" className="panel-title">내 작업 목록</h2>
          <button type="button" className="button secondary small"
            onClick={()=>{setLoading(true);void refresh()}} disabled={loading||Boolean(selecting)}>목록 새로고침</button>
        </div>
        {error && <p className="notice notice-warning" role="alert">{error}</p>}
        {loading && <p className="muted" role="status">내 작업을 불러오는 중입니다…</p>}
        <p className="field-hint">저장된 진행 상태를 불러옵니다. 브라우저에 원본 사진 파일 자체를 재저장하지는 않습니다.</p>
        {!loading && jobs.length===0 && <div className="empty">
          <p className="empty-title">저장된 광고 작업이 없습니다.</p>
          <p>제품 사진을 등록해 AI 작업을 시작하면 여기에 기록됩니다.</p>
        </div>}
        <ul className="live-eval-items">
          {jobs.map((item,i)=><li key={item.job_id}>
            <button type="button" className="live-eval-item"
              disabled={busy||Boolean(selecting)}
              onClick={()=>void openJob(item)}>
              <span className="live-eval-index">{String(i+1).padStart(2,'0')}</span>
              <span className="live-eval-item-details">
                <strong>{item.product_name} · {item.job_id.slice(0,8)}</strong>
                <small>{resumeLabel(item.state)} · {item.generation_mode==='composed'?'Composed':'Freeform'} · {item.image_size}</small>
                <small>{localTime(item.created_at)}</small>
              </span>
              <span className="live-eval-item-action">{selecting===item.job_id?'확인 중…':
                item.state==='COMPLETED'?'결과 보기':'이어서 만들기'}</span>
            </button>
          </li>)}
        </ul>
      </section>
    </div>
  </main>
}
