# IT-TEM P03 — Full-Feature Beta 팀 UAT 준비 패키지 (미승인 초안)

**상태: `TEAM_UAT_READY=HOLD`.** 2026-11-10 작성. 실제 베타 URL, 사용권 확보 제품, 인증/SSO, 비용 상한과 Provider Worker, C-A 독립감사 승인 없음. **절차 준비 ≠ 공개·배포·실모델 호출 허가**.

## 1. 팀 접속 안내 — 운영자가 배포 승인 후 작성할 부분

| 필드 | 확정된 값 또는 차단 |
|---|---|
| 대상 환경 | GCP A 전용 격리 후보, 팀 전용 HTTPS + 인증, B/Live/기존 QA와 분리 |
| 최종 팀 URL | `NOT_ASSIGNED` — 임의로 URL 생성하거나 기존 Live 주소를 재사용하지 않음 |
| 인증 | `SIGNED_SSO_NOT_AUDITED`; 사용자별 Actor 권한, 인증 쿠키 범위 확인 필요 |
| 초대/계정 발급 | PM이 승인한 비공개 채널로만; 테스트 문서에 패스워드/초대 코드/API Key 포함 금지 |
| 실제 제품 자료 | 소유·광고 사용권·제품/라벨·브랜드 이미지 권리 증빙이 있는 제품 최소 1종; 현재 `PENDING` |
| 비용/실모델 | `PAID_WORKER_HOLD`; PM 승인 비용 상한·자격증명·중복 과금·3개 원장 검증 이후에만 진행 |
| 피드백 접수 링크 | `PM_FEEDBACK_ROUTE_NOT_ASSIGNED`; 운영 전 PM 지정 필수 |
| 실행 Runtime SHA | `GCP_RUNTIME_NOT_VERIFIED`; 배포 후 HEAD/Tree/JS 번들 SHA/Owner Epoch 재검증 필요 |
| 베타 표기 | `BETA / NOT COMMERCIAL RELEASE` + 모델 한계·사용권·불법 광고표현 점검 고지 |

## 2. 실제 모델/팀 UAT 6개 케이스 — **서로 다른 Job 여섯 건**

| UAT ID | 사용자 선택 | 후보 수 | 필수 광고 검증 및 현재 Gate |
|---|---|---:|---|
| UAT-01 | Composed 4:5 | 1 | 승인된 Head/Sub/CTA 정확히 1회 이미지 합성; v3 Profile/Font/Mask/Policy Epoch 서명 후 활성화 |
| UAT-02 | Composed 3:4 | 1 | 실제 승인 Copy의 이미지 표시·가독성·제품 보호 및 기존 v2 계약 검증 |
| UAT-03 | Composed 9:16 | 1 | **PM의 9:16 CTA 최종 처리 정책 선확정 필요**; 결정 전 실모델 품질 수용 HOLD |
| UAT-04 | Freeform 4:5 | 1 | 모델 생성 한글의 정확도·브랜드/라벨·광고 완성도; 서버 텍스트 오버레이 없음 |
| UAT-05 | Freeform 3:4 | 1 | 모델 생성 문구·제품 충실도·모바일 레이아웃; 서버 텍스트 오버레이 없음 |
| UAT-06 | Freeform 9:16 | 1 | 모델 자체 텍스트와 플랫폼 CTA 처리 정책, 인스타 UI safe zone, 제품·라벨 보존; 서버 오버레이 없음 |

각 Job에서 제품 사진 **2~5장**, 참고 이미지 **0~5장**, 단일 생성 모드 및 단일 비율만 제출한다. 다른 Job의 시안을 한 요청에 묶거나 Batch/Gallery를 추가하는 것은 계약 위반. 샘플이 다른 실제 고객 자료일 경우 사용권 확인을 각각 시행한다.

## 3. 브라우저에서 실제 수행할 한 Job의 검증 절차

1. 권한을 부여받은 테스트 사용자로 로그인. 비로그인 401, 다른 Actor Job 조회 404, 로그아웃 후 보호 자료가 표시되지 않음을 확인.
2. 제품 이미지 2~5장을 업로드하고 권리 체크·제품명·특징·목표·모드·비율을 선택. 사용자 화면에서 정확히 선택된 단일 모드/비율을 확인.
3. 실제 모델 분석 → 조사 → 광고 기획 → Copy → 규제/표시광고 검수 기록, 기존 수정/복원/CAS·Approval SHA가 연결되는지 확인. 위반 표현 차단·필수 근거 누락 Fail-Closed 확인.
4. 승인된 Copy를 이미지 생성으로 전달. 실제 Provider Attempt ID, 사용량/Receipt, Queue·Cost·Owner Image Attempt 3중 원장 일치, 단일 후보 1개 검증.
5. 첫 이미지를 검토 후 필요시 거절 → 사용자가 **명시적으로** 재생성 버튼 클릭 → 새 Attempt Version·Image SHA, 원본 승인 Copy SHA 유지, 과거 이미지 재승인 차단. 단순 새로고침/재접속이 재과금을 유발하면 FAIL.
6. 최종 이미지 승인 → Composed의 실제 합성/Freeform의 오버레이 없는 내보내기 → 브라우저 PNG·UTF‑8 Caption 다운로드. 서버와 다운로드 바이트 SHA·Dimensions·승인/Receipt SHA가 모두 일치해야 함.
7. Desktop, 모바일 390px, 360px에서 각 화면(업로드, Copy, 검수, Image, Export)을 검사. 한국어 오버플로·버튼 겹침·가로 스크롤·실패 메시지·재접속 GET-only를 별도 증거로 보존.
8. 실제 제품·브랜드·라벨 원본과 출력물을 나란히 확인(제품 형태/색/디자인/로고/작은 라벨 글자/허위 인증/효능). 인간 Owner·PM 각각의 명시적 승인 기록과 연결.
9. 최종 결과물의 마케팅 목적·한국어 Typography·Headline/Sub/CTA 위계·색상 대비·제품 보호·다운로드 해상도 평가. 단순 Glyph SHA 통과만으로 실제 광고 품질 PASS 처리 금지.

## 4. PASS/FAIL 안전성 부정 테스트

- 이미지 다중 후보 2/3/4, Composed+Freeform 혼합, 과금 없이 HTTP 422.
- 수정·복원 후 과거 Copy Review/승인 SHA 재활성화 409/422; 현재 검수 기준으로 재승인 필요.
- Image Reject 후 stale Image SHA 승인 409/422; 명시적 재시도 1개만 허용.
- Reload/reconnect는 GET-only; 세션 갱신이 허가되지 않은 POST/Provider 반복 시 FAIL.
- 잘못된 Font SHA/Template SHA/Policy Epoch/Receipt/Mask, Copy 누락·Overflow·충돌은 Fail-Closed.
- 본 테스트와 관계없는 B/Live/QA 환경·이전 v2 Job·Receipt·Artifact SHA의 변경은 P0 BLOCK.
- 공유 API 계정에서 발생한 Usage 미가격/과금 상태 불명/중복 전송 가능성은 즉시 HOLD하고 원장을 보존.

## 5. UAT 피드백 레코드 표준 (한 문제 = 한 행)

| 필드 | 기록 규칙 |
|---|---|
| `case_id` | UAT-01 ~ UAT-06 |
| `job_id_pseudonym` | 사내 비식별 Job 토큰; 외부 공개 금지 |
| `timestamp_kst`, `device` | 시간·OS·브라우저·화면 폭 360/390/Desktop |
| `scenario_step` | Upload / Planning / TextCompliance / CopyReview / ImageAttempt / Approval / Export / Resume |
| `expected` / `observed` | 기대 vs 실제. 비용·개인정보·키/토큰 값 기록 금지 |
| `severity` | P0 기능·결제·권한/무결성 차단 / P1 제품 품질·UX / P2 장식·선호 |
| `source_sha`, `runtime_sha`, `profile_epoch` | 해당 세션에서 실제 검증한 값만 |
| `approval_sha`, `attempt_id_masked`, `artifact_sha` | 출처 추적용 비식별 SHA / 직접 승인자 서명은 원본 저장소 링크만 |
| `image_quality` | 한글/CTA/라벨/제품/브랜드/클레임/라이선스 항목 별 PASS/FAIL/NOT_AUDITED |
| `screenshot_ref`, `receipt_ref` | 권한 있는 비공개 증거 저장소 경로 |
| `owner_review`, `pm_review`, `c_a_review` | 각 실제 검토자 별 PASS/FAIL/PENDING. 임의 승인 금지 |
| `resolution_status` | OPEN / FIXED_AWAITING_RETEST / VERIFIED_FIXED / DEFERRED_WITH_PM_APPROVAL |

## 6. 베타 오픈 전 필수 PM/Owner 운영 체크

현재 모든 필수 베타 게이트는 아직 수용되지 않음: `SOURCE_AND_SECURITY_PASS`, `PROFILE_V3_RUNTIME_PASS`, `OWNER_INTEGRATION_PASS`, `REAL_PROVIDER_E2E_PASS`, `UI_UX_BETA_PASS`, `VISUAL_QUALITY_BETA_PASS`, `TEAM_UAT_READY`. **중요 기능 누락을 `CONDITIONAL_GO`로 처리하지 않음.**

**우선 해결할 인간/운영 의사결정:** (a) v3 정확한 Profile A/C 기본형·폰트 라이선스·제품 보호 Mask/정확한 SHA·서명; (b) 9:16 CTA 정책; (c) GCP A 운영자 인증 복구·읽기 전용 실제 원장 조사와 구버전 배포 SHA 대사; (d) 비용 하드 캡·자격증명·원장 과금 안전성 및 실제 Provider 6건 승인; (e) HTTPS/SSO/팀 URL 및 별도 피드백 접수 경로 지정.

**참조:** `BP18_A51_PROFILE_V3_RUNTIME_C_A_DIFFERENTIAL_AUDIT_PACKET_20261110.md`과 `evidence/A51_20261110/`. 이 문서는 작업 절차 초안이며 실제 운영 접근권한이나 테스트 승인을 부여하지 않습니다.
