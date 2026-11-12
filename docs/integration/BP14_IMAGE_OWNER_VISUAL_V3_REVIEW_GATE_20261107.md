# IT-TEM Image Owner Track V — Visual v3 Production Policy 수용요청
기준일 2026-11-07. **PROTOTYPE ONLY / NOT PRODUCTION AUTHORIZED**. 박지수님 Image Owner, 김다혜님 Text Owner, 이태민 PM 최종 수용 필요.

## 실제 무과금 동등 비교
- Mac Studio `/Users/Shared/ittem-bp13-bp14-visual-v3-20261107/`.
- GCP 기존 BP11 완료 Job **4건**, 각 원본 `image.png`+기존 `final.png`+승인 카피+Receipt+고정 Layout SHA를 읽기 전용으로 확보.
- 실제 동일 AI 원본에 3가지 v3 스타일(A Editorial Warm, B Modern Contrast, C Soft Premium)을 로컬 Pillow로 그려 **12개 PNG 및 360px 축소본 12개** 제작.
- `V2_VS_V3_COMPARE_4JOBS.png`, `REVIEW_GALLERY.html`, `V3_EXPERIMENT_MANIFEST.json`, `V3_OWNER_PM_REVIEW_SCORECARD.csv`, `VISUAL_GOLDEN_SHA256.txt`.
- 실제 한글 글리프 미지원 초기 결함을 발견하여 한글 지원 NanumGothic으로 수정 후 재렌더. B 스타일의 Sub 대비 부족도 수정. **프로덕션 Owner 렌더러 코드는 변경하지 않음**.
- v3 후보 Head/Sub 정격 차등 및 CTA 4:5 표시. 9:16 CTA는 명시적으로 미확정, 3:4 기존 CTA 보존 가정.
- 4:5 e612db06 새 후보 Head A/B/C = 81/98/92px; Sub = 58/58/54px; CTA = 42/43/42px. v2 Head88/Sub59 CTA platform.
- 4:5 60421156 새 후보 Head A/B/C=102/108/92px; Sub=58/58/54px; CTA=42/43/42px. v2 Head128/Sub59 CTA platform.
- 기존 Owner Protected Region은 **목표 좌표**이며 실제 제품/라벨 Segmentation Proof가 아님. 이 실험은 텍스트 박스와 목표 좌표의 기하학적 비중첩만 자동 검사. 실제 겹침/대비/브랜드 조화/가독성은 반드시 사람 검수.
- 폰트 사용/상용화 라이선스 확인 전에는 어떤 시험용 Apple 시스템 폰트도 생산 코드·배포물에 포함하지 말 것. Font bytes 공유 금지.

## Image Owner가 승인해야 하는 상용 v3 DesignProfile Contract
1. `design_profile_id`, `profile_version`, `layout_sha`, `font_sha`, `prompt_policy_version`, `prompt_policy_sha`를 Job 생성 시 원자적 고정, 과거 v2 Snapshot 불변.
2. 각 `ratio+placement+generation_mode`별 Head/Sub/CTA 영역, 제품 보호 박스 및 적절한 글꼴 license, weight, 기준 픽셀 수, 자간·행간·정렬.
3. Head 기준 크기는 먼저 결정한 다음 카피가 물리적으로 넘칠 때만 축소. 독립 영역 최대화로 Sub가 Head보다 커지지 않게 제한.
4. 생략·치환·무단 줄임 금지. 수용 불가능할 경우 `TEXT_OVERFLOW`/이미지 승인 차단. Korean glyph coverage·색상 대비·모바일 360px 읽기 검증.
5. 이미지 내 CTA: **신규 4:5 composed 필수**; 3:4 이미지 CTA 보존; 9:16 신규 CTA 정책은 Owner+PM 선택. 플랫폼 UI CTA와 이미지 CTA 중복 정책 명시.
6. 제품이 라벨까지 안전하게 보이는지 원본 이미지와 합성 이미지로 사람 검수. Target box 비중첩만으로 Pass 불가. 어떤 스타일에서도 제품 자체는 덧칠·기형 수정하지 않음.
7. 자유형은 Text Owner Art Direction과 동일 version/DesignProfile을 받고 모델이 승인한 Head/Sub/CTA를 정확히 그리도록 지시. 서버는 폰트로 재합성 금지. 실제 AI가 한글·라벨에 실패하면 사용자 검수 Reject, OCR 자동 승인 금지.
8. Image Owner 코드 SHA/영향 파일, Golden renders/sha, 무료 회귀 결과, 폰트 라이선스 자료를 수령한 뒤 **새 Job에만** 차등 적용.

## PM 디자인 의사결정
- A/B/C 중 브랜드별 권장안 (또는 개선 시안)을 각 화장품 카테고리와 모바일 가독성으로 선택.
- 9:16 reels/story CTA 정책, CTA 크기/대비, 이미지 내 브랜드 노출 기준을 명시.
- 품질 점수 자동 부여 금지. `V3_OWNER_PM_REVIEW_SCORECARD.csv`에 사람별 의견과 승인 SHA를 작성.
- 샘플 4건만으로 전 제품 카테고리 출시 적합성을 단정하지 않음.

**게이트:** `VISUAL_V3_OFFLINE_CANDIDATES_HASH_VERIFIED` · `IMAGE_OWNER_PRODUCTION_V3_PENDING` · `PM_DESIGN_ACCEPTANCE_PENDING`.
