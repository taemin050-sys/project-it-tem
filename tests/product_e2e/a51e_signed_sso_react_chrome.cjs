/** A51E actual React Chrome against localhost-only HMAC FAKE SIGNING PROXY.
 * This is not real Tailscale Serve or paid model E2E. Synthetic fixtures only.
 */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const {chromium}=require(process.env.A41_PLAYWRIGHT_CORE_MODULE);
const base=process.env.A51E_BASE_URL;
const out=process.env.A51E_EVIDENCE_DIR;
const photos=[process.env.A51E_PHOTO_1,process.env.A51E_PHOTO_2];
const mpo=process.env.A51E_MPO;
const source=process.env.A51E_SOURCE_SHA;
if(!/^http:\/\/127\.0\.0\.1:\d{4,5}$/.test(base||'')||
   !/^[a-f0-9]{40}$/.test(source||'')||!out||
   ![...photos,mpo].every(p=>p&&fs.existsSync(p)))throw Error('A51E_LOCAL_TEST_ONLY_REQUIRED');
fs.mkdirSync(out,{recursive:true});
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const results={
 contract:'IT_TEM_P03_A51E_SYNTHETIC_FAKE_SIGNER_REACT_CHROME_V1',
 code_sha:source,mode:'OFFLINE_FIXTURE_SIGNED_ASSERTION_SIMULATOR',
 real_tailscale_serve:false,real_provider:false,real_product:false,
 owner_pm_mpo_policy_approved:false,steps:[],downloads:[],
 screenshots:[],external:[],errors:[],http:[],job_id:null,status:'PENDING',
};
const pass=(name,more={})=>{
 results.steps.push({name,...more});console.log('A51E_CHROME_STEP_PASS',name);
};
(async()=>{
 let browser;
 try{
 browser=await chromium.launch({
   executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
   headless:true,args:['--disable-background-networking','--no-first-run',
     '--no-default-browser-check']
 });
 const context=await browser.newContext({
   viewport:{width:1440,height:900},acceptDownloads:true,
   serviceWorkers:'block'
 });
 const page=await context.newPage();
 page.on('pageerror',e=>results.errors.push(e.message.slice(0,250)));
 page.on('request',req=>{
   try{if(new URL(req.url()).origin!==base)results.external.push({
     url_host:new URL(req.url()).hostname,method:req.method()
   })}catch{}
 });
 page.on('response',r=>{
   try{const u=new URL(r.url());
     if(u.origin===base && (u.pathname.startsWith('/api/')||
         u.pathname.startsWith('/demo/api/')))
       results.http.push({method:r.request().method(),path:u.pathname,status:r.status()})
   }catch{}
 });
 await page.route('**/*',route=>{
   const u=route.request().url();
   if(u.startsWith('data:')||u.startsWith('blob:'))return route.continue();
   try{if(new URL(u).origin===base)return route.continue()}catch{}
   return route.abort();
 });
 const screenshot=async(name)=>{
   const p=path.join(out,name+'.png');
   await page.screenshot({path:p,fullPage:true});
   results.screenshots.push({name,sha256:sha(fs.readFileSync(p))});
 };
 await page.goto(base+'/',{waitUntil:'domcontentloaded'});
 await page.getByText('Tailscale 인증됨').waitFor({timeout:15000});
 assert.match(await page.locator('body').innerText(),/비과금/);
 pass('SYNTHETIC_SIGNED_PROXY_REAL_REACT_SSO_GATE');
 await page.goto(base+'/create/product',{waitUntil:'domcontentloaded'});
 await page.locator('#photos').setInputFiles(mpo);
 await page.getByText('다중 프레임 MPO는 현재 Owner 승인 대기 중입니다.',
   {exact:false}).waitFor({timeout:15000});
 assert.match(await page.locator('#photos').evaluate(
   el=>el.closest('section')?.textContent||''),/0 \/ 5장/);
 pass('HIDDEN_MPO_JPG_REJECTED_IN_SIGNED_BETA_UI_BEFORE_UPLOAD');
 await screenshot('01_mpo_owner_pending_reject');
 await page.locator('#photos').setInputFiles(photos);
 await page.getByText('2 / 5장').first().waitFor({timeout:15000});
 await page.locator('#brand_name').fill('라움');
 await page.locator('#product_name').fill('데일리 크림');
 await page.locator('#product_category').selectOption('스킨케어');
 await page.locator('#features').fill('보습과 촉촉한 사용감');
 await page.locator('#photo_verified').check();
 await page.locator('input[name="generation-mode"][value="composed"]')
   .locator('xpath=..').click();
 await page.locator('input[name="ratio"][value="4:5"]')
   .locator('xpath=..').click();
 const createResponse=page.waitForResponse(r=>
     r.request().method()==='POST' &&
     new URL(r.url()).pathname==='/demo/api/a51e/beta/jobs',{timeout:20000});
 await page.getByRole('button',{name:'다음: 기획·카피 만들기'}).click();
 const created=await createResponse;
 assert.equal(created.status(),201,await created.text());
 const jid=(await created.json()).job_id;results.job_id=jid;
 assert.match(jid,/^[a-f0-9]{32}$/);
 pass('SIGNED_SSO_ACTOR_BETA_UPLOAD_B0_JOB_CREATED',{job_id:jid});
 await page.waitForURL('**/create/copy',{timeout:15000});
 const snapshot=async()=>{
    const res=await page.request.get(base+'/demo/api/live/jobs/'+jid);
    // Upload 201 and React navigation can complete before background
    // Live input creation; this is a race in test observation, not an
    // auto-retry of any POST. Poll only GET until initial input exists.
    if(res.status()===422 || res.status()===404){
      const body=await res.json();
      return {state:'INPUT_PENDING',reason:body.detail};
    }
    assert.equal(res.status(),200,await res.text());
    return res.json();
 };
 const waitState=async(want)=>{
   const began=Date.now();
   for(;;){
     const v=await snapshot();
     if(v.state===want)return v;
     if(Date.now()-began>25000)throw Error('A51E_STATE_TIMEOUT_'+want+'_'+v.state);
     await new Promise(ok=>setTimeout(ok,300));
   }
 };
 let j=await waitState('COPY_REVIEW_REQUIRED');
 assert.equal(j.mode,'OFFLINE_FIXTURE');
 assert.equal(j.image_size,'4:5');assert.equal(j.generation_mode,'composed');
 pass('HMAC_SIGNED_OWNER_TEXT_F09_COPY_REVIEW',{copy_sha:j.copy_sha});
 await page.getByRole('button',{name:'이 카피로 이미지 만들기'}).waitFor();
 await page.locator('input[type="checkbox"]').first().check();
 await page.getByRole('button',{name:'이 카피로 이미지 만들기'}).click();
 await page.waitForURL('**/create/draft',{timeout:20000});
 j=await waitState('IMAGE_REVIEW_REQUIRED');
 assert.equal(j.image_attempt_version,1);
 assert.match(j.image_sha,/^[a-f0-9]{64}$/);
 pass('ONE_SYNTHETIC_OWNER_IMAGE_CANDIDATE_CREATED',{image_sha:j.image_sha});
 await page.getByRole('button',{name:'이 이미지로 광고 완성하기'}).waitFor();
 await page.getByRole('button',{name:'이 이미지로 광고 완성하기'}).click();
 await page.waitForURL('**/create/export',{timeout:20000});
 j=await waitState('COMPLETED');
 assert.deepEqual(j.output_size,{width:1080,height:1350});
 pass('HMAC_SIGNED_SINGLE_CANDIDATE_COMPOSED_4X5_COMPLETED',
      {final_sha:j.final_sha,caption_sha:j.caption_sha});
 await screenshot('02_signed_desktop_final');
 let download=page.waitForEvent('download');
 await page.getByRole('button',{name:'광고 이미지 저장 (PNG)'}).click();
 let item=await download;
 const png=path.join(out,'a51e_signed_fixture_ad.png');
 await item.saveAs(png);
 assert.equal(sha(fs.readFileSync(png)),j.final_sha);
 results.downloads.push({kind:'png',sha256:j.final_sha});
 download=page.waitForEvent('download');
 await page.getByRole('button',{name:'텍스트 저장 (.txt)'}).click();
 item=await download;
 const caption=path.join(out,'a51e_signed_fixture_caption.txt');
 await item.saveAs(caption);
 assert.equal(sha(fs.readFileSync(caption)),j.caption_sha);
 results.downloads.push({kind:'caption',sha256:j.caption_sha});
 pass('SIGNED_BETA_SIMULATED_BROWSER_DOWNLOAD_SHA_MATCH_2_OF_2');
 for(const width of [390,360]){
  await page.setViewportSize({width,height:844});
  await screenshot('03_mobile_'+width);
  const scroll=await page.evaluate(()=>document.documentElement.scrollWidth);
  assert.equal(scroll,width);
  pass('MOBILE_NO_HORIZONTAL_SCROLL_'+width,{width,scroll});
 }
 await page.setViewportSize({width:1440,height:900});
 const httpBefore=results.http.length;
 await page.reload({waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'광고 이미지 저장 (PNG)'}).waitFor();
 assert.equal((await waitState('COMPLETED')).final_sha,j.final_sha);
 assert.equal(results.http.slice(httpBefore).filter(x=>x.method==='POST').length,0);
 pass('SIGNED_SSO_REFRESH_GET_ONLY_RESUME_NO_NEW_JOB');
 // A second signed identity cannot be spoofed with a browser-string header
 // because proxy always overwrites identity with authenticated TEST actor.
 const direct=await page.request.get(base+'/demo/api/session');
 assert.equal(direct.status(),200);
 assert.equal((await direct.json()).auth_provider,'TAILSCALE_SERVE');
 assert.equal(results.http.filter(h=>h.path==='/demo/api/a51e/beta/jobs'&&
     h.method==='POST').length,1);
 assert.equal(results.errors.length,0);
 assert.equal(results.external.length,0);
 results.status='PASS_FAKE_SIGNED_ASSERTION_OFFLINE_FIXTURE_NOT_REAL_TAILSCALE';
 results.png_sha=j.final_sha;results.caption_sha=j.caption_sha;
 fs.writeFileSync(path.join(out,'a51e_signed_chrome_trace.json'),
                  JSON.stringify(results,null,2)+'\n');
 console.log('A51E_REAL_REACT_BROWSER_LOCAL_HMAC_SIMULATOR_E2E_PASS');
 await context.close();
 }catch(e){
  console.error('A51E_CHROME_FAILED',e.stack||e);
  results.status='FAIL';
  fs.writeFileSync(path.join(out,'a51e_signed_chrome_trace.failed.json'),
                  JSON.stringify(results,null,2)+'\n');
  process.exitCode=1;
 }finally{if(browser)await browser.close()}
})();
