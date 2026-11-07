# IT-TEM BP16 — 최종 이미지 실측 화면비·거절 UX 및 RUNNING/UNKNOWN 복구

작성: 2026-11-07. BP15 125b392에서 계속한 Owner-First 격리 후속 변경. **Owner Source v3/Compliance Model 계약 미승인; Live 반영 금지.**

## 확인 정본
- Official GitHub dev `9f798169110e0bb6807c15347444f7c31ad05bae` (11:13 KST).
- FE #26 OPEN `c9c204b88af5ce1b25dfda501d16446750a41204`.
- Image #24 OPEN `b3ee33fd524fbbb83890472be890c96974160e9c`.
- Text #25 MERGED, newer v3/Text context Owner PR not observed at 11:13 KST.
- Starting local Source SHA `125b39249227bc9b67ed08799d636c07b9086447`/Tree `4feae746fc735e6357fad8036e9497725cad310d`, CLEAN.
- No official PR post/close/merge or Live 18088 deployment. Historical 9 completed Live assets, SHA, rollback inventory preserved.

## Corrected issue: Team Shared Evaluation actual ratio
- Found literal `CREATIVE / 4:5` in `app/src/demo/LiveEvaluationBoard.tsx` and CSS `aspect-ratio:4/5` in `LiveEvaluationBoard.css`.
- `/demo/api/live/shared` now returns `image_size`, `output_size`, `dimensions_source` **only from SHA-verified final PNG bytes** for owner-shared Live completed Jobs. 1080×1440 → 3:4; 1080×1350 → 4:5; 1080×1920 → 9:16. Unknown valid dimensions show ‘기타 화면비’; damaged PNG returns UNAVAILABLE and redacts dimensions.
- FE `sharedArtworkDisplay.ts` rejects missing or contradictory input: actual final pixel geometry controls label and CSS aspect, never form selection or template ratio. Requested/claimed ratio mismatch is explicitly labeled ‘화면비 메타데이터 불일치’.
- Original team sharing permissions, published SHA binding, Actor ACL, rating revisions, Timestamp and existing DB schema remain unchanged.
- Python `tests/demo_live/test_shared_evaluation.py` covers real verified 3:4/4:5/9:16 plus supported-size-unknown, then verifies tampered PNG has no visible dimensions; FE `app/tests/sharedArtworkDisplay.test.ts` covers 3 ratios, mislabeled actual 9:16, missing/corrupt and legacy.
- Design pixel measurement is about final PNG dimension. It does NOT prove image text/label quality.

## Corrected issue: Image rejection message
- Replaced outdated ‘이미지 거절 후 재생성 미지원’ text in `app/src/pages/DraftPage.tsx` with accurate explicit retry contract; no new paid call, model or wire route introduced.
- Existing user-triggered Attempt v2 ID, archived PNG/Receipt, zero Text/Research recall and BILLING_UNKNOWN protections preserved.

## RUNNING / BILLING_UNKNOWN browser safety
- Mac Chrome on GCP loopback fixture 18092, mocked GET `task-status`: reload→RUNNING displayed, second reload GET-only, unknown billing displayed as manual hold. **3/3 PASS, 0 POST**.
- These tests intercept network status only. Real GCP paid Worker RUNNING/wake/restart and provider billing reconciliation remain PENDING.
- Prior BP15 crash injection tests (queue registration gap, simultaneous retry, provider bytes/Receipt failure, manual read-only inspector) remain in place; no automatic Provider replays.

## Validation gates
- Whole Python **897/897 PASS** with pinned system Korean font.
- FE node tests **52/52 PASS**, Oxlint 0/0, TS/Vite build PASS.
- GCP BP16 code SHA deployment & Chrome verification, pre/post Live inventory to be recorded in external QA audit evidence.
- Visual v3 A/B/C 12 prototypes in `/Users/Shared/ittem-bp13-bp14-visual-v3-20261107`; all 30 Golden SHA checks passed in prior unit; **not** Image Owner or PM production design approval.
- Text Owner `ComplianceRevisionContextV1` proposed at `docs/integration/BP13_TEXT_OWNER_V11_CONTRACT_PROPOSAL_20261107.md`; **still not used by actual revise_copy Owner model**.
- Genuine iPhone-derived MPO file not present in approved visible Mac sample search: the available `real_2_frame.mpo` is a test MPO not proven iPhone-sourced. Genuine device file remains external input gate.
- Existing Tailscale intermittent HTTP502 root cause unresolved; previous 16 probes all HTTP200, not closure.
- Paid real AI calls **0** during this unit. No PM approval for commercial Visual v3, no production deployment/PR change.
