# IT-TEM BP17-P2 — GCP 격리 QA 개인정보·제품 정보 최소화 및 보존·정리 정책(안)

작성 2026-11-07 KST. **B′ 지적사항 후속 개발 검증. 보존 기간은 제안값이며 PM/데이터 관리자 최종 승인 전 자동 삭제 없음.**

## 1. 권한·분류

- 범위: 코드·모델 소유자의 기존 PR과 공식 dev를 변경하지 않고, GCP 과거 실제 사용자 광고 5건을 복사한 QA 공간에만 적용.
- **원본 제품 사진 미복사 ≠ 개인정보/영업정보 0건.** 실제 격리 QA `live.sqlite/live_jobs` 5개 레코드에 `input_json`, `analysis_json`, `research_json`, `research_display_json`, `copy_json`, `compliance_json`, `prompt_json` 등이 남음. 일부 `live_events`, `live_copy_previous`, `live_copy_revision_feedback` 및 인가 테이블·기존 소스 SHA도 검토 대상.
- 등급 Q2(민감한 영업 데이터가 포함된 내부 QA): 기존 18094·18095의 Full history mirror, 기존 2026-11-07 Mac Chrome 원본 PNG/캡션 증거, 제품 시안 패키지. 접근 필요자·목적 제한, 외부 공개/로그 본문 인용 금지.
- 등급 Q1(최종 광고만 남기는 내부 검토 복제): 아래 공개 승인을 받은 5개 최종 PNG·Caption과 Identity SHA 메타데이터만 가진 별도 최소 파생본. **Q1도 고객·브랜드 광고이므로 팀 외부 재공유 금지.**
- GCP Live `/home/macstudio/ittem-owner24-text25-liveqa-20261105` 및 기존 Live 18088, Tailscale 10000/8443은 이 정책의 정리·삭제 대상 **절대 아님**.

## 2. 실제 런타임 검토 — 무엇이 필요한가

| 데이터 | 기존 Serving `/demo/api/live/shared`의 동작상 역할 | 새 비서빙 Minimal Projection |
|---|---|---|
| `shared_live_results` JobID·Actor 권한·Final/Caption SHA·발행일 | 공유 자격 확인과 감사 필수 | 공개 승인된 JobID/SHA/발행일만, Actor 이름 제외 |
| `runtime/demo.sqlite3/jobs` Actor↔JobID | 인증된 공유 권한 확인 필수 | Actor/인증 DB 미포함 |
| `live_jobs`: state, mode, final_sha, caption_sha | Completed/LIVE·공유 원장 일치 확인 필수 | 사전 검증 후 JobID·SHA만, 운영 Job DB 자체 미포함 |
| `live_compose_manifests` 및 receipt.json | 승인 합성 Receipt/Final identity 검사 | Receipt **SHA만** 사전 검증 후 포함; 원문/DB 미포함 |
| 실제 `final.png`·`caption.txt` | 다운로드 바이트·SHA·실제 픽셀 검증 필수 | **두 파일만 복사**, SHA·PNG 픽셀 확인 |
| `input_json,analysis_json,research_json,research_display_json,copy_json,compliance_json,prompt_json` | 과거 완결 Job의 전체 재현/개인 Job 상태 API에는 필요. 단 **최종 광고 오프라인 시각 평가에는 불필요** | **전부 미포함**. Copy/Review/Approval SHA는 검증용 digest만 포함 |
| `live_events,live_copy_previous,live_copy_revision_feedback` | 과거 진단·편집 과정/감사에는 필요. 최종 광고 오프라인 검토에는 불필요 | 미포함 |
| `queue.sqlite,cost.sqlite` | 실제 Provider/운영 장애 분석에는 필요. 최종 PNG 미리보기에는 불필요 | 미포함 |
| 원본 제품 업로드·초대코드·세션 | 개인 Job 회귀에는 일부 필요. 공유된 최종 광고 평가에는 불필요 | **미포함** |

**주의:** 기존 authenticated 공유 API는 `LivePipeline.validate_final_artifacts`, `JobStore.owns`, Manifest 및 인가에 의존한다. **기존 QA DB를 무단 NULL/DELETE하면 원본 SHA·승인 무결성 계약과 재현성이 깨진다.** 최소 파생본은 오프라인 시각 평가/감사에만 사용하며, 기존 공유 API 서비스를 대체하지 않는다.

## 3. 실제 신규 최소 파생본: 생성·검증 완료

- 출처: 승인된 BP17-F `/home/macstudio/ittem-bp17-final-qa-20261107` (GCP 18095). 읽기 전용 SQLite + 승인된 5건의 `LIVE/COMPLETED`, Actor→Job 소유권 및 Published SHA 확인.
- **새 디렉터리:** `/home/macstudio/ittem-bp17-published-minimal-20261107`, mode **0700**, 기존 DB/서비스 코드·ports 변경 없음.
- 출처/허용 경로 고정 추출기: `scripts/bp17_shared_ad_minimal_export.py`. 원본 QA 경로를 allowlist로 제한하고 symlink/기존 결과 덮어쓰기 금지, PIN PNG·Receipt·Caption SHA 검사 후 최종 PNG·Caption·Digest만 저장. 원본 Actor 값·개인정보 본문·DB 파일/Receipt 원문/초대코드 미복사.
- 검증: 실제 5개 명시적 Share, 최종 PNG **5/5 SHA**, Caption **5/5 SHA**, 분포 3:4 ×1·4:5 ×2·9:16 ×2, 미공유 Job 0건, private `*.sqlite*` 0개. GCP 최소 파생본 Manifest SHA256 `75d60ca476fb3aa0a9e147f9dc9dd51d38b6a3ddb434d8956e85da3902f8a25c`.
- 신규 단위 `tests/demo_live/test_bp17_shared_minimal_export.py`: (1) 사적 필드 및 미공유 Job 제외, (2) PNG SHA 변조 시 fail-closed, (3) Share Actor 위조 차단, (4) 소스 allowlist·symlink·덮어쓰기 금지. **4/4 PASS**.
- 재현 증거: `/Users/Shared/ittem-bp17-shared-qa-evidence-20261107/BP17_P2_REAL_GCP_MINIMAL_EXPORT_VERIFY_20261107.json`.
- GCP QA Full Mirror 18094/18095 및 기존 18088 Live 원장은 **한 행도 삭제하거나 NULL 처리하지 않음**. 신규 Paid Provider/Worker 호출 0.

## 4. 보존·정리 시점 제안 — **승인 전 정책 확정 아님**

| 자산 | 보존 목적 | **검토 제안일 (KST)** | 정리 조건 |
|---|---|---|---|
| 역사적 Live BP11 원본 및 공식 Provider/Job/Artifact 원장 | 실서비스·법적 회계·사업 기록 | 본 정책에서 정리 기한 지정하지 않음 | 해당 원본의 독립 운영·보존 정책만 따름 |
| 격리 Full Mirror 18094·18095 + 기존 QA Session DB 및 역사적 사적 JSON | 감사 B′의 35 Chrome 샘플 재현과 내부 오류 조사 | **2026-11-14 18:00** | B′가 SHA·증거 수용 및 재현 불필요를 명시한 후, PM/운영자가 정리 승인. 그 전에는 보존하되 외부 접속 금지 |
| 최소 파생본(광고 최종 PNG·Caption·SHA만) | Visual v3 Owner·PM 시각 검토 | **2026-11-21 18:00** | 시안 검토 완료 및 필요한 영구 증거 SHA 인계 후 담당자 승인 |
| Mac Studio Chrome QA PNG/갤러리/외부 전달 ZIP (내부 공유 광고 이미지 포함) | 화면비 증거·디자인 합의 | **2026-11-21 18:00** | B′·Image Owner·PM 검토 완료 후 접근범위/보존 필요성 재평가 |
| 텍스트 중심 감사 보고서·SHA manifest·문서 테스트 | 장기 추적·재현성 | 프로젝트 종료·정책 재검토 시 | 기밀/토큰/원본 개인정보 없는지 재검수 후 보존 |

**날짜는 삭제 자동 작업이 아니다.** 검토일 전까지 Owner/PM/운영자에게 승인·연장 근거 확인. 미응답이면 무단 삭제 대신 **접근 제한 유지, 정리 대기 기록**으로 남긴다. 영업정보가 담긴 QA가 불필요하게 무기한 유지되지 않게 검토일마다 재승인한다.

## 5. 실제 정리 전 안전 체크

1. 정리 승인자·정본·보존기간 종료·영향 받을 팀원·감사 증거 목록을 기록한다. 실제 Live ROOT를 QA 정리 대상으로 절대 지목하지 않는다.
2. `ss -lnt` 및 PID·SSH tunnel 소유자를 확인하고 해당 **격리 QA** 사용자 검증/Owner 리뷰가 종료됐는지 확인한다. 18094/18095를 현재 검증 중이면 먼저 보존 기간 연장 승인.
3. 원본 Live 18088, Owner PR, Tailscale 상태와 완료 PNG·Caption SHA를 읽기 전용 재확인. Minimal derived Manifest/파일 SHA 기록을 별도 증거 위치에 보존.
4. 한정된 QA ROOT의 이름·realpath·UID·inode·승인한 루트 목록을 사전 검증하고, **실제 삭제 조치는 별도 명시 승인을 받은 후** 독립 실행한다. 범용 `rm -rf`나 소스 임의 NULL 갱신 금지.
5. 클라우드 VM 스냅샷/백업/운영 로그 등 별도 복제본도 민감도·접근 범위·보존 책임자를 확인. 파일 삭제만으로 모든 복제본의 완전 삭제를 주장하지 않는다.
6. 정리 후 실제 Live/추가 QA의 SHA·Health/Provider ledger 불변, 정리 완료 기록 및 잔여 접근권한을 확인한다.

## 6. 상태

`P2_SOURCE_SCHEMA_AND_PRIVACY_CENSUS_COMPLETE` / `P2_NEW_MINIMAL_PROJECTION_REAL_GCP_5_OF_5_PASS` / `P2_RETENTION_PROPOSED_NOT_APPROVED` / `OLD_MIRROR_NOT_DELETED` / `LIVE_IMMUTABLE`.

Owner Text/Visual v3와 PM 제품 승인과 별개로 P2는 최소화 구현/증거를 확보했으나 보존 기한은 별도 승인 필요.
