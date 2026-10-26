# IT-TEM 통합 인터페이스 계약 v0.2 — 2026-10-26 회의 반영

> 문서 성격: 10/26 PM 참석 파트 연동 회의에서 합의한 결정의 통합 기준안. 이 PR에서 리뷰·병합하여 저장소 공식 SSOT로 확정한다.
> 적용 버전: contract v0.2 / text schemas.py v0.5.
> 주의: 계약 승인 ≠ 구현 완료. 이 문서는 새로운 엔드포인트가 현재 동작한다고 주장하지 않는다.
> 참고: docs/contracts/README.md (배포 자료), docs/contracts/DECISION_REGISTER.md (결정/보류), docs/contracts/SCHEMA_MAPPING.md (필드 매핑).

## 1. 범위·파트 책임

사용자 입력 + 단일 화장품 제품 사진 2~5장(참고 사진 0~5장) → VLM 화장품 분석 → Research/Planning(웹 검색 가능) → 광고 콘셉트·카피 + 규제 검수 → 카피 승인 → Image AI → 이미지 승인 → Composition → 1080×1350 PNG와 UTF-8 캡션·해시태그.

- 텍스트 AI 소유: 김다혜. 제품 분석 VLM, 검색/기획, 카피, ComplianceReport, ImagePromptOutput. OpenAI API wrapper. **텍스트팀 schemas.py v0.5가 텍스트 데이터 의미/필드의 우선 기준.**
- 이미지·합성 AI 소유: 박지수. OpenAI API wrapper 기반 이미지 생성과 최종 합성. 이미지 금지 프롬프트·제품 보존, 4:5 리사이즈 담당.
- React UI: 권혁상. 사용자 입력, 조사 요약, 검수 경고·하이라이트, 승인, 다운로드.
- FastAPI/서빙: 이형기. HTTP wire 계약, 저장/Job/Asset, 모델 래퍼 입출력 변환, 상태·승인·권한·비용/중복/오류 차단, 최종 파일 등록.
- PM/QA: 이태민. 변경 관리, 모델/비용/보안 승인, 병합 순서, 10/30 수용 판정.

## 2. 확정 E2E 계약 (MVP) 및 범위 경계

1. React에서 ProductInput과 제품 이미지 2~5개·참고 0~5개를 전달한다. 서버는 실제 파일 검사·보관·asset_id 부여 후 바이트로 VLM 및 이미지 어댑터에 전달한다. 사진 권리 확인은 사용자 체크로 입력한다. 체크가 실제 소유권을 증명하는 것은 아니다.
2. VLM은 2~5장을 함께 분석하여 ProductAnalysis로 화장품 여부·용기·색·라벨·무드 등을 반환한다. MVP는 화장품 여부 판단을 시행하며 **동일 제품/세트 판별 및 비화장품 결과에 대한 최종 UX 정책은 고도화 의사결정**. 위험한 경우 자동 과금 후속 단계로 진입하지 않도록 별도 실패/보류 응답을 마련한다(기술적 제안, 정책 승인 필요).
3. 텍스트 모듈 안에서 웹 검색을 수행하고 ResearchResult를 조립한다. ResearchOutput에는 카피 검토 화면용 display_summary를 동일 생성 호출에서 만든다(별도 요약 유료 호출 없음). 출처 유형은 '사용자 입력' / '검색 결과' / 'AI 추론'; VLM 분석도 AI 추론이다. 인용 URL·제목은 OpenAI 응답의 실제 url_citation에서 추출하고 AI가 본문에 만든 URL을 인용으로 채택하지 않는다.
4. 검색 실패 시 웹 검색 없이 계속 진행할 수 있으나 research_performed=false, 조사 내용은 AI 추론으로 표시한다. 출처 URL 존재는 사실성 또는 규제 적합성 검증을 의미하지 않는다.
5. AdCopyOutput은 plan(AdPlan), ad_copy(CopySet: headline/subline/cta), caption, hashtags로 전달한다. 다섯 필드의 UI/합성 형식과 항목별 글자 수는 실험 후 결정. 기존 단일 CopyResult.text의 글자 수는 회의에서 **임시 최대 400자**로 정했으나 아직 구현된 제약은 220자이므로 코드 반영 전 차이가 있다.
6. ComplianceReport는 1차 금칙어·정규식 + 2차 LLM으로 작성한다. risk_level='위반 의심'이 하나라도 있으면 passed=false → 카피 승인 서버/React 양쪽에서 차단해야 한다. '근거 확인 필요'는 경고·대체 문구·근거를 표시한다. 각 Issue의 field/start/end를 텍스트가 반환한다. '게시 전 최종 확인 책임은 사용자에게 있습니다' 고지를 제공한다.
7. 텍스트는 ImagePromptOutput(concept, 한국어 prompt, mood)을 이미지팀에 제공한다. 동일한 AdPlan.concept/mood를 사용한다. 이미지 금지문구(글자/워터마크/타 브랜드 로고)와 제품 원형 보존 지시는 이미지팀이 고정으로 보강한다. 레거시 VisualBrief.negative_constraints는 비워 전달할 수 있고, mood를 확장해야 한다. 바깥 5% 최소 여백: 최종 1080×1350 캔버스 기준 정규화 0.05~0.95 (템플릿별 실배치는 실험).
8. 이미지팀은 후보 이미지 바이트와 메타데이터를 반환한다. 서빙은 승인된 **정확한 카피 revision/hash**, job 및 자산 소유권을 확인하고 파일 형식·디코딩·치수·SHA-256을 검사·등록한다. 사람의 외형/라벨 보존 검토는 바이트 검증과 별개.
9. 이미지 승인 후 이미지팀 Composition을 통해 4:5, 1080×1350 PNG 생성. 서빙은 실제 승인된 이미지·카피를 사용했는지 검사하고 최종 파일·caption·hashtags를 등록·배포한다. 합성 표현 방식(모델 내부 합성 vs 후처리 텍스트 레이어)은 실험 후 결정.
10. 카피 거절 뒤 수정·재승인하는 루프는 고도화 우선 항목. 기존 Mock 거절 terminal 상태를 MVP 중에 무단 재정의하지 않는다.

## 3. 텍스트팀 데이터 계약 / 서버 매핑

텍스트팀 v0.5 모델명과 필드명은 축약·재명명 없이 수용한다(상세표: docs/contracts/SCHEMA_MAPPING.md).
- ProductInput: brand_name nullable, product_name, product_category nullable, features, ad_purpose, is_functional, photo_verified, product_image_count 2~5, reference_image_count 0~5.
- ProductAnalysis: is_cosmetic, product_type, container_type, colors[], label_text[], mood[], is_transparent. is_same_product는 MVP 없음.
- ResearchOutput: product_summary, functional_notes, market_insights[], similar_products[], ad_direction, display_summary[] (text/source).
- ResearchResult: research, citations[{title?,url}], research_performed. **LLM Structured Output이 아닌 코드 조립값.**
- AdCopyOutput: plan{target,concept,key_message,tone,mood[]}, ad_copy{headline,subline,cta}, caption, hashtags[].
- ImagePromptOutput: concept, prompt(한국어), mood[]. negative_prompt 없음.
- ComplianceReport: passed, issues[{field,text,start,end,category,risk_level,reason,suggestion?,basis?,detected_by,auto_fixed}], revised_fields, checklist, notice.
- 실제 텍스트 모듈의 schemas.py v0.5가 타입·Literal 범위의 source-of-truth. 기존 서빙 ProductFacts/Evidence/PlanResult/CopyResult/VisualBrief/ImageResult/GenerationReceipt는 *내부 provisional DTO*이며 같은 wire 타입이라고 주장하지 않는다. lossless mapping + compatibility fixture 필요.

## 4. HTTP 및 상태 계약: 현재 vs 목표 구분

HTTP 기본 prefix /api/v1. 필드는 snake_case. 성공 시 기존 endpoint는 직접 Job JSON 또는 파일 바이너리; 공통 data wrapper 없음.
**브랜치 현실**: 2026-10-26 조사 기준 origin/dev=d5d07aa에는 P1 /health 기반만 있고, 아래 13개 /api/v1 라우트는 아직 미병합 feat/p4-contract-handoff=f979331의 구현이다. 이 문서가 dev의 13개 가동을 의미하지 않는다.

Feature 브랜치의 현재 13개:
- POST /jobs (multipart **product_images**, **reference_images** 반복 필드) → 201 Job
- GET /jobs/{job_id}; GET /jobs/{job_id}/assets/{asset_id}
- POST /jobs/{job_id}/mock/plan; POST /jobs/{job_id}/mock/copy
- POST /jobs/{job_id}/approvals/copy
- POST /jobs/{job_id}/mock/image; POST /jobs/{job_id}/approvals/image
- POST /jobs/{job_id}/mock/compose; GET /jobs/{job_id}/artifacts/{kind}
- GET /capabilities
- POST /jobs/{job_id}/ai/plan; POST /jobs/{job_id}/ai/copy

회의 후 **추가·수정이 필요한 HTTP 계약**: ProductInput 입력/화장품 분석, ResearchResult/AdCopyOutput/ComplianceReport 조회, text ImagePromptOutput 전달, 이미지·합성 공개 경로, 판정 실패·비용·승인 revision 등. 이 PR은 API 이름·요청·응답·신규 상태를 임의 확정하지 않는다. 구현 직전 OpenAPI/Fixture를 기준으로 별도 변경 PR에서 정한다.

기존 Feature 브랜치의 9개 상태 (현재 구현):
INPUTS_VALIDATED → PLAN_READY → COPY_REVIEW_REQUIRED → COPY_APPROVED → IMAGE_REVIEW_REQUIRED → IMAGE_APPROVED → COMPLETED, 거절 terminal: COPY_REJECTED, IMAGE_REJECTED.
승인 이전 후속 단계 / 중복 승인 / 잘못된 순서 → HTTP 409. 새 VLM·Compliance 결과의 상태 확장은 아직 설계·코드 반영 전. UI는 서버 Job 재조회로 동기화하며 자동 재과금 호출을 반복하지 않는다.

## 5. 비용·실행·품질 규칙

- 팀 베이스라인 유료 API 비용은 **실험 포함 총 $10 제한**, 추가 지출 시 PM 사전 승인. 예상 비용을 확정 청구액으로 표시하지 않는다.
- 유료 호출은 서버만 수행, 비밀 API 키는 .env/비밀관리 경로(커밋 및 React 번들 금지), 기본 OFF. PM 예산·모델 허가, 중복/과금 실패 보호를 통과한 후만 Live 활성화.
- 호출 timeout 300초, max output 1200토큰, SDK 자동 retry 0회(10/26 합의 초기값). 단계별 출력 절단·체류시간·사용료는 실험 검증 후 변경관리.
- 검색 횟수는 초기 고정 제한 없음(실험 검토), **전역 $10 예산과 안전 차단의 예외가 아님**. Cost Guard는 동일 작업의 중복 실행은 막되 검색→기획→카피→검수 등 서로 다른 순차 sub-operation을 막으면 안 된다. 세부 키·원자성은 구현 과제.
- 타임아웃/429/응답 유실/청구 불명확 시 자동 재시도 금지; billing unknown 보존, Job 결과 조회 후 책임자 확인. 성공을 임의 Mock으로 대체하지 않는다.
- 업로드: UI 정책은 일반 사진의 용량·해상도 제한 없이 수용하고 큰 사진 자동 축소·압축. 기존 feature 구현은 10MiB/파일, 60MiB/요청, 40MP 제한이 있어 **현재 코드와 계약 불일치**. 실물리적 요청 크기·메모리·악성 입력의 서버 안전 상한은 별도 기술 구현 결정이 필요하며 검증을 없애지 않는다.
- 보안: GCP dev VM port 8000 공개 금지(인증/HTTPS/CORS/프록시 정책 전). GPU VM 사용자 승인 없이 중지/재부팅 금지.
- 인수 증빙은 Contract / Mock E2E / Live Text+Research / Live Image+Composer / React Browser E2E / 광고표현·제품보존 / 비용·보안 별도 PASS/FAIL로 기록.
- 기술 이력: feat/p4-contract-handoff 118 tests passed (GCP 당시 로그; 별도 Mac 로컬 폰트 주입 후 118 passed), OpenAPI 1 + JSON Schema 7 + manifest 1, 13-route 감사 PASS_FOR_TEAM_REVIEW. 모두 **팀 계약 반영 또는 Live 완료를 뜻하지 않는다**.

## 6. 계약 변경 관리

docs/interface_spec.md가 공식 규범 문서이며 docs/contracts/README.md가 배포 진입점. 변경 시 v0.x 버전/승인자/변경 이유/필드·UI·비용·테스트 영향/하위호환/관련 PR을 반드시 기록. 배포 대상별 자료는 이 문서와 상충할 수 없고 참조 링크만 유지한다.
- **회의에서 결정됨:** 팀 제공 회의 결과(10/26)와 텍스트 schemas.py v0.5.
- **후속 실험으로 남음:** 카피 필드/글자 수의 최종 정책, 텍스트 합성 방식, 비화장품/동일 제품 UX, 검색 호출 정책 최적화, 모델/사용금액 세부 계약, 공개 신규 endpoint/wire mapping, 보안/운영 수용.
- **효력:** PM의 본 계약 PR 리뷰·병합 이후 공식 SSOT. 그 전에는 PR 브랜치의 회의 반영안이며 기존 서비스에 자동 적용되지 않는다.
