import { useEffect, useState } from 'react'
import { useProjectStore } from '../store/projectStore'

type Event = {
  step:string;mode:string;start_utc:string;duration_ms:number;
  http_status:number;outcome:string;server_status:string | null
}
type Identity = { authenticated:true;evaluator_id:string;role:'evaluator'|'admin';mode:'MOCK' }
type Category = {id:string;name:string}
const categories:Category[]=[
  {id:'product_recognition',name:'제품 인식'},
  {id:'plan_copy_compliance',name:'기획·카피·규제'},
  {id:'image_fidelity',name:'제품 이미지 보존'},
  {id:'final_layout_korean',name:'최종 레이아웃·한글'},
  {id:'speed_reliability',name:'속도·안정성'},
  {id:'ui_ux',name:'UI·UX'},
]
export default function DemoEvaluation({identity}:{identity:Identity}){
  const jobId=useProjectStore(s=>s.jobId)
  const [events,setEvents]=useState<Event[]>([])
  const [category,setCategory]=useState(categories[0].id)
  const [score,setScore]=useState(3)
  const [comment,setComment]=useState('')
  const [scenario,setScenario]=useState('UC-01')
  const [needs,setNeeds]=useState(false)
  const [feedback,setFeedback]=useState('')
  const [nReviews,setNReviews]=useState(0)
  const [admin,setAdmin]=useState('')
  useEffect(()=>{
    if(!jobId)return
    let active=true
    async function refresh(){
      try{
        const r=await fetch('/demo/api/jobs/'+jobId+'/events',{cache:'no-store'})
        if(r.ok && active) {
          const data=await r.json() as {events:Event[]}
          setEvents(data.events)
        }
      }catch { /* Failed GET never starts another POST/provider retry. */ }
    }
    void refresh()
    const timer=window.setInterval(()=>void refresh(),3500)
    return ()=>{active=false;window.clearInterval(timer)}
  },[jobId])
  async function submit(){
    if(!jobId)return
    setFeedback('')
    try{
      const r=await fetch('/demo/api/evaluations',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({job_id:jobId,scenario_id:scenario,category,score,comment,needs_improvement:needs})})
      if(!r.ok)throw Error('평가 저장 실패 ('+r.status+'). Job 완료 여부와 본인 권한을 확인해 주세요.')
      const data=await r.json() as {revision:number;artifact_sha256:string}
      setNReviews(nReviews+1)
      setFeedback('저장 완료 · 개정 '+data.revision+' · 결과 SHA '+(data.artifact_sha256?.slice(0,12) || 'N/A'))
    }catch(e){setFeedback(e instanceof Error?e.message:'평가 오류')}
  }
  async function summary(){
    const r=await fetch('/demo/api/admin/evaluations',{cache:'no-store'})
    if(!r.ok){setAdmin('관리자 인증이 필요합니다.');return}
    const data=await r.json() as {n:number;results:Array<{score:number}>}
    const scores=data.results.map(x=>x.score).sort((a,b)=>a-b)
    const p=(q:number)=>scores.length?scores[Math.ceil(q*scores.length)-1]:'N/A'
    const timingsResponse=await fetch('/demo/api/admin/timings',{cache:'no-store'})
    const timings=timingsResponse.ok ? (await timingsResponse.json() as {
      stages:Record<string,{n:number;p50_ms:number;p95_ms:number}>
    }).stages : {}
    const parts=Object.entries(timings).map(([step,x])=>
      step+': n='+x.n+' P50 '+x.p50_ms+'ms / P95 '+x.p95_ms+'ms')
    setAdmin('품질평가 '+data.n+'건 · 점수 P50 '+p(.5)+' / P95 '+p(.95)+
      ' · n='+scores.length+' | 서버 단계 지연 '+parts.join(' / '))

  }
  return <section style={{maxWidth:1050,margin:'24px auto',padding:'18px',border:'1px solid #9da8b4',borderRadius:12}}>
    <h2>시연 관찰·품질 평가 <small>MOCK / AI 미호출</small></h2>
    <p>평가자: {identity.evaluator_id} · 실행 모드: <strong>MOCK</strong> · 큐 지연/Provider 지연: N/A</p>
    {!jobId ? <p>제품을 업로드하면 단계별 실제 서버 시간을 표시합니다.</p> : <>
      <p>Job: <code>{jobId}</code> · 기록된 단계 {events.length}건 · 평가 저장 {nReviews}회</p>
      <div style={{maxHeight:250,overflow:'auto'}}>
        <table style={{width:'100%',fontSize:13}}><thead><tr>
          <th>단계</th><th>상태</th><th>서버 처리(ms)</th><th>요청 결과</th>
        </tr></thead><tbody>{events.map((ev,i)=><tr key={i}>
          <td>{ev.step}</td><td>{ev.server_status || '—'}</td>
          <td>{ev.duration_ms.toFixed(1)}</td><td>{ev.http_status} · {ev.outcome}</td>
        </tr>)}</tbody></table>
      </div>
      <h3>단계별 독립 평가 (완료된 Job만 저장)</h3>
      <div style={{display:'flex',gap:12,flexWrap:'wrap',alignItems:'end'}}>
        <label>시나리오 <select value={scenario} onChange={e=>setScenario(e.target.value)}>
          {['UC-01','UC-02','UC-03','UC-04'].map(x=><option key={x}>{x}</option>)}
        </select></label>
        <label>평가 분야 <select value={category} onChange={e=>setCategory(e.target.value)}>
          {categories.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}
        </select></label>
        <label>점수 (1~5) <select value={score} onChange={e=>setScore(Number(e.target.value))}>
          {[1,2,3,4,5].map(x=><option key={x}>{x}</option>)}
        </select></label>
        <label><input type="checkbox" checked={needs} onChange={e=>setNeeds(e.target.checked)}/> 개선 필요</label>
      </div>
      <label>평가 의견 <textarea maxLength={1800} value={comment} onChange={e=>setComment(e.target.value)} rows={2} style={{display:'block',width:'100%'}}/></label>
      <button type="button" onClick={()=>void submit()}>평가 기록 저장</button>
      {feedback&&<p role="status">{feedback}</p>}
    </>}
    {identity.role==='admin'&&<div>
      <h3>PM 요약</h3><button type="button" onClick={()=>void summary()}>독립 평가 집계 갱신</button>
      <a href="/demo/api/admin/evaluations.csv" style={{marginLeft:14}}>평가 CSV 내려받기</a>
      {admin&&<p>{admin}</p>}
    </div>}
    <p style={{fontSize:12}}>여기서 저장한 의견은 서버 영속 원장에 기록됩니다. 다른 평가자의 응답은 평가자 화면에 표시하지 않습니다.</p>
  </section>
}
