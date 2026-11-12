# IT-TEM — BP13/14 Track F + Visual v3 Track V + Text Owner Track T
작성 2026-11-07 · 개발/격리 QA 증거 인계 · B′ 최종 수용 전 HOLD

## 정본
- 원본 조건부 수용 HEAD `61e1512b8eab94b6fa260ecdd19623f236d7de4e`, Tree `370d9b9a7e33b8fd76270d7fe06f1f90a512a6ad`; 이후 모든 변경 격리 브랜치 `integration/bp13-bp14-ownerfirst-20261106`에서만.
- 공식 dev `9f798169110e0bb6807c15347444f7c31ad05bae`, FE #26 OPEN `c9c204b`, Image #24 OPEN `b3ee33f`, Text #25 MERGED. GitHub PR·dev 미변경.
- 기존 BP11 Live `18088` SHA `3bb1143`, 기존 Tailscale 10000 / QA 8443와 18089/18090 보호.

## Track F — 무과금 기능 확인
- 별도 GCP QA `/home/macstudio/ittem-bp13-bp14-offline-qa-20261107`, `127.0.0.1:18091` (Mac SSH tunnel 18901), 코드 SHA **61e1512b**, JS sha256 `34169759240124ce8c4ff1001ec37fb1f1b5f33c58c04ad408b0914f554f517f`.
- 새로운 QA SQLite/Queue/Provider/output와 가상 Actor 2명. Web에 유료 AI Provider 키 없음, 실제 AI Worker 미실행, `MONITOR_ONLY`, `OFFLINE_FIXTURE` 표시 의무. 새 Provider Attempt 0.
- Actual Google Chrome channel chrome: 기존 합성형 3:4/4:5/9:16 Desktop+Mobile E2E **10/10 PASS**, 화면비·PNG·Caption SHA 일치, 이전 단계로 GET-only 복구, 새 광고만 초기화.
- 자유형 4:5/3:4 Desktop, 9:16 Mobile QA 모든 파일 SHA·`output_size` 일치. 추가 이미지 Reject→Attempt v2→Approve→Compose PNG/Caption 완주, 승인 Copy/Review/Generation 원형, 동일 Job 중복요청 거부, 타 Actor 404, MPO→JPEG source/derived SHA, 예상비용 Freeform Unknown/Composed Reference Only PASS. 모바일 자동화의 숨겨진 radio 직접 클릭은 실패하여 실제 보이는 라벨 클릭으로 수정 후 PASS; 제품 결함으로 판정하지 않음.
- 증거: `/Users/Shared/ittem-bp13-bp14-qa-evidence-20261107/QA_CHROME_LEGACY_RATIOS.log`, `BP12_STANDARD_CHROME_E2E.json`, `QA_CHROME_EXTENDED_R2.log`, `BP13_BP14_CHROME_EXTENDED.json`, `BP14_MOBILE_9_16.log`, `BP14_MOBILE_FREEFORM_9_16.json`, screenshot/download proofs.
- 별도 Python crash injection: image retry begin→enqueue 사이 중단, concurrent requests, queued/running/unknown replay block, image artifact write failure, freeform Receipt persisted→DB transition failure. 새 operator utility `scripts/bp13_image_recovery_audit_readonly.py` is read-only and **never replays provider**. Any unknown remains manual hold.
- Actual GCP read-only postflight: BP11 Live 14 Job, 9 completed/18 final assets checksum PASS, Queue 42 SUCCEEDED, aggregate Provider Attempt 70 SUCCEEDED_USAGE_UNPRICED, Billing Unknown 0, rollback 5 releases. New QA 11 Job, 9 completed/18 final assets checksum PASS, Queue 0, Provider Attempt 0, HTTP 18088/18089/18090/18091 = 200. `GCP_BP13_POSTFLIGHT_20261107.json`.

## New code after conditional acceptance
- Image cost estimate now uses exact **same pure profile resolver as actual Worker**: `demo_staging/live/image_runtime_profile.py`. Default model gpt-image-2.6-sunburst, medium/high; explicitly configured changes to quality/complexity become effective on BOTH Worker and estimate; mismatched profile returns Unknown, not invented price. No new Hard Cap or cost booking.
- Crash safety regression tests and manual read-only recovery auditor; no Owner Source generation/code modification.
- Expanded whole repository Python **894/894 PASS**, FE **48/48 PASS**, Oxlint PASS, Build PASS with local Korean font env. Logs under `/Users/Shared/ittem-bp13-bp14-qa-evidence-20261107/BP13_BP14_FINAL_...`.
- Code modifications were not deployed to QA port 18091 as of first QA. New code needs its own code SHA/QA verification before B′.

## Track V — Owner Visual v3 independent
- Read-only GCP original AI image+v2 result+Copy+Layout+Receipt 4 Jobs, SHA verified.
- 3 experiment styles A/B/C × 4 Jobs → 12 full-resolution candidates + 12 mobile360. 4:5 CTA visually shown, old Layout and v2 results untouched. 9:16 image CTA policy pending.
- Actual initial glyph tofu and insufficient dark-style Sub contrast detected and amended in experiment only. All 12 current outputs hashed, v3 Head size > Sub, no copy changes, protected *target* geometry nonoverlap. Does NOT prove actual product object label nonoverlap or human quality acceptance.
- Mac `/Users/Shared/ittem-bp13-bp14-visual-v3-20261107/`: `V2_VS_V3_COMPARE_4JOBS.png`, `REVIEW_GALLERY.html`, `V3_VISUAL_OWNER_PM_REVIEW_BRIEF_20261107.md`, `V3_OWNER_PM_REVIEW_SCORECARD.csv`, `V3_EXPERIMENT_MANIFEST.json`, `VISUAL_GOLDEN_SHA256.txt`.
- Original source files local permissions readonly; 30-file SHA manifest PASS. Apple system fonts local experimentation only; commercial license unresolved. Image Owner·PM must sign official v3 profile and approve 9:16 policy. Prototype is **not** production Owner renderer.

## Track T — proposed, not yet Owner accepted
- `BP13_TEXT_OWNER_V11_CONTRACT_PROPOSAL_20261107.md` contains exact proposed ComplianceRevisionContext with current issues and Copy/Review SHA/Generation/basis provenance, backward-compatible `revise_copy` signature, no-op & partial-removal tests, verified official citation policy.
- Serving preflight binds review context but actual Text Owner model has NOT accepted/consumed its new parameter. Text Owner approval + new Owner commit required.
- Mode-specific art direction must separate composed textless background and freeform product+approved words+typography with same new design profile, without redoing Research on image retry.

## Open gates
1. Owner Text actual structured revision input, compliant source URLs, prompt art direction.
2. Owner Image production v3 Layout/Font/Typography/4:5 CTA, 9:16 policy, font license and Golden visual human acceptance.
3. Genuine iPhone MPO; existing test MPO sample not proven iPhone-sourced.
4. Real Worker RUNNING browser-refresh and provider billing ambiguity (no paid calls used; synthetic crash tests are not real provider verification).
5. Additional live model E2E with explicit approval, human cosmetic ad/label QA, B′ final audit and PM UAT.
6. Historical 502 not reproduced in current Chrome QA; no root-cause closure claimed.
7. Official dev/Owner PR merge, final PR, Live update continue **HOLD**.
