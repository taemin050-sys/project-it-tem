# IT-TEM 월요일(2026-10-26) 계약 회의 운영 보드

> **회의용 보조 문서 / 미승인.** 최종 계약은 PM 확인 후 `docs/interface_spec.md`에만 기록. 토요일 GCP Stage 2 `eb8a512`에서 `107 passed`, Push/clean 확인.

## 오늘의 목표

**30~40분 안에 P0 결정 12개를 승인하거나, 보류 사유·책임자·해결 기한을 적는다.** 모든 팀은 확정된 7개 DTO Fixture와 기존 13개 HTTP 경로의 호환성을 인지하고 병렬 구현한다.

| 결정 ID | 권고 기본안 / 꼭 들을 반론 | 결과 (`ACCEPT`/`MODIFY`/`HOLD`) | 담당·마감 |
|---|---|---|---|
| C-01 | `/api/v1`, `docs/interface_spec.md` 유일 SSOT | | |
| C-02 | 제품2~5/참고0~5, PNG/JPEG/WEBP | | |
| C-03 | ProductFacts + Evidence 출처, 미확인 사실 분리 | | |
| C-04 | 승인 카피 revision·VisualBrief 입력, 재승인 규칙 | | |
| C-05 | 이미지 1개, 원형 보존 수동 QA, 이미지 래퍼 입력 제한 | | |
| C-06 | 9개 P3 상태 유지, 거절 terminal/새 Job 권고 | | |
| C-07 | `detail` 호환, 409/422/429/502/503/504, 자동 재호출 금지 | | |
| C-08 | 10/30 웹 검색 우선, 논문/브라우저는 조건부 | | |
| C-09 | `not_checked`를 광고 승인으로 오인하지 않음 | | |
| C-10 | 실제 모델·API 키·건당 예산/호출 수 PM 명시 승인 | | |
| C-11 | 10/30 Mock PASS와 Live PASS 분리, 평가 Fixture | | |
| C-12 | 각 담당 RACI, 중복파일 수정 금지, stacked PR 통합 순서 | | |

## 담당자 한 문장 확인

- **React:** 기존 `GET job`을 SSOT로 삼고 승인 후에만 다음 POST, 409면 재조회, TS 타입은 계약 확정 후 생성.
- **기획/Research:** 실제 검색 + Evidence 출처가 없다면 조사완료로 표시하지 않으며 팀 검색 제공자·검증 기준 합의.
- **텍스트/카피:** 기획 결과를 1개 카피/VisualBrief로 변환하고 승인 카피 revision·위험 플래그 전달.
- **이미지:** 승인된 브리프·제품 원본 바이트를 받고 후보 1개 반환, 라벨·로고·색 보존/비용/불확실 시 재시도 금지.
- **서빙/인프라:** JobStore 상태/보안/예산 단일 진실 공급; 모델팀의 독립 모듈을 소비하고 중복 과금 방지 연결.
- **PM/QA:** 최종 계약·예산·품질 통과선·PR merge 승인 및 미결 사항 issue 소유.

## 세 가지 P0 통합 차단 위험 (즉시 담당 지정)

1. **Research→P4A plan 미연결**: 현재 `/ai/plan`은 검색 없이 생성. 연결 담당과 근거 검증 범위 확정.
2. **P4A text API→Stage2 비용 원장 미연결**: 기존 인프로세스 락만으로 중복 과금 안전 주장 금지. 실호출 전 가드 연결.
3. **Image Adapter→JobStore/승인/HTTP 미연결**: image wrapper 성공만으로 E2E 완료 아님. 승인 revision·원본 소유권·atomic 저장·Pillow 연계를 별도 수용.

## 회의 종료 기록

- 승인 상태: `APPROVED / CONDITIONALLY APPROVED / HOLD` = ___
- 문서 버전 / 변경이력: ___
- PM 및 각 담당 review 확인: ___
- 계약 미결정 사항(담당/마감/Mock fallback): ___
- `dev` 선행 PR(현재 확인 필요: P1 #3) 리뷰·병합 순서: ___
- 10/30에 필수 Live 단계와 허용 Mock 단계: ___

**승인되지 않은 결론은 코드 주석/개인 초안에서만 `PROVISIONAL`로 유지하고 공용 계약을 덮어쓰지 않는다.**
