# IT-TEM P03 Track A — A5-0F 실제 제품 증빙·마스크·폰트·사람 품질 검수 계획

**상태: `REAL_ASSET_SET_0_VERIFIED / D50_05_D50_06_HOLD / HUMAN_VISUAL_NOT_ACCEPTED`.**
**근거:** C-A5-0D-R1/A5-0E 감사 `C_A50DR1_APPROVAL_DRAFT_GENERATOR_REPAIR_ACCEPTED`, `C_A50E_REFLOW_MOCK_DESIGN_PROPOSAL_REPRODUCIBLE_ACCEPTED_WITH_NOTE`; 현재 Track A 실제품 이미지와 사용권 증빙이 연결된 검증 세트 없음.

## 1. 대표 실제품 데이터셋 — 현재 0개, 필요한 최소 검토 범위

필수 입력을 **사용권이 확인된 적법한 실제 자료**로만 준비한다. A/C 또는 v3 모델 제품 충실도를 평가하는 데에는 적어도 다음 **서로 다른 위험 조건**을 제안한다. 수량과 임계값은 PM 최종 승인사항이므로 특정 숫자를 제품 수용선으로 확정하지 않는다.

| Sample class | 광고 제품 / QA 위험 | 요구되는 사용권·라벨 증거 | 현재 |
|---|---|---|---|
| R-01 | 일반 스킨케어 용기, 큰 한글·영문 라벨 | 브랜드 소유 또는 고객 허가, 정면/후면 사진, 라벨 읽기 참조 | MISSING |
| R-02 | 슬림 튜브·펌프 또는 크기가 큰 패키지 | 겉면 전체 경계, 상세 라벨, 실제 제품 마스크 | MISSING |
| R-03 | 투명·반사 용기, 작은 로고/약관 문구 | 컬러/반사/제품 형태 보존 판단, 라벨 마스크 | MISSING |
| R-04 | 여러 제품·박스+용기 또는 작은 제품 | 객체 간 겹침, 이미지 리플로우·Safe Zone | MISSING |
| R-05 | 사람/제품 동시 촬영(사용권·초상권 포함) | 모델 초상권/사용 범위, 얼굴·피부/제품 마스크 | MISSING |

모든 Sample의 원본 SHA·촬영/저작권자·사용허락 범위·검토 담당자·사용권 문서 SHA와 내부 액세스 경로를 **비공개 자산 등록부**에 연결한다. 법무·Owner 승인 없는 외부 웹 이미지, 경쟁사 광고 캡처·브랜드 이미지, 과거 발표용 사진을 실제품 검수에 재사용하지 않는다. 유료 모델 호출 및 GCP 배포는 본 데이터 수집에서 승인하지 않는다.

## 2. 표준 원본·Mask 증거 계약

정본 입력 스키마: `docs/integration/BP18_A50F_REAL_ASSET_INTAKE_TEMPLATE_20261110.json`. 읽기 전용 사전점검 도구: `scripts/a50f_real_product_qa_intake.py --manifest <private manifest> --out <new QA report JSON>`.

1. `source_image_path`와 SHA256(허가된 실제 제품 사진), `rights_file_path`와 SHA256(권리 문서), `rights_document_ref`, 사용 허용 범위, Owner/법무 리뷰 참조. **권리 증거의 존재와 실제 권리 인증은 구분**한다.
2. `candidate_canvas_path` 1080×1350 및 SHA256(정식 Provider 결과인지, 허가된 대체 미디어인지 명시). 모델이 생성한 실제 광고가 아닌 Mock을 실모델로 표시하지 않는다.
3. 제품·브랜드·로고·라벨/모델 보호 영역을 **실제 결과 캔버스 1080×1350 좌표계**에서 마킹한 단일 채널 PNG 0/255 Mask와 SHA256. 비어 있거나 알파·그레이 확률 Mask/차원이 틀리면 HOLD. Owner가 좌표계 변환 `source_pixel -> final_pixel`을 설명하고 변환 파라미터/해시, 누락 제품/라벨 검토를 제공해야 한다.
4. 승인 Head/Sub/CTA 각 Region과 Mask 픽셀 충돌이 0인지 검사. 충돌·과대 이미지·마스크 미확인 시 자동 PASS 금지. 결과는 **`MASK_RECT_NONOVERLAP_ONLY` 또는 `MASK_COLLISION_HOLD`**이고 실제 브랜드 충실도·객체 검출 정확도·License Clearance는 사람 별도 검토.
5. 동일 1080 이미지의 축소 360/390 및 플랫폼 Crop 전후 원본/해시·한글 가독성, CTA 누락/중복·라벨 가림을 사람이 실제 화면에서 점검. 기존 A50E 12px Crop은 단지 임의 시뮬레이션이다.
6. 실제 생성 이미지에서 패키지·라벨 왜곡, 로고 오타, 모델 얼굴/손의 오류, 허위 전후 사진, 규제에 저촉되는 Copy가 있으면 사람 Reject 및 수정. 이미지/캡션 무결성 PASS만으로 허용되지 않는다.

**파일 보안:** 실제 사진·초상·License·마스크 원본은 승인된 접근 제한 위치에 보관하고 일반 Git/ZIP/이메일 본문에 넣지 않는다. 검증 결과 문서에는 식별 가능한 파일 경로/원본 내용 대신 CASE ID, SHA, 계측 결과, 권한 검토 ID만 기록한다. 실제 원본 로컬 경로는 인증된 검토자의 사설 Manifest에만 둔다.

## 3. 4:5 Composed A/C Design/Profile UX 평가 (가안, 미승인)

**Hard Gate (하나라도 미통과 시 점수 평가 이전에 HOLD/REJECT):** 사용권·모델 초상권/브랜드 승낙, 광고 카피의 사실성·규제, CTA 이미지 내 정확히 1회, Head/Sub/CTA 승인 UTF-8 Copy SHA와 레이아웃/실제 제품·로고·라벨 마스크 충돌 0, 줄 넘침·문자 잘림·글리프 누락 없음, Font 배포 사용권, Actor/Job/Approval/Policy/Attempt/Artifact SHA, 표준 제품 크기/Ratio 1080×1350.

| 사람 검수 축 | 평가 질문 | 가안 배점 (승인 전 점수 아님) |
|---|---|---:|
| Typography | 헤드라인·서브카피·CTA 한글 자간·행간·위계/줄바꿈/읽기 | 30 |
| CTA | 360/390 실기기 CTA 발견성·대조·하단 크롭·행동 유도 | 25 |
| Brand/Product | 실제 패키지·로고·라벨과 제품 사진 충실도/시선 통합 | 20 |
| Commercial visual | 사진·구도·공간·톤 앤 매너·실사용 광고 적합성 | 15 |
| Mobile | 360/390 플랫폼 UI 크롭·CTA/제품 중요영역 Safe | 10 |

점수의 가중치·최저점·영역별 최소점·평가자 수/독립성·거부 기준은 **D50-07 Owner/PM 결정** 필요. 모든 점수는 실제 광고와 지정된 검토자가 직접 평가해야 하며, 지금의 샘플 행은 점수 공백으로 남긴다. 기계가 편의상 100점을 부여하거나 A/C에 우열 점수를 붙이지 않는다.

## 4. 현재 사용 가능한 폰트 근거와 미완료

`Pretendard Variable 1.3.9`는 FE에서 이미 사용. 로컬 설치 TTF SHA `3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22`, 설치 OFL LICENSE SHA `b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e`. 고정된 로컬 QA 한국어 카피 글리프 19/19. 이 사실은 **상업용 서버 Font 설치/배포 방식, 정확한 Weight, License Notice와 법무 서명의 확정이 아님**. 바이너리를 보고서/ZIP에 복제하지 않는다.

## 5. Gate / 후속 단계

실제로 미수령: Image Owner 박지수의 디자인 방향 의견·제품 보호 마스크 검토, PM 이태민의 디자인·광고 수용 기준, 적법한 실제 사진, 법무 Font 사용권, 서명된 Profile ID/Version/JSON SHA/정책 Epoch, 서명 원장 인증 절차. 이후 단계에서도 작업을 섞지 않는다.

`A5_0F_REVIEW_MESSAGE_PREPARED / REAL_PRODUCT_RIGHTS_CLEARED_SAMPLES_VERIFIED_0 / D50_05_D50_06_HOLD / OWNER_PM_SIGNOFF_0 / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

C-A 독립감사에는 **도구의 무결성, 권리 증빙 누락 시 Fail-Closed, 실제품 미검증이라는 정확한 상태 표현**을 제출한다. 사람 결정 없이 정책 점수/좌표를 확정하거나 Runtime을 변경하지 않는다.
