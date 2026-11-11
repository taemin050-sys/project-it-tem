# IT-TEM P03 / Track A — A5-1F Actual Source Rights / Real Beta Activation Gate Differential Submission

**기준일:** 2026-11-11 KST. **상태:** A5-1F 개발 구현 및 정적 배포 준비도 평가, 실제 사업 운영·유료 모델/배포/권리 승인 아님. 기존 수용 A5-1E 보존.

## 0. 독립 감사 기준과 최소 변경 범위

- 이전 C-A 공식 수용: HEAD `60dca54e16a5614318806532d122053ca8246d95`, Tree `b27f7c8889bc352e303f32ef419ce040a44931ac`. 감사보고서 /Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A51E_SIGNED_NONBILLABLE_INGRESS_INDEPENDENT_AUDIT_20261111.md, SHA-256 `0429ae01d45dc5fe177e0abd40e2b64d6378ab01b5d68fe133c15b168308ed5e`.
- **A5-1F 고정 실행 코드 HEAD:** `5769d49af1f20c5a272185741753864d5b181d77`, Tree `42b2239b54667e026042f9d1cb4906b121faa1ff`. 기존 Worker 1파일의 추가 fail-closed 확인 + 신규 production-oriented 권리 서명 검증기 1파일 + read-only 실제 베타 적격성 판별 도구 1파일 + 2개 표적 테스트 = 총 5개 실행/테스트 파일. 이후 Owner/PM 요청서와 감사 증거만 별도 문서 커밋.
- 신규 기술 사용 목적: **제품 이미지·광고 모델 사용권 증빙을 Paid Worker의 실행 전 추가 확인하는 계약**. 실제 승인서 발행, 신규 Provider 호출, GCP 자원 수정, 현행 v2 수정 또는 실제 Signed Beta 전환 시도는 없음.

## 1. 추가 구현 코드의 계약과 안전 경계

1. `demo_staging/live/a51f_product_rights_authority.py`:
   - `IT_TEM_P03_A51F_DUAL_SIGNED_SOURCE_RIGHTS_V1` 신규 버전 제안. 실제 B0 `JobStore`의 사진 애셋을 SHA 검증하며, 제품 사진 2~5·참고 사진 0~5의 **순서 있는 SHA·asset ID·role** 전체를 권리 원장에 결속.
   - 보호된 private evidence 파일과 정확히 일치하는 SHA, Image Owner #24·PM의 **서로 다른 Ed25519 공개키 지문** 및 두 서명 파일을 직접 검증. 서명된 본문에 Actor, Job, SKU, Provider, source commit, Policy Epoch, Freeform|Composed 및 선택한 3:4|4:5|9:16, UTC 30일 이내 유효기간이 모두 결속. Browser의 자의적 동의만으로는 승인 불가.
   - 제품 이미지 원본·사람 승인 증거·Secret을 Git/감사 증거에 복사하지 않음. 검증 성공은 **해당 서명과 원본 SHA/문서 SHA의 진위 검증**만 의미하며, 법률적인 권리 진정성, 제품/라벨 품질, 상업적 배포 또는 Provider/과금 승인으로 승격하지 않음.
2. `demo_staging/live/worker.py`: 기존 `A51C_HARD_CAP`의 서명·4개 제품 권리 Boolean·현재 A51B Signed Profile 재검증 **이후** 별도 `validate_signed_source_rights`를 추가 호출. 기존 FAIL_CLOSED를 해제하지 않고, 기존 Product/Queue/Cost/BILLING_UNKNOWN 보호를 유지. **현재 A51B의 4개 Boolean은 모두 false이고 현재 signed v3는 offline-only라 실제 호출 불가능**. 신규 권리 계약은 그 결함을 거짓으로 해제하는 토글이 아님.
3. `scripts/a51f_real_beta_readonly_release_gate.py`: C-A 승인된 읽기 전용 GCP Probe JSON을 로컬 고정 소스와 비교. GCP 구버전·Owner Provider Attempt 원장 누락·실제 SSO·제품권리·최종 User UAT 미완료를 기계적으로 `HOLD` 판정. 미승인 외부 JSON이 `beta_ready=true`라고 주장해도 실제 배포 승인으로 승격하지 않음. **이 도구는 GCP에 연결·쓰기, DB migration, 모델 호출, API Key 조회를 하지 않음**.

## 2. 제품 기능·인프라의 실제 미완료 의존성 (이것이 최우선 작업)

| Gate | 실물 상태·의존성 | 다음 승인·구현 책임 |
|---|---|---|
| MPO Owner/PM | 원본 24장 중 MPO 15장, 기존 v2 Frame0 동작; 신규 Signed Beta는 Fail-Closed REJECT. 실베타 Owner/PM 정식 프레임 선택 또는 정식 반려 정책 **미승인** | Image Owner #24 + FE #26 + PM. A51D-R1 CAS를 프로덕션 SSO 영속 선택 원장으로 버전 적용, 승인 전 기능 활성화 금지 |
| 실제 SKU·권리·마스크 | 사용권 서명된 원본 2~5장, 제품/로고/라벨 Mask, Profile v3 A/C 실제 광고 품질/CTA/Font **미확인** | Image Owner / PM 실제 자료, 서명·사람 검수 |
| Signed v3 / 6조합 | A51B Signed Profile은 **Composed 4:5에 한정**; 4개 Paid Authority Boolean false; `select_signed_beta`, `image_request`, `compose`가 LIVE를 의도적으로 차단. 전체 6개 모드 실제 Provider 계약 **미완성** | Owner의 버전 명시 6개 독립 승인 Profile·Worker/Serving 계약 정립 및 C-A 차등 검증. v2 불변 |
| GCP A 실제 소스 | C-A 관측 `9879eb0f85747312a224ecd898aaff84d834590b`. A5-1F 미배포, Owner Provider Attempt DB 없음 | PM 사전 승인 + infra A-only 별도 안전 배포, source/build/runtime/font SHA·Signed SSO·WAL Backup/Rollback |
| PM 비용·실모델 | 실제 비용 Hard Cap 승인/Provider Attempt·Usage·Receipt 대사·Worker-only key 미확인. 실모델 E2E **0/6** | PM Finance 비용·실제 6 Job 승인을 별도로 수령, unknown/failed 자동 재호출 금지 |
| 팀 UAT | 팀 실 Tailscale Serve와 모바일·재접속·실물 광고·권한 차단 실증 미수행 | 실제 동일 고정 배포 SHA에서 팀 UAT 및 C-A 차등감사 |

**Owner/FE/PM 간 실제 결정 요청서:** `docs/integration/BP18_A51F_OWNER_PM_ACTUAL_BETA_DECISION_AND_SIGNING_REQUEST_20261111.md`. **작성 완료, 전송/서명 증빙 없음.** 기존 2생성 방식·3비율·단일 시안 정책은 재승인 요청하지 않음.

## 3. 개발자 검증 증거와 재현 방법

- Python 전체 **1,374/1,374 PASS** (환경 글꼴은 `IT_TEM_KOREAN_FONT=/System/Library/Fonts/Supplemental/AppleGothic.ttf`, 네트워크/과금 없음).
- 신규 A51F dual-signed source rights 및 release gate 표적 **41/41 PASS**. 실제 Ed25519 서명 알고리즘을 사용했으나 **키·서명은 테스트 전용 임시 인격/라이선스**. 28종 위변조/만료/원본 변경/타 Actor/Provider 변경/키 교환, 미승인 root 및 다른 Mode/Ratio를 차단. 테스트 통과가 실제 사람 승인 아님.
- React **61/61**, Lint·Build PASS. 변경된 FE 실행 소스 없으며 기존 C-A51E Chrome 10단계와 6개 synthetic API 조합 수용을 유지. 이번에 기존 React Chrome 전체를 다시 열어 권리 승인을 가장하지 않았음.
- C-A의 GCP A 읽기 전용 JSON: `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/evidence/C_A51E_20261111_0900/C_A51E_GCP_READONLY_LEDGER.json`. 현행 old GCP Source SHA/Owner attempt ledger absent를 다시 **문서 기반** 비교. 이번 A5-1F에서 새로운 GCP SSH 수행·원격 변경은 없음.
- 권리 검증 테스트: `tests/demo_live/test_a51f_signed_source_rights_authority.py`.
- GCP 독립 운영 준비 진단 테스트: `tests/demo_live/test_a51f_readonly_beta_release_gate.py`.
- 원장 사전 배포 진단 진입점: `python3 -B scripts/a51f_real_beta_readonly_release_gate.py --gcp-readonly-evidence <C_A51E_GCP_READONLY_LEDGER.json>`.
- 증거: `docs/integration/evidence/A51F_20261111` (별도 SHA256 Manifest, raw 고객 이미지/실제 HMAC·PM 키 없음).

## 4. C-A 감사 요청과 실제 GO/HOLD

C-A는 이전 A5-1E 1333회/61회 무과금 전체 기능을 재개발하거나 재평가할 필요가 없음. 이번 범위만 차등 감사:
- 5개 신규·수정 소스/테스트, 특히 Worker 권리 확인 단계가 원본 실 bytes와 두 서명에 결속되는지, 테스트용 합성 서명이 실제 사용권으로 오인되지 않는지, 기존 유료 fail closed가 풀리지 않았는지.
- 출처 SHA·원장 상태·현재 GCP 소스 불일치·Owner DB 누락을 read-only gate가 HOLD 처리하고 과금 승인으로 상승시키지 않는지.
- 실제 A5-1F는 아직 운영 배포된 Signed Beta Runtime이 **아님**. 서명권한, 마스크, 6조합 실제 Model Job, 팀 UAT, rollback은 모두 후속 **미완료**.

**판정 (개발자만):** `A51F_DUAL_SIGNED_SOURCE_RIGHTS_GUARD_DEVELOPER_PASS / C_A51F_DIFFERENTIAL_AUDIT_PENDING / SOURCE_AND_COST_GUARDS_PRESERVED / REAL_OWNER_PM_APPROVAL_PENDING / GCP_A_DEPLOYMENT_HOLD / REAL_PROVIDER_E2E_0_OF_6 / FULL_FEATURE_BETA_DELIVERY_HOLD / COMMERCIAL_RELEASE_READY=NO`.
