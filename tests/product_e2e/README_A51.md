# A5-1 Profile v3 A/C — 실제 Owner Composite + 공식 React Chrome E2E

**검증 환경:** Mac Studio 로컬 / Chrome 157 / 정식 React 빌드 / FastAPI + SQLite 실제 Workflow / **OFFLINE_FIXTURE ONLY** / 실제 Provider 호출·과금·GCP 배포 없음.

## 기술 구현 (검증 대상)

- 신규 Job에만 `IT_TEM_A5_V3_BETA_PROFILE=A|C`와 `IT_TEM_A5_V3_OFFLINE_DEV_ALLOWED=YES`를 명시한 **무과금 개발 프로세스**에서 `owner-composed-4x5-v3-beta-proposal1` 계약 생성. 기존 v2 Job은 무변경.
- A/C 고정 기하, Prompt/Copy/Approval/Font/Profile/Layout/Policy Context SHA, Image Attempt·Receipt SHA를 실제 Serving 및 Owner Composition 경로에서 결속.
- Profile v3(합성형 4:5에만 적용) 실 PNG가 Head/Sub/CTA 1회 표시하도록 보호, 정해진 Font SHA의 설치 FE Pretendard 1.3.9을 테스트 환경에서만 사용.
- 고정 `protected_regions`는 **Mock용 가상 Product Target**. 실제 브랜드 로고·라벨 검출 마스크가 아니므로 실 Provider/실고객 활성화는 명시적으로 차단.
- 3:4/9:16, Freeform 및 기존 4:5 v2 Job, Batch 제외·단일 시안 정책 불변.
- 9:16 CTA 정책은 독립 미결정. Composed 4:5 v3에서만 이미지 내 CTA 확정 요구를 충족.

## 한 Profile씩 Chrome 재현 (각각 독립 Job)

```bash
cd '/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
export A41_PYTHON='/Users/Shared/ittem-migration-M0-20261109/venv-m2-python312/bin/python3'
export A41_PLAYWRIGHT_CORE_MODULE='/Volumes/SSD 4T/z_ai_asset/P03_it-tem/experiments/free-first-benchmark-lab/.tools/t06_browser_tools/node_modules/playwright-core'
export A41_FONT="$PWD/app/node_modules/pretendard/dist/public/variable/PretendardVariable.ttf"
unset OPENAI_API_KEY GOOGLE_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY
A51_PROFILE=A A41_PORT=18543 bash tests/product_e2e/run_a51_v3_offline_chrome.sh
A51_PROFILE=C A41_PORT=18544 bash tests/product_e2e/run_a51_v3_offline_chrome.sh
```

- 두 Runner는 격리된 `/private/tmp/ittem-a41-product-*` 아래에서만 임시 서버를 실행하고 자체 프로세스를 종료한다. 계정 비밀 코드·SQLite 원본·폰트 바이너리는 증거 출력에 포함하지 않는다.
- 정식 React 사용자 여정의 제품 사진 2개 업로드 → 실제 QA Text DTO·F09 Compliance → 수정·복원·승인 → 단일 Image Attempt 1 거절 / 명시적 Attempt 2 재생성 → 최종 합성 PNG·Caption SHA/브라우저 다운로드 → GET-only Refresh → 360/390px Screenshot 및 Actor Access denial을 실제 Chrome으로 재실행한다.
- 비교/검증은 HTTP 성공을 넘어 **SQLite 실제 원장 및 Owner Receipt**(CTA image, omitted=[], Head/Sub/CTA UTF-8 SHA, fixed Profile ID/Version/Epoch/Layout SHA, locked Font SHA, Attempt 2/2, Queue 0/Cost 0)를 읽기 전용으로 확인한다.
- 최종 Source Commit/Tree·Chrome Trace·Screenshot/PNG/Caption SHA를 독립 C-A에 제출.

## 필수 불변 게이트

`SOURCE_SECURITY_PASS_PENDING_C_A / PROFILE_V3_OFFLINE_FIXTURE_ONLY / OWNER_PM_SIGNOFF_PENDING / REAL_BRAND_MASK_NOT_AUDITED / REAL_PROVIDER_E2E_NOT_AUDITED / SIGNED_SSO_DEPLOYMENT_NOT_AUDITED / GCP_QA_DEPLOYMENT_HOLD / PAID_WORKER_HOLD / FULL_FEATURE_BETA_READY_FOR_TEAM_UAT=NO`.

특히 `PROFILE_V3_OFFLINE_FIXTURE_ONLY`는 가짜 이미지를 실제 모델 출력으로 대체하거나, 서명·비용·법적 사용권을 승인했다고 의미하지 않는다.
