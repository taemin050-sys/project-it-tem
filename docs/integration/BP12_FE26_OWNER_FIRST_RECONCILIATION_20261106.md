# IT-TEM BP12 — 공식 dev·FE Owner PR #26 차등 통합 및 보호 계약

작성일: 2026-11-06 KST | 구현 A' 단독 검증 | 독립 B'·팀원 UAT 미완료

## 정본 및 범위

- 공식 GitHub `taemin050-sys/project-it-tem`, 기준 `dev@9f798169110e0bb6807c15347444f7c31ad05bae` (FE #22 MERGED).
- BP11 로컬 검증 후보 `3bb114359fdd05f8e6365f613e70254465b4e9b1`, Tree `e5ec3001c98833bc40d349c9593b2a7151d9fd64`.
- FE Owner PR #26 정확한 HEAD `32eb263ab06bd882c3578f34a961593754a6b4dc` (인수 시점 OPEN).
- 새 격리 Worktree: `/Users/Shared/ittem-bp12-dev-fe26-ownerfirst-20261106`; 통합 브랜치 `integration/bp12-dev-fe26-ownerfirst-20261106`.
- 기준 dev와 BP11의 Merge Commit: `f7afe8e`. 이력상 dev/BP11/PR26 원 커밋의 조상을 최종 통합 커밋에서 확인할 것.
- 공식 dev·Owner PR·기존 GCP Live·기존 Job/Artifact/QA 릴리스 **변경 없음**. 배포·유료 Provider 호출 없음.

## 최신 FE #26 소스 수용: Exact 3 / Adapted 9

Git Blob을 실제 FE #26 HEAD와 비교. Exact: `app/src/index.css`, `app/src/pages/LandingPage.tsx`, `app/src/types/textSchema.ts`.

Adapted / 이유:
1. `app/src/api/liveFlow.ts`: BP11의 QA Fixture/Owner A 고정 Layout, 비동기 Text Revision CAS 및 복원 무재호출 경로 유지. PR26의 동등한 수정·복원 동작은 기존 구현에 포함.
2. `app/src/api/liveJobs.ts`: PR26의 ratio 타입과 Live 입력 `image_size` 유지, BP11의 Revision/Restore Fail-Closed·정확한 동기 Restore DTO·QA Fixture 라우팅 유지.
3. `app/src/api/liveMapping.ts`: PR26 `guardCopyRevision` 명칭은 `guardCopyReviewMutation`의 alias로 수용, 승인 가드와 절대 혼동하지 않음. Owner `output_size`는 BP11에서 이미 정확한 서버 응답 기반으로 반영. 실제 Serving DTO `revision_feedback`의 `source`·nullable `note` 보존.
4. `app/src/api/useJob.ts`: FE #26 이어하기 GET-only 캐시 최신화 수용. 원래 BP11 ratio 저장·복구, 수동 시작 확인, Job/Artifact 보존 유지.
5. `app/src/demo/DemoGate.tsx`: Owner #26 `/create` 이어하기 동선 수용, 실제 Tailscale Signed Actor·QA Offline Fixture·권한별 메뉴 보존.
6. `app/src/pages/CopyPage.tsx`: FE #26 수정 요청·되돌리기·Feedback의 의도 수용. BP11의 Generation Fence·Live Snapshot/Job 동기화·Evidence Ack·Compliance 불통과 시 수정 허용/승인 차단·비용 안내·Caption 권장 길이 안내 유지. 변경 필드는 Owner 한국어 라벨로 표시.
7. `app/src/pages/DraftPage.tsx`: FE #26 Mock 전용 이미지 수정 표시 수용. BP11 제품·라벨 수동 검토 경고 추가 유지.
8. `app/src/pages/ExportPage.tsx`: PR26의 Live `output_size` 의도 수용. BP11 서버 Owner Ratio/PNG 무결성 검증, 합성 재시도, 기존 Artifact·Caption 다운로드 보존.
9. `app/tests/liveMapping.test.ts`: FE #26의 Revision Alias 동일성 테스트 추가. BP11 더 강한 실패 검수·CAS·승인 불변식 테스트 유지.

기존 BP11 대비 `src/`, `demo_staging/`, `configs/`, `tests/` 하위 **소스 변경 없음**(합병 전후 git diff 검증). Image #24 자유형·다중 후보 엔진은 소스 그대로 보존하되 A안 FE Batch UI 노출은 추가하지 않음. Text v0.10 기능성 10종·이모티콘 3단계와 3:4·4:5·9:16 합성형 1개 경로 유지.

## 검증 및 안전 게이트

- React node:test 47/47 PASS, oxlint 0 warnings/errors, TypeScript + Vite Build PASS.
- 핵심 무과금 Python 134/134 PASS, 확대 `tests/demo_live tests/image_generation tests/demo_staging tests/test_s4o_text_owner_offline_integration.py` **607/607 PASS** (Python 3.12 격리 venv).
- 최초 새 격리 Python 환경에서 `fontTools` 미설치로 collection 실패. `demo_staging/requirements-live-extra.txt` (`fonttools>=4,<5`), `tests/image_generation/requirements.txt` (`fonttools==4.68.0`) 확인 후 오프라인 캐시 설치, 607/607 PASS. 신규 lock 정책 변경 불필요.
- GCP 18088 Web/Worker/FE 모두 기존 BP11 HEAD/Bundle 동일, MONITOR_ONLY, Unicode16 vendor 유지. 기존 Live·Queue/Provider 모두 읽기 전용으로 검증.
- BP11 After Snapshot의 기존 Job 11건 **154개 DB 필드 불변**, 완료 Job 8건 PNG·Caption **SHA 16건 전부 일치**, Compose Manifest **8건 불변**. 최신 관찰 시 Live Job 14건(완료9), Queue42건 전부 SUCCEEDED, Provider70건 전부 SUCCEEDED_USAGE_UNPRICED, BILLING_UNKNOWN 0.
- Tailnet Live 10000과 과거 QA 8443 HTTP 200. 과거 Chrome Noto Serif KR 및 간헐 Job·Task 502 관찰은 원인/완치 미확정; 별도 P2 조사 필요.

## 게이트 구분 및 남은 항목

**개발자 자체 무과금 검증 PASS**. 아직 BP12 신규 GCP 독립 QA 슬롯 미배포/실제 브라우저 최신 후보 E2E 미수행, 팀원·PM 실기기 UAT 미완료, 독립 감사 B' 미수행, 최종 단일 통합 PR 미게시. BP11 현재 Live 배포를 변경하지 말 것.

다음 순서: 정확한 통합 SHA·Tree와 코드/검증 증거 고정 → 독립 B' 차등 코드 감사 → 기존 Job/Queue/Provider/Artifact preflight 재확인 → GCP **격리 QA 슬롯**에 무과금 Fixture로 해당 SHA만 반영 → 브라우저 데스크톱·모바일 계약·ACL·복구·다운로드 테스트 및 502 진단 → 팀원 실제 UAT → 결함 최소 수정·재검증 → 단일 PM 리뷰용 PR 준비. 기존 GCP Live, 다른 QA, Rollback 및 유료 결과는 그대로 유지.

Owner PR #22 재병합, #24/#26 임의 Merge·Close, #18 선행 병합, 공식 dev 직접 수정, 자동 AI 재호출, 승인·SHA 검증 완화 모두 금지.
