import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const id = process.env.B0_RECOVERY_JOB_ID;
const evidence = process.env.B0_EVIDENCE_DIR;
const url = process.env.B0_FRONT_URL ?? "http://127.0.0.1:4173";
const chrome = process.env.CHROME_BIN ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
assert.match(id ?? "", /^[0-9a-f]{32}$/, "B0_RECOVERY_JOB_ID must be valid");
assert.ok(evidence && fs.existsSync(evidence), "B0_EVIDENCE_DIR is required");
const browser = await puppeteer.launch({
  executablePath: chrome, headless: true,
  args: ["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
});
const page = await browser.newPage();
const trace = [];
page.on("response", response => {
  if (!response.url().includes("/api/v1/")) return;
  trace.push({method:response.request().method(), status:response.status(),
    url:new URL(response.url()).pathname});
});
try {
  await page.goto(url + "/?job=" + id, {waitUntil:"networkidle2"});
  await page.waitForFunction(() => document.querySelector('[data-testid="status"]')?.textContent === "COMPLETED");
  assert.equal(await page.$eval('[data-testid="job-id"]', e => e.textContent), id);
  assert.ok(await page.$('[data-testid="final-download"]'));
  assert.ok(await page.$('[data-testid="caption-download"]'));
  assert.ok(trace.some(r => r.method==="GET" && r.status===200 && r.url.endsWith("/jobs/" + id)));
  assert.equal(trace.filter(r => r.method==="POST").length, 0, "post-restart browser must only GET");
  const image = await page.evaluate(async id => {
    const r = await fetch("/api/v1/jobs/" + id + "/artifacts/final");
    const b = await r.blob();
    const bitmap = await createImageBitmap(b);
    const result = {status:r.status, width:bitmap.width,height:bitmap.height,
      type:r.headers.get("content-type")};
    bitmap.close();return result;
  },id);
  assert.equal(image.status,200);
  assert.equal(image.width,1080);
  assert.equal(image.height,1350);
  await page.screenshot({path:path.join(evidence,"post_restart_browser.png"),fullPage:true});
  fs.writeFileSync(path.join(evidence,"post_restart_browser_trace.json"),
    JSON.stringify({job_id:id,mode:"MOCK",browserReloadAfterBackendRestart:true,
      image,trace,unexpectedPOST:0},null,2)+"\n");
  process.stdout.write("PASS Chrome browser after backend restart: Job COMPLETED, image 1080x1350, POST=0\n");
} finally {
  await browser.close();
}
