# IT-TEM BP17-T/V Owner Source First — 구현자 독립 수용을 위한 변경 요청·검증 계약
2026-11-07 KST · 준비 문서 · **Text Owner·Image Owner·PM에게 아직 전달/승인되지 않은 제안서**

## 현 Owner Code Readiness (실제 소스 기준)
- Official dev `9f798169110e0bb6807c15347444f7c31ad05bae`.
- Text Owner #25 이미 MERGED `7803aa4f8498d9e45f368055903e19fc39007674`. 현재 `src/text_generation/copy_generator.py:552 revise_copy`는 `ComplianceRevisionContextV1` 실제 모델 입력을 받는 새 승인 계약이 **없음**.
- Image Owner #24 OPEN `b3ee33fd524fbbb83890472be890c96974160e9c`. 현재 `src/image_generation/layout_profiles.py`는 여전히 `instagram-copy-hierarchy-v2`, 신규 4:5 `cta_placement=platform`. v3 Production Profile 승인 소스 **없음**.
- FE Owner #26 OPEN `c9c204b88af5ce1b25dfda501d16446750a41204`; 최신 UX는 BP16까지 차등 수용, 새 소스 없으면 재개발 금지.
- 기존 `BP13_TEXT_OWNER_V11_CONTRACT_PROPOSAL_20261107.md`, `BP14_IMAGE_OWNER_VISUAL_V3_REVIEW_GATE_20261107.md` 및 Visual v3 12개 후보/360px 결과와 비교할 것.

## Track T — 김다혜님에게 요청할 소스/계약
1. 기존 **5 positional args** 호환 유지, optional `compliance_context`를 받는 versioned Owner DTO/method 설계 제안. Schema: current Copy SHA, Review SHA, Generation, ComplianceReport SHA 및 issues의 field/original/risk/reason/suggestion/basis (source unverified 표시), evidence binding.
2. 실제 `revise_copy` LLM request 구성 단계에서 이 구조화된 검수 컨텍스트를 **데이터로 사용**해야 한다. Serving preflight가 만드는 context JSON만으로 PASS 불가. 모델이 위험 표현 잔존 시 안전하다고 표시하지 않도록 신뢰·검수 규칙 유지.
3. 바뀐 필드 목록과 바뀌지 않은 필드·무변경 사유 정확히 반환. 무변경이면 Generation/Review SHA 변경 금지. 위험 표현 일부만 삭제하면 남은 이슈를 새 검수로 보고하고 승인 차단. Head만 수정 요청했으면 Sub 무단 변경 금지.
4. 근거 URL/법령은 검증된 원문에만 연결; unknown이면 URL 없음, PASS를 법률 인증으로 표시 금지. 새 효능·제품 특징 발명 금지.
5. `text_art_direction_version`과 `design_profile_sha`를 Image Owner와 공동 고정: composed는 제품·브랜드·콘셉트/안전한 텍스트 영역을 설계하고 모델은 실제 광고 글자를 그리지 않음; freeform은 승인 Head/Sub/CTA와 제품·타이포그래피를 통합한 장면 구성, composed의 고정 빈 텍스트박스 요구 강제 금지.
6. **인계물:** 실제 Owner commit SHA/브랜치/PR, 정확한 DTO·API contract, 5arg 호환/실제 모델 메시지 스냅샷/부분 삭제·무변경·untrusted URL·모드별 ArtDirection tests. Serving은 승인된 코드를 차등 통합.

## Track V — 박지수님과 PM에게 요청할 소스/결정
1. Visual 비교 `/Users/Shared/ittem-bp13-bp14-visual-v3-20261107/IT_TEM_VISUAL_V3_OWNER_PM_REVIEW_20261107.zip` (12개 후보 4×3, 모바일360, 원본 v2 동일 AI·카피 및 SHA 고정; 폰트 파일 없음)을 검토하고 A/B/C 중 선택 또는 디자인 재작성. **자동으로 후보 A/B/C를 상용 품질 승인하지 않음.**
2. 상용 v3 `DesignProfile`: Head/Sub/CTA font family, license, weight, target PX, kerning, line height, line wrap, contrast, button style/position, 안전 영역 및 실제 제품/라벨 사람 검수 지침. 긴 한글 Copy 임의 생략·축약 대신 fit 실패 처리. 글리프 검증과 모바일 360 가독성.
3. 신규 **4:5 composed 이미지 CTA 필수**, 3:4 기존 정책 보호, 9:16 reels/story CTA 이미지 vs 플랫폼 정책을 명시적으로 결정. Freeform CTA를 모델이 직접 그리는 방식과 동일 승인 카피 SHA/문구 일치 수용.
4. Profile/Font/Layout/Prompt/Art Direction Version+SHA와 active Job binding; **기존 v2 완료 Job/Receipt/Artifact 어떤 것도 재해석·변경 금지**. Freeform 서버 텍스트 재합성 금지, 제품/라벨 실제 비침범 사람 검수 필요.
5. **인계물:** 실제 Image Owner SHA·PR, licensed fonts 사용 증빙(파일은 공유 금지), Geometry/Golden Images SHA, supported image ratios/CTA decisions, Local Unicode Golden tests, PM 디자인 승인 기록.

## PM — 이태민님 최종 수용
- 디자인 시안 모바일360/실제 iPhone과 데스크톱 브라우저에서 제품/라벨/Head/Sub/CTA 및 브랜드 적합성 판정. 점수표 12/12 Owner/PM PENDING을 실제 판정으로 갱신(자동 점수 없음).
- Owner T/V 계약이 모두 확정되면 승인된 HEAD 기준 BP17-I 통합; Python 기준 899 + FE 52 및 새 수용 테스트. 실모델 자유형/합성형 광고 UAT 뒤 B′ 최종 감사.
- `MONITOR_ONLY` 유지, 사용자 명시 생성 요청만 실모델 호출, 외부 API 사용량 측정. 별도 Hard Cap이나 새 PM 건별 승인 절차는 추가하지 않음.
- 기존 GCP Live 18088/Tailscale 10000·8443와 Owner PR #24·#26 및 PR #18을 변경·병합하지 않음.

**계약 상태:** `T_OWNER_INPUT_PENDING` / `V_PRODUCTION_PROFILE_PENDING` / `PM_VISUAL_UAT_PENDING`. 이 문서는 실제 Owner·PM 승인을 주장하지 않는다.
