import { useEffect, useState } from 'react'

type Shared={job_id:string;final_sha:string;shared_at:string}
type Rated={score:number;comment:string;category:string;artifact_sha256:string;revision:number}
const categories=[
  ['product_recognition','제품 분석 정확도'],
  ['plan_copy_compliance','기획·카피·규제 적절성'],
  ['image_fidelity','제품 이미지 보존'],
  ['final_layout_korean','한국어 합성·가독성'],
  ['speed_reliability','속도·안정성'],
  ['ui_ux','UI/UX'],
]
const api='/demo/api/live'
async function json<T>(url:string, method='GET',body?:unknown):Promise<T>{
  const r=await fetch(url,{method,credentials:'same-origin',cache:'no-store',
    ...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})})
  if(!r.ok)throw new Error('HTTP '+r.status)
  return r.json() as Promise<T>
}
export default function LiveEvaluationBoard(){
  const [items,setItems]=useState<Shared[]>([])
  const [selected,setSelected]=useState<string|null>(null)
  const [category,setCategory]=useState(categories[0][0])
  const [score,setScore]=useState(3)
  const [comment,setComment]=useState('')
  const [reviews,setReviews]=useState<Rated[]>([])
  const [error,setError]=useState('')
  const [message,setMessage]=useState('')
  const refresh=async()=>setItems((await json<{jobs:Shared[]}>(api+'/shared')).jobs)
  useEffect(()=>{void Promise.resolve().then(refresh).catch(()=>{})},[])
  async function choose(jid:string){
    setSelected(jid);setError('')
    try{setReviews((await json<{reviews:Rated[]}>(api+'/shared/'+jid+'/evaluations')).reviews)}
    catch{setReviews([])}
  }
  async function submit(){
    if(!selected)return
    setError('');setMessage('')
    try{
      const x=await json<{saved:boolean}>(api+'/shared/'+selected+'/evaluations','POST',{
        job_id:selected,scenario_id:'UC-01',category,score,comment,needs_improvement:score<=2})
      if(x.saved){setMessage('검토 결과가 광고 파일 SHA에 결속되어 저장됐습니다.');await choose(selected)}
    }catch(e){setError(String(e))}
  }
  return <section style={{marginTop:32,paddingTop:20,borderTop:'2px solid #bbb'}}>
    <h2>팀 공동 Live 품질 평가</h2>
    <p>광고 작성자가 명시적으로 공유한 최종 광고만 표시됩니다. 원본 제품 사진과 다른 작업 내역은 공개되지 않습니다.</p>
    <button type="button" onClick={()=>void refresh().catch(()=>setError('목록 조회 실패'))}>공유 광고 새로고침</button>
    <ul>{items.map(x=><li key={x.job_id}>
      <button onClick={()=>void choose(x.job_id)}>{x.shared_at} · {x.job_id.slice(0,8)} · 실제 AI 광고</button>
    </li>)}</ul>
    {selected&&<section>
      <h3>평가 광고 — {selected.slice(0,8)}</h3>
      <img alt="팀 공유 최종 광고 이미지" src={api+'/shared/'+selected+'/artifacts/final'}
        style={{width:'100%',maxWidth:360}}/>
      <p><a href={api+'/shared/'+selected+'/artifacts/caption'}>Caption 확인</a></p>
      <label>평가 영역
        <select value={category} onChange={e=>setCategory(e.target.value)}>
          {categories.map(x=><option key={x[0]} value={x[0]}>{x[1]}</option>)}
        </select>
      </label>
      <label>평가 점수 (1~5)
        <input type="number" min={1} max={5} value={score} onChange={e=>setScore(Number(e.target.value))}/>
      </label>
      <label>개선 의견
        <textarea rows={3} maxLength={1800} value={comment} onChange={e=>setComment(e.target.value)}/>
      </label>
      <button disabled={score<1||score>5||!Number.isInteger(score)}
        onClick={()=>void submit()}>평가 저장</button>
      <h4>본인 평가 기록</h4>
      <ul>{reviews.map((r,i)=><li key={i}>{r.category} · {r.score}점 · Revision {r.revision} · {r.comment}</li>)}</ul>
    </section>}
    {error&&<p role="alert">{error}</p>}
    {message&&<p role="status">{message}</p>}
  </section>
}
