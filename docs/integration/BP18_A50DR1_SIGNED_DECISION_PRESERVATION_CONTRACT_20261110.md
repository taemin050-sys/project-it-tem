# IT-TEM P03 A5-0D-R1 — 승인 원장 보존 및 Draft 재생성 안전 계약

2026-11-10 KST | `A50D_P1_01_GENERATOR_CLOBBER_REPAIRED_DEV_TEST_ONLY / SIGNED_LEDGER_NOT_INITIALIZED / OWNER_PM_SIGNOFFS_0`

## 1. 감사·결함 고정점

C-A5-0D 보고서 `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/audit/track-a/IT_TEM_P03_C_A50D_OWNER_PM_DECISION_READINESS_INDEPENDENT_AUDIT_20261110.md`, SHA-256 `6c8a8484cc5ab6ef8cf6bb2c78fd994e717be00ac4df931ff53cd1e7fc0bf475`. 기준 HEAD `9ccd8d95aa3d33cde00b166e25ba494e34e75bb6`.

- `A50D-P1-01`: 기존 생성기가 신규 unsigned CSV/JSON을 `docs/integration/` 정본에 덮어쓰면서, 미래 Owner/PM 승인·서명·Epoch가 사라질 수 있었음.
- `A50D-P2-02`: 외부 `--out` 호출에서 BASE-relative 문자열 출력 오류 및 공식 docs 암묵적 갱신.
- 현재 실제 승인 서명 **0건**, 기존 승인 손실 실사례 **없음**. C-A의 가상 서명 실험은 격리 Git Archive에서만 수행됨.

## 2. R1 실제 코드 수정 (제품 Runtime과 무관)

`scripts/a50d_owner_pm_decision_preflight.py`는 다음 세 Draft 파일을 **오직 명시한 `--out` 디렉터리 내부**에만 생성한다. 기존 동일 이름의 공식 `docs/integration/` 파일, 실제 승인·원장/서명 디렉터리, 혹은 ZIP에 자동으로 쓰지 않는다.

1. `A50D_GEOMETRY_AND_DECISION_PREFLIGHT.json`
2. `BP18_A50D_PROFILE_V3_REVIEW_ONLY_CONTRACT_20261110.json`
3. `BP18_A50D_OWNER_PM_DECISION_REGISTER_20261110.csv`

- 출력 대상 세 파일 중 **하나라도 이미 존재**하면 사전 검사에서 거부하고 기존 바이트를 변경하지 않는다. 심볼릭 링크 파일도 거부.
- 작성에 `O_CREAT|O_EXCL` 및 가능 시 `O_NOFOLLOW` 사용. 동시 생성 중 대상 선점도 거부. 생성 도중 실패하면 **해당 실행이 새로 만든 Draft만** 정리.
- 외부 감사 디렉터리 허용, macOS `/var` → `/private/var` 경로 별칭 정규화. 임시 감사 Dir는 호출자가 소유·격리된 경로여야 한다. `--out`은 서명 원장이 아니며 승인 상태를 저장하는 옵션도 아니다.
- 기존 `IT_TEM_P03_A50D_OWNER_PM_REVIEW_ONLY_20261110.zip` **바이트 불변** (SHA-256 `fb8fb89a76a675b994aba9b62d4229a8ff715747b18486c998ea9ab41ef07eff`). 기존 `scripts/a50d_make_owner_pm_review_zip.py`는 ZIP 목적지가 존재하면 이미 덮어쓰지 않으며, 신규 Reflow 패키지는 새 이름/버전으로만 만든다.

## 3. 미래 승인 원장 v1 설계 (미구현 — 결정/서명 수집 금지)

**정본 Draft CSV/JSON을 서명 원장으로 사용하지 않는다.** 정식 승인 프로세스는 PM/Owner의 실제 승인행위가 제출·검증된 이후 별도 권한을 가진 기록 서비스/도구와 immutable 저장소로 연결한다. 현 단계에서는 스키마와 무결성 요구만 확정 제안하고, 실제 승인 원장 생성이나 임의 서명은 하지 않는다.

권고 레코드의 필수 필드:

```json
{
  "schema_version": "decision-event-v1",
  "decision_id": "D50-02",
  "event_version": 1,
  "previous_event_sha256": null,
  "event_type": "APPROVE|REJECT|REQUEST_REVISION|SUPERSEDE",
  "actor_role": "Image Owner|PM|Legal|Serving",
  "actor_identity_ref": "AUTHENTICATED_EXTERNAL_REF",
  "approved_at_utc": "RFC3339_UTC",
  "decision_evidence_sha256": "64-hex",
  "selected_mock_sha256": "64-hex_or_null",
  "profile_json_sha256": "64-hex_or_null",
  "font_file_sha256": "64-hex_or_null",
  "font_license_evidence_sha256": "64-hex_or_null",
  "effective_policy_epoch": "versioned_epoch_or_null",
  "source_owner_commit": "40-hex_or_null",
  "review_rationale": "Nonempty string",
  "signer_authentication_proof_ref": "external_reviewed_signature"
}
```

- 실제 서명/인증 증명은 **이벤트 JSON 내부에 이름만 적었다고 유효하지 않음**. 서명 제공자 인증, 역할 권한 검증 및 서명 시각·원본 연결을 외부 증거로 확인해야 한다.
- 저장 시 이벤트의 canonical JSON 바이트 SHA256을 계산하고 이전 이벤트 SHA를 연결하여 **append-only version chain**으로 기록. 기존 이벤트 수정·제거 금지, 수정 결정은 명시적 `SUPERSEDE`로 새 버전을 추가하고 이전 상태/서명·사유 모두 보존.
- 내용 검증은 `event_version` 연속, `previous_event_sha256` 이전 해시 일치, evidence SHA/프로필 SHA/Font License SHA/Policy Epoch 고정, 승인 역할 2인(Owner+PM) 각각 독립 인증, 동일 프로필 양측 SHA 합치 여부를 확인. 결손/혼선은 반드시 HOLD.
- 저장소 레벨 버전 관리/WORM 또는 쓰기 차단/서버 시각 감사 로그 + 배타적 CAS 권한은 추후 Owner/PM·PM/Infra 공동 지정. **Git SHA 체인만으로 인증 또는 위변조 방지 보장이 완성되는 것은 아님**.
- 테스트에서 쓰는 `TEST_OWNER_SIGNATURE_ONLY`, `TEST_PM_SIGNATURE_ONLY` 문자열은 가상 Fixture이며 실제 서명으로 사용하지 않는다.
- 현 코드의 `a5_1_implementation_authorized=false`는 승인 프로세스와 무관하게 유지. 실제 승인·계약 해시 확인 후 **별도 후속 구현 승인이 있어야만** Runtime 수정 가능.

## 4. 격리 Git Archive 부정 시험 및 수용 범위

`tests/product_e2e/test_a50dr1_approval_record_protection.py`는 기존 HEAD `9ccd8d9...`에 대한 실제 `git archive`를 파싱해 필요한 파일을 격리 추출한 뒤 **테스트 대상인 R1 생성기만 해당 복제본에 넣는다**.

- **P1 최초 결함 재검증:** Archive의 CSV/JSON에 테스트 Owner/PM Approval, Profile SHA, Epoch 삽입 → 외부 `--out` 재생성 → 가상 서명 레코드 byte/SHA **동일**.
- 기존 승인 파일이 있는 경로를 출력으로 지정 → **거부/바이트 보존**, 생성 전 기존 Destination 하나라도 존재하면 일괄 거부.
- 외부 감사 경로 `--out` → 3개 **unsigned** Draft 생성, 공식 레코드 변경 0건; 같은 경로 재실행은 덮어쓰기 거부.
- symlink 목적지 거부, 기존 A50D ZIP SHA 동일, 운영 원본 A/B/DB/GCP 변경 0.
- C 독립감사에서는 원본 C 스크립트를 변경하지 말고 **기존의 취약 동작이 더는 발생하지 않는 것**과 새 부정 테스트 PASS를 함께 확인할 것.

## 5. 운영 게이트

`OWNER_PM_SIGNOFF_PENDING / SIGNED_DECISION_LEDGER_NOT_INITIALIZED / A5_1_IMPLEMENTATION_HOLD / A41_PRODUCT_CTA_01_HOLD / GCP_A_QA_DEPLOYMENT_HOLD / A_GCP_PAID_WORKER_HOLD / NOT_RELEASE_READY`.

R1을 기술 수용받아도 실제 Owner/PM 서명이 자동 생성되지 않으며, 제품의 CTA P1을 수정했다고 주장하지 않는다.
