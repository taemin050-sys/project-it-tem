/**
 * A4-1: Actual Owner/PM Track A React Product -> Copy -> Draft -> Export.
 * Local loopback-only OFFLINE_FIXTURE, user clicks via Chrome, zero paid calls.
 * Prerequisite: isolated FastAPI make_demo_app + real Vite QA build.
 * Secrets only from A41_INVITE_FILE, never emitted to evidence.
 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const toolPath = process.env.A41_PLAYWRIGHT_CORE_MODULE;
if (!toolPath) throw Error('A41_PLAYWRIGHT_CORE_MODULE_REQUIRED');
const {chromium} = require(toolPath);
const base = process.env.A41_BASE_URL;
const dest = process.env.A41_EVIDENCE_DIR;
const invitePath = process.env.A41_INVITE_FILE;
const photos = [process.env.A41_PHOTO_1, process.env.A41_PHOTO_2];
const sourceSha = process.env.A41_SOURCE_SHA;
if (!base || !/^http:\/\/127\.0\.0\.1:[0-9]{4,5}$/.test(base) ||
    !dest || !invitePath || !photos.every(p=>p&&fs.existsSync(p)) ||
    !/^[a-f0-9]{40}$/.test(sourceSha||'')) {
  throw Error('A41_LOCAL_ONLY_PRECONDITION_MISSING');
}
fs.mkdirSync(dest,{recursive:true});
const evidence = {contract:'IT_TEM_A41_OFFICIAL_REACT_CHROME_FIXTURE_V1',
  source_commit:sourceSha,qa_fixture:true,actual_react_app:true,
  real_provider_e2e:'NOT_AUDITED',human_ad_quality:'NOT_ACCEPTED',
  origin:base, steps:[],http:[],screenshots:[],exfiltration_attempts:[],
  browser_errors:[],network_external_post_count:0};
let page,context,browser,jobId;
const wait = ms=>new Promise(r=>setTimeout(r,ms));
const bytes = b=>crypto.createHash('sha256').update(b).digest('hex');
function record(label,snapshot,extra={}) {
  evidence.steps.push({label,job_id:jobId||null,
    state:snapshot?.state??null,input_sha:snapshot?.input_sha??null,
    copy_sha:snapshot?.copy_sha??null,review_sha:snapshot?.review_sha??null,
    generation:snapshot?.generation??null,approval_current:snapshot?.approval_current??null,
    image_sha:snapshot?.image_sha??null,image_attempt_version:snapshot?.image_attempt_version??null,
    final_sha:snapshot?.final_sha??null,caption_sha:snapshot?.caption_sha??null,
    generation_mode:snapshot?.generation_mode??null,image_size:snapshot?.image_size??null,...extra});
  console.log('STEP_OK',label,snapshot?.state??'UI_ONLY');
}
async function shot(name) {
  const f=path.join(dest,name+'.png');
  await page.screenshot({path:f,fullPage:true});
  evidence.screenshots.push({filename:path.basename(f),sha256:bytes(fs.readFileSync(f))});
}
async function api(u,method='GET',body) {
  return await page.evaluate(async({u,method,body})=>{
    const r=await fetch(u,{method,credentials:'same-origin',cache:'no-store',
      ...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
    let j=null;try{j=await r.clone().json()}catch{}
    return {status:r.status,body:j};
  },{u,method,body});
}
async function snap() {
  const r=await api('/demo/api/live/jobs/'+jobId);
  assert.equal(r.status,200,'Authoritative snapshot GET denied: '+r.status);
  return r.body;
}
async function untilState(target,timeout=20000) {
  const start=Date.now();
  for (;;) {
    let s;
    try{s=await snap()}catch{}
    if(s && (Array.isArray(target)?target.includes(s.state):s.state===target))return s;
    if(Date.now()-start>timeout)throw Error('STATE_TIMEOUT '+target+' last='+s?.state);
    await wait(350);
  }
}
async function waitEnabled(name,timeout=20000) {
  await page.waitForFunction(label=>{
    const b=[...document.querySelectorAll('button')].find(el=>el.textContent.trim()===label);
    return b && !b.disabled;
  },name,{timeout});
}
async function browserSha(url) {
  return await page.evaluate(async u=>{
    const r=await fetch(u,{credentials:'same-origin',cache:'no-store'});
    if(!r.ok)return {status:r.status};
    const arr=await r.arrayBuffer(),hash=await crypto.subtle.digest('SHA-256',arr);
    return {status:r.status,sha256:Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join(''),bytes:arr.byteLength,content_type:r.headers.get('content-type')};
  },url);
}
async function checkNoPaid() {
  // Separate browser-side disabled LIVE gate, not a license to activate it.
  const r=await api('/demo/api/live/capabilities');
  assert.equal(r.status,200);
  assert.equal(r.body.live_enabled,false);
  assert.equal(r.body.image_generation.candidate_count,1);
  assert.equal(r.body.image_generation.batch_supported,false);
}
(async ()=>{
  browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless:true,args:['--no-first-run','--disable-background-networking','--no-default-browser-check']});
  try {
    context=await browser.newContext({acceptDownloads:true,viewport:{width:1440,height:900},
      downloadsPath:dest,serviceWorkers:'block'});
    page=await context.newPage();
    page.on('pageerror',err=>evidence.browser_errors.push('PAGE_SCRIPT_ERROR: '+String(err.message).slice(0,400)));
    page.on('request',request=>{
      const u=request.url();
      if(u.startsWith('http:')||u.startsWith('https:')){
        const url=new URL(u);
        if(url.origin!==base){
          evidence.exfiltration_attempts.push({method:request.method(),host:url.hostname});
          if(request.method()==='POST')evidence.network_external_post_count++;
        }
      }
    });
    page.on('response',response=>{
      let u;
      try{u=new URL(response.url())}catch{return}
      if(u.origin===base && (u.pathname.startsWith('/api/')||u.pathname.startsWith('/demo/api/'))){
        evidence.http.push({method:response.request().method(),path:u.pathname,
          status:response.status()});
      }
    });
    await page.route('**/*',route=>{
      const u=route.request().url();
      if(u.startsWith('blob:')||u.startsWith('data:'))return route.continue();
      let parsed;
      try{parsed=new URL(u)}catch{return route.abort()}
      if(parsed.origin!==base)return route.abort();
      return route.continue();
    });
    await page.goto(base+'/',{waitUntil:'domcontentloaded'});
    await page.locator('#demo-invite').fill(fs.readFileSync(invitePath,'utf8'));
    await page.getByRole('button',{name:'시연 시작'}).click();
    await page.getByText('IT-TEM QA OFFLINE_FIXTURE',{exact:false}).first().waitFor({timeout:15000});
    assert.match(await page.locator('body').innerText(),/실제 AI 아님/);
    await checkNoPaid();
    await shot('01_qa_login');
    record('QA_USER_LOGIN',null,{user:'alice',auth:'INVITE_COOKIE_LOOPBACK_ONLY'});

    await page.goto(base+'/create/product',{waitUntil:'domcontentloaded'});
    await page.locator('#photos').setInputFiles(photos);
    await page.getByText('2 / 5장').first().waitFor({timeout:10000});
    await page.locator('#brand_name').fill('라움');
    await page.locator('#product_name').fill('데일리 크림');
    await page.locator('#product_category').selectOption('스킨케어');
    await page.locator('#features').fill('보습과 촉촉한 사용감');
    await page.locator('#photo_verified').check();
    await page.locator('input[name="generation-mode"][value="composed"]').check();
    await page.locator('input[name="ratio"][value="4:5"]').check();
    await shot('02_selected_composed_4x5');
    const created = page.waitForResponse(r=>r.request().method()==='POST' &&
      new URL(r.url()).pathname==='/api/v1/jobs',{timeout:15000});
    await page.getByRole('button',{name:'다음: 기획·카피 만들기'}).click();
    const createResponse=await created,createdData=await createResponse.json();
    assert.equal(createResponse.status(),201);
    jobId=createdData.job_id;
    assert.match(jobId,/^[a-f0-9]{32}$/);
    await page.waitForURL('**/create/copy',{timeout:15000});
    let s=await untilState('COPY_REVIEW_REQUIRED');
    assert.equal(s.generation_mode,'composed');
    assert.equal(s.image_size,'4:5');
    assert.match(s.input_sha,/^[a-f0-9]{64}$/);
    record('UPLOAD_AND_COPY_FIXTURE',s,{uploaded_product_photos:2});
    await waitEnabled('수정 요청');
    await shot('03_copy_review_initial');
    const initialCopy={copy_sha:s.copy_sha,review_sha:s.review_sha,generation:s.generation};
    assert.equal((await browserSha('/demo/api/qa/jobs/'+jobId+'/artifacts/candidate')).status,409);
    assert.equal((await browserSha('/demo/api/qa/jobs/'+jobId+'/artifacts/final')).status,409);
    const batchCases={};
    for (const count of [2,3,4]) {
      const negative=await api('/demo/api/qa/jobs/'+jobId+'/prompt-image?candidate_count='+count,'POST');
      assert.equal(negative.status,422);
      batchCases['candidate_count_'+count]=negative.status;
    }
    const mixed=await api('/demo/api/qa/jobs/'+jobId+'/prompt-image?image_modes=freeform,composed','POST');
    assert.equal(mixed.status,422);
    record('PREAPPROVAL_AND_BATCH_REJECTION',s,{
      http_unapproved_candidate:409, ...batchCases, mixed_modes_http:mixed.status});

    await page.getByRole('button',{name:'수정 요청',exact:true}).click();
    await page.locator('textarea[maxlength="300"]').fill('헤드라인을 좀 더 산뜻하게 바꿔 주세요');
    await page.getByRole('button',{name:'수정 요청 보내기'}).click();
    for(let i=0;i<60;i++){s=await snap();if(s.generation>initialCopy.generation)break;await wait(300)}
    assert.equal(s.generation,initialCopy.generation+1);
    assert.notEqual(s.review_sha,initialCopy.review_sha);
    assert.equal(s.approval_current,false);
    record('COPY_REVISION_CHANGED_SHA_AND_GENERATION',s);
    await waitEnabled('이전 버전으로 되돌리기');
    await shot('04_revised_copy');
    await page.getByRole('button',{name:'이전 버전으로 되돌리기'}).click();
    for(let i=0;i<60;i++){s=await snap();if(s.generation>initialCopy.generation+1)break;await wait(300)}
    assert.equal(s.generation,initialCopy.generation+2);
    assert.equal(s.copy_sha,initialCopy.copy_sha,'restore exact initial approved copy');
    assert.notEqual(s.review_sha,initialCopy.review_sha,'restore must not revive old review hash');
    assert.equal(s.approval_current,false);
    record('COPY_RESTORED_BUT_OLD_APPROVAL_NOT_REVIVED',s);
    await waitEnabled('수정 요청');
    const restoreGen=s.generation,restoreReview=s.review_sha,restoreCopy=s.copy_sha;
    const staleApprove=await api('/demo/api/live/jobs/'+jobId+'/approve-copy','POST',{
      expected_generation:initialCopy.generation,
      expected_review_sha:initialCopy.review_sha,acknowledge_evidence:true});
    assert.ok([409,422].includes(staleApprove.status));
    record('STALE_COPY_APPROVAL_DENIED',s,{http_stale_approval:staleApprove.status});
    await shot('05_copy_restore_no_ack');
    const ack=page.locator('input[type="checkbox"]').first();
    await ack.check();
    await waitEnabled('이 카피로 이미지 만들기');
    await page.getByRole('button',{name:'이 카피로 이미지 만들기'}).click();
    await page.waitForURL('**/create/draft',{timeout:20000});
    s=await untilState('IMAGE_REVIEW_REQUIRED',20000);
    assert.equal(s.copy_sha,restoreCopy);
    assert.equal(s.review_sha,restoreReview);
    assert.equal(s.generation,restoreGen);
    assert.equal(s.image_attempt_version,1);
    assert.equal(s.approval_current,true);
    const img1=await browserSha('/demo/api/qa/jobs/'+jobId+'/artifacts/candidate');
    assert.equal(img1.sha256,s.image_sha);
    record('ONE_IMAGE_AFTER_COPY_APPROVAL',s,{candidate_bytes:img1.bytes});
    await waitEnabled('이 이미지로 광고 완성하기');
    await shot('06_first_candidate_1_of_1');
    await page.getByRole('button',{name:'이미지 거절'}).click();
    s=await untilState('IMAGE_REJECTED');
    assert.equal(s.image_sha,img1.sha256);
    assert.equal((await browserSha('/demo/api/qa/jobs/'+jobId+'/artifacts/candidate')).status,409);
    record('EXPLICIT_IMAGE_REJECTION',s);
    await waitEnabled('승인 카피 유지하고 이미지 다시 만들기');
    await shot('07_image_rejected');
    await page.getByRole('button',{name:'승인 카피 유지하고 이미지 다시 만들기'}).click();
    s=await untilState('IMAGE_REVIEW_REQUIRED');
    assert.equal(s.image_attempt_version,2);
    assert.equal(s.copy_sha,restoreCopy);
    assert.equal(s.review_sha,restoreReview);
    assert.equal(s.generation,restoreGen);
    assert.notEqual(s.image_sha,img1.sha256);
    const img2=await browserSha('/demo/api/qa/jobs/'+jobId+'/artifacts/candidate');
    assert.equal(img2.sha256,s.image_sha);
    const oldApprove=await api('/demo/api/live/jobs/'+jobId+'/approve-image','POST',{image_sha:img1.sha256});
    assert.ok([409,422].includes(oldApprove.status));
    record('SECOND_CANDIDATE_NEW_ATTEMPT_NEW_SHA',s,
      {first_image_sha:img1.sha256,second_image_sha:img2.sha256,old_approval_http:oldApprove.status});
    await waitEnabled('이 이미지로 광고 완성하기');
    await shot('08_new_candidate_after_retry');
    await page.getByRole('button',{name:'이 이미지로 광고 완성하기'}).click();
    await page.waitForURL('**/create/export',{timeout:20000});
    s=await untilState('COMPLETED',20000);
    assert.equal(s.image_sha,img2.sha256);
    assert.deepEqual(s.output_size,{width:1080,height:1350});
    assert.match(s.final_sha,/^[a-f0-9]{64}$/);
    assert.match(s.caption_sha,/^[a-f0-9]{64}$/);
    record('COMPOSED_FINAL_ARTIFACT_READY',s);
    await waitEnabled('광고 이미지 저장 (PNG)',15000);
    await shot('09_final_desktop');
    let pending=page.waitForEvent('download',{timeout:15000});
    await page.getByRole('button',{name:'광고 이미지 저장 (PNG)'}).click();
    const imageDownload=await pending;
    const imageFile=path.join(dest,'ad_1080x1350.png');
    await imageDownload.saveAs(imageFile);
    assert.equal(bytes(fs.readFileSync(imageFile)),s.final_sha);
    pending=page.waitForEvent('download',{timeout:15000});
    await page.getByRole('button',{name:'텍스트 저장 (.txt)'}).click();
    const textDownload=await pending;
    const textFile=path.join(dest,'caption.txt');
    await textDownload.saveAs(textFile);
    assert.equal(bytes(fs.readFileSync(textFile)),s.caption_sha);
    const caption=fs.readFileSync(textFile,'utf8');
    assert.ok(caption.includes(s.copy.ad_copy.headline)||caption.includes('매일'),'expected Korean in caption');
    record('ACTUAL_CHROME_DOWNLOAD_SHA_MATCH',s,{file_image_sha256:bytes(fs.readFileSync(imageFile)),
      file_caption_sha256:bytes(fs.readFileSync(textFile)),
      png_bytes:fs.statSync(imageFile).size,caption_bytes:fs.statSync(textFile).size});
    const mark=evidence.http.length;
    await page.reload({waitUntil:'domcontentloaded'});
    await waitEnabled('광고 이미지 저장 (PNG)',15000);
    const afterRefresh=evidence.http.slice(mark);
    assert.equal(afterRefresh.filter(e=>e.method==='POST').length,0,'reload must GET-only');
    s=await snap();
    assert.equal(s.state,'COMPLETED');
    record('GET_ONLY_REFRESH_RESUME',s,{post_count_after_reload:0});
    await shot('10_final_refresh');

    for(const width of [390,360]){
      await page.setViewportSize({width,height:844});
      await shot('11_mobile_'+width);
      record('MOBILE_VIEWPORT_'+width,s,{viewport:{width,height:844},
        scroll_width:await page.evaluate(()=>document.documentElement.scrollWidth)});
    }
    // Separate unprivileged actor context: never expose same session cookie.
    const visitor=await browser.newContext({viewport:{width:390,height:844}});
    const stranger=await visitor.newPage();
    const unauthorized=await stranger.request.get(base+'/demo/api/live/jobs/'+jobId);
    assert.equal(unauthorized.status(),401);
    const bobCode='not'+fs.readFileSync(invitePath,'utf8');
    const bobAuth=await stranger.request.post(base+'/demo/api/session',{
      headers:{Origin:base,'Content-Type':'application/json'},
      data:{invite_code:bobCode}});
    assert.equal(bobAuth.status(),200);
    const foreign=await stranger.request.get(base+'/demo/api/live/jobs/'+jobId);
    assert.equal(foreign.status(),404);
    record('FOREIGN_ACTOR_AND_UNAUTHENTICATED_DENIED',s,{
      http_without_session:401,http_foreign_actor:404});
    await visitor.close();
    await checkNoPaid();
    assert.equal(evidence.network_external_post_count,0);
    assert.deepEqual(evidence.exfiltration_attempts,[]);
    assert.deepEqual(evidence.browser_errors,[]);
    evidence.completed_job_id=jobId;
    evidence.final_state=s.state;
    evidence.final_sha=s.final_sha;
    evidence.caption_sha=s.caption_sha;
    evidence.image_attempt_version=s.image_attempt_version;
    evidence.http_totals={post:evidence.http.filter(x=>x.method==='POST').length,
      get:evidence.http.filter(x=>x.method==='GET').length};
    fs.writeFileSync(path.join(dest,'browser_trace.json'),JSON.stringify(evidence,null,2)+'\n');
    console.log('A41_OFFICIAL_REACT_CHROME_FIXTURE_E2E_PASS',jobId,
      'STEPS',evidence.steps.length,'DOWNLOAD_SHA_MATCH=2/2','EXTERNAL_POST=0');
  } catch(error) {
    console.error('A41_BROWSER_ERROR',error.stack);
    try{if(page)await page.screenshot({path:path.join(dest,'FAILURE_SCREENSHOT.png'),fullPage:true})}catch{}
    evidence.error=String(error.message);
    fs.writeFileSync(path.join(dest,'browser_trace_failed.json'),JSON.stringify(evidence,null,2)+'\n');
    process.exitCode=1;
  } finally {
    if(context)await context.close();
    await browser.close();
  }
})().catch(error=>{console.error('A41_BROWSER_BOOTSTRAP_ERROR',error.stack);process.exit(1)});
