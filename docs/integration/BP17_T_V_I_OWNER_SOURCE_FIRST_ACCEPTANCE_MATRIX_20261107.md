# IT-TEM BP17-T/V/I — Owner Source First 수용 계약 및 통합 지점 체크리스트
작성 2026-11-07 KST. **요청·검토용 기술 계약. 실제 Owner/PM 수용은 아직 없음.**

## 최신 실제 Repo 사실 (2026-11-07 16:06 KST 재검증)
- Canonical official dev: `9f798169110e0bb6807c15347444f7c31ad05bae`.
- FE Owner PR #26 OPEN `c9c204b88af5ce1b25dfda501d16446750a41204`.
- Image Owner PR #24 OPEN `b3ee33fd524fbbb83890472be890c96974160e9c`.
- Text Owner #25 MERGED `7803aa4f8498d9e45f368055903e19fc39007674`.
- Current BP17-F `28a0ecc42246b31960ceeb47d68880e1862d086a`. New owner T/V PR was not present in GitHub at the time of inspection; thus **no T/V code to integrate**.

## Track T — 김다혜 Text Owner 변경 요청: 현재 실제 API 경로
- `src/text_generation/copy_generator.py:552` public Owner `revise_copy(product,analysis,research,previous,request,model,reasoning_effort)` → `_build_revision_input(product,analysis,research,previous,request)` → `call_structured(..., instructions=REVISION_INSTRUCTIONS)`. **현재 `ComplianceReport.issues` 없음**.
- `demo_staging/live/pipeline.py:223 revision_context`에서 현재 Report 원문, 위험 표현, Copy SHA/Review SHA/Generation, Source Report SHA 검증. 그러나 `pipeline.py:264 revise_copy`는 `provider.revise_copy(product,analysis.analysis,research,previous,instruction)`로만 전달.
- `OfficialTextProvider.revise_copy`도 그대로 legacy 다섯 data args를 Owner에 전달함. Serving Preflight가 Owner LLM이 이슈를 봤다는 증거는 **아님**.
- 새 Owner 선택형 버전 계약(제안): `ComplianceRevisionContextV1` = `copy_sha`, `review_sha`, `generation`, `compliance_report_sha`, `issues(field,text,risk_level,reason,suggestion,basis,basis_verification)`. 현재 사용자 수정 요청 및 5개 기존 입력과 함께 모델 입력 메시지에 **데이터**로 포함. 모델 system prompt보다 높은 권한으로 사용 금지. 5args 기존 호출은 동일 동작 유지.
- Owner test evidence: 실제 `call_structured` mock input snapshot에 현재 1개 이상 이슈 포함, stale Review SHA 거절, 일부 위반 표현 남았을 때 승인 금지, 안전/위험 표현 섞인 카피의 정확한 changed_fields, 0 변경 + note 시 Generation/승인 불변. Head-only 수정 요청에 Sub 불변. 검증하지 않은 법령 URL 미생성.
- **운영 통합 유의:** 기존 Queue `context_sha=digest(revision_context)`와 Checkpoint fingerprint를 깨지 않도록 버전을 명시. 이전 대기 중인 `QUEUED`/재시도 중인 Revise Task의 인가·중복 호출 보존. 신규 context를 무단으로 old context SHA 계산에 반영하지 말 것.
- 새 Owner의 정확한 commit SHA, schema version, import path, 호출 Signature, 테스트 결과가 제공되기 전에는 A′가 Signature를 임의 구현/반영하지 않음.

## Track T — Image Art Direction 분기와 비재호출
- 현재 `src/text_generation/image_prompt_generator.py`의 Owner `INSTRUCTIONS`는 "배경 설계"에 집중하며 `_build_input(plan,analysis)`은 승인된 Head/Sub/CTA 전체를 받지 않음. `generate_image_prompt(plan,analysis,model,...)`은 별도 입력 계약 필요.
- Composed v3: Research·제품·컨셉·브랜드가 반영된 배경/제품 구도를 설계하되, 실제 광고 문구는 **서버 합성**으로 한 번만 렌더. v3 Head/Sub/CTA 안전 구역은 Image Layout과 같은 프로필 버전을 사용.
- Freeform v3: **전체 승인 Copy 원문**과 Copy SHA/Review SHA/Generation, 브랜드·제품·제품 보호 및 v3 Art Direction을 모델에게 제공해 **제품+한글 문구+Typography를 함께 구성**. Composed의 "제품은 그리지 말 것/상단을 비울 것/광고 글자 그리지 말 것"을 Freeform 전체 그림에 그대로 전달하지 않음.
- 동일 승인 카피를 기준으로 Image Retry 시 **Research/VLM/Text 재호출 0**; 이전 PromptVersion/Profile SHA를 유지하고 새 이미지 Attempt ID만 기록.
- 기존 완료 Job의 v2 Prompt/Copy/Approval SHA 및 Snapshot을 변경하지 않음.

## Track V — 박지수 Image Owner + 이태민 PM
- 현재 `src/image_generation/layout_profiles.py`는 `LAYOUT_VERSION="instagram-copy-hierarchy-v2"`, Head/Sub 각각 독립 `max_font_size=128`; `feed-4:5`는 `cta_placement=platform`, `reels/story-9:16`도 `platform`.
- 4x3 v2→v3 A/B/C 후보는 `/Users/Shared/ittem-bp13-bp14-visual-v3-20261107`에 보존. 기존 4건 *동일 AI 원본·카피*와 360px 시안/Golden SHA를 보고 전문적인 Typography 프로필을 새로 결정해야 함. **현재 12/12 Owner·PM 점수표 PENDING**.
- Owner API·디자인 계약에 `design_profile_id/version`, Layout/Font/Prompt SHA, 허가된 사용 폰트 이름·굵기·라이선스 증빙, Head/Sub/CTA px 기준·최소축소·줄바꿈·자간·행간·정렬·배경대비, 제품/라벨 보호·CTA 버튼을 포함. Overflow/한글 글리프 부족은 Fail Closed; 글자 삭제·의도치 않은 무단 복사 금지.
- **신규 4:5 Composed는 이미지 CTA 필수**. 3:4 v2 Layout 보호, **9:16 플랫폼 CTA vs 이미지 CTA 정책은 Owner+PM의 명시적 결론 필요**. Freeform은 이미지 모델이 승인 CTA/Head/Sub를 직접 그리며 서버 재합성 금지.
- Image Owner가 제공할 자료: 새 commit/branch/PR HEAD, 정본 v3 Profile 객체 및 버전·정확한 SHA, 상용 폰트 사용 허가(바이트 공유 금지), 새 v3 Golden PNG 및 Source SHA, 기존 v2와 비교, 제품·라벨·모바일360 실기기 검수 기록.
- PM이 제품/브랜드별 스타일을 선택하거나 수정 방향을 승인. 임시 Pillow A/B/C 하나를 자동 상용 기본값으로 승격하지 않음.

## BP17-I 통합 수용 절차 (아직 시작 불가)
1. 최신 GitHub official dev와 Text/Image/FE Owner HEAD를 **당일 재조회**; Owner별 변경 파일 목록과 Exact/Adapted 계약을 기록.
2. Parent BP17-F `28a0ecc...` 고정. Owner 변경분은 **새 격리 브랜치**에 cherry-pick/Adapter 차등 통합; 공식 dev/Owner PR은 변경/병합/종료 금지.
3. Job 생성 시 새 Profile/Prompt/Font/Copy/Review/Approval/Generated Artifact SHA 결속; 구형 Completed v2와 과거 Job에는 v3 정책 미적용. 승인 후 카피 실제 변경에만 새 Generation/Review, 규제 실패 승인 차단, CAS 및 Actor ACL.
4. Python baseline **899 tests** + FE baseline **52 tests** + Owner 신규 테스트; ratio 3:4/4:5/9:16 × mode Freeform/Composed 각 1 후보와 재생성, 4:5 CTA·Sub size·text overflow·Korean Glyph Golden, MOQ PNG SHA, MPO, 수동 Provider UNKNOWN no-replay, 실제 공유 평가, 다운로드를 동일 QA 계열에서 재검증.
5. 유료 실모델은 Owner 소스/PM 디자인 QA 승인이 완료된 후 사용자 명시 생성 요청으로만 실행. `MONITOR_ONLY` 유지; 비용 수치 임의 보증, Hard Cap·예약·새 PM 건별 승인 제도 금지.
6. B′ 기능·보안·시각 **3축 독립 수용**과 팀원/PM 실제 제품 UAT가 완료되기 전 단일 통합 PR·Live 배포 HOLD.

**현재 상태:** `T_OWNER_CONTEXT_ACTUAL_MODEL_INPUT_PENDING` / `V_OWNER_PRODUCTION_V3_PENDING` / `PM_VISUAL_AND_FONTS_PENDING` / `BP17_I_SOURCE_INTEGRATION_NOT_STARTED`.

Owner·PM의 서명 또는 새 HEAD가 없음을 모델이 임의 승인으로 간주해서는 안 된다.
