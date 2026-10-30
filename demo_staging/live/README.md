# IT-TEM Live L0-L4 isolated integration

Status: OFFLINE_OWNER_E2E_PASS / LIVE_PROVIDER_DISABLED

- Source: dev cfb5bc5f + Owner PR 15/16/17 + Serving PR 9/10/11, integrated only in isolated repository. Official dev and Owner/Serving branches untouched.
- Original B0 public HTTP has 10 Job operations + health = 11 unchanged. New /demo/api/live/* is provisional isolated Staging only, NOT approved canonical Wire or active Protected Tunnel.
- Exact ProductInput, original photos/SHA; Owner VLM strict fail closed; Research raw vs sanitized UI; full Copy and revision; Real Compliance 1st-pass rules + conservative brand claim extra guard.
- Approval digest includes input, analysis, full Copy SHA, review SHA, generation and evidence acknowledgement. Copy change and revert cannot revive an old approval.
- Owner Image native BackendImageInput, duplicate-call attempt ledger, receipt, Korean composition 1080x1350 PNG and UTF-8 Caption SHA. Copy approved BEFORE image prompt.
- SQLite queue one running task at a time. Worker restart turns running task into BILLING_UNKNOWN with no retries.
- Owner Text llm_client.py modified ONLY inside isolated integration to capture sanitized model ID, response ID and token usage. Requires Owner approval before any canonical merge. No raw user content/credentials retained in receipt.
- Image Owner DTO currently supports sunburst snapshot 2026-09-08 or GPT Image 2 snapshot; Flare not allowed without Owner contract change.
- Provider default OFF even if API key exists. Explicit PM approval, model readiness, actor allowlist and per-request/aggregate reserves are required before a call.
- Booked USD reservations are soft preventive limits, NOT hard provider billing ceilings. Succeeded token receipts have UNPRICED cost and remain reserved pending separate invoice reconciliation.
- No team account entitlement or remaining budget verification, no actual model calls, no GCP Live service started or new public tunnel published.
- Remaining: PM Live Wire approval, text receipt hook Owner review, safe failure/charge reconciliation, provider/budget permissions, real generated ad and human/remote evaluation.
- This is a repeatable preflight/development asset, NOT a real Live E2E acceptance or legal cosmetics advertising certification.

## Post-handoff hardening (isolated commit following fc395dc)

- Web queue capability and worker execution policy are separately gated. Staging web can enqueue only if LIVE_WEB_QUEUE_ENABLED, LIVE_ENABLED, LIVE_EXECUTION_APPROVED and PROVIDER_READINESS_CONFIRMED are all explicitly YES, actor is individually allowlisted and positive budget/count limits parse successfully. No provider API key is read or held in web process. Worker separately enforces secret availability, allowlist and budget before claiming a task.
- The first stored owner Text result sets mode LIVE or OFFLINE_FIXTURE in the **same transaction** as the product/copy snapshots. INPUT_ONLY is never presented as real AI completion.
- The Text Vision, Research, Copy and Image-Prompt stage checkpoints each bind actor, Job, execution mode, model/context SHA and official Owner schema. Valid saved results are reusable without calling the provider again. A charged attempt with no durable checkpoint is an explicit manual reconciliation HOLD; never auto-retry.
- React DemoLiveConsole restores the evaluator-scoped saved Job ID from sessionStorage and fetches the authorized server Job. If the image upload succeeded but the Live ProductInput write failed, the same uploaded Job is reused rather than POSTing the photos a second time. Polling does not overwrite edits in progress.
- No Mock output is published under LIVE. Image generation access, provider spending and final acceptance remain explicitly unapproved.
- Mac full Python suite: 655 PASS with licensed/local Korean font explicitly supplied as environment configuration, 24 Owner React unit tests PASS, lint 0 warnings/errors and Vite build PASS. All tests run without a real OpenAI key.
