# IT-TEM P03 Track A — A1.2 FE Owner PR #26 Selective Integration

Date: 2026-11-09 KST
Role: A Owner Source First only; **developer self-validation, not C independent acceptance**.
Source before implementation: `integration/bp18-baseline-e2e-20261111@a7141b826cb7c1bb2a4710148734fde565945f06` (Tree `38fa38551cd554f8fec1a4f07f6601c587be146a`, CLEAN).
Team GitHub Owner FE PR #26: **MERGED** at original HEAD `c9c204b88af5ce1b25dfda501d16446750a41204`; `gh pr view` read-only verified 2026-11-09. Official `dev@62b6dcdef5663d5aa15c596b77ac601b245886db` read-only verified. No merge/cherry-pick/bulk-copy from Owner.

## File-level disposition: A HEAD vs original #26 (13 files)

| Owner file | Disposition | Evidence and contract decision |
|---|---|---|
| `app/src/index.css` | EXACT | Git object identical; unchanged |
| `app/src/pages/LandingPage.tsx` | EXACT | Git object identical; unchanged |
| `app/src/types/textSchema.ts` | EXACT | Git object identical; unchanged |
| `app/src/api/liveFlow.ts` | ADAPTED | Owner approval/restore/revision route preserved; A stronger QA/Live fences, pinned compose, explicit retry, no-op outcome helper. Never queue paid POST on GET-only restore |
| `app/src/api/liveJobs.ts` | ALREADY_EQUIVALENT | Owner ratio and revision CAS wire present; A additionally preserves generation mode, QA fixture and single image retry. No source rewrite |
| `app/src/api/liveMapping.ts` | ADAPTED | Owner DTO fields and approval checks preserved; A additional generation/hash hydration, source provenance, image/published integrity and strict no-change revision predicate |
| `app/src/api/useJob.ts` | ADAPTED | Owner selection-sensitive new-ad confirmation and GET-only resume preserved; candidate/final Blob caching now keys on exact expected SHA and verifies bytes before exposure |
| `app/src/demo/DemoGate.tsx` | ALREADY_EQUIVALENT | Owner `/create` resume flow preserved; A has additional signed Tailscale SSO, QA banner/fixture isolation and build/track identification. No rewrite |
| `app/src/pages/CopyPage.tsx` | ADAPTED | Owner revise/restore UI preserved; A prevents stale acknowledgements. No-change revision can release pending generation fence only after current authoritative GET, and old ack is revoked. Mock approval navigates only after success |
| `app/src/pages/DraftPage.tsx` | ADAPTED | Owner image review preserved; A binds candidate Blob to server `image_sha`, requires verified displayed preview before approval; Mock approval navigates only after success; image retry/Compose-only recovery retained |
| `app/src/pages/ExportPage.tsx` | ADAPTED | Owner ratio-specific output display retained; A now checks final PNG SHA, UTF-8 Caption SHA, actual image dimensions and approved text before download/share controls; approval and job metadata stay server authoritative |
| `app/src/store/projectStore.ts` | ALREADY_EQUIVALENT | Owner ratio, category and emoji persistence supported; A additionally persists composed/freeform mode and performs explicit legacy emoji migration. No rewrite |
| `app/tests/liveMapping.test.ts` | ADAPTED | Owner failed-compliance revision and CAS coverage retained; A extends no-change vs changed generation/SHA negative tests |

The three semantically equivalent files are **NOT** byte-exact; the three EXACT paths remain source-identical. The seven ADAPTED Owner paths incorporate stronger A-specific implementation/test behavior. Two supporting files were added: `app/src/api/verifiedBlob.ts`, `app/tests/verifiedBlob.test.ts`. Shared hook `app/src/lib/useObjectUrls.ts` additionally prevents a revoked prior Object URL being displayed during a new Blob revision. No DEFERRED/REJECTED Owner behavior identified in this differential scope.

## Targeted defects resolved

1. **Candidate Blob stale-cache / mismatch:** Server may reuse `/artifacts/candidate` after rejection and a new single image attempt. Prior `['blob', path]` React Query key could show earlier bytes, while user-approved `image_sha` pointed to the new image. Now React Query key includes `expectedSha`, fetch verifies WebCrypto SHA-256, and preview authorization requires a verified loaded current image. Mismatches fail closed; GET never triggers paid retry.
2. **Final export integrity:** SHA-verified final PNG and Caption now gate publish, PNG download, text download/copy. Filename dimensions follow server metadata; actual decoded pixels must match. A final preview URL is associated with its specific Blob, not stale image dimensions.
3. **No-change revision UI deadlock:** Owner Text may return `changed_fields=[]`, a nonblank note, and unchanged Generation. Former UI `minGeneration=old+1` stayed permanently barred even after a legitimate no-op. Authoritative GET now distinguishes genuine unchanged from changed result, clears only the local fence, and **clears the human acknowledgement**. Any changed copy/review/generation cannot bypass the fence.
4. **Mock UI navigation ordering:** Copy and image approval do not navigate before the approved POST completes successfully.

## Verification completed — strict evidence levels

- FE: `npm --prefix app test` **55/55 PASS** (baseline 52; three new cases covering no-change and byte SHA), `npm --prefix app run lint` **0 warnings/errors**, `npm --prefix app run build` **PASS**, `git diff --check` PASS.
- Python full, **no billable keys**: two independent complete runs **943 passed / 1 failed**; isolated reproduction also FAIL. Existing documented case `tests/demo_live/test_bp17_shared_minimal_export.py::test_existing_output_replaced_never_after_concurrent_publication` child process segfaults under macOS Python 3.12 `fork` + SQLite at `scripts/bp17_shared_ad_minimal_export.py:35 read_db`. The FE implementation did not modify that test/script. **DO NOT mark Python full PASS or silently skip this issue.** Evidence: `/Users/Shared/ittem-a1-2-owner26-evidence-20261109/A12_FULL_PYTHON.log`, `A12_PYTHON_FORK_ISOLATED.log`, `A12_FULL_PYTHON_RERUN.log`.
- GCP A: an additional read-only `gcloud compute ssh` attempt was blocked by expired local Google authentication (`Reauthentication failed`). Last *independently observed in handoff* A deploy HEAD `9879eb0f85747312a224ecd898aaff84d834590b` / Health 200 remains historical, **not a fresh re-verification**. No deployment or Worker changes executed.
- Actual browser/UAT, real paid Provider, six ratio×mode E2E, QA deployment, C independent validation: **NOT RUN** for this A1.2 commit. Product remains **NOT_RELEASE_READY**.

## Owner/Image/source protection

- FE #26 exact three blobs verified unchanged against original Owner commit.
- Text Owner #27 (13/13 existing EXACT) not recopied; A1.1 adapter retained.
- Image Owner #24 (previous 9/10 EXACT) not recopied; the A `src/image_generation/composition.py` `unicodedata2 as unicodedata` Unicode compatibility patch remains untouched.
- No changes to B Worktree/GCP18100, protected Live18088 or QA18095, official dev or Owner PR, historical A `/Users/Shared` original, existing DB/Job/Artifact/Provider ledger. No billable provider call, no new VM/GPU, no secrets or customer images copied.

## Release Master r0.1 impact — NOT release acceptance

- F05 new/resume and old Job preservation; F09/F10/F11 failed-compliance revision/no-change CAS and review generation; F16 candidate SHA vs image approval; F17 final artifact and Caption; F19 GET-only recovery.
- S02/S03 current actor/copy/image approval CAS, S04 no automatic paid rerun, S07/S09 artifact/cache integrity; V02/V04 visual text and dimensions require future human/real-model assessment.
- These are **CODE_IMPL + local FE TEST**, not `REAL_PROVIDER_E2E_PASS`, `HUMAN_OWNER_PM_ACCEPTED`, `C_INDEPENDENT_VERIFIED` or `RELEASE_DEPLOYED`. All F01–F20/V01–V08/S01–S10 remain individually gated by the Release Master (proposed contract, pending Owner/PM approval).

## C differential audit requests

1. Verify mutation/restore no-op does not revive any prior evidence acknowledgement, approval, Prompt/Image association or policy epoch.
2. Verify React Query and Object URL transitions cannot display/approve old image bytes after regeneration even if URL path remains unchanged; ensure SHA mismatch fails closed with a visible recovery path.
3. Verify final file + caption SHA and size download/share fence, including existing legitimate completed jobs and authenticated ownership.
4. Investigate isolated macOS Python 3.12 fork/SQLite segfault separately without waiving or weakening the concurrent publication test.
5. Verify deployed A source and A-only signed actor, Worker/Queue/Attempt guard **before** any paid Provider/GCP QA E2E. GCP latest was not accessible this session due CLI authentication.

No PR merge, push or production promotion is implied by this local commit.
