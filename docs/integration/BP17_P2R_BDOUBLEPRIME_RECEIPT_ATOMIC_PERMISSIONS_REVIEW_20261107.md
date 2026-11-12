# IT-TEM BP17-P2-R — B″ 추가 감사 지적 01~04 보완 증거

2026-11-07 KST · 구현 A′ · 기존 BP17-F/P2 조건부 수용 유지, 최종 광고 출시 준비 승인 아님.

## Scope/동결
기준 부모 HEAD `79c2fef548e95db50b34d5e85a4a0e27f63ea113`, Tree `43dd6c32defbcb100add8947397af868e603738f`.
Official `dev` `9f798169110e0bb6807c15347444f7c31ad05bae`; Image Owner PR#24 `b3ee33f...` OPEN, FE Owner #26 `c9c204b...` OPEN, Text #25 MERGED; 신규 Owner 계약 미접수.
변경은 비서빙 Offline P2 exporter, 예외/경합 Unit tests, Serving Offline Revision matrix tests, 운영/Owner 결정 문서만. 실제 Owner Model API/Prompt, Runtime Server, Live, 완료 광고 Artifact/Approval SHA를 변경하지 않음.

## BPP2-P2-01 — Manifest/Receipt Fail Closed

- **현재 지원하는 공유 광고는 기존 Composed Completed LIVE 5건**이며, 이 표본에는 모든 `live_compose_manifests` 행과 `outputs/<job>/receipt.json`이 있다. 기존 5/5 전부 Receipt SHA 일치. 추가로 DB receipt_json SHA=DB Receipt SHA=별도 receipt.json 파일 SHA, DB envelope_json SHA=envelope_sha도 5/5 검증했다.
- 예전 `if manifest:`는 없는 행을 묵인했으나, 이제 Manifest 없으면 `SHARED_RECEIPT_MANIFEST_MISSING`으로 중단한다. Receipt 부재/변조/Manifest SHA 불일치 시 `SHARED_RECEIPT_MANIFEST_MISMATCH`로 Fail Closed.
- 작업 Scope는 **광고 검토를 위한 원본 공유 객체의 최소 파생본**이다. 아직 공식 증거 계약이 확인되지 않은 미래 Freeform 방식에서 유예 또는 예외를 발명하지 않는다. 이후 Owner가 generation_mode별 승인 Receipt/Provenance 버전과 정확한 SHA 검증을 정하면 해당 계약을 versioned 경계로 차등 확장.
- 음성 테스트: Manifest 누락, Receipt 없거나 변조, DB receipt_json·envelope_sha 변조, Receipt SHA 불일치, Job-vs-Share SHA 불일치, 미완료 Job, Actor 불일치, PNG 변조, 소스 Symlink, 기존 결과 수정 방지. 외부 청구/유료 호출 0.

## BPP2-P2-02 — 원자적 No-Replace

- `os.rename(tmp,dest)`는 제거. 새 `_publish_no_replace`에서 같은 Parent DirFD를 사용하고 Linux `renameat2(RENAME_NOREPLACE)` 또는 macOS `renameatx_np(RENAME_EXCL)` 플랫폼 제공 연산으로 원자적 Commit. 알 수 없는 OS/파일시스템에서 **성공한 척 Fallback 하지 않음**.
- 실제 Mac multiprocessing 동시 **2 프로세스 경합**: 정확히 1개 `PUBLISHED`, 다른 하나 `EXISTS`, 최종 Manifest/PNG SHA 일치, 임시 디렉터리 0. 기존 유효 결과가 경쟁 중 도착하는 테스트에서 Sentinel SHA 보존.
- Linux GCP 별도 `/tmp/ittem-p2r-linux-race-*`에 2프로세스 `renameat2` 동시 게시와 Nonreplace 기존 Sentinel 보존 **PASS**. 새로운 파일 포맷/네트워크/유료 모델 호출 없음.
- 강제 Prepublish fault에서는 기존 대상 미생성, Temporary 디렉터리 즉시 삭제, 이후 재실행 PASS. Destination Symlink/소스 Symlink/기존 Directory 방어. 디렉터리 Parent 자체가 공격자에 의해 동시 rename되는 경우 추가 환경 통제 위험은 별도; 기존 격리 Parent와 Source를 운영자의 소유·허용 경로로 제한한다.

## BPP2-P2-03 — QA Permissions 실제 영향 분석 (무변경)

GCP `/home/macstudio/ittem-bp17-final-qa-20261107`, Ubuntu, 18095, Service UID:GID `1007:1008 macstudio:macstudio`. 실제 `namei -l`:
- `/home` mode0755; `/home/macstudio` mode0750; QA root **0775**, QA `runtime` **0775**, `runtime/live` **0700**.
- `runtime/demo.sqlite3` **0644**, `config/invites.sha256.json` **0600**, Minimal projection **0700**. 서버 프로세스 `macstudio:macstudio`로 동작, port `127.0.0.1:18095`에만 Bind.
- CLI 셸 umask **0002** 확인; 서비스 프로세스의 umask와 완전히 일치한다고 단정하지 않음. `getfacl` 도구 미설치 → 별도 확장 ACL 부재를 명시적으로 입증하지 못함. POSIX mode와 상위 디렉터리만 확인.
- 따라서 `0644`라는 개별 파일 Mode가 즉시 네트워크 공개 또는 익명 사용자 읽기 권한을 뜻하지 않는다. 상위 `/home/macstudio` 0750이 기본 외부 traversal을 제한. 단, 같은 OS group `macstudio` 및 권한 있는 시스템 계정의 접근 여지는 남으므로 **서비스 팀원·UID/GID·ACL/Cloud VM 백업 권한까지 감사 필요**.
- 권고(아직 적용하지 않음): 별도 스테이징 QA 복제에서 QA ROOT/runtime **0700**, demo.sqlite3 **0600**, 신규 생성 umask **0077**, 로그인/세션/Chrome E2E 401/404/승인/원장 재생 영향 검증. 적법한 동시 운영 프로세스가 동일 UID인지, group dependency 있는지 판단 후 B″/PM 별도 변경 승인.
- 기존 GCP Live/QA chmod, process restart, User/group 변경 **전혀 없음**.

## BPP2-P2-04 — 보존·정리 정책

- 기존 `BP17_P2_QA_DATA_MINIMIZATION_RETENTION_20261107.md`의 **2026-11-14 18:00, 2026-11-21 18:00 KST는 재검토 제안일**일 뿐 삭제일이 아니다.
- 기존 Full Mirror에 제품/리서치 JSON 보존 중. 새 Minimal은 오프라인 이미지/Caption/SHA 검증용 비서빙 파생본이며 인증된 공유 API 대체 불가. 광고 자체에도 브랜드/카피 등 내부 자료가 있으므로 외부 공개 금지.
- 명시적으로 PM/운영 담당자/독립 B″ 감사가 승인하고 재현성/백업/로그/법적 보존 영향을 확인하기 전 원장·QA DB 삭제, SQL NULL, 자동 Retention Scheduler 설정 **금지**.
- 새로운 P2R GCP `/home/macstudio/ittem-bp17-published-minimal-r2-20261107` 생성, 5개 Published 광고 최종 PNG/Caption SHA 원본과 동일. Manifest SHA256 `75d60ca476fb3aa0a9e147f9dc9dd51d38b6a3ddb434d8956e85da3902f8a25c`. 기존 `ittem-bp17-published-minimal-20261107` 및 Full Mirror 변경 없음.

## 효율화 및 증거

- 소규모 경계 검증: `tests/demo_live/test_bp17_shared_minimal_export.py` **14/14 PASS**; macOS Race+Linux Rename/실제 GCP 5건 별도 재현.
- `tests/demo_live/test_bp17_revision_binding_matrix.py` 6개 상황 **6/6 PASS** (실제 지원 범위 한정; 상세는 별도 matrix 문서). P2R 작은 변경만을 이유로 기존 903 전체 Python/52 FE/Chrome 35를 매 단계 재실행하지 않음. Owner 소스 통합 후 새 통합 후보에서 전체 회귀.
- **명시적 미해결**: 같은 Copy/Report이지만 새 정책 version만 바뀌는 경우의 활성 Review SHA 재결속은 현재 Owner 승인 정책 버전 계약이 없어 **PENDING**. 디자인 v3·실제 Provider 복구도 별도 HOLD.
- B″와 PM에 의해 수용되기 전 자체 개발 검증은 최종 독립 PASS가 아니다.
