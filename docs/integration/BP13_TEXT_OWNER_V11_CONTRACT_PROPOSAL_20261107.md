# IT-TEM BP13 Track T — Text Owner 검수 입력·Art Direction 계약 협의안
기준일 2026-11-07 · **PROPOSED / NOT OWNER ACCEPTED** · 오너 김다혜님 승인 및 Owner 소스 PR/커밋 필요

## 1. 현재 코드와 미완료 경계
- Text Owner #25 구현의 `revise_copy(product, analysis, research, previous, instruction)`는 **다섯 입력**이며 `ComplianceReport.issues`는 실제 LLM 수정 입력에 포함되지 않음.
- Serving `revision_context()`는 최신 `Copy SHA`, `Review SHA`, `Generation`, 이슈 필드·원문·위험수준·사유·권고·basis를 수집하고 원장 해시를 대조함. **이 단계는 프리플라이트일 뿐 Owner 모델 입력으로 아직 전달되지 않음**.
- `ComplianceReport.basis`는 자유 문구. 출처 원문 링크가 확인되지 않은 상태이므로 자동 URL 생성 및 법적 적합성 판정 금지.

## 2. 요청하는 Owner 입력 계약 (기존 스키마 하위 호환)

선택적 `ComplianceRevisionContextV1` 데이터 구조를 Owner와 공동 확정:

```text
schema_version: "compliance-revision-context-v1"
job_id: existing stable ID
input_sha: 64hex
copy_sha: 64hex
review_sha: 64hex
generation: integer
compliance_report_sha: 64hex
issues: [
  {
    field: original ComplianceIssue field,
    text: verbatim risky text,
    risk_level: original issue risk_level,
    reason: original issue reason,
    suggestion: original issue suggestion | null,
    basis: original issue free text | null,
    basis_verification: "unverified" until separate official source verification
  }
]
```

Proposed method extension, only after Owner acceptance:

```python
revise_copy(product, analysis, research, previous, instruction,
            *, compliance_context: ComplianceRevisionContextV1 | None = None)
```

- Old five-argument invocations remain valid and semantically identical.
- Serving accepts only latest generation/Copy SHA/Review SHA and report hash under CAS; once Owner DTO/schema is approved, serializes versioned context into the Owner input (structured data, never as a higher-priority command).
- Do not let untrusted `reason`/`basis`/product text override user request, system policy, source fidelity, or compliance rules.
- No Research or VLM call on a copy revision. Changed Copy output triggers deterministic strict re-review; unchanged Copy + unchanged compliance leaves Generation, Review SHA and existing approval intact; `note`/changed_fields=[] shown to user without claiming successful edit.
- If only headline was authorized, unchanged subline must be identical. Warn about duplicated Head/Sub instead of silently modifying unrelated fields. Do not invent any claimed efficacy, ingredient, numeric outcome or product proof.
- Partial removal of unsafe wording must not pass; report each remaining `risk_level=위반 의심` and block approval.

## 3. Regulatory source references (NOT implement until verified)
- Optional structured official citation object: document name, applicable article/standard, issuing agency, canonical source URL, verified-at timestamp and content/ref hash.
- If not backed by verified official content, use `basis` explanatory text only with `basis_verification=unverified` and **no URL**.
- “검수 PASS” is internal screen/claim policy preflight, **not governmental/legal certification**.

## 4. Art Direction version proposal
- Existing generated `image_prompt` is mainly background/atmosphere. Keep its original `concept`, `mood`, Research evidence and previous approved Copy.
- **composed**: define product and scene composition *plus* versioned copy regions; instruct model not to draw ad wording, let Owner/Serving font engine render exactly approved text.
- **freeform**: give the Image Owner model the exact approved headline/subline/CTA + product/label protection + design guidance; avoid carrying over composed-only “fixed empty boxes / background only” constraints. Never force image model to redraw already-composed text.
- Version/Hash pin: `text_art_direction_version`, `design_profile_version`, `layout_sha`, `copy_sha`, `review_sha`, and eventual prompt_sha must come from the same immutable new Job context. Retrying an Image attempt **reuses** those exact Text outputs; do not regenerate.

## 5. Owner acceptance evidence request
1. Owner SHA, exact/modified files, method signature and JSON schema.
2. 5-arg backward-compatible Owner tests; new context actually present in structured model input.
3. Negative tests: stale review SHA, partial removal of unsafe phrases, forged regulatory source URL, unrelated field changes, no-op copy with meaningful note.
4. Mode-specific prompts: exact approved text, composed text-free behavior, freeform product/typography joint art direction; no new claims.
5. PM and Image Owner agree Layout v3 and Art Direction version before real image generation.

**Current gate:** `TRACK_T_OWNER_INPUT_NOT_ACCEPTED`. Serving's existing preflight safety cannot be declared a completed Text Owner integration.
