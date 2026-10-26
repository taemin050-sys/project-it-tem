# IT-TEM 통합 계약 v0.2 — 팀 공지·배포 패키지

> **사용 시점:** PR #4 영향 담당 리뷰 및 `dev` 병합 후, **동일한 확정 Git SHA**로만 배포한다. 병합 전 공유하는 경우 **`PR REVIEW`**라고 표시한다.

## 1. 전 팀원 공통 공지 (붙여넣기용)

IT-TEM 10/26 PM 참석 연동 회의에서 결정한 내용을 `docs/interface_spec.md v0.2`에 통합했습니다. **전원은 공통 [배포 인덱스](README.md)에서 계약 → 결정 레지스터 → 스키마 매핑 → 실행 로드맵을 순서대로 읽어 주세요.** 이후 **자신의 파트별 가이드 하나**를 참고해 구현합니다. 채팅으로 개별 계약 문구를 복제·수정하지 않고, Git 커밋의 문서를 단일 기준으로 사용합니다.

| 파트 | 담당 | 역할별 문서 |
|---|---|---|
| React | 권혁상 | [FRONTEND.md](partners/FRONTEND.md) |
| Text AI · VLM/Research/Copy/Compliance | 김다혜 | [TEXT_AI.md](partners/TEXT_AI.md) |
| Image AI · Composition | 박지수 | [IMAGE_COMPOSER.md](partners/IMAGE_COMPOSER.md) |
| FastAPI/Serving/Infra | 이형기 | [SERVING.md](partners/SERVING.md) |
| PM/QA | 이태민 | [PM_QA.md](partners/PM_QA.md) |

**중요 변경:** 김다혜 `schemas.py v0.5` 우선, 서빙에서 DTO 호환; 제품 사진 VLM 분석, 조사 요약·검색 사실/AI 추론 구분, Compliance 위반 의심 시 카피 승인 차단, 한국어 이미지 프롬프트·무드, 박지수 이미지·합성 책임, **총 $10** 베이스라인 실험 예산.

**미결정:** 카피 최종 길이/표시·합성 방법, 비화장품/동일 제품 처리 정책, 거절 후 재수정, 신규 HTTP endpoint 명세·오류. 구현 완료나 무조건적인 서비스 가능 상태를 의미하지 않습니다.

**현재 코드 구분:** `dev=d5d07aa`에는 기본 `/health`만, 13개 레거시 API와 118개 테스트는 누적 `f979331` 기능 브랜치에만 있습니다. 모델 연결 전에 반드시 코드/계약/Fixture/브라우저 검증을 진행합니다.

## 2. 전송 담당자 체크리스트

- [ ] 문서 PR #4 리뷰, PM 및 영향 담당 변경 사항 확인, `dev` 병합 여부 기록
- [ ] **병합 커밋 SHA·계약 버전·docs/contracts/README.md** 링크를 전체 팀에게 전달
- [ ] 각 담당자에게 **같은 SHA의** 해당 `partners/` 가이드 안내
- [ ] 텍스트팀 `schemas.py v0.5` 실제 코드 path/commit/schema+Fixture·이미지 Wrapper signature 수합
- [ ] 변경 요청은 C-ID·필드·영향·테스트·PR로 정리, 별도 비공식 SSOT 생성 금지
- [ ] 신규 유료 호출 플래그 기본 OFF, 키 비공개, VM 무승인 중지/재시작 금지

## 3. 회신 요청 (간단)

각 담당자는 **① 본인 스키마/Wrapper 코드 링크 및 commit SHA, ② 서버에 필요한 입력/출력, ③ Contract 테스트 1개 이상, ④ 막힌 사항 및 영향 C-ID**를 GitHub PR 코멘트 또는 Issue로 남겨 주세요. 별도 회의를 전제로 작업을 보류할 필요는 없습니다.
