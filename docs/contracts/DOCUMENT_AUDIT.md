# IT-TEM 계약·파트별 배포 문서 전면 감사 (2026-10-27)

> **대상:** PR #4의 2026-10-26 회의 반영 docs-only 문서. 이 감사는 문서·회의 스키마 정합성 검사이며 Live/Browser E2E 증거가 아니다.

## 1. 지적 사항과 교정 결과

| 기존 결함 | 교정 조치 | 근거·남은 한계 |
|---|---|---|
| v0.2 81줄로 축약되어 v0.1 241줄의 계약 상세 누락 | interface_spec를 9개 대영역, 약 400줄로 복원·확장 | 구형 13 API·Job/Artifact·9 status·7 DTO·오류/비용/QA 반영 |
| 긴 산문 중심, 표·시각화 부족 | 공통 및 역할별 문서에 데이터 표/흐름도·Mermaid/예제·체크리스트 반영 | Mermaid 렌더링은 GitHub 미리보기 추가 확인 필요 |
| 기존 구현/회의 합의/새 제안의 구분 불명확 | LEGACY-IMPLEMENTED / INTERNAL-READY / DECIDED TO-IMPLEMENT / EXPERIMENT·DEFER 분리 | origin/dev는 P1만, f979331은 feature 구현 |
| 텍스트 v0.5 스키마 vs legacy DTO/HTTP 혼동 | 개별 필드별 무손실 매핑·출처/Compliance 예시·타입 주의사항 | 실제 텍스트팀 repo path/SHA 재확인 필요 |
| 중복·모호한 담당자 문서 | 공통 4종→해당 담당 1종 읽기 구조, 각자의 I/O·실패·인수 증빙 중심 | 계약 의미는 interface_spec 단일 SSOT |
| Markdown 가독성 | 표 헤더/범위 en dash/코드펜스·상대 링크 정리, PR 설명은 줄바꿈 교정 | GitHub 렌더 확인은 사람의 시각 QA 권장 |

## 2. 문서별 개정/독립 감사

| 파일 | 이번 재검토에서 보완한 핵심 |
|---|---|
| docs/interface_spec.md | 13개 API, 업로드·Job/Artifact·9상태·승인·모델/DTO·비용·보안·인수, E2E/sequence/state diagram |
| docs/contracts/README.md | SSOT 읽기 순서, 공통/역할별 배포, 현재 구현 수준, 자동화 계약 단계 |
| docs/contracts/DECISION_REGISTER.md | C-01~12 전부 검토, 확정/이행/실험/고도화 차이, 확정하지 않은 사항 |
| docs/contracts/SCHEMA_MAPPING.md | 텍스트 v0.5 실제 필드와 Serving 7 DTO의 손실 위험·변환 테스트 |
| docs/contracts/IMPLEMENTATION_PLAN.md | dev/stacked feature PR 계보, S0~S7 병렬 개발과 인수 조건 |
| docs/contracts/TEAM_DISTRIBUTION.md | 팀 공통 공지 및 개별 안내·응답 체크리스트 |
| docs/contracts/partners/FRONTEND.md | 화면별 JSON, HTTP/409, 검색 요약·위반 하이라이트 UX, TypeScript 증빙 |
| docs/contracts/partners/TEXT_AI.md | VLM/Search/Copy/Compliance 포트, 실제 url_citation, 2단계 검수/Fixture |
| docs/contracts/partners/IMAGE_COMPOSER.md | 이미지 바이트·hash·5% 여백, 4:5, 한글 합성·제품 원형 QA 비교 |
| docs/contracts/partners/SERVING.md | Job/승인 revision, 비용 suboperation, 오류·Mock/Live 혼동 금지, API/TS 검증 순서 |
| docs/contracts/partners/PM_QA.md | 각 검증 게이트 독립 판정·예산·승인/병합 위험 표 |
| docs/contracts/fixtures/README.md | 합성 Fixture 7개 역할과 실제 스키마·HTTP/Live 구별 |

## 3. 수행한 자동·수동 대조

- [x] 2026-10-26 사용자 제공 회의 결론/텍스트 v0.5 스냅샷 원문을 기준으로 필드명/타입/Nullable/리서치 출처/Compliance 처리 대조.
- [x] 회의 공유 v0.5 스냅샷을 임시로 import해 합성 Fixture 7개 모두 Pydantic model_validate **PASS**. **김다혜님 실제 저장소 원본 commit 확인과는 다름**.
- [x] 수정된 Markdown 간 상대 링크·코드펜스 닫힘·Mermaid 블록 유무 정적 검사 문제 0.
- [x] 기존 FastAPI dev 기본 pytest **2 PASS**, 패키지 정적 검사 PASS, git diff --check PASS (문서 전용 변경).
- [ ] 텍스트 담당자의 실제 schemas.py v0.5 경로·커밋·타입 export/공식 Fixture 승인.
- [ ] 신규 OpenAPI/TypeScript 타입 및 실제 Live Provider·React Browser/광고·제품 원형 E2E.

## 4. 배포 기준

PR #4에 포함된 문서의 버전·SHA만 배포하고, 각 담당자에게 공통 문서 4종과 자기 파트의 1종을 안내한다. 스키마 원본 확인·새 endpoint 구현 이전에는 새 v0.2 API가 이미 작동한다고 표현하지 않는다.
