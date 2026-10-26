# 서빙·백엔드·인프라 / 이형기 — 연동 가이드

공통 필독: ../README.md → ../../interface_spec.md → ../DECISION_REGISTER.md → ../SCHEMA_MAPPING.md

**소유:** FastAPI HTTP wire/JobStore·자산·원자 기록, text v0.5 DTO 호환, VLM/Research/Copy/Compliance/Image/Composer 오케스트레이션, 승인·비용·오류·secret·배포 안전성.
- dev=d5d07aa(P1만), stacked feature f979331(P2→Stage3) 별도. 계약 PR에서 코드 통합 금지; 이후 dev 기준 P2/P3/P4A/Stage1/2/3 diff 검토·순차 리뷰.
- 신규 ProductInput+VLM 분석 Job 기록, 이미지 바이트 검증 및 asset ownership, ResearchResult 실제 URL/display_summary, AdCopyOutput 구조 보존, ComplianceReport, ImagePromptOutput prompt/mood mapping.
- ComplianceReport.passed=false라면 승인 API도 **403/409/422 등 별도 합의 오류 코드로 차단**. 프론트 비활성만으로 충분하지 않음. 승인 대상 copy revision/hash를 Job에 보관하고 image/compose 입력과 동일성 확인.
- 기존 Stage2 CostGuard는 (job_id,stage) 중복 차단이 너무 거칠고 /ai/* 미연결. **다른 suboperation은 허용, 동일 입력·시도 중복은 보호**. 타임아웃·429·응답 유실 billing unknown 유지, 총 $10 예산(실험 포함) 집계 및 승인된 실호출 보호. 유료 플래그만 켜지 않기.
- 기존 10MiB/파일·60MiB/요청·40MP와 회의의 자동 resize 정책 충돌. 서버 메모리/DoS를 보호하면서 대형 정상 사진을 전처리하는 설계·테스트 별도.
- image wrapper 연결 순서: Job/asset/Compliance/approved copy → budget reservation → provider → bytes/MIME/sha 검사 → atomic persist → image approval → composer → 최종 1080×1350 PNG+caption.
- OpenAPI는 **실제로 구현된 서버**에서 내보내고, TS 타입과 JSON Schema, Fixture, contract tests를 동기화. 현재 기존 13 API·9 상태·118 테스트는 feature 브랜치의 증거; 새 HTTP 경로는 계약·구현 PR 필요.
- 운영: 300s/1200 tokens/SDK retry=0, API 키 서버만, GCP VM 임의 중지/재부팅 금지, 포트 8000 인증 없이 외부 노출 금지.

**인수:** 118 기존 회귀 + 신규 스키마/검수 차단/승인 hash/비용 suboperation/중복 과금/검색 실패/이미지 bytes 위변조/브라우저 E2E 각각 PASS. 모델 품질은 담당팀, 저장·승인·API·비용 차단은 서빙팀.
