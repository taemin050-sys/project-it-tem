# IT-TEM BP17-F — 실제 공유 광고 브라우저 검증 및 재생성 장애 복구 안전성
**작성 2026-11-07 KST. 구현 A′. 독립 감사 B′ 재검증 및 Owner·PM 최종 수용 전 단계.**

## 1. 정본/분기
- 출발점 BP16 `59275c5b5557278a8d6f76f1476067eb1f5758e8` / Tree `41a0899a352b1a3f7e7212fd9e2e2974107eae7f` / CLEAN.
- Official GitHub `dev` `9f798169110e0bb6807c15347444f7c31ad05bae` 확인. FE #26 OPEN `c9c204b88af5ce1b25dfda501d16446750a41204`, Image #24 OPEN `b3ee33fd524fbbb83890472be890c96974160e9c`, Text #25 MERGED. Legacy Integration #18 OPEN.
- Owner Source First. 이번 단위 **실행 경로/FE/Text/Image 엔진 변경 0건**. 외부 Text Owner 실제 입력 및 Image v3 Production DesignProfile은 별도 Owner 승인 전까지 변경 금지.
- BP17-F 신규 변경은 읽기 전용 운영 runbook + 장애 재발 방지 Python 테스트 + 감사 계약 문서. 공식 dev/Owner PR/GCP Live 직접 변경 없음.

## 2. 왜 이 별도 실험이 필요한가
B′는 BP16 UI 화면비 Chrome 시험의 공유 목록이 Stub/Mock이고 실제 PNG 크기 확인이 Python 별도 시험이라는 격차를 지적했다. 따라서 **실제 과거 완료·명시적 공유된 AI 광고**를 GCP에서 샘플로 취하고, 새로운 유료 Provider 호출 없이 같은 인증 세션에서 공유 목록·실제 PNG/Caption·화면비·Actor ACL을 끝까지 검증했다.

## 3. 과거 실모델 완료 광고 5건의 격리 Mirror

- GCP 원본: `/home/macstudio/ittem-owner24-text25-liveqa-20261105` BP11, `127.0.0.1:18088`; **READ ONLY SOURCE**, 현재 14 Job(9 COMPLETED), 5 Explicitly Shared.
- 완전히 독립된 GCP `/home/macstudio/ittem-bp17-shared-history-qa-20261107`, **loopback 127.0.0.1:18094**, Mac SSH tunnel `127.0.0.1:18904`. Repo/FE **BP16 SHA 59275c5**, Tree 41a0899, previously independently verified Vite QA bundle e53e91de... 동일.
- 원본 DB는 SQLite **readonly connection + backup**으로 일관된 스냅샷을 생성, Mirror 안에서는 비공개 Job을 필터링·VACUUM. 사용자 원본 사진과 미공유 광고 이미지는 복제하지 않음. 다만 내부 DB row에는 공유 완료 Job의 과거 입력·검수 메타데이터가 일부 존재하므로 mirror root 접근권한 0700, 네트워크 loopback만 허용. 원본에는 어떤 쓰기도 수행하지 않음.
- 공유 완료 5건의 PNG+Caption 바이트 및 필요한 Composition Receipt만 복제. 5개 명시적 Share의 Actor·JobID를 정확한 로컬 평가 Ledger에 가져와 공개된 공유 기능을 사용했고, 그 외 Job Ownership은 이전하지 않음. Mirror QA 리뷰 DB는 **독립 사본으로 생성**(원본 사용자 세션/토큰 미복사). 파일 SHA 및 원본 공유 Ledger가 결속됨.
- 별도 `audit/history_mirror_provenance.json`에 5건의 실제 파일 SHA·픽셀 크기·source JobID, 원본/사본 위치·수집시각·모델 호출0을 기록. SHA256 `95805108d2331b608788390bcfa07286e01313bb735ab93058b587762f31e821`. Mac에서도 제한권한 copy.
- QA 환경은 `IT_TEM_LIVE_ENABLED=NO`, `IT_TEM_LIVE_EXECUTION_APPROVED=NO`, `IT_TEM_LIVE_WEB_QUEUE_ENABLED=NO`, `IT_TEM_QA_FIXTURE_ENABLED=NO`; Provider keys 없음, Worker 없음. **원본 광고의 실제 `mode=LIVE` 상태는 변경하지 않음.** 신규 이미지 생성은 절대 불가. Mirror 서비스 자체는 로그인/평가 API를 가진 독립 개발 서버이며 OS 수준 모든 API가 read-only인 것은 아니지만, 이번 Chrome 스크립트는 로그인 외 실제 작업 쓰기 요청 0건.

### 실제 공유된 최종 PNG 크기
| 화면비 | 공유 건수 | 실제 최종 PNG | 출처 |
|---|---:|---:|---|
| 3:4 | 1 | 1080×1440 | BP11 원본 Live SHA 검증 |
| 4:5 | 2 | 1080×1350 | BP11 원본 Live SHA 검증 |
| 9:16 | 2 | 1080×1920 | BP11 원본 Live SHA 검증 |

## 4. Google Chrome 실 API·파일 통합 회귀: **35/35 PASS**

- Browser Chromium channel='chrome' 실제 Google Chrome, 데스크톱1440×900 + 모바일390×844. **네트워크 응답 Mock 0건**. `/demo/api/live/shared` 실제 서버 GET, 공유 광고 선택, 최종 이미지 실제 다운로드 GET, Caption GET, 브라우저 naturalWidth/naturalHeight 및 화면비 표시/DOM·CSS 검증.
- 인증 전 공유 GET 401; 인증 후 5건 목록 200, SHA 검증된 `dimensions_source=VERIFIED_FINAL_PNG` 전부 일치.
- 각 비율(3:4/4:5/9:16)의 UI 텍스트·이미지 픽셀·실제 PNG SHA·**Caption SHA**와 **GCP 원본 명시적 공유 Ledger**까지 결속, 총 3개 독립 브라우저 샘플+5개 공유 목록.
- 타 Actor의 개인 Job GET은 **404**, 공개된 최종 Artifacts는 명시적 공유 범위 안에서만 접근 가능; 익명 공유 Final GET은 401.
- 페이지 새로고침은 GET-only, 모바일 9:16 표시 PASS; 자동 생성·이미지 승인·재생성 POST **0건**.
- QA 스크립트/JSON/Chrome Screenshot/PNG proof: `/Users/Shared/ittem-bp17-shared-qa-evidence-20261107/` 안의 `qa_bp17_actual_published_chrome.py`, `BP17_REAL_SHARED_CHROME_E2E.json`, `BP17_REAL_SHARED_BROWSER.log`, `BP17_REAL_SHARED_*_CHROME.png`, `BP17_REAL_SHARED_9_16_MOBILE.png`, `BP17_MIRROR_SOURCE_PROVENANCE.json`.
- **수용 범위:** 역사적 실모델 광고의 유효한 공개 API/브라우저 표시. 신규 BP17 AI 이미지 생성, 현재 Tailnet SSO, 실제 Provider Worker 중단 검증은 아님.

## 5. Provider/Queue 중단·중복 과금 방지

- 기존 BP15 `scripts/bp13_image_recovery_audit_readonly.py`와 `test_bp13_retry_failure_injection.py`, `test_bp13_recovery_inspector.py`, `test_queue.py`, `test_worker_guard.py` 재사용.
- 신규 `tests/demo_live/test_bp17_no_replay_operational_recovery.py` 2건: 재생성 Queue RUNNING 상태에서 Worker 프로세스 재시작을 **시뮬레이션**해 `BILLING_UNKNOWN` 전환·동일 RequestKey replay 차단·AttemptID/승인 SHA 불변·read-only inspector HOLD 확인; state commit 후 enqueue 전 Orphan Attempt가 새 유료 Attempt로 바뀌지 않음을 확인. 관련 선행 장애 회귀 포함 **14/14 PASS**.
- 운영 Runbook `docs/integration/BP17_IMAGE_RETRY_UNKNOWN_RECOVERY_RUNBOOK_20261107.md` 작성. Snapshot/read-only audit/Provider RequestID·Receipt·usage 교차 검증, Queue/DB/Artifact 실패점별 Fail Closed, 정합화 요청서 증거 필드 정의. 범용 UPDATE SQL이나 재시도 명령 제공 안 함.
- **실제 유료 Provider 중단·청구 Unknown Invoice 조회 실험은 수행하지 않음.** 중복 과금 방지 회귀만 검증, 비용 청구 확정/복구 최종 PASS는 아님.

## 6. 최신 회귀
- 전체 Python `899/899 PASS` (BP16 897에서 2건 신규).
- FE Node `52/52 PASS`; Oxlint 오류/경고0; TS/Vite build PASS; `git diff --check` PASS.
- 신규 유료 호출 **0**, 기존 Live Provider Attempt **70**, Queue **42 SUCCEEDED**, BILLING_UNKNOWN **0** 유지. 기존 Live 9개 COMPLETED Final PNG/Caption SHA **18/18 PASS**. Mirror 완료 5건 Final PNG/Caption **10/10 PASS**, Mirror Queue0/Provider0, Health 200.
- QA port 18094만 새로 사용. 기존 18088/18089/18090/18091/18092/18093과 Tailscale 10000/8443를 건드리지 않음.

## 7. 미해결 의사결정 (임의 PASS 금지)
1. **Track T:** Text Owner 김다혜님의 새 `revise_copy` 실제 검수 컨텍스트 입력 버전 및 이미지 Art Direction Owner SHA 필요. 현재 Serving Preflight는 원본 Owner 모델 수용과 다르며 대체 불가.
2. **Track V:** Image Owner 박지수님과 PM 이태민님의 신설 Typography·CTA·Font license·Contrast·protected product+label DesignProfile SHA 승인 필요. A/B/C 12개는 오프라인 비교 시안일 뿐 신규 제품 배포 Layout이 아님. 9:16 CTA 미정.
3. **Track E/U:** 승인이 끝난 후 실제 화장품 원본으로 자유형/합성형 한글·라벨·광고 콘셉트 E2E와 팀원/PM 사람 검수 필요.
4. **P2:** Genuine iPhone-created MPO 원본 파일 미확보; Tailscale 장기 HTTP502 원인 재현 미완료.
5. **최종 감사 B′와 PM:** 기능/보안/시각 3축 각각 독립 수용 후 단일 PR·Live 릴리스 승인 가능. 지금은 `LIVE_RELEASE_HOLD / PR_HOLD`.

**상태:** `BP17_F_REAL_SHARED_UNMOCKED_CHROME_PASS / BP17_F_RESTART_NO_REPLAY_FIXTURE_PASS / TRACK_T_PENDING / TRACK_V_PENDING / REAL_PROVIDER_E2E_PENDING / FINAL_PR_AND_LIVE_HOLD`.
