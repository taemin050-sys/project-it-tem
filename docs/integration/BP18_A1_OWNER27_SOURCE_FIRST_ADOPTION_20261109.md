# IT-TEM BP18 — Track A A1.1 Text Owner #27 Source-First Integration

Date: 2026-11-09 KST
Authority: `C_PHASE4_MIGRATION_ACCEPTED`; M3 ledger updated by M.
Scope: Track **A only**. No B/Live/QA/official GitHub edits, no GCP deploy, no paid Provider calls.

## Canonical source and boundaries

- A SSD working directory: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first`
- Starting A HEAD: `9879eb0f85747312a224ecd898aaff84d834590b`
- Starting Tree: `e554a4317a9a90ef84b17de51dd74001728d034d`
- Current official `dev` at preflight: `62b6dcdef5663d5aa15c596b77ac601b245886db`
- Text Owner 김다혜 PR #27: **MERGED**, original HEAD `33c46b765c17b8f028553c343124f29de2969382`.
- Image Owner #24 OPEN, head `b3ee33fd524fbbb83890472be890c96974160e9c`: **9/10 files already exact A Blob match**; A's different `composition.py` deliberately pins `unicodedata2` for newer emoji categories on GCP Python. Do not blindly revert to stdlib Unicode.
- FE Owner #26 MERGED, head `c9c204b88af5ce1b25dfda501d16446750a41204`: 3/13 files exact; 10/13 differ. A already contains additional generation mode, QA/Live fences, server SHA review binding, image retry, and cost estimates; bulk overwrite would regress current tested capabilities. Review selectively in A1.2.

## EXACT adoption — 13/13 PR #27 source blobs

Fetched by GitHub Git Blob API pinned to PR #27 HEAD. For each file, source Git Blob SHA was verified before writing; all 13 match Owner exactly:

1. `scripts/README.md`
2. `scripts/eval_compliance.py` (new)
3. `scripts/test_compliance.py`
4. `scripts/test_revision.py`
5. `src/text_generation/README.md`
6. `src/text_generation/compliance/eval_holdout.jsonl` (new, 30 lines)
7. `src/text_generation/compliance/eval_set.jsonl` (new, 100 lines)
8. `src/text_generation/compliance/report_builder.py`
9. `src/text_generation/compliance/rule_checker.py`
10. `src/text_generation/compliance/rules.yaml`
11. `src/text_generation/copy_generator.py`
12. `src/text_generation/researcher.py`
13. `src/text_generation/schemas.py`

The Owner schema is v0.11 with `ComplianceIssue.basis_url` and explicit functional type selection; `revise_copy(issues=...)` now supports structured ComplianceIssue input.

## ADAPTED — A Serving integration, never Owner source modification

- `demo_staging/live/contracts.py`: Owner v0.11 rewrites the descriptive `reason` and no longer uses the v0.10 `기능성(<type>)` marker. A's existing conservative adapter incorrectly rejected *selected* `주름개선`. Now compare exact functional issue text against Owner's compiled rule taxonomy; allow a selected function as **근거 확인 필요**, block an unselected or unknown category. Keep conservative old reason fallback and old brand-safety/literal functional fallback.
- `demo_staging/live/pipeline.py`: Source-first enhancement to `OfficialTextProvider.revise_copy(..., issues=...)`. Only forward typed, current `ComplianceReport` issues from server-side SHA-bound review. Compare current generation, review SHA, copy SHA and full report digest against the existing SHA-bound revision context before any paid call. Original FakeOwner 5-argument offline test transport remains compatible.
- `tests/test_s4o_text_owner_offline_integration.py`: Keep strict source-pinning test; update Owner schema SHA256 from PR #25 v0.10 to verified merged PR #27 v0.11 `8ee6f48a8df0ad8d7c0ecd0ec9123cb12ce6752fccc524578c23827edd3c191b` (Git blob `19fdbe5a641df28402ba751aab524ebbffd0cad1`).
- `tests/demo_live/test_bp18_a1_owner27_integration.py`: new no-network tests for selected/unselected functional rules, verified `basis_url`, and actual Owner revision prompt populated with typed issues through the Serving adapter (mocked model transport).

## Reproduction and results (A worktree only, zero paid calls)

- Before adapting: Owner #27 exact import led to **84/85 targeted PASS, 1 contract failure**: selected `주름개선` incorrectly blocked by A's older reason-regex assumption. Fixed via Serving adapter only.
- After adapting: targeted Owner Text/Image/approval test suite **85/85 PASS**, new revision/functional-context test suite **34/34 PASS**.
- Rule-only official Owner evaluation script: main **50/50 risk detected, 1/50 false positive**, exact risk **99/100**; holdout **21/21 detected, 0/9 false positives**, exact risk **30/30**. This is *not* an LLM second-stage compliance or legal accuracy certification.
- Complete Python suite with verified macOS Korean system font path and no model secrets: **944/944 PASS**, log `/Users/Shared/ittem-a-owner27-a1-evidence-20261109/A1_OWNER27_FULL_PYTHON.log`.
- React tests **52/52 PASS**, lint **0 errors/warnings**, FE TypeScript/Vite build PASS; evidence logs in the same protected Mac internal folder.
- **Historical C exception remains OPEN:** `tests/demo_live/test_bp17_shared_minimal_export.py::test_existing_output_replaced_never_after_concurrent_publication` can crash via macOS Python 3.12 fork+SQLite. It reproduced once in an initial no-font full run, but passed in the subsequent properly configured complete suite. Do not silently waive or mark as resolved.

## Unresolved requirements / next A unit

- F09: actual **rules + LLM second-stage compliance** still unverified, do not declare complete.
- F11: Owner issues now bind into Serving revision LLM request **in code and mock transport**, not yet real provider semantic-quality evidence; text/approval policy Epoch remains a separate contractual gate.
- A1.2: review only the 10 nonexact FE #26 files while preserving A's stronger safety and 2-mode functions; evaluate A-vs-Owner Image #24 Unicode design adaptation without removing it.
- A2/A3: restricted Actor-based safe Worker/Queue, real 4:5 Composed ad then remaining 5 mode×ratio combinations, PNG/Caption/Receipt SHA and human quality.
- EX03/EX10 Browser, visual CTA/font license/mobile, F/V/S r0.1 acceptance, C independent audit remain separate gates.

B remains independently active; all official GitHub PRs/dev, historical release roots and completed GCP A/B/Live/QA artifacts are unchanged. No production promotion or release acceptance is implied.
