# Track B · C-B 감사의견 반영 점검과 미반영 항목 보완

2026-11-09 KST · `SELF_VALIDATION` · `NOT_RELEASE_READY`

점검 대상은 사용자가 첨부한 C-B 레퍼런스 4/4 추가 시각감사와 공식 `audit/track-b/00_C_B_AUDITOR_CONTACT_AND_CODEX_HANDOFF.md`다. 시작 소스는 `6bc7c7d27346e7c6eb0f5c225f2c657eb2b3f56f`, Tree `e041e493688212dc4a361bfcdbc9d59abbca40a2`, Branch는 `integration/bp18-product-complete-20261111`이다. 시작 당시 CLEAN이었다.

## 이미 반영된 내용

| 감사 항목 | 기존 근거 | 이번 처리 |
|---|---|---|
| 레퍼런스 4/4 원본 확보·직접 열람·SHA | 원본 매니페스트와 C-B 18:41 보고서 | 기존 근거 계승 |
| Bold 우선안과 남색 로고·CTA 연결 | 6bc7c7d의 세 프로파일·시각 비교 | 세 방향 선택지를 유지 |
| Editorial CTA 대비 | 중앙 정렬과 채운 녹색 CTA | 기존 개선 유지 |
| Graphic 큰 네이비 면·`루틴` 단독 줄 | 한 줄 승인 제목과 작은 연두 강조 면 | 기존 개선 유지 |
| 버전형 렌더러·가변 굵기·자간·행간·장평·승인 원문 보존 | 6bc7c7d 구현, 신규 38개 회귀 | 기존 구현을 바탕으로 아래 누락 범위만 보완 |
| F09/F11·Approval·Worker·CostLedger·B5·EX12 | 이전 고정 소스와 실제 B2의 한정 인수 | 관련 코드 계승, 이번 전체 회귀에서 함께 확인 |

## 새로 보완한 내용

**일반적인 긴 한글 제목.** 이전 연구 프로파일은 제목의 최소 크기가 90–128px여서 약 20자의 일상적인 문장도 overflow로 거부했다. 세 프로파일의 제목 최소 크기를 64px로 확대하고 Editorial·Graphic의 두 줄 표시를 허용했다. 한글 단어 경계를 우선해 줄을 나누며 원문 공백까지 보존한다. 단일 단어가 너무 길면 기존 cluster 단위 경계를 적용한다. 너무 긴 문구는 축약·삭제 대신 실패로 처리한다.

단어 경계 로직 변경을 입력 지문에서 구별하도록 활성 렌더러는 `korean-composition-v3`, 연구 프로파일은 `bp18-ad-typography-4x5-v2`로 올렸다. 스타일이 없는 과거 v1은 기존 경로를 사용한다. 기존 승인 입력의 세 PNG와 Caption은 이전 결과와 바이트가 같다. Layout SHA와 Receipt 입력 지문은 새 계약에 맞게 달라진다.

**세 비율 검증.** 합성용 native 입력을 별도로 만든 fixture에서 1080×1440, 1080×1350, 1080×1920을 검증했다. 각 비율에서 Copy·Caption·보호 영역 픽셀과 이미지/플랫폼 CTA 계약을 확인했다. 실제 승인 4:5 제품 사진의 비율을 바꾸지 않았다. 9:16 최종 CTA 정책과 나머지 실제 모델 조합은 별도다.

**Export 하단 가림.** `StepPage`에 `stickyActions` 선택 옵션을 추가하고 Export는 문서 흐름 배치를 사용한다. `.step-actions.in-flow`가 `position: static`으로 표시된다. 이 변경은 최종 결과 화면의 하단 바가 광고와 Caption 위에 겹치는 원인을 제거한다. 세 파일의 작은 수정이며 다운로드·승인·GET 복구 코드를 변경하지 않았다.

## 실제 로컬 브라우저 검증

증거 폴더는 `/Users/Shared/ittem-bp18-codex-evidence-20261109/cb-followup-20261109`다. 실제 React QA 빌드를 Chromium에서 열고 loopback 전용 읽기 전용 fixture 서버로 검증했다. 화면에는 `QA OFFLINE_FIXTURE · 실제 AI 아님`이 표시된다. 이는 GCP Signed Live 여정과 구별한다.

| 실행 범위 | 실제 결과 |
|---|---|
| Bold 데스크톱 1699×1167 | 광고 표시 397×496, 하단 바 static, PNG·Caption 포인터 다운로드 SHA 일치 |
| 세 방향 360×800 | 광고 표시 320×400, 가로 overflow 없음, 상단/광고/본문/하단 스크롤 위치에서 하단 바와 내용·이미지 겹침 없음 |
| 세 방향 390×844 | 광고 표시 350×438, 같은 겹침 검사 통과 |
| 다운로드 | PNG 5건과 Caption 3건의 실제 브라우저 저장 바이트 SHA 일치 |
| 화면 포커스 | Bold 세 viewport에서 Caption 버튼 포커스 확인 |
| 좁아진 세로 공간 | 360×480 viewport에서도 static 배치·가로 overflow 검사 통과. 실제 OS 키보드 검증과 구별 |
| 요청 | 브라우저 요청 trace의 상태 변경 메서드 0건. 시험 서버는 GET/HEAD만 허용 |

대표 파일은 `browser-result.json`, `browser-build-provenance.json`, `bold_type_hero_360_browser.png`, `bold_type_hero_390_browser.png`, `export_actions_360.png`, `local_fixture_banner.png`다. 실제 320px·350px 표시 크기로 시안을 확인했다. 전문 광고 미감과 가독성의 최종 사람 수용은 열려 있다.

## 검증 결과와 산출물 연속성

- 전체 Python **1,102 PASS**, 31.11초. 외부 네트워크 차단·Loopback 허용, Provider 키 제거와 billable flag 비활성 상태에서 실행했다. 로그는 `python-regression.log`다.
- 신규 타이포그래피 표적 **61 PASS**, skip 0. 짧은 문구·승인 문구·일반적인 긴 한글·과도한 장문·원문 경계와 세 native 비율을 포함한다.
- React **53 PASS**, lint 오류·경고 없음, TypeScript와 Vite build 통과. 각각 `react-tests.log`, `react-lint.log`, `react-build.log`에 보존했다.
- 새로운 정상 합성 함수 실행 결과는 하위 `typography-v2/`에 있다. 세 PNG·Caption이 6bc7c7d 결과와 동일하며 근거는 `artifact-continuity.json`이다. 각 Receipt에는 렌더러 v3와 실제 스타일, 적용된 글꼴 축·크기·행과 입력 지문이 있다.
- PNG·Caption·승인 원본·과거 네 레이아웃에 대한 기존 SHA 증거는 보존한다. 기존 참고 이미지와 원본 고객 사진을 공유 감사 폴더로 옮기지 않았다.

## 미검증 항목과 제출

`NOT_VERIFIED`는 실제 모바일 기기의 OS 키보드·업로드부터의 전체 UAT, GCP에서의 새 화면 배포, 새 프로파일의 Signed Live 다운로드, 작은 연청색 라벨 문자, 실제 USD 청구 대사, 남은 다섯 실모델 조합과 Owner·PM 상업적 품질 수용이다. 긴 문구에서 마지막 짧은 단어가 한 행에 남는 미감은 사람 평가가 필요하다. 일반 UAX29 전체 지원을 주장하지 않는다.

이번 단위의 Provider 호출은 0회다. 이전 실모델 1/6과 실제 여섯 Attempt는 과거 증거로 보존한다. 현재 원격 원장·운영 SHA를 새로 조회한 것으로 확대하지 않는다.

C-B 공식 제출은 공유 `audit/track-b/SUBMISSION_B_CODEX_*.md` 파일로 수행한다. 파일 작성은 자동 알림을 발생시키지 않으며 사용자가 C-B 대화에 제출 경로를 전달해야 한다. 이 문서는 B 자체 검증 보고이며 C 독립 PASS를 나타내지 않는다.
