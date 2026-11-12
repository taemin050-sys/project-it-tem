/** Mask editor adapted from Konva's MIT React free-drawing example.
 * Konva handles paths, erasing, touch and native-resolution PNG export.
 * Only an alpha mask is submitted; the signed server owns source PNGs.
 */
import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Stage, Layer, Line, Rect } from 'react-konva'
import type Konva from 'konva'
import { ApiError, request } from '../api/client'
import { revisionArtifactPath, revisionPath, type CopyFields } from '../api/resultRevisionContract'
import { download } from '../lib/download'
import { useFile } from '../lib/useVerifiedRevisionFile'
import RevisionCostDetails, { type RevisionCostSummary } from './RevisionCostDetails'

type Stroke = {tool: 'brush' | 'eraser'; width: number; points: number[]}
type Mark = Stroke | {tool: 'rect'; x: number; y: number; width: number; height: number}
type Result = {
  correction_id: string; edge_blend_applied?: boolean; state: string; revision: number; prompt: string; error_code?: string
  preview_sha: string | null; final_sha: string | null; caption_sha: string | null; receipt_sha: string | null
  artifacts: Partial<Record<'preview'|'final'|'caption'|'receipt',string>>
}
type Snapshot = {
  available: boolean; job_id: string; source_image_sha: string; source_artifact: string
  source_size: [number,number]; copy_sha: string; approval_sha: string; approved_copy: CopyFields
  corrections: Result[]; cost_summary: RevisionCostSummary
}
const STATUS: Record<string,string> = {QUEUED:'수정 대기',RUNNING:'선택 영역 수정 중',REVIEW_REQUIRED:'수정본 검수 필요',
  COMPLETED:'수정본 승인 완료',REJECTED:'수정본 거절',HOLD:'안전 확인 보류',BILLING_UNKNOWN:'과금 확인 필요 · 재호출 중지'}

export default function FinalInpaintingPanel({jobId,mode,canMutate}: {jobId:string;mode:'composed'|'freeform';canMutate:boolean}) {
  const [open,setOpen]=useState(false)
  const base=revisionPath(jobId,'final-inpainting')
  const query=useQuery({queryKey:['final-inpainting',jobId],enabled:open,retry:false,refetchOnWindowFocus:false,staleTime:10_000,
    queryFn:()=>request<Snapshot>(base),refetchInterval:q=>q.state.data?.corrections.some(r=>['QUEUED','RUNNING'].includes(r.state))?2500:false})
  return <details className="stack inpaint-panel" open={open} data-testid={`inpaint-${mode}`}
    onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>이 최종 시안에서 원하는 부분만 수정</summary>
    {open && <div className="stack">
      <p>완성된 {mode==='composed'?'합성형':'자유형'} 광고에서 바꿀 부분을 칠하고 요청을 적으세요. 선택 영역 밖은 원본 픽셀을 유지합니다.</p>
      <p className="field-hint">이미지 AI 1회 호출 · 기존 승인본 유지 · 수정본은 별도 검수 후 저장. 문구 자체를 바꾸려면 카피 수정·검수 기능을 이용하세요.</p>
      {query.isPending?<p role="status">최종 광고 불러오는 중…</p>:query.isError&&!query.data?<div role="alert">
        <p>편집 상태를 불러오지 못했습니다.</p><button className="button secondary small" onClick={()=>void query.refetch()}>다시 확인</button></div>:
        query.data?.available?<Workspace key={query.data.source_image_sha} snapshot={query.data} canMutate={canMutate} refresh={()=>query.refetch()} />:
          <p>현재 이 최종 광고의 부분 수정을 사용할 수 없습니다.</p>}
      {query.isError&&query.data&&<div role="alert"><p>최신 상태를 확인하지 못했습니다. 선택 영역과 입력 내용은 유지됩니다.</p><button className="button secondary small" onClick={()=>void query.refetch()}>상태 다시 확인</button></div>}
    </div>}
  </details>
}

function Workspace({snapshot,canMutate,refresh}: {snapshot:Snapshot;canMutate:boolean;refresh:()=>Promise<unknown>}) {
  const base=revisionPath(snapshot.job_id,'final-inpainting')
  const source=useFile(snapshot.source_artifact===`${base}/source?sha256=${snapshot.source_image_sha}`?snapshot.source_artifact:undefined,snapshot.source_image_sha)
  const [mask,setMask]=useState('')
  const [prompt,setPrompt]=useState('')
  const [paid,setPaid]=useState(false)
  const [pending,setPending]=useState(false)
  const [error,setError]=useState('')
  const [uncertain,setUncertain]=useState(false)
  const key=useRef<string|null>(null)
  const frozen=useRef<string|null>(null)
  const flight=useRef(false)
  const busy=snapshot.corrections.some(r=>['QUEUED','RUNNING','BILLING_UNKNOWN'].includes(r.state))
  // Preserve the same idempotency key and exact input after an uncertain POST.
  async function submit() {
    if(flight.current||busy||!mask||!paid||!canMutate)return
    flight.current=true;setPending(true);setError('')
    key.current??=crypto.randomUUID().replaceAll('-','')
    frozen.current??=JSON.stringify({expected_image_sha:snapshot.source_image_sha,expected_copy_sha:snapshot.copy_sha,
      expected_approval_sha:snapshot.approval_sha,mask_png_base64:mask,prompt,acknowledge_paid_edit:true,request_key:key.current})
    try {
      await request(base,{method:'POST',headers:{'Content-Type':'application/json'},body:frozen.current})
      key.current=null;frozen.current=null;setUncertain(false);setPaid(false)
    } catch(e){const maybeSent=!(e instanceof ApiError)||e.status===0||e.status>=500;setUncertain(maybeSent);if(!maybeSent){frozen.current=null;key.current=null}setError(e instanceof Error?e.message:'수정 요청 저장 실패')}
    finally{await refresh();flight.current=false;setPending(false)}
  }
  return <div className="stack">
    {source.url?<MaskEditor source={source.url} size={snapshot.source_size} disabled={!canMutate||busy||pending||uncertain} onMask={setMask} />:
      <div><p>원본 파일 확인 중…</p>{source.query.isError&&<button className="button secondary small" onClick={()=>void source.query.refetch()}>원본 다시 확인</button>}</div>}
    <label>어떻게 바꿀까요?<textarea value={prompt} maxLength={1200} rows={3} disabled={!canMutate||busy||pending||uncertain}
      placeholder="예: 왼쪽 배경의 물방울만 지워 주세요. 제품과 글자는 유지해 주세요."
      onChange={e=>setPrompt(e.target.value)} /></label>
    <label className="consent-label"><input type="checkbox" checked={paid} disabled={!canMutate||busy||pending}
      onChange={e=>setPaid(e.target.checked)} /><span>선택한 부분 수정에 이미지 AI를 1회 호출합니다. 수정본을 다시 검수하겠습니다.</span></label>
    {error&&<p role="alert" className="field-error">{error} 같은 요청을 다시 확인해도 새 유료 요청을 중복 실행하지 않습니다.</p>}
    <button className="button" disabled={!canMutate||busy||pending||!mask||prompt.trim().length<3||!paid} onClick={()=>void submit()}>
      {pending?'요청 저장 중…':uncertain?'동일 요청 상태 확인':'선택한 부분 수정 요청'}</button>
    {busy&&<p role="status">{snapshot.corrections.some(r=>r.state==='BILLING_UNKNOWN')?'과금 불확실 상태입니다. 자동 재호출하지 않습니다.':'한 번의 수정 요청을 처리하고 있습니다.'}</p>}
    {[...snapshot.corrections].reverse().map(row=><Review key={row.correction_id} row={row} snapshot={snapshot} canMutate={canMutate} refresh={refresh} />)}
    <RevisionCostDetails cost={snapshot.cost_summary} />
  </div>
}

function MaskEditor({source,size,disabled,onMask}: {source:string;size:[number,number];disabled:boolean;onMask:(value:string)=>void}) {
  const wrapper=useRef<HTMLDivElement>(null)
  const layer=useRef<Konva.Layer>(null)
  const [width,setWidth]=useState(280)
  const [marks,setMarks]=useState<Mark[]>([])
  const [redo,setRedo]=useState<Mark[]>([])
  const [tool,setTool]=useState<'brush'|'eraser'>('brush')
  const [brush,setBrush]=useState(60)
  const [exportRevision,setExportRevision]=useState(0)
  const [maskError,setMaskError]=useState('')
  const [rect,setRect]=useState([10,10,30,20])
  const drawing=useRef(false)
  const scale=width/size[0]
  useEffect(()=>{const node=wrapper.current;if(!node)return;const observer=new ResizeObserver(entries=>setWidth(Math.max(1,Math.min(560,entries[0].contentRect.width))));observer.observe(node);return()=>observer.disconnect()},[])
  useEffect(()=>{
    if(drawing.current)return
    if(!layer.current||!marks.length){onMask('');setMaskError('');return}
    const canvas=layer.current.toCanvas({x:0,y:0,width,height:width*size[1]/size[0],pixelRatio:size[0]/width})
    const pixels=canvas.getContext('2d')!.getImageData(0,0,canvas.width,canvas.height).data
    let count=0;for(let i=3;i<pixels.length;i+=4)if(pixels[i]>0)count++
    if(count===0||count>size[0]*size[1]*.85){onMask('');setMaskError(count===0?'수정할 영역을 칠해 주세요.':'부분 수정은 전체 이미지의 85% 이하로 선택해 주세요.');return}
    setMaskError('');const image=canvas.toDataURL('image/png');onMask(image.slice(image.indexOf(',')+1))
  },[marks,width,size,onMask,exportRevision])
  function position(stage:Konva.Stage) {
    const p=stage.getPointerPosition()
    return p?[Math.max(0,Math.min(size[0]-.01,p.x/scale)),Math.max(0,Math.min(size[1]-.01,p.y/scale))]:null
  }
  function stop(){drawing.current=false;setExportRevision(v=>v+1)}
  return <div className="stack">
    <div className="button-row">
      <button className="button secondary small" type="button" aria-pressed={tool==='brush'} disabled={disabled} onClick={()=>setTool('brush')}>브러시</button>
      <button className="button secondary small" type="button" aria-pressed={tool==='eraser'} disabled={disabled} onClick={()=>setTool('eraser')}>지우개</button>
      <button className="button secondary small" type="button" disabled={disabled||!marks.length} onClick={()=>{setRedo(r=>[...r,marks.at(-1)!]);setMarks(m=>m.slice(0,-1))}}>되돌리기</button>
      <button className="button secondary small" type="button" disabled={disabled||!redo.length} onClick={()=>{setMarks(m=>[...m,redo.at(-1)!]);setRedo(r=>r.slice(0,-1))}}>다시 실행</button>
      <button className="button secondary small" type="button" disabled={disabled||!marks.length} onClick={()=>{setMarks([]);setRedo([])}}>선택 지우기</button>
    </div>
    <label>브러시 크기 {brush}px<input type="range" min={8} max={240} step={4} value={brush} disabled={disabled} onChange={e=>setBrush(Number(e.target.value))} /></label>
    <p className="field-hint">색으로 표시된 부분만 바뀝니다. 마우스나 손가락으로 칠하세요. 키보드로는 아래 사각 영역을 지정할 수 있습니다.</p>
    <div ref={wrapper} className="inpaint-canvas" style={{position:'relative',width:'100%',maxWidth:560,touchAction:'none'}}
      role="img" aria-label="최종 광고 부분 수정 마스크 편집기">
      <img src={source} alt="부분 수정을 위한 승인된 최종 광고" style={{display:'block',width:'100%',height:'auto',pointerEvents:'none'}} />
      <div style={{position:'absolute',inset:0,opacity:.65}}>
        <Stage width={width} height={width*size[1]/size[0]} scaleX={scale} scaleY={scale}
          onPointerDown={e=>{if(disabled||marks.length>=500)return;const p=position(e.target.getStage()!);if(!p)return;drawing.current=true;onMask('');setRedo([]);
            (e.evt.target as HTMLElement).setPointerCapture?.(e.evt.pointerId);
            setMarks(m=>[...m,{tool,width:brush,points:[...p,p[0]+.01,p[1]+.01]}])}}
          onPointerMove={e=>{if(!drawing.current||disabled)return;const p=position(e.target.getStage()!);if(!p)return;
            setMarks(m=>{const last=m.at(-1);return !last||last.tool==='rect'||last.points.length>20000?m:[...m.slice(0,-1),{...last,points:[...last.points,...p]}]})}}
          onPointerUp={stop} onPointerCancel={stop}>
          <Layer ref={layer} listening={false}>{marks.map((mark,i)=>mark.tool==='rect'?<Rect key={i} {...mark} fill="#f05a9d" />:
            <Line key={i} points={mark.points} stroke="#f05a9d" strokeWidth={mark.width} lineCap="round" lineJoin="round"
              globalCompositeOperation={mark.tool==='eraser'?'destination-out':'source-over'} />)}</Layer>
        </Stage>
      </div>
    </div>
    <details><summary>사각 영역을 숫자로 지정</summary><div className="stack">
      {['왼쪽','위쪽','너비','높이'].map((name,i)=><label key={name}>{name} (%)<input type="number" min={0} max={100} value={rect[i]} disabled={disabled}
        onChange={e=>setRect(r=>r.map((v,k)=>k===i?Number(e.target.value):v))} /></label>)}
      <button className="button secondary small" type="button" disabled={disabled||rect.some(v=>!Number.isFinite(v)||v<0)||rect[2]<=0||rect[3]<=0||rect[0]+rect[2]>100||rect[1]+rect[3]>100}
        onClick={()=>{setRedo([]);setMarks(m=>[...m,{tool:'rect',x:rect[0]*size[0]/100,y:rect[1]*size[1]/100,width:rect[2]*size[0]/100,height:rect[3]*size[1]/100}])}}>사각 영역 추가</button>
    </div></details>
    {maskError&&<p role="alert" className="field-error">{maskError}</p>}
    <p role="status">{marks.length?`선택 작업 ${marks.length}개 · 원본 해상도 ${size[0]}×${size[1]}`:'아직 선택한 영역이 없습니다.'}</p>
  </div>
}

function Review({row,snapshot,canMutate,refresh}: {row:Result;snapshot:Snapshot;canMutate:boolean;refresh:()=>Promise<unknown>}) {
  const base=revisionPath(snapshot.job_id,'final-inpainting')
  const path=(kind:'preview'|'final'|'caption'|'receipt')=>revisionArtifactPath(snapshot.job_id,'final-inpainting',row.correction_id,kind,row.artifacts[kind],row[`${kind}_sha`])
  const image=useFile(path(row.state==='COMPLETED'?'final':'preview'),row.state==='COMPLETED'?row.final_sha:row.preview_sha)
  const caption=useFile(path('caption'),row.caption_sha)
  const receipt=useFile(path('receipt'),row.receipt_sha)
  const [checks,setChecks]=useState({product_matches:false,label_matches:false,cta_policy_matches:false,no_extra_text:false})
  const [observed,setObserved]=useState<CopyFields>({headline:'',subline:'',cta:''})
  const [pending,setPending]=useState(false)
  const [error,setError]=useState('')
  const flight=useRef(false)
  const ready=Object.values(checks).every(Boolean)&&Object.keys(observed).every(k=>observed[k as keyof CopyFields]===snapshot.approved_copy[k as keyof CopyFields])
  async function decide(approve:boolean) {
    if(flight.current)return;flight.current=true;setPending(true);setError('')
    try{await request(`${base}/${row.correction_id}/decision`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      expected_revision:row.revision,expected_preview_sha:row.preview_sha,approve,...(approve?{visual_review:{...checks,observed_copy:observed}}:{})})})}
    catch(e){setError(e instanceof Error?e.message:'검수 저장 실패')}
    finally{await refresh();flight.current=false;setPending(false)}
  }
  async function blendEdges() {
    if(flight.current)return;flight.current=true;setPending(true);setError('')
    try{await request(`${base}/${row.correction_id}/blend-edges`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:row.revision,expected_preview_sha:row.preview_sha})})}
    catch(e){setError(e instanceof Error?e.message:'경계 블렌딩 실패')}
    finally{await refresh();flight.current=false;setPending(false)}
  }
  return <section className="stack panel" aria-label="부분 수정 결과">
    <h3>{STATUS[row.state]??row.state}</h3><p>{row.prompt}</p>
    {row.error_code&&<p role="alert">처리를 중단했습니다. 추가 호출 없이 상태를 확인하세요. {row.error_code}</p>}
    {image.url&&<img className="result-image" style={{aspectRatio:`${snapshot.source_size[0]} / ${snapshot.source_size[1]}`}} src={image.url} alt="선택 영역을 수정한 새 광고" />}
    {row.state==='REVIEW_REQUIRED'&&!row.edge_blend_applied&&<div className="stack"><p>이전 수정본은 경계를 먼저 블렌딩한 뒤 새 시안으로 검수합니다. 모델 추가 호출은 없습니다.</p><button className="button secondary" disabled={!canMutate||pending} onClick={()=>void blendEdges()}>추가 과금 없이 경계 블렌딩</button></div>}
    {row.state==='REVIEW_REQUIRED'&&<fieldset className="stack"><legend>원본과 수정본을 대조해 검수</legend>
      {([['product_matches','제품 전체·브랜드가 원본과 일치합니다.'],['label_matches','라벨을 확대해 원본과 대조했습니다.'],
        ['cta_policy_matches','CTA가 정확하며 제품을 가리지 않습니다.'],['no_extra_text','추가 주장·오탈자·중복이 없고 경계가 자연스럽습니다.']] as const).map(([k,label])=>
        <label key={k} className="consent-label"><input type="checkbox" disabled={!canMutate||pending} checked={checks[k]} onChange={e=>setChecks(c=>({...c,[k]:e.target.checked}))} /><span>{label}</span></label>)}
      {([['headline','헤드라인'],['subline','서브 문구'],['cta','CTA']] as const).map(([k,label])=><label key={k}>이미지에서 읽은 {label}
        <textarea value={observed[k]} disabled={!canMutate||pending} onChange={e=>setObserved(o=>({...o,[k]:e.target.value}))} /></label>)}
      {error&&<p role="alert">{error}</p>}
      <div className="button-row"><button className="button secondary small" disabled={!canMutate||pending} onClick={()=>void decide(false)}>이 수정본 거절</button>
        <button className="button" disabled={!canMutate||pending||!image.url||!ready||!row.edge_blend_applied} onClick={()=>void decide(true)}>이 수정본 승인</button></div>
    </fieldset>}
    {row.state==='COMPLETED'&&<div className="button-row">
      <button className="button" disabled={!image.url} onClick={()=>download(image.url!,`inpaint_${row.correction_id}.png`)}>수정본 PNG 저장</button>
      <button className="button secondary small" disabled={!caption.url} onClick={()=>download(caption.url!,`inpaint_caption_${row.correction_id}.txt`)}>본문 TXT 저장</button>
      <button className="button secondary small" disabled={!receipt.url} onClick={()=>download(receipt.url!,`inpaint_receipt_${row.correction_id}.json`)}>Receipt 저장</button>
    </div>}
    <RevisionCostDetails cost={snapshot.cost_summary} revisionId={row.correction_id} />
  </section>
}
