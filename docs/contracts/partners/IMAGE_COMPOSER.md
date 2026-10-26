# 이미지 AI·합성 / 박지수 — 연동 가이드

공통 필독: ../README.md → ../../interface_spec.md → ../DECISION_REGISTER.md → ../SCHEMA_MAPPING.md

**소유:** OpenAI 이미지/합성 API wrapper, 생성 프롬프트의 고정 금지·보존 지시, 이미지 리사이즈·크롭, 최종 Composition 및 사람 시각 QA.
- 입력은 Job/asset 승인 확인을 거친 검증 제품/참고 이미지 **바이트**, ProductAnalysis, ImagePromptOutput(concept,한국어 prompt,mood), 승인된 AdCopyOutput의 revision/hash.
- 고정 금지: 새 워터마크·타사 로고·원래 없는 글자, 제품/라벨 훼손. 최종 4:5 **1080×1350 PNG**, 바깥 5% 여백(정규화 0.05~0.95). 텍스트팀은 negative_prompt 제공하지 않음.
- 생성 image bytes + MIME/width/height/sha + attempt/usage/estimated cost를 서빙에 전달. 모델 바이트 적합성 != 제품 로고·용기·라벨 보존 적합성.
- 서버가 JobStore, 카피/이미지 승인, asset ownership, 저장/비용/다운로드 소유. image wrapper가 JobStore 상태를 직접 수정하지 않음.
- **실험 대기:** 광고 헤드라인·서브라인·CTA 길이 상한, 모델 이미지 내부 문자 생성 vs Composition 후처리 레이어, 비용·한글 가독성·자유도.
- 실험결과로 적정 글자 수/크롭/투명 용기/원본 제품 로고·라벨/여백 QA를 공유. 자동 재시도 0·unknown 과금시 재실행 금지. 후보 기본 1개.

**인계 필수 산출물:** 실제 wrapper 모듈 경로·SHA·호출 signature, 제품사진 입력 한도, Fake+승인받은 제한적 Live Fixture, PNG bytes/hash/메타데이터, 한글 긴·짧은 카피 합성 및 보존 QA, 429/timeout 실패 증거. 실이미지 public HTTP endpoint 이름은 아직 확정·구현되지 않음.
