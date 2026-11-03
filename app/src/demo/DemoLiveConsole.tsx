import { useCallback, useEffect, useRef, useState } from 'react'
import LiveEvaluationBoard from './LiveEvaluationBoard'
import { AD_LAYOUT as layout } from '../config'

type Stage = 'INPUT_STORED' | 'COPY_REVIEW_REQUIRED' | 'COPY_APPROVED' | 'COPY_REJECTED' |
             'PROMPT_READY' | 'IMAGE_REVIEW_REQUIRED' | 'IMAGE_APPROVED' | 'IMAGE_REJECTED' | 'COMPLETED'
type LiveSnapshot = {
  job_id:string;state:Stage;generation:number;mode:string;
  copy_sha?:string;review_sha?:string;image_sha?:string;final_sha?:string;
  approval_current:boolean;
  analysis?:{analysis:{product_type:string;colors:string[];container_type:string;label_text:string[]}};
  research_display?:{research:{display_summary:Array<{text:string;source:string}>};research_performed:boolean};
  copy?:{plan:{target:string;concept:string;key_message:string;mood:string[]};
    ad_copy:{headline:string;subline:string;cta:string};caption:string;hashtags:string[]};
  compliance?:{passed:boolean;issues:Array<{field:string;text:string;risk_level:string;reason:string;start:number;end:number}>;checklist:string[];notice:string};
  image_prompt?:{concept:string;prompt:string;mood:string[]};
}
type Task = {task_id:string;state:string;error_code?:string|null}
type Performance={timings:Array<{stage:string;state:string;server_elapsed_s:number|null}>;
  provider_attempts:Array<{stage:string;state:string;model:string|null;
    usage:Record<string,number>|null;billing_unknown:boolean}>;
  project_spend_status:string;application_cost_policy:string}
type State = {live_enabled:boolean;mode:string;reason:string}
const api='/demo/api/live'

async function request<T>(url:string, method='GET', payload?:unknown):Promise<T>{
  const res=await fetch(url,{method,credentials:'same-origin',cache:'no-store',
    ...(payload!==undefined ? {headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {})})
  if(!res.ok){
    const info=await res.json().catch(()=>({detail:res.statusText})) as {detail?:unknown}
    const text=typeof info.detail==='string'?info.detail:JSON.stringify(info.detail)
    throw new Error('서버 요청이 차단되었습니다 ('+res.status+'): '+text)
  }
  return res.json() as Promise<T>
}

export default function DemoLiveConsole({evaluatorId}:{evaluatorId:string}){
  const [cap,setCap]=useState<State|null>(null)
  const [snap,setSnap]=useState<LiveSnapshot|null>(null)
  const [pendingId,setPendingId]=useState<string|null>(null)
  const [savedCounts,setSavedCounts]=useState({products:0,references:0})
  const savedJobKey='ittem.live.job.'+evaluatorId
  const [task,setTask]=useState<Task|null>(null)
  const [perf,setPerf]=useState<Performance|null>(null)
  const [error,setError]=useState('')
  const [shared,setShared]=useState(false)
  const [busy,setBusy]=useState(false)
  const [files,setFiles]=useState<File[]>([])
  const [refs,setRefs]=useState<File[]>([])
  const [brand,setBrand]=useState('')
  const [product,setProduct]=useState('')
  const [category,setCategory]=useState('스킨케어')
  const [features,setFeatures]=useState('')
  const [purpose,setPurpose]=useState('신제품 홍보')
  const [functional,setFunctional]=useState(false)
  const [rights,setRights]=useState(false)
  const [evidence,setEvidence]=useState(false)
  const [form,setForm]=useState({headline:'',subline:'',cta:'',caption:''})
  const [candidateUrl,setCandidateUrl]=useState<string|null>(null)
  const lastId=useRef<string|null>(null)
  const lastCopyHash=useRef<string|null>(null)
  const update=useCallback(async(id:string)=>{
    const x=await request<LiveSnapshot>(api+'/jobs/'+id)
    setSnap(x)
    if(x.mode==='LIVE'){
      void request<Performance>(api+'/jobs/'+id+'/performance').then(setPerf).catch(()=>{})
    }
    // Polling must never erase text the evaluator is currently editing.
    if(x.copy && x.copy_sha !== lastCopyHash.current){
      setForm({headline:x.copy.ad_copy.headline,subline:x.copy.ad_copy.subline,
        cta:x.copy.ad_copy.cta,caption:x.copy.caption})
      lastCopyHash.current=x.copy_sha || null
    }
    if(x.state==='IMAGE_REVIEW_REQUIRED'&&x.mode==='LIVE'){
      setCandidateUrl(api+'/jobs/'+id+'/artifacts/candidate')
    }
    return x
  },[])
  useEffect(()=>{
    let on=true
    void request<State>(api+'/capabilities').then(x=>{if(on)setCap(x)})
      .catch(e=>{if(on)setError(String(e))})
    return ()=>{on=false}
  },[])
  useEffect(()=>{
    let active=true
    const saved=sessionStorage.getItem(savedJobKey)
    if(!saved || !/^[0-9a-f]{32}$/.test(saved))return
    lastId.current=saved
    void Promise.resolve().then(()=>update(saved)).catch(async()=>{
      // B0 upload may have succeeded before the Live input write failed.
      // Reuse its uploaded images; never re-POST and create another Job.
      try{
        const response=await fetch('/api/v1/jobs/'+saved,{
          credentials:'same-origin',cache:'no-store'})
        if(!response.ok)throw Error('Previous upload unavailable')
        const job=await response.json() as {
          assets?:Array<{role:string}>,status?:string
        }
        if(!active)return
        if(job.status!=='INPUTS_VALIDATED')throw Error('Previous upload state changed')
        setSavedCounts({products:(job.assets||[]).filter(x=>x.role==='product').length,
                        references:(job.assets||[]).filter(x=>x.role==='reference').length})
        setPendingId(saved)
      }catch{
        if(active){sessionStorage.removeItem(savedJobKey);lastId.current=null}
      }
    })
    return ()=>{active=false}
  },[savedJobKey,update])
  useEffect(()=>{
    const timer=setInterval(()=>{
      if(lastId.current){
        void update(lastId.current).catch(()=>{/* no retrying provider POSTs */})
      }
      if(task?.task_id){
        void request<Task>(api+'/tasks/'+task.task_id).then(setTask).catch(()=>{})
      }
    },3000)
    return ()=>clearInterval(timer)
  },[task?.task_id,update])
  async function action(callback:()=>Promise<void>){
    setBusy(true);setError('')
    try{await callback()}catch(e){setError(e instanceof Error?e.message:'오류')}
    finally{setBusy(false)}
  }
  async function create(){
    const productCount=pendingId?savedCounts.products:files.length
    const referenceCount=pendingId?savedCounts.references:refs.length
    if(productCount<2||productCount>5||referenceCount>5||!rights||!product.trim()||!features.trim()){
      throw Error('제품 사진 2~5장, 참고 0~5장, 제품 정보와 사용권 확인이 필요합니다.')
    }
    let jobId=pendingId
    if(!jobId){
      const data=new FormData()
      files.forEach(f=>data.append('product_images',f))
      refs.forEach(f=>data.append('reference_images',f))
      const response=await fetch('/api/v1/jobs',{method:'POST',body:data,credentials:'same-origin'})
      if(!response.ok)throw Error('제품 사진 업로드 실패 (HTTP '+response.status+')')
      const job=await response.json() as {job_id:string}
      jobId=job.job_id
      lastId.current=jobId
      sessionStorage.setItem(savedJobKey,jobId)
      setPendingId(jobId)
      setSavedCounts({products:productCount,references:referenceCount})
    }
    const record=await request<LiveSnapshot>(api+'/jobs/'+jobId+'/input','POST',{
      customer_request_id:'demo-'+jobId,
      product:{
        brand_name:brand.trim()||null,product_name:product.trim(),
        product_category:category||null,features:features.trim(),ad_purpose:purpose.trim(),
        is_functional:functional,photo_verified:rights,
        product_image_count:productCount,reference_image_count:referenceCount,
      }})
    lastId.current=jobId
    setPendingId(null)
    setSnap(record)
  }
  const enqueue=async(step:'queue-text'|'queue-prompt'|'queue-image')=>{
    if(!snap)throw Error('Job이 없습니다')
    const t=await request<Task>(api+'/jobs/'+snap.job_id+'/'+step,'POST')
    setTask(t)
  }
  async function revise(){
    if(!snap?.copy)throw Error('카피 원본이 없습니다')
    const old=snap.copy
    const next={...old,ad_copy:{...old.ad_copy,headline:form.headline,
       subline:form.subline,cta:form.cta},caption:form.caption}
    await request(api+'/jobs/'+snap.job_id+'/copy','POST',{copy_output:next})
    await update(snap.job_id)
  }
  async function approveCopy(){
    if(!snap?.review_sha)throw Error('검수 결과가 없습니다')
    await request(api+'/jobs/'+snap.job_id+'/approve-copy','POST',{
      expected_generation:snap.generation,expected_review_sha:snap.review_sha,
      acknowledge_evidence:evidence})
    await update(snap.job_id)
  }
  async function rejectCopy(){
    if(!snap)throw Error('Job이 없습니다')
    await request(api+'/jobs/'+snap.job_id+'/reject-copy','POST')
    await update(snap.job_id)
  }
  async function rejectImage(){
    if(!snap?.image_sha)throw Error('이미지 후보가 없습니다')
    await request(api+'/jobs/'+snap.job_id+'/reject-image','POST',{image_sha:snap.image_sha})
    await update(snap.job_id)
  }
  async function approveImage(){
    if(!snap?.image_sha)throw Error('이미지 후보가 없습니다')
    await request(api+'/jobs/'+snap.job_id+'/approve-image','POST',{image_sha:snap.image_sha})
    await update(snap.job_id)
  }
  async function publishForTeam(){
    if(!snap || snap.state!=='COMPLETED')throw Error('완료된 Live 광고만 공유할 수 있습니다')
    await request(api+'/jobs/'+snap.job_id+'/share','POST')
    setShared(true)
  }
  async function compose(){
    if(!snap)throw Error('Job이 없습니다')
    await request(api+'/jobs/'+snap.job_id+'/compose','POST',{layout})
    await update(snap.job_id)
  }
  const disabled=!cap?.live_enabled
  return <main style={{maxWidth:900,margin:'28px auto',padding:20}}>
    <h1>IT-TEM 실제 AI 광고 제작 <small>LIVE</small></h1>
    <p>이 화면은 Mock 생성 결과로 대체하지 않습니다. 모델 호출은 비용·계약·안전 승인 후에만 실행됩니다.</p>
    <div role="status" style={{padding:12,border:'1px solid #a0aab8',borderRadius:8,marginBottom:18}}>
      모델 호출 상태: <strong>{disabled?'LIVE 잠금 — 승인 및 비용 게이트 대기':'승인된 Live 호출 준비'}</strong>
      {task&&<p>작업: {task.state} · {task.error_code || '상태 조회 중'}</p>}
    </div>
    {error&&<p role="alert" style={{color:'#9b1721'}}>{error}</p>}
    {!snap&&<section>
      <h2>1. 제품 사진·정보 입력</h2>
      <p>기존 B0 이미지 업로드 검증을 재사용합니다. 원본 사진은 AI 추정의 확정 근거가 아닙니다.</p>
      {pendingId&&<p role="status">기존 제품 사진 업로드가 복구됐습니다. 제품 정보만 확인한 후 이어서 저장하세요. 새 업로드를 하지 않습니다.</p>}
      <label>제품 사진 (2~5장)
        <input disabled={Boolean(pendingId)} type="file" accept="image/png,image/jpeg,image/webp" multiple
          onChange={e=>setFiles(Array.from(e.target.files || []))}/>
      </label>
      <label>디자인 참고 (최대 5장)
        <input disabled={Boolean(pendingId)} type="file" accept="image/png,image/jpeg,image/webp" multiple
          onChange={e=>setRefs(Array.from(e.target.files || []))}/>
      </label>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(250px,1fr))',gap:12}}>
        <label>브랜드명 (선택)<input value={brand} onChange={e=>setBrand(e.target.value)}/></label>
        <label>제품명<input required value={product} onChange={e=>setProduct(e.target.value)}/></label>
        <label>제품 카테고리<input value={category} onChange={e=>setCategory(e.target.value)}/></label>
        <label>광고 목적<input value={purpose} onChange={e=>setPurpose(e.target.value)}/></label>
      </div>
      <label>제품 특징·실증 가능한 사실
        <textarea value={features} rows={3} onChange={e=>setFeatures(e.target.value)}/>
      </label>
      <p><label><input type="checkbox" checked={functional} onChange={e=>setFunctional(e.target.checked)}/> 기능성 화장품</label></p>
      <p><label><input type="checkbox" checked={rights} onChange={e=>setRights(e.target.checked)}/> 사진 사용권을 확인했습니다</label></p>
      <button disabled={busy} onClick={()=>void action(create)}>제품 원본 저장</button>
    </section>}
    {snap&&<section>
      <h2>2. AI 단계·검수 및 승인</h2>
      <p>Job <code>{snap.job_id}</code> · 상태 <strong>{snap.state}</strong> · 모드 {snap.mode} · Revision {snap.generation}</p>
      {snap.state==='INPUT_STORED'&&<button disabled={busy||disabled}
        onClick={()=>void action(()=>enqueue('queue-text'))}>실제 제품 분석·기획·카피 접수</button>}
      {snap.analysis&&<details open><summary>실제 제품 분석 결과</summary>
        <pre>{JSON.stringify(snap.analysis.analysis,null,2)}</pre>
        <p>라벨 인식은 AI 추정으로 사용자 검증이 필요합니다.</p></details>}
      {snap.research_display&&<details><summary>Research 결과·출처</summary>
        <p>검색 수행: {String(snap.research_display.research_performed)}</p>
        <ul>{snap.research_display.research.display_summary.map((x,i)=>
          <li key={i}>{x.text} ({x.source})</li>)}</ul>
        <small>개별 출처 연결이 확인되지 않은 주장은 AI 추론입니다.</small></details>}
      {snap.copy&&<div>
        <h3>카피 검토 · Copy Revision {snap.generation}</h3>
        {(['headline','subline','cta','caption'] as const).map(key=>
          <label key={key}>{key}
            <textarea rows={key==='caption'?4:2} value={form[key]}
              onChange={e=>setForm({...form,[key]:e.target.value})}/>
          </label>)}
        <p>타깃: {snap.copy.plan.target} · 콘셉트: {snap.copy.plan.concept}</p>
        {(snap.state==='COPY_REVIEW_REQUIRED'||snap.state==='COPY_REJECTED')&&<button disabled={busy}
          onClick={()=>void action(revise)}>수정 후 검수 재실행</button>}
      </div>}
      {snap.compliance&&<section>
        <h3>Real Compliance · 1차 규칙 검수</h3>
        <p>{snap.compliance.passed?'위반 의심 미탐지 (법적 적합성 확정 아님)':'위반 의심: 서버 승인 차단'}</p>
        <ul>{snap.compliance.issues.map((i,n)=><li key={n}>
          {i.field} · {i.risk_level} · {i.text} · {i.reason} (위치 {i.start}–{i.end})
        </li>)}</ul>
        <p>{snap.compliance.notice}</p>
        {snap.state==='COPY_REVIEW_REQUIRED'&&<div>
          <label><input type="checkbox" checked={evidence} onChange={e=>setEvidence(e.target.checked)}/>
            근거 확인 필요 표현의 시험·표시광고 적합성을 직접 확인했습니다.
          </label>
          <button disabled={busy||!snap.compliance.passed}
            onClick={()=>void action(approveCopy)}>검수된 카피 승인</button>
          <button disabled={busy} onClick={()=>void action(rejectCopy)}>카피 거절</button>
        </div>}
      </section>}
      {snap.state==='IMAGE_REJECTED'&&<p>이미지가 거절됐습니다. 비용 중복 방지를 위해 이 Job을 자동 재실행하지 않습니다. 새 Job을 만드세요.</p>}
      {snap.state==='COPY_REJECTED'&&<p>카피가 거절됐습니다. 카피를 수정하면 새로운 검수가 수행됩니다.</p>}
      {snap.state==='COPY_APPROVED'&&<button disabled={busy||disabled}
        onClick={()=>void action(()=>enqueue('queue-prompt'))}>승인된 카피의 이미지 프롬프트 생성</button>}
      {snap.image_prompt&&<details><summary>승인 후 Image Prompt</summary>
        <pre>{snap.image_prompt.prompt}</pre></details>}
      {snap.state==='PROMPT_READY'&&<button disabled={busy||disabled}
        onClick={()=>void action(()=>enqueue('queue-image'))}>실제 제품 이미지 편집 접수</button>}
      {candidateUrl&&snap.state==='IMAGE_REVIEW_REQUIRED'&&<section>
        <h3>3. 이미지 후보 검토</h3>
        <img src={candidateUrl} alt="실제 이미지 생성 후보" style={{maxWidth:320,width:'100%'}}/>
        <p>실제 제품 보존·브랜드/로고 왜곡·가짜 라벨을 직접 확인하십시오.</p>
        <button disabled={busy} onClick={()=>void action(approveImage)}>이미지 승인</button>
        <button disabled={busy} onClick={()=>void action(rejectImage)}>이미지 거절</button>
      </section>}
      {snap.state==='IMAGE_APPROVED'&&<button disabled={busy}
        onClick={()=>void action(compose)}>승인된 한글 카피 합성</button>}
      {perf&&<details>
        <summary>실제 AI 단계별 처리시간·사용량</summary>
        <p>비용 정책: {perf.application_cost_policy} · 프로젝트 전체 사용액: {perf.project_spend_status}</p>
        <table><thead><tr><th>단계</th><th>상태</th><th>처리시간</th><th>모델·Usage</th></tr></thead>
        <tbody>{perf.provider_attempts.map((a,i)=><tr key={i}>
          <td>{a.stage}</td><td>{a.state}</td>
          <td>{perf.timings.find(t=>t.stage===a.stage)?.server_elapsed_s ?? '확인 필요'}초</td>
          <td>{a.model||'확인 필요'} · {a.usage?JSON.stringify(a.usage):'Usage 확인 필요'}</td>
        </tr>)}</tbody></table>
        <p>서비스 내부 기록은 OpenAI 프로젝트 전체 청구액이 아닙니다. 청구금액 미확인 상태에서는 잔액을 추정하지 않습니다.</p>
      </details>}
      {snap.state==='COMPLETED'&&<section>
        <h3>최종 실제 광고</h3>
        <img src={api+'/jobs/'+snap.job_id+'/artifacts/final'} alt="최종 광고" style={{maxWidth:320,width:'100%'}}/>
        <p><a href={api+'/jobs/'+snap.job_id+'/artifacts/final'}>최종 PNG 다운로드</a></p>
        <p><a href={api+'/jobs/'+snap.job_id+'/artifacts/caption'}>Caption UTF-8 다운로드</a></p>
        <p>팀원에게는 최종 광고 이미지와 Caption만 공유되며 제품 사진 원본은 공유되지 않습니다.</p>
        <button type="button" disabled={busy||shared}
          onClick={()=>void action(publishForTeam)}>{shared?'공동 평가 공유 완료':'팀 품질 평가에 명시적으로 공유'}</button>
      </section>}
    </section>}
    <LiveEvaluationBoard />
  </main>
}
