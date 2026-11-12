/** A51D real official React Chrome + authenticated demo B0 Job HTTP E2E,
 * OFFLINE_FIXTURE synthetic 2-frame JPG-named MPO. No live model or Provider.
 * All local public URLs must be loopback, private invitation is never logged.
 */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {chromium}=require(process.env.A41_PLAYWRIGHT_CORE_MODULE);
const base=process.env.A41_BASE_URL;
const evidencePath=process.env.A41_EVIDENCE_DIR;
const photo1=process.env.A41_PHOTO_1;
const photo2=process.env.A41_PHOTO_2;
const invite=process.env.A41_INVITE_FILE;
const sha=process.env.A41_SOURCE_SHA;
if(!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(base||'') ||
   !/^[a-f0-9]{40}$/.test(sha||'') ||
   ![photo1,photo2,invite].every(p=>p&&fs.existsSync(p)) ||
   !evidencePath)throw Error('A51D_LOCAL_FIXTURE_REQUIRED');
fs.mkdirSync(evidencePath,{recursive:true});
const sha256=data=>crypto.createHash('sha256').update(data).digest('hex');
const evidence={
  contract:'IT_TEM_P03_A51D_OFFICIAL_REACT_MPO_ACTOR_JOB_BROWSER_FIXTURE_V1',
  source_commit:sha,official_react_chrome:true,live_provider_calls:0,
  paid_model:false,owner_policy_approved:false,real_product:false,
  browser_errors:[],external_requests:[],http:[],screenshots:[],
  browser_confirmed_mpo_frame_index:1,job_id:null,
  status:'PENDING',observed_source_sha:null,derived_sha:null,
  actor_job_acl:null,step_results:[],
};
const record=(name,detail={})=>{
  evidence.step_results.push({step:name,...detail});
  console.log('A51D_STEP_PASS',name);
};
(async()=>{
  let browser;
  try{
    browser=await chromium.launch({
      executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      headless:true,args:['--no-first-run','--disable-background-networking','--no-default-browser-check'],
    });
    const context=await browser.newContext({viewport:{width:1440,height:900},serviceWorkers:'block'});
    const page=await context.newPage();
    page.on('pageerror',e=>evidence.browser_errors.push(String(e.message).slice(0,300)));
    page.on('request',req=>{
      try{const u=new URL(req.url());
        if(u.protocol.startsWith('http')&&u.origin!==base)
          evidence.external_requests.push({method:req.method(),host:u.hostname});
      }catch{}
    });
    page.on('response',res=>{
      try{const u=new URL(res.url());
        if(u.origin===base && (u.pathname.startsWith('/api/')||
                              u.pathname.startsWith('/demo/api/')))
          evidence.http.push({method:res.request().method(),
                              path:u.pathname,status:res.status()});
      }catch{}
    });
    await page.route('**/*',route=>{
      const u=route.request().url();
      if(u.startsWith('blob:')||u.startsWith('data:'))return route.continue();
      try{if(new URL(u).origin===base)return route.continue()}catch{}
      return route.abort();
    });
    const shot=async(name)=>{
      const f=path.join(evidencePath,name+'.png');
      await page.screenshot({path:f,fullPage:true});
      evidence.screenshots.push({name,sha256:sha256(fs.readFileSync(f))});
    };
    await page.goto(base+'/',{waitUntil:'domcontentloaded'});
    await page.locator('#demo-invite').fill(fs.readFileSync(invite,'utf8'));
    await page.getByRole('button',{name:'시연 시작'}).click();
    await page.getByText('IT-TEM QA OFFLINE_FIXTURE',{exact:false}).first()
      .waitFor({timeout:15000});
    record('ACTUAL_OWNER_REACT_INVITE_AUTH_LOCAL');
    await page.goto(base+'/create/product',{waitUntil:'domcontentloaded'});
    const pendingResponse=page.waitForResponse(r=>
      r.request().method()==='POST'&&
      new URL(r.url()).pathname==='/demo/api/a51d/mpo/preview',
      {timeout:15000});
    await page.locator('#photos').setInputFiles([photo1,photo2]);
    const previewResponse=await pendingResponse;
    assert.equal(previewResponse.status(),200);
    const preview=await previewResponse.json();
    assert.equal(preview.source_frame_count,2);
    assert.equal(preview.contract_final_owner_approved,false);
    assert.equal(preview.source_sha256,sha256(fs.readFileSync(photo1)));
    assert.equal(preview.frames.length,2);
    record('HIDDEN_MPO_IN_JPG_DETECTED_NO_FRAME0_DEFAULT',
      {source_sha:preview.source_sha256,frame_count:2});
    const prompt=page.locator('section[aria-label="MPO 프레임 직접 선택"]');
    await prompt.waitFor({timeout:15000});
    await shot('01_actual_react_frame0_frame1_preview');
    assert.equal(await prompt.getByRole('button',{name:'선택한 프레임 확정'})
      .isDisabled(),true);
    const chooseFrame1=prompt.locator('button').filter({hasText:'프레임 2'}).first();
    await chooseFrame1.click();
    assert.equal(await chooseFrame1.getAttribute('aria-pressed'),'true');
    await shot('02_user_chose_frame_index1');
    const confirmedAction=page.waitForResponse(r=>
      r.request().method()==='POST'&&
      new URL(r.url()).pathname==='/demo/api/a51d/mpo/confirm',
      {timeout:15000});
    await prompt.getByRole('button',{name:'선택한 프레임 확정'}).click();
    const confirmedResponse=await confirmedAction;
    assert.equal(confirmedResponse.status(),200);
    const confirmedJson=await confirmedResponse.json();
    assert.equal(confirmedJson.confirmed,true);
    assert.equal(confirmedJson.frame_index,1);
    record('ACTOR_BOUND_SERVER_CONFIRM_CAS_ACTION');
    await page.getByText('2 / 5장').first().waitFor({timeout:15000});
    assert.match(await page.locator('#photos').evaluate(el=>
      el.closest('section')?.textContent||''),/2 \/ 5장/);
    record('EXPLICIT_PREVIEW_FRAME1_CONFIRMED_IN_REACT');
    await page.locator('#brand_name').fill('라움');
    await page.locator('#product_name').fill('데일리 크림');
    await page.locator('#product_category').selectOption('스킨케어');
    await page.locator('#features').fill('보습과 촉촉한 사용감');
    await page.locator('#photo_verified').check();
    await page.locator('input[name="generation-mode"][value="composed"]')
      .locator('xpath=..').click();
    await page.locator('input[name="ratio"][value="4:5"]')
      .locator('xpath=..').click();
    const created=page.waitForResponse(r=>
      r.request().method()==='POST'&&
      new URL(r.url()).pathname==='/demo/api/a51d/mpo/jobs',
      {timeout:20000});
    await page.getByRole('button',{name:'다음: 기획·카피 만들기'}).click();
    const resp=await created;
    assert.equal(resp.status(),201,await resp.text());
    const job=await resp.json();
    evidence.job_id=job.job_id;
    const first=job.assets[0].source_provenance;
    assert.equal(first.selected_frame,1);
    assert.equal(first.original_sha256,preview.source_sha256);
    assert.equal(first.selected_frame_preview_png_sha256,
                 preview.frames[1].preview_png_sha256);
    assert.equal(first.color_normalization_contract,'EXIF_UPRIGHT_ICC_TO_SRGB_V2');
    assert.equal(first.external_provider_transfer_permitted,false);
    assert.match(first.normalized_sha256,/^[a-f0-9]{64}$/);
    assert.equal(job.assets.length,2);
    assert.equal(job.status,'INPUTS_VALIDATED');
    evidence.observed_source_sha=first.original_sha256;
    evidence.derived_sha=first.normalized_sha256;
    record('EXPLICIT_FRAME_B0_JOB_PROVENANCE_SHA_COMMITTED',
      {frame:1,derived_sha:first.normalized_sha256});
    await page.waitForURL('**/create/copy',{timeout:15000});
    const seen=await page.request.get(base+'/demo/api/live/jobs/'+job.job_id);
    assert.equal(seen.status(),200);
    const live=await seen.json();
    assert.equal(live.image_size,'4:5');
    assert.equal(live.generation_mode,'composed');
    record('ACTUAL_REACT_ADVANCED_TO_LIVE_COPY_JOURNEY',
      {mode:live.generation_mode,ratio:live.image_size,live_state:live.state});
    const b0=await page.request.get(base+'/api/v1/jobs/'+job.job_id);
    assert.equal(b0.status(),200);
    assert.equal((await b0.json()).assets[0].sha256,first.normalized_sha256);
    await shot('03_after_job_commit_copy_ui');
    // Complete the already C-A accepted Text→Image→Compose fixture journey
    // from the NEW authorized MPO-Job input, not from a manually seeded Job.
    const untilState=async(target,seconds=25)=>{
      const start=Date.now();
      for(;;){
        const response=await page.request.get(base+'/demo/api/live/jobs/'+job.job_id);
        assert.equal(response.status(),200);
        const state=await response.json();
        if(state.state===target)return state;
        if(Date.now()-start>seconds*1000)
          throw Error('A51D_BROWSER_LIVE_STATE_TIMEOUT_'+target+'_'+state.state);
        await new Promise(resolve=>setTimeout(resolve,300));
      }
    };
    let step=await untilState('COPY_REVIEW_REQUIRED');
    assert.match(step.copy_sha,/^[a-f0-9]{64}$/);
    assert.equal(step.mode,'OFFLINE_FIXTURE');
    record('ACTUAL_SYNTHETIC_MPO_JOB_REACHED_TEXT_COMPLIANCE_REVIEW',
      {copy_sha:step.copy_sha});
    const seenCopy=step.copy_sha;
    await page.getByRole('button',{name:'수정 요청',exact:true}).waitFor();
    await page.locator('input[type="checkbox"]').first().check();
    await page.getByRole('button',{name:'이 카피로 이미지 만들기'}).click();
    await page.waitForURL('**/create/draft',{timeout:20000});
    step=await untilState('IMAGE_REVIEW_REQUIRED');
    assert.equal(step.copy_sha,seenCopy);
    assert.equal(step.image_attempt_version,1);
    assert.match(step.image_sha,/^[a-f0-9]{64}$/);
    record('SINGLE_IMAGE_AFTER_REGULATORY_COPY_APPROVAL',
      {attempt:1,image_sha:step.image_sha});
    await page.getByRole('button',{name:'이 이미지로 광고 완성하기'}).waitFor();
    await page.getByRole('button',{name:'이 이미지로 광고 완성하기'}).click();
    await page.waitForURL('**/create/export',{timeout:20000});
    step=await untilState('COMPLETED');
    assert.equal(step.copy_sha,seenCopy);
    assert.equal(step.image_attempt_version,1);
    assert.deepEqual(step.output_size,{width:1080,height:1350});
    assert.match(step.final_sha,/^[a-f0-9]{64}$/);
    assert.match(step.caption_sha,/^[a-f0-9]{64}$/);
    record('OWNER_COMPOSED_FINAL_PNG_AND_CAPTION_RECEIPT',
      {final_sha:step.final_sha,caption_sha:step.caption_sha});
    await page.getByRole('button',{name:'광고 이미지 저장 (PNG)'}).waitFor();
    await shot('04_final_desktop_1440');
    let download=page.waitForEvent('download',{timeout:15000});
    await page.getByRole('button',{name:'광고 이미지 저장 (PNG)'}).click();
    let completed=await download;
    const png=path.join(evidencePath,'ad_1080x1350.png');
    await completed.saveAs(png);
    assert.equal(sha256(fs.readFileSync(png)),step.final_sha);
    download=page.waitForEvent('download',{timeout:15000});
    await page.getByRole('button',{name:'텍스트 저장 (.txt)'}).click();
    completed=await download;
    const caption=path.join(evidencePath,'caption.txt');
    await completed.saveAs(caption);
    assert.equal(sha256(fs.readFileSync(caption)),step.caption_sha);
    assert.ok(fs.readFileSync(caption,'utf8').length>8);
    evidence.final_sha=step.final_sha;
    evidence.caption_sha=step.caption_sha;
    evidence.output_size=step.output_size;
    evidence.image_attempt_version=step.image_attempt_version;
    record('ACTUAL_BROWSER_PNG_CAPTION_DOWNLOAD_SHA_MATCH_2_OF_2');
    for(const width of [390,360]){
      await page.setViewportSize({width,height:844});
      await shot('05_mobile_'+width);
      record('MOBILE_READABLE_BROWSER_'+width,
        {width,scroll_width:await page.evaluate(()=>document.documentElement.scrollWidth)});
    }
    await page.setViewportSize({width:1440,height:900});
    // The same completed Job is immutable on refresh; no new POST on reload.
    const httpBeforeRefresh=evidence.http.length;
    await page.reload({waitUntil:'domcontentloaded'});
    await page.getByRole('button',{name:'광고 이미지 저장 (PNG)'}).waitFor({timeout:15000});
    const onRefresh=evidence.http.slice(httpBeforeRefresh);
    assert.equal(onRefresh.filter(r=>r.method==='POST').length,0);
    assert.equal((await untilState('COMPLETED')).final_sha,step.final_sha);
    record('GET_ONLY_COMPLETED_JOB_REFRESH_AND_RESUME');
    const bob=await browser.newContext({viewport:{width:390,height:844}});
    const bp=await bob.newPage();
    await bp.goto(base+'/',{waitUntil:'domcontentloaded'});
    await bp.locator('#demo-invite').fill('not'+fs.readFileSync(invite,'utf8'));
    await bp.getByRole('button',{name:'시연 시작'}).click();
    const denied=await bp.request.get(base+'/api/v1/jobs/'+job.job_id);
    // The A41 restricted fixture intentionally allows only alice, so bob's
    // invite is rejected at the outer gate (401), rather than reaching
    // per-Job ACL (404); separate FastAPI test exercises bob 404 directly.
    assert.equal(denied.status(),401);
    evidence.actor_job_acl='ALICE_200_UNAUTHORIZED_CONTEXT_401';
    record('SECOND_CHROME_CONTEXT_AUTHENTICATION_401');
    await page.reload({waitUntil:'domcontentloaded'});
    const afterReload=await page.request.get(base+'/api/v1/jobs/'+job.job_id);
    assert.equal(afterReload.status(),200);
    record('REFRESH_GET_ONLY_NO_NEW_UPLOAD');
    assert.equal(evidence.http.filter(h=>h.method==='POST'&&
      h.path==='/demo/api/a51d/mpo/jobs').length,1);
    assert.equal((await untilState('COMPLETED')).final_sha,step.final_sha);
    assert.equal(evidence.external_requests.filter(r=>r.method==='POST').length,0);
    assert.equal(evidence.browser_errors.length,0);
    evidence.status='PASS_OFFLINE_FIXTURE_ONLY';
    fs.writeFileSync(path.join(evidencePath,'browser_trace.json'),
                     JSON.stringify(evidence,null,2)+'\n');
    console.log('A51D_OFFICIAL_REACT_CHROME_MPO_SELECTION_JOB_PASS',job.job_id);
    await bob.close();
    await context.close();
  }catch(e){
    console.error('A51D_BROWSER_FAIL',e.stack||String(e));
    evidence.status='FAILED';
    fs.writeFileSync(path.join(evidencePath,'browser_trace.failed.json'),
                      JSON.stringify(evidence,null,2)+'\n');
    process.exitCode=1;
  }finally{
    if(browser)await browser.close();
  }
})();
