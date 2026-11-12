# BP18 B6 — EX12 Final PNG/Caption GET-Only Download Recovery

Status: **B-only PROVISIONAL**, not Product Release Acceptance.

## Problem
Previously the export UI queried the final PNG and caption, but a failed HTTP GET left the finished ad hidden without an actionable file retry. The generic React Query retry setting could also re-fetch automatically, obscuring whether a user explicitly retried.

## B-only change
- Expose the cached artifact Blob query result via `useBlobQuery`; keep Owner-compatible `useBlob` and `useBlobUrl` interfaces unchanged.
- ExportPage renders a visible failure notice when the completed-job PNG or caption retrieval fails.
- Separate explicit `이미지 파일 다시 가져오기` and `본문 파일 다시 가져오기` buttons invoke only `query.refetch()` on the SAME GET URL.
- Both queries have `retry:false` and `refetchOnWindowFocus:false`; no automatic provider retry, copy/regulation recomputation, composition or image generation.
- Completed final/download SHA remains owned and validated by backend; this UI change does not manipulate receipts, provenance, approvals, artifacts or historical Jobs.

## Browser test actually run
- Mac Studio isolated local Chrome + local Vite preview; network route interception supplies synthetic SSO user, completed Live snapshot and synthetic 1080×1350 PNG/Caption. No GCP API writes, provider access or real paid models.
- First PNG and Caption GET each injects HTTP503. Both errors visible, save button disabled; each GET count exactly 1 without auto retry.
- Explicit user clicks make second GET succeed. PNG loads 1080×1350, caption appears, save enabled and error clears.
- Network POST count **0**; GET counts **2 PNG + 2 Caption**.
- Evidence: `BP18_B6_EX12_LOCAL_CHROME_RESULTS.json` and `BP18_B6_EX12_LOCAL_CHROME.log` under the external BP18 isolated evidence folder.

## Remaining
- Run the same browser injection against a pinned deployed B candidate after protected SSO/Policy prestart verification.
- Actual finished ads and mobile user acceptance still pending; this is an offline error-path QA result only, not a real-model E2E case.
- EX03 Research failure and EX10 RUNNING refresh are separate requirements, not claimed as completed.
- Final F/V/S release acceptance remains A0/38, B0/38; production/official dev unchanged.
