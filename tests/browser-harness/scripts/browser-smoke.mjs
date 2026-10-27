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
page.on("console", (m) => {
  if (m.type() !== "error") return;
  // Chrome logs expected HTTP 409 as a console resource error. Actual JS
  // exceptions must still fail; the 409 is asserted separately in this test.
  if (m.text().includes("Failed to load resource: the server responded with a status of 409 (Conflict)")) return;
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

  // Browser refresh must read persisted Job from URL, without replaying billable/side-effectful POST.
  await page.reload({ waitUntil: "networkidle2" });
  await awaitStatus("COMPLETED");
  assert.match(page.url(), new RegExp("job=" + jobId));
  process.stdout.write("PASS refresh_restores_existing_job_without_replay\n");

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

  assert.equal(consoleErrors.length, 0, "browser JS console/page errors: " + consoleErrors.join("; "));
  assert.ok(trace.some((r) => r.status === 201 && r.method === "POST"));
  assert.ok(trace.some((r) => r.status === 409));
  assert.ok(trace.some((r) => r.url.endsWith("/artifacts/final") && r.status === 200));

  fs.writeFileSync(path.join(evidence, "browser_network_trace.json"),
    JSON.stringify({ mode: "MOCK", job_id: jobId, rejected_job_id: rejectedJobId,
      frontend: front, trace, consoleErrors,
      summary: "B0 React harness only; frontend Owner real application NOT VERIFIED", },
    null, 2) + "\n");

  process.stdout.write("PASS BROWSER HARNESS E2E (not owner FE)\n");
  process.stdout.write("EVIDENCE_DIR=" + evidence + "\n");
} finally {
  await browser.close();
}
