# IT-TEM BP17-P2R / B″ P2-05 — Single Parent FD 보완 및 차등 감사 인계

기록일: 2026-11-07 KST. **구현 A′ 내부 검증 완료, B″ 독립 재감사 승인 전 P2-05 OPEN.** 전체 제품 NOT RELEASE READY.

## 1. 작업 범위와 기준

- 기준 HEAD 518ce33f7095cb47456ed85fb5d79c91000f89a5 / Tree 6e3f915f6ae752b88b87bf6945ce2e68e99b2fe8. 이전 BP17-F/P2 조건부 수용 유지.
- 변경 파일은 Offline Export 스크립트, 해당 단위 테스트, 이 문서 **3개뿐**. Text/Image Owner 모델, Serving, Worker, FE, 공식 dev/Owner PR, 18088 Live, 18095 QA 원본은 변경하지 않음.
- 제품·인증 원본을 복제하거나 공개하지 않음. 실증 GCP는 별도의 새 파생 대상만 생성.
- 감사 메타 문서 `/Users/Shared/ittem-bdoubleprime-p2r-metaaudit-20261107/BP17_P2R_META_AUDIT_P205_ENHANCED_DIRECTIVE_20261107.md` 자체 SHA256 PASS 확인.

## 2. 수정 전 독립 재현 두 사례 (격리 Fixture)

- 스크립트 `/Users/Shared/ittem-bp17-p205-evidence-20261107/reproduce_p205_before.py`는 **불변 Git 부모 `518ce33`의 스크립트만 git show로 불러와서**, 현재 체크아웃 HEAD와 관계없이 같은 실험을 반복한다. 실제 GCP/사용자 광고는 절대 사용하지 않음.
- RACE-A 게시 직전 원래 Parent 경로를 실제 Dir로 교체한 뒤 같은 임시 Stage 이름에 위조된 Manifest 배치: **기존 코드가 위조 Manifest를 게시하고 성공 반환, 원래 Stage orphan 1건**.
- RACE-B `tempfile.mkdtemp` 직전 경로 교체: 기존 코드가 `DESTINATION_PARENT_CHANGED_BEFORE_PUBLISH`로 실패하지만 **교체된 Parent에 Staging/임시 이미지/Caption orphan 1건**.
- `BP17_P205_GIT_PINNED_BEFORE_RACE_A_B.log` 증거 보존. 수정 전 성공/실패를 신규 구현 PASS로 오인하지 않음.

## 3. 실제 수정: Single Parent FD Authority

1. 지정된 최종 디렉터리를 canonical parent Path로 한 번 확정한 뒤 Parent FD(`O_DIRECTORY|O_NOFOLLOW`)를 열어 **st_dev/st_ino 및 UID, 그룹·기타 사용자 쓰기 권한 차단** 검사.
2. Stage 생성: `secrets.token_hex(16)`으로 만든 이름에 `os.mkdir(...,dir_fd=pfd)`; `os.open(...,dir_fd=pfd,O_DIRECTORY|O_NOFOLLOW)`; 원래 Stage FD의 device/inode 결속. Path 문자열 기반 `tempfile.mkdtemp` 제거.
3. 내부 `final_ads/JobID/` 디렉터리와 `final.png`, `caption.txt`, `projection_manifest.json`은 단계별 고정 DirFD와 `O_CREAT|O_EXCL|O_NOFOLLOW`로 생성, fd 기반 파일 fsync 및 chmod, 하위 디렉터리 fsync. 사용자 외부 경로의 파생물을 따라가지 않음.
4. 게시: Linux `renameat2(RENAME_NOREPLACE)` 또는 macOS `renameatx_np(RENAME_EXCL)`를 **동일 pfd로 Source/Destination 모두 호출**. 부모 경로 재오픈 제거. Unsupported OS/FS는 Fail Closed.
5. 게시 검증: 원래 Stage FD와 Destination DirFD의 inode 일치, 예상 Manifest SHA와 실제 FD-relative 읽기 SHA 일치, 반환 시점 Parent Path inode 및 최종 Destination inode 일치 점검. **절대경로에서 다른 Manifest를 신뢰해 성공 반환하는 코드 제거.**
6. 실패 정리: 원래 pfd와 stagefd로 자식들을 재귀 열고 검증한 뒤 `unlinkat/rmdirat`에 해당하는 Python `os.unlink/os.rmdir(dir_fd=...)` 사용. `shutil.rmtree(dir_fd)`는 GCP Python에서 미지원이므로 제거. Stage 생성 직후 openat/fchmod 실패 시 빈 Stage 직접 정리하고, 하위 Directory의 fchmod 실패도 Stage FD를 통해 일괄 정리. Stage 객체가 분실되거나 Cleanup이 안전하지 않으면 수동 정합화 오류 반환.
7. 게시 이후 늦은 실패(Parent Path가 바뀜, fsync 실패, Manifest/Identity 불일치)에서는 원래 Published 객체를 **삭제하지 않고** `PUBLISHED_BUT_UNVERIFIED_MANUAL_RECONCILIATION` 오류를 반환. 누구도 성공 판정으로 처리하지 않음.
8. SQLite Source 검사: `Path.resolve().as_uri()+"?mode=ro"`, `uri=True`, 연결 직후 `PRAGMA query_only=ON`, `PRAGMA database_list` 실경로 검사, 원래 DB 미생성/무변경.

**보안 보장의 한계:** 보안 주체는 pfd inode와 원래 Stage inode다. 상위 경로 공격자가 이후 다시 rename하면 함수 반환 뒤 영구적인 경로 안정성은 보장하지 못한다. 당해 Parent의 Group/Other Write는 거부하지만 동일 UID 권한 및 상위 경로의 공격자 Rename 가능성은 VM 파일시스템 관리자의 별도 정책과 접근 제어가 필요하다. macOS fsync/리눅스 fsync와 일반적인 atomic visibility를 제공하되 전원 장애까지 완전한 persistence를 이식성 있게 보장한다고 주장하지 않음(F_FULLFSYNC, 파일시스템 설정, 백업/스냅샷 등 별도 확인 필요).

## 4. R1~R10 시험 결과/근거

| ID | 시험 | 격리 증거 | 구현개발 판정 |
|---|---|---|---|
| R1 | Stage mkdirat 직전 Parent 경로 실제 디렉터리 교체 | `test_p205_r1_swap_before_mkdirat_has_no_external_stage_or_private_orphan` 및 Linux FD 명령 | PASS: 외부 0, 원래 임시 0 |
| R2 | Stage 생성 후 게시 전 Parent 실제 디렉터리 교체 | `test_p205_r2_and_r4_real_parent_swap_fake_same_stage_name_not_published` 및 Linux FD 명령 | PASS: 잘못된 성공·위조 게시 없음 |
| R3 | Publish 성공 직후 반환 전에 Parent 경로 교체 | `test_p205_r3_post_publish_replaced_path_cannot_return_forged_manifest` | PASS: 수동 정합화 오류, 원래 Published 불삭제 |
| R4 | 대체 Parent에 동일 Stage 이름과 위조 Manifest 삽입 | R2 공동 fixture에서 genuine/forged Manifest SHA 별도 비교 | PASS: 위조 산출물 거절 |
| R5 | Parent Symlink 교체 | `test_parent_path_symlink_swap_fails_and_cleans_old_inode_stage` | PASS: 외부 미게시·미삭제 |
| R6 | Parent 경로 실제 Dir 객체 교체 | `test_p205_r6_parent_object_swap_without_symlink_rejected` | PASS: 원본 Stage 정리, no Leak |
| R7 | 두 프로세스 같은 대상 동시 게시 | `test_existing_output_replaced_never_after_concurrent_publication` 및 Linux FD 명령 | PASS: 정확히 1개 게시, 1개 거부 |
| R8 | 기존 게시물·Sentinel 보호 | `test_atomic_exclusive_publish_disallows_existing_nonempty_directory` | PASS: No-Replace, 기존 SHA 보존 |
| R9 | 게시 전 인위적 오류, Stage FD-open 및 Stage/Child Directory fchmod 오류 | `test_fault_injection_pre_publish_keeps_target_absent_and_cleans_temp`, `test_p205_openat_failure_after_mkdirat_removes_empty_stage, test_p205_stage_fchmod_failure_before_return_does_not_orphan, test_p205_nested_directory_fchmod_failure_cleans_complete_stage` | PASS: 유실 0, 재실행 가능 |
| R10 | 실제 GCP 명시적 Share 5건 | 새 nonserving derived directory로 원본 SQLite mode=ro만 사용 | PASS: PNG 5/5·Caption 5/5, 이전 Manifest SHA 정확히 동일 |

- Mac 새 Export 대상 테스트 **23/23 PASS**. BP17 Revision 6/6 + BP14 기존 Mode 7/7 + Provider Recovery 2/2 포함 **전체 관련 회귀 38/38 PASS**. Python compile 및 git diff --check PASS.
- Linux `BP17_P205_FINAL_LINUX_R1_R2_R7.log`: Parent FD Staging Cleanup/경로 바꿔치기/renameat2 2프로세스 경합 모두 PASS. GCP Python이 `shutil.rmtree(dir_fd)`를 지원하지 않아 처음엔 실패했고, FD Recursive Cleanup으로 수정하여 재실행 PASS. **초기 실패 기록을 생략하지 않음.**
- 고정된 최종 스크립트 바이트 SHA (최종 Git Commit 이전 검증): `c998aae90b9c5d537a4ad462a5ea881adfaccd131fdb581cbed5942ab8f4ae56`; Local과 GCP 동일.
- 실제 GCP 파생: `/home/macstudio/ittem-bp17-p205-published-minimal-faultsafe-20261107`, 원본 QA 데이터와 기존 파생물 보호. Manifest SHA256 `75d60ca476fb3aa0a9e147f9dc9dd51d38b6a3ddb434d8956e85da3902f8a25c`, 신규 billable Provider 0, 기존 Share 5건만 오프라인 리뷰용.

## 5. 기존 GCP 사후 불변 점검

읽기 전용 URI+query_only+database_list로 확인:
- GCP Live 18088 BP11 SHA `3bb114359fdd05f8e6365f613e70254465b4e9b1`, 14 Job/9 Completed, 최종 PNG+Caption SHA **18/18 일치**, Queue 42 SUCCEEDED, Provider Attempt 70, BILLING_UNKNOWN 0, Health 200.
- BP17-F GCP QA 18095 SHA `28a0ecc42246b31960ceeb47d68880e1862d086a`, 5 Job Completed, SHA **10/10 일치**, Queue/Provider 0, Health 200.
- 신규 최소 파생본 mode 0700, PNG5/5 Caption5/5, SQLite 0, Provider API 호출 0. 기존 원본 SQLite/오래된 파생물의 삭제/NULL/권한 변경 없음.
- 상세 `/Users/Shared/ittem-bp17-p205-evidence-20261107/BP17_P205_FINAL_GCP_READ_ONLY_INTEGRITY.json`.

## 6. Owner 협업·품질 수용 별도 Gate

Text Owner 김다혜: `IT_TEM_BP17_T_TEXT_OWNER_PACKET_20261107.zip`. Image Owner 박지수와 PM 이태민: `IT_TEM_BP17_V_IMAGE_OWNER_PM_PACKET_20261107.zip`. 둘 다 Mac 보호 폴더 `/Users/Shared/ittem-bp17-owner-approval-packet-20261107`, **PREPARED / DELIVERED 불확인(미전달)**. 승인된 팀 협업 채널에 **실제 ZIP 파일**을 전달하고 Owner 수신을 기록해야 함. 경로만 공유하거나 0700/0600 권한을 완화하는 것은 금지.

Text Owner의 실제 structured `revise_copy` input, 정책 버전-only Review/Approval SHA binding 및 모드별 Art Direction, Image Owner의 approved Production Visual v3 Font/CTA/Profile·PM UAT는 소스 미접수/미승인. BP17-I 차등 통합/Live 유료 실모델 테스트/최종 단일 PR은 HOLD.

### 감사 판정 경계
- B″ 부모: `BP17_P2R_PARTIALLY_ACCEPTED / BPP2R-P2-05_OPEN`.
- A′ 새 HEAD: **P2-05 DEVELOPER_VERIFICATION_PASS / B″ INDEPENDENT_REAUDIT_PENDING**. 감사 승인 전 CLOSED 선언 불가.
- Axis 1 기능·운영: 기존 BP17-F 조건부 수용 유지, 실제 Provider 실패 E2E 대기.
- Axis 2 승인·무결성: 기존 계약 유지, 신규 FD Export 대상 검증 PASS, B″ 차등 재감사·Owner 정책 버전 계약 대기.
- Axis 3 실광고 디자인: **HOLD** (Visual v3 승인·실모델 UAT·상용 폰트·CTA 정책 미완료).
- 전체 제품 `NOT RELEASE READY`, 공식 dev·Owner PR·GCP Live 배포 변경 없음.
