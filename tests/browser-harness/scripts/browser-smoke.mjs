/**
 * IT-TEM B0 local browser proof. Not the frontend owner's production application.
 * Uses localhost Vite proxy + actual FastAPI server. No external services or API key.
 * Requires B0_TEST_IMAGE_A/B and optional B0_EVIDENCE_DIR.
 */
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const front = process.env.B0_FRONT_URL ?? "http://127.0.0.1:4173";
const chrome = process.env.CHROME_BIN ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const imageA = process.env.B0_TEST_IMAGE_A;
const imageB = process.env.B0_TEST_IMAGE_B;
const evidence = process.env.B0_EVIDENCE_DIR ?? path.resolve("../.runtime/b0_browser_harness");
assert.ok(imageA && imageB && imageA !== imageB, "two distinct photo file paths required");
assert.ok(fs.existsSync(imageA) && fs.existsSync(imageB), "test photo files missing");
fs.mkdirSync(evidence, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: chrome,
  headless: true,
  args: ["--no-first-run", "--no-default-browser-check", "--disable-extensions"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 1000, deviceScaleFactor: 1 });
const trace = [];
const consoleErrors = [];
const downloads = path.join(evidence, "chrome_downloads");
fs.mkdirSync(downloads, { recursive: true });
await page._client().send("Page.setDownloadBehavior", { behavior: "allow", downloadPath: downloads });
async function waitFile(filename) {
  const target = path.join(downloads, filename);
  for (let i = 0; i < 120; i++) {
    if (fs.existsSync(target) && fs.statSync(target).size > 0 &&
        !fs.readdirSync(downloads).some(name => name.endsWith(".crdownload"))) return target;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error("Browser did not save " + filename);
}

page.on("console", (m) => {
  if (m.type() !== "error") return;
  // Chrome logs expected HTTP 409 as a console resource error. Actual JS
  // exceptions must still fail; the 409 is asserted separately in this test.
  if (/Failed to load resource: the server responded with a status of (409 \(Conflict\)|404 \(Not Found\))/.test(m.text())) return;
  consoleErrors.push(m.text());
});
page.on("pageerror", (e) => consoleErrors.push("PAGE_ERROR: " + e.message));
page.on("response", (resp) => {
  const url = resp.url();
  if (!url.includes("/api/v1/")) return;
  trace.push({
    method: resp.request().method(),
    url: new URL(url).pathname,
    status: resp.status(),
    contentType: resp.headers()["content-type"] ?? null,
  });
});

function status() {
  return page.$eval('[data-testid="status"]', (el) => el.textContent?.trim());
}
async function awaitStatus(expected) {
  await page.waitForFunction(
    (text) => document.querySelector('[data-testid="status"]')?.textContent?.trim() === text,
    { timeout: 15000 },
    expected,
  );
  assert.equal(await status(), expected);
  process.stdout.write("PASS status=" + expected + "\n");
}
async function button(testid, statusExpected) {
  await page.locator(`[data-testid="${testid}"]`).click();
  await awaitStatus(statusExpected);
}

let jobId = null;
try {
  await page.goto(front, { waitUntil: "networkidle2" });
  assert.match(await page.$eval('[data-testid="mode"]', (el) => el.textContent), /MOCK/);
  await (await page.$('[data-testid="products"]')).uploadFile(imageA, imageB);
  await button("upload", "INPUTS_VALIDATED");
  jobId = await page.$eval('[data-testid="job-id"]', (el) => el.textContent.trim());
  assert.match(jobId, /^[0-9a-f]{32}$/);
  process.stdout.write("PASS created_job=" + jobId + "\n");

  const premature = await page.evaluate(async (id) => {
    const r = await fetch(`/api/v1/jobs/${id}/mock/image`, { method: "POST" });
    return { status: r.status, body: await r.json() };
  }, jobId);
  assert.equal(premature.status, 409);
  process.stdout.write("PASS wrong_order_409=" + JSON.stringify(premature.body) + "\n");

  await button("refresh", "INPUTS_VALIDATED");
  await button("plan", "PLAN_READY");
  await button("copy", "COPY_REVIEW_REQUIRED");
  assert.match(await page.$eval('[data-testid="compliance"]', (el) => el.textContent), /NOT CHECKED/);
  await button("copy-approve", "COPY_APPROVED");
  await button("image", "IMAGE_REVIEW_REQUIRED");
  await button("image-approve", "IMAGE_APPROVED");
  await button("compose", "COMPLETED");
  assert.equal(await page.$eval('[data-testid="final-spec"]', (el) => el.textContent), "1080×1350 PNG");
  assert.ok(await page.$('[data-testid="final-download"]'));
  assert.ok(await page.$('[data-testid="caption-download"]'));

  const downloadResult = await page.evaluate(async (id) => {
    const p = `/api/v1/jobs/${id}/artifacts`;
    const image = await fetch(`${p}/final`);
    const imageBlob = await image.blob();
    const bitmap = await createImageBitmap(imageBlob);
    const caption = await fetch(`${p}/caption`);
    const text = await caption.text();
    const result = {
      imageStatus: image.status, imageContentType: image.headers.get("content-type"),
      width: bitmap.width, height: bitmap.height, bytes: imageBlob.size,
      captionStatus: caption.status,
      captionType: caption.headers.get("content-type"), text,
    };
    bitmap.close();
    return result;
  }, jobId);
  assert.deepEqual(
    [downloadResult.imageStatus, downloadResult.width, downloadResult.height, downloadResult.captionStatus],
    [200, 1080, 1350, 200],
  );
  assert.match(downloadResult.imageContentType, /image\/png/);
  assert.match(downloadResult.text, /라움/);
  assert.match(downloadResult.captionType, /text\/plain/);
  fs.writeFileSync(path.join(evidence, "artifact_checks.json"),
    JSON.stringify(downloadResult, null, 2) + "\n");
  process.stdout.write("PASS download=" + JSON.stringify(downloadResult) + "\n");

  // Real React click -> Chrome download manager -> physical saved files.
  await page.locator('[data-testid="final-download"]').click();
  const savedPng = await waitFile("final_mock.png");
  const savedBytes = fs.readFileSync(savedPng);
  assert.equal(savedBytes.subarray(0, 8).toString("hex"), "89504e470d0a1a0a");
  assert.equal(savedBytes.readUInt32BE(16), 1080);
  assert.equal(savedBytes.readUInt32BE(20), 1350);
  await page.locator('[data-testid="caption-download"]').click();
  const savedCaption = await waitFile("caption.txt");
  const savedText = new TextDecoder("utf-8", { fatal: true }).decode(fs.readFileSync(savedCaption));
  assert.match(savedText, /라움/);
  process.stdout.write("PASS actual Chrome saved PNG and UTF-8 caption\n");
  fs.writeFileSync(path.join(evidence, "chrome_download_checks.json"),
    JSON.stringify({png: path.basename(savedPng), bytes: savedBytes.length,
      mime: "image/png", signature: savedBytes.subarray(0, 8).toString("hex"),
      width: savedBytes.readUInt32BE(16), height: savedBytes.readUInt32BE(20),
      caption: path.basename(savedCaption), captionText: savedText,
      method: "React button click -> Chrome Blob download -> filesystem"}, null, 2) + "\n");

  // Network-fault injection for missing artifact, requiring a visible React error.
  await page.setRequestInterception(true);
  const failCaption = async request => {
    if (request.url().includes("/artifacts/caption")) {
      await request.respond({status: 404, contentType:"application/json", body:'{"detail":"Artifact not found"}'});
    } else { await request.continue(); }
  };
  page.on("request", failCaption);
  await page.locator('[data-testid="caption-download"]').click();
  await page.waitForFunction(() => document.querySelector('[data-testid="error"]')?.textContent?.includes("다운로드 실패"));
  assert.match(await page.$eval('[data-testid="error"]', el => el.textContent), /404/);
  page.off("request", failCaption);
  await page.setRequestInterception(false);
  process.stdout.write("PASS React surfaces failed download\n");

  // Refresh: GET existing Job, no POST; Job and artifact links preserved.
  const beforeReload = trace.length;
  const finalLabel = await page.$eval('[data-testid="final-download"]', el => el.textContent);
  await page.reload({ waitUntil: "networkidle2" });
  await awaitStatus("COMPLETED");
  assert.match(page.url(), new RegExp("job=" + jobId));
  const newNetwork = trace.slice(beforeReload);
  assert.ok(newNetwork.some(x => x.method === "GET" && x.url.endsWith("/jobs/" + jobId) && x.status === 200));
  assert.equal(newNetwork.filter(x => x.method === "POST").length, 0);
  assert.equal(await page.$eval('[data-testid="job-id"]', el => el.textContent), jobId);
  assert.equal(await page.$eval('[data-testid="final-download"]', el => el.textContent), finalLabel);
  process.stdout.write("PASS refresh GET + artifact restore, POST=0\n");

  await page.screenshot({ path: path.join(evidence, "b0_browser_harness_completed.png"), fullPage: true });

  // Explicit rejection path: new Job, negative copy approval, image generation denied by server 409.
  await (await page.$('[data-testid="products"]')).uploadFile(imageA, imageB);
  await button("upload", "INPUTS_VALIDATED");
  const rejectedJobId = await page.$eval('[data-testid="job-id"]', (el) => el.textContent.trim());
  assert.notEqual(rejectedJobId, jobId);
  await button("plan", "PLAN_READY");
  await button("copy", "COPY_REVIEW_REQUIRED");
  await button("copy-reject", "COPY_REJECTED");
  const afterReject = await page.evaluate(async (id) => {
    const r = await fetch(`/api/v1/jobs/${id}/mock/image`, { method: "POST" });
    return { status: r.status, body: await r.json() };
  }, rejectedJobId);
  assert.equal(afterReject.status, 409);
  process.stdout.write("PASS rejection_blocks_image_409\n");

  // Real UI 409: another request advanced backend while React is stale.
  await (await page.$('[data-testid="products"]')).uploadFile(imageA, imageB);
  await button("upload", "INPUTS_VALIDATED");
  const conflictJobId = await page.$eval('[data-testid="job-id"]', el => el.textContent.trim());
  await button("plan", "PLAN_READY");
  const advanced = await page.evaluate(async id => {
    const response = await fetch("/api/v1/jobs/" + id + "/mock/copy", {method:"POST"});
    return response.status;
  }, conflictJobId);
  assert.equal(advanced, 200);
  assert.equal(await status(), "PLAN_READY", "React state must still be stale");
  const beforeConflictClick = trace.length;
  await page.locator('[data-testid="copy"]').click();
  await awaitStatus("COPY_REVIEW_REQUIRED");
  await page.waitForFunction(() => document.querySelector('[data-testid="info"]')?.textContent?.includes("409 충돌"));
  assert.match(await page.$eval('[data-testid="error"]', el => el.textContent), /HTTP 409/);
  const calls = trace.slice(beforeConflictClick).filter(x =>
    x.url.endsWith("/jobs/" + conflictJobId) || x.url.endsWith("/jobs/" + conflictJobId + "/mock/copy"));
  const posts = calls.filter(x => x.method === "POST");
  const gets = calls.filter(x => x.method === "GET");
  assert.equal(posts.length, 1, "must only attempt one stale UI POST");
  assert.equal(posts[0].status, 409);
  assert.equal(gets.length, 1, "React must GET the latest Job after 409");
  assert.equal(gets[0].status, 200);
  await new Promise(resolve => setTimeout(resolve, 350));
  assert.equal(trace.slice(beforeConflictClick).filter(x => x.method === "POST" &&
    x.url.endsWith("/jobs/" + conflictJobId + "/mock/copy")).length, 1);
  process.stdout.write("PASS React UI 409 -> GET Job -> reconciled UI -> no retry\n");

  assert.equal(consoleErrors.length, 0, "browser JS console/page errors: " + consoleErrors.join("; "));
  assert.ok(trace.some((r) => r.status === 201 && r.method === "POST"));
  assert.ok(trace.some((r) => r.status === 409));
  assert.ok(trace.some((r) => r.url.endsWith("/artifacts/final") && r.status === 200));

  fs.writeFileSync(path.join(evidence, "browser_network_trace.json"),
    JSON.stringify({ mode: "MOCK", job_id: jobId, rejected_job_id: rejectedJobId, conflict_job_id: conflictJobId,
      frontend: front, trace, consoleErrors,
      summary: "B0 React harness only; frontend Owner real application NOT VERIFIED", },
    null, 2) + "\n");

  process.stdout.write("PASS BROWSER HARNESS E2E (not owner FE)\n");
  process.stdout.write("EVIDENCE_DIR=" + evidence + "\n");
} finally {
  await browser.close();
}
