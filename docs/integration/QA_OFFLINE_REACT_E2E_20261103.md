# PR18 — Real React QA-only offline fixture E2E contract

QA requires the isolated backend IT_TEM_QA_FIXTURE_ENABLED=YES and a separate React bundle VITE_QA_OFFLINE_FIXTURE=YES. The backend also requires Live execution disabled, loopback client, local-only cookie and allowlisted authenticated QA actor. Default is OFF.

QA endpoint routes reuse official Owner Text DTO, rule compliance, approval, Owner A safe_zone, Korean composition and SHA manifest, but images and text are static OFFLINE_FIXTURE test data. Zero OpenAI provider calls and zero billing attempts.

Normal Live-only queue, artifact endpoints, sharing and evaluation still reject OFFLINE_FIXTURE. The UI displays a persistent QA banner and fixture provenance badge across original ProductPage/CopyPage/DraftPage/ExportPage screens.

Only the static unit-test brand '라움' is supported by this fixture; other brands fail closed. No actual product photo recognition, product preservation, AI quality or Live performance may be inferred.

This QA runtime must never be served through the existing 8443 Tailnet path or exposed externally with test credentials. GCP port 18082 only, no team demo or official PR modifications. QA browser screenshots and actual Live E2E remain separately classified.

## Copy editor asynchronous hydration and revision gate (2026-11-03)

Real Chrome found a race: Product Job DTO could finish loading before its separately polled
Live copy snapshot. An editable empty controlled textarea was displayed before the saved
copy arrived. A user edit during that interval could be overwritten by the incoming
initial snapshot, leading to COPY_EDIT_UNCHANGED. This was **not** a Real Compliance
false negative: the server rule checker rejects "치료 크림으로 치료" with two drug-claim issues.

CopyPage now gates all editable fields and approval on a hydrated (job_id, copy_sha)
pair. Dirty drafts cannot be approved, cannot silently be replaced by a concurrent
server revision, and require explicit save/recheck. At save click, actual visible
textarea values are captured synchronously and compared against the current server
copy SHA before submission. Successful edits advance the immutable server generation;
the FE refreshes both Live Snapshot and mapped B0 Job before re-enabling approval.

The QA bundle's global banner/login/navigation explicitly distinguishes OFFLINE_FIXTURE
from actual Live. Production builds do not activate the QA provider endpoint.

Acceptance: Chrome user edit of "치료 크림으로 치료" -> revision increases,
Compliance fails, approval button disabled, server rejects direct approval,
original text restored by another save -> later generation and distinct review SHA.
Separate backend tests cover prior approvals never reviving on edit/restore.
