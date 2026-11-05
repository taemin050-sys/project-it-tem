# 이미지 MVP dev 검토 안내

2026-10-30 · 대상: `feat/image-generation → dev`

## 1. 이번 PR의 목적

실제 제품 사진과 텍스트 결과를 이미지 모듈에 연결한다.
이미지 후보를 만든 뒤, 승인된 한글 카피를 별도로 합성한다.
최종 산출물은 1080×1350 PNG와 UTF-8 캡션 파일이다.

**현재 판정: 이미지 모듈 구현과 오프라인 검증은 완료했다. 실제 웹서비스 인수는 남아 있다.**

이 PR은 `src/image_generation/`과 그 시험·문서를 추가한다.
기존 FastAPI HTTP 경로, JobStore 상태, 텍스트 생성 코드는 바꾸지 않는다.
서빙은 이미지 모듈을 호출하고 승인·저장·다운로드를 연결해야 한다.

## 2. 개발된 기능과 스펙

| 기능 | 현재 동작 | 코드 |
|---|---|---|
| 텍스트 결과 수신 | 제품 분석 결과, 한글 이미지 프롬프트, 헤드·서브·CTA를 받는다. 분석 실패와 성공/error 모순을 차단한다. | [backend_adapter.py](../src/image_generation/backend_adapter.py), [product_analysis.py](../src/image_generation/product_analysis.py) |
| 프롬프트 호환 | `concept·prompt·mood` 객체, `prompt`만 있는 객체, 문자열을 받는다. 한국어를 번역하지 않는다. 전달된 무드를 유지한다. | [backend_adapter.py](../src/image_generation/backend_adapter.py) |
| 사진 입력 | 제품 사진 2~5장과 선택 참고 사진 0~5장을 받는다. PNG·JPEG·WebP·MPO를 내부 PNG로 정리한다. | [assets.py](../src/image_generation/assets.py) |
| MPO 처리 | 프레임 0 하나를 선택한다. EXIF 회전, ICC→sRGB, 색상 모드, 파일 제한, 메타데이터 제거를 유지한다. | [업로드·저장 문서](imageAssetPortability.md) |
| 외부 이미지 요청 | 생성·편집·생성형 누끼 요청을 지원한다. 기본 생성 원본은 1152×1440, 품질은 medium이다. 실제 이미지 바이트·크기·형식을 검사한다. | [openai_images.py](../src/image_generation/openai_images.py), [contracts.py](../src/image_generation/contracts.py) |
| A 카피 영역 | 상단 헤드·서브와 하단 CTA를 중앙 정렬한다. 상단 safe_zone은 제품·소품·무늬·강한 반사광을 피하도록 지시한다. | [A 템플릿 문서](imageATemplate.md) |
| 한글 최종 합성 | 승인된 이미지와 전체 카피의 해시를 검사한다. 글자 폭을 재서 줄바꿈·크기를 조정한다. 안 맞는 문구는 자르지 않고 오류로 돌려준다. | [composition.py](../src/image_generation/composition.py) |
| 최종 크기 | 생성 원본을 로컬에서 1080×1350으로 줄인 뒤 한글을 합성한다. 이 과정은 이미지 API를 호출하지 않는다. | [ad_resize.py](../src/image_generation/ad_resize.py) |
| 중복 호출 방지 | 제출 전에 시도와 예약금액을 저장한다. 동일 작업의 정상 결과는 다시 읽는다. 변경 입력과 불확실한 시도는 자동 재전송하지 않는다. | [재조회·원장 문서](imageReceiptAndReplay.md) |
| 사용 기록 | 모델, 요청 ID, 시도 상태, 처리 시간, 제공자가 반환한 사용량을 기록한다. 없는 사용량을 0으로 만들지 않는다. | [provider_attempts.py](../src/image_generation/provider_attempts.py) |

### 입력·출력 제한

- 생성·편집 이미지는 4:5 비율을 사용한다. 기본 생성 크기와 최종 광고 크기는 다르다.
- 외부 API 입력 검사는 사진 1장 20 MiB, 전체 100 MiB를 기본 상한으로 둔다.
- 응답 본문은 32 MiB, 출력 이미지 바이트는 20 MiB를 기본 상한으로 둔다.
- 외부 요청의 기본 대기 시간은 120초다.
- HEIC/HEIF와 일반 애니메이션은 지원하지 않는다.
- 생성형 누끼 요청이 성공해도 원본 제품 픽셀 보존을 보장하지 않는다.
- `safe_zone`은 모델 지시다. 보장된 마스크가 아니다.
- A는 선택형 helper다. 호출자가 `make_a_template()`의 결과를 생성·합성 입력에 연결해야 한다.

## 3. 입출력 계약

여기서 계약은 파트 사이에 주고받는 값과 검증 책임을 뜻한다.
아래는 Python 모듈 계약이다. 새 HTTP API가 구현됐다는 뜻은 아니다.

| 단계 | 입력 | 출력·검증 |
|---|---|---|
| 생성 요청 | 서버가 확인한 `project_id`, `BackendImageInput` | `BackendImageAdapter`가 내부 요청을 만들고 실행한다. |
| 필수 입력 | `job_id`, `copy_revision`, `copy_hash`, `product_analysis`, `image_prompt`, `ad_copy`, 제품 사진 바이트 | 제품 사진 2~5장. 필드 형식과 분석 상태를 검사한다. |
| 선택 입력 | `reference_images`, `safe_zone`, `caption`, `hashtags` | 참고 사진 0~5장. safe_zone은 0~1 정규화 좌표이며 외곽 5% 여백 안에 둔다. |
| 카피 버전 | 1 이상 정수 또는 비어 있지 않은 문자열 | 문자열은 최대 128자다. 숫자처럼 보여도 정수로 바꾸지 않는다. |
| 생성 결과 | 내부 생성 결과 | `BackendGeneratedImage`: 실제 `image_bytes`, MIME, width, height, SHA-256, 작업·카피 식별자, mock 여부, receipt |
| 합성 요청 | `CompositionInput`: 승인 이미지 바이트·해시, 전체 `AdCopyOutput`·해시, 카피 버전, layout | `compose_ad_png(..., font_path=...)`가 이미지와 카피의 일치를 검사한다. |
| 합성 결과 | 승인된 입력과 폰트 | `ComposedAd`: 1080×1350 PNG 바이트, UTF-8 캡션·해시태그 바이트, 해시, 배치 기록 |
| 재조회 | 같은 프로젝트·작업·입력 snapshot | 정상 결과의 파일과 해시를 다시 검사한다. API가 꺼져 있어도 새 호출 없이 반환한다. |

**승인 책임:** 해시가 맞는다는 사실만으로 사용자 승인을 증명할 수 없다.
서빙은 사용자·프로젝트 소유권, 카피 승인, 이미지 승인을 확인해야 한다.
생성 어댑터의 `copy_hash`는 서버가 준 승인 식별자다.
합성기는 `plan·ad_copy·caption·hashtags`를 포함한 전체 카피의 해시를 다시 계산한다.

**오류 책임:** 이 모듈은 `GatewayError.code` 또는 제공자 오류 코드를 돌려준다.
HTTP 상태와 사용자 안내는 서빙이 연결해야 한다.
주요 코드는 `COMPOSITION_TEXT_OVERFLOW`, `COMPOSITION_COPY_HASH_MISMATCH`,
`COMPOSITION_IMAGE_HASH_MISMATCH`, `COMPOSITION_GLYPH_MISSING`,
`PROVIDER_ATTEMPT_CONFLICT`, `PROVIDER_SUBMISSION_UNKNOWN`이다.

### 카피 길이: 잠정 작성안

| 항목 | 총 글자 수 | 한 줄 작성 가이드 | 최대 줄 수 |
|---|---:|---:|---:|
| 헤드 | 15자 이내 | 15자 이내 | 1줄 |
| 서브 | 25자 이내 | 15자 이내 | 2줄 |
| CTA | 10자 이내 | 10자 이내 | 1줄 |

공백·문장부호는 포함하고 줄바꿈 문자는 제외하는 안이다.
현재 A와 NanumGothic 시험 폰트에서 대표 한글·영문 폭을 실측했다.
서브 한 줄 15자는 물리적 최대치가 아니라 여유를 둔 작성 가이드다.

이 안은 **팀 확정 전**이다. 현재 코드가 15·25·10자나 1·2·1줄을 강제하지 않는다.
코드는 픽셀 폭으로 줄바꿈한다. 명시한 줄바꿈도 보존한다.
운영 폰트, 실제 카피, API·프론트의 줄바꿈 보존, 모바일 가독성을 확인해야 한다.
입력 방어 상한인 헤드 600자·서브 2000자·CTA 600자와 광고 작성 기준을 혼동하지 않는다.

## 4. 모델·내부 버전·실행 조건

### 코드에 고정된 모델과 버전

| 항목 | 현재 값 | 의미 |
|---|---|---|
| 기본 모델 ID | `gpt-image-2.6-sunburst` | 새 작업의 기본 설정이다. |
| 기본 complexity | `high` | 2.6 전용 옵션이며 요청 snapshot·해시·receipt에 기록한다. |
| 기본 quality | `medium` | complexity와 별개이며 자동으로 high로 바꾸지 않는다. |
| 허용 이전 모델 ID | `gpt-image-2.5-sunburst-2026-09-08`, `gpt-image-2-2026-04-21` | 명시 선택만 허용한다. complexity는 지원하지 않는다. |
| 내부 파이프라인 | `openai-images`, revision `2` | `ExternalImageRequest`의 고정 값이다. |
| 한글 공통 정책 | `ko-v1` | 제품 보존·배경·한글 정책이다. |
| 워터마크 정책 | `exclude-v1` | 제품 라벨과 불필요한 워터마크를 구분한다. |
| 새 safe_zone 프롬프트 | `backend-v02-ko-v3` | 기존 저장 요청의 v1/v2는 바꾸지 않는다. |
| 최종 한글 합성기 | `korean-composition-v1` | receipt에 합성기 버전을 기록한다. |
| 카피 구조 | 텍스트 v0.5의 `AdCopyOutput` 구조 | 텍스트 생성 패키지 자체를 설치하거나 import하지 않는다. |

모델 ID는 **코드 설정을 확인한 값**이다.
이번 PR에서 실제 계정의 사용 가능 여부, 제공자 단가, 새 유료 호출을 확인하지 않았다.
모델 이름만으로 품질이나 제품 보존을 합격 처리하지 않는다.
이전 작업의 재조회는 당시 모델·quality 설정을 명시해야 한다. 2.6 기본 설정으로 같은 job을 호출하면
입력 충돌을 유지하며, 새 모델 실행에는 새 job이 필요하다. 기존 저장 요청의 JSON·해시는 바꾸지 않는다.

### 실행 기본값

- `OpenAIImagesConfig.live_calls=False`다.
- `ExternalImageProcessor.budget_limit_usd="0"`이다.
- 새 호출은 서버의 승인·예산 확인과 명시적인 실행 설정이 필요하다.
- `reservation_usd`는 예산 예약값이다. 추정 비용이나 청구액이 아니다.
- 타임아웃·응답 유실은 불확실한 시도로 남긴다. 같은 작업을 자동 재전송하지 않는다.
- 저장된 정상 결과를 읽는 동작과 새 유료 요청의 허가 조건을 분리한다.
- API 키는 서버에서 전달한다. 문서·로그·소스에 키를 넣지 않는다.
- `compose_ad_png`에는 서버가 정한 폰트 경로를 전달한다. 사용자 입력을 폰트 경로로 쓰지 않는다.

## 5. 재현에 필요한 환경

### 이미지 모듈 시험 환경

이번 PR의 재검증 환경은 **Python 3.11.15**다.
고정 목록은 [tests/image_generation/requirements.txt](../tests/image_generation/requirements.txt)에 있다.

| 패키지 | 고정 버전 | 용도 |
|---|---:|---|
| Pydantic | 2.14.1 | 입력·출력 검사 |
| HTTPX | 0.28.1 | 외부 요청과 MockTransport |
| Pillow | 13.0.0 | 사진 정규화·리사이즈·합성 |
| fonttools | 4.68.0 | 폰트의 한글 지원 검사 |
| pytest | 9.2.0 | 오프라인 시험 |

별도 가상환경에서 실행한다. 기존 서빙 환경을 덮어쓰지 않는다.

```bash
python3.11 -m venv /tmp/ittem-image-mvp-review
/tmp/ittem-image-mvp-review/bin/python -m pip install -r tests/image_generation/requirements.txt
/tmp/ittem-image-mvp-review/bin/python -B -m pytest -p no:cacheprovider -c tests/image_generation/pytest.ini tests/image_generation -q
/tmp/ittem-image-mvp-review/bin/python -B docs/contracts/validate_package.py
```

시험 폰트는 `tests/image_generation/fixtures/fonts/NanumGothic-Regular.ttf`다.
같은 폴더의 `OFL.txt`와 `provenance.json`에 라이선스와 해시가 있다.
이 폰트를 운영 폰트로 확정한 것은 아니다.

### 최신 dev의 기존 HTTP 계약 시험

별도 통합 시험 환경에 다음 버전을 추가했다.

| 패키지 | 사용 버전 |
|---|---:|
| FastAPI | 0.161.1 |
| Starlette | 1.7.0 |
| python-multipart | 0.0.32 |

이 값은 [GCP 서빙 lock](../configs/requirements-serving-gcp.lock.txt)에서 가져왔다.
이번 통합 시험은 이미지 시험 목록의 Pillow 13.0.0을 사용했다.
GCP lock의 Pillow 12.3.0 환경에서 이미지 전체 시험을 완료한 것은 아니다.

```bash
/tmp/ittem-image-mvp-review/bin/python -m pip install fastapi==0.161.1 starlette==1.7.0 python-multipart==0.0.32
IT_TEM_KOREAN_FONT="$PWD/tests/image_generation/fixtures/fonts/NanumGothic-Regular.ttf" /tmp/ittem-image-mvp-review/bin/python -B -m pytest -p no:cacheprovider tests/test_api_list_contract.py tests/test_b0_s3b2_http_contract.py -q
```

마지막 두 시험 파일은 최신 `dev`에 있다. `dev`와 합친 검토 사본에서 실행한다.
`IT_TEM_KOREAN_FONT`는 기존 B0 Mock 합성기의 설정이다.
새 이미지 합성기는 `font_path` 인수를 사용한다.

## 6. MVP 완료·미완료 판정

| MVP 항목 | 현재 판정 | 완료한 것 | 남은 조건 |
|---|---|---|---|
| 실제 텍스트 결과 입력 | 모듈 완료 / 서비스 인수 대기 | 분석 결과·한국어 프롬프트·카피 수신, 실패·모순 차단 | 실제 팀원 JSON과 서빙 mapper 확인 |
| MPO 업로드 | 모듈 완료 / 실제 연결 재확인 | 대표 프레임 처리, 정규화, 실제 MPO 2개의 로컬 저장·재조회 | 다혜님 원본과 실제 웹 업로드 경로 확인 |
| A 카피 영역·한글 합성 | 모듈 완료 / 시각 인수 대기 | A 영역, safe_zone 보강, 원문 보존, 넘침 오류 | 운영 폰트, 실제 카피, 제품 가림·잘림·모바일 가독성 |
| 제품 보존 | 검토 대기 | 보존 지시, 수동 검토 상태, 선언한 제품 영역과 글자 영역의 겹침 차단 | 정확한 원본과 후보의 각도·비율·색·라벨 비교 |
| 승인 후 최종 다운로드 | 모듈 완료 / 서비스 연결 대기 | 1080×1350 PNG와 캡션 바이트 반환 | 실제 승인 snapshot, UI 미리보기, PNG·캡션 다운로드 연결 |
| 기본 사용량·신뢰성 | 일부 완료 | 시도 원장, 시간·사용량, 동일 작업의 중복 POST 차단, 정상 결과 재조회 | 모델·단가 근거를 붙인 추정 비용 계산·표시, 실제 정산 대조 |
| 수집·기록 재처리 | 별도 확인 대기 | 저장 결과와 receipt를 생성 없이 읽는 함수 | 실제 수집 worker가 기록 실패 때 생성 API를 재호출하지 않는지 확인 |

**서비스 MVP 전체를 완료로 표시하지 않는다.**
외부 호출 성공, 파일 검증, 제품 보존 합격, 사용자 승인은 각각 별도 판정이다.

### 범위를 분리한 항목

- **협업 환경 보완:** Windows 로컬 Python 저장 호환은 구현했다. 실제 Windows 시험은 NOT_RUN이다. 팀원이 그 환경을 계속 사용할 때 확인한다. 웹 MVP의 선행 조건으로 두지 않는다.
- **조건부 추가 지원:** HEIC/HEIF는 미구현이다. 휴대폰 원본 직접 업로드를 지원 범위로 약속하면 추가해야 한다.
- **제품 보존 후속 경로:** 변형이 계속되면 원본 누끼 고정 합성과 캐시를 적용·검증해야 한다. 이 PR의 생성형 누끼 통신과 구분한다.
- **고도화:** 팔레트·콘셉트·소품 자동 추천, 연상어 사전, 여러 서체, 자동 품질 점수, 비용 자동 최적화는 포함하지 않는다.
- **내부 도구:** Langfuse·W&B는 서빙의 필수 의존성이 아니다.

## 7. 검증 결과

기능 코드 기준은 `b0cf72e`다.
테스트 경로 오탐 보완은 `d4a06ff`다.
비교한 `dev`는 `cfb5bc5f5ba225680f4ab841c3065155ecbc602a`다.
실제 브랜치를 병합하지 않고 합친 임시 사본에서 검사했다.

| 검사 | 결과 | 확인 범위 |
|---|---|---|
| 최신 dev와 합친 트리 | 충돌 없음 | Git 변경의 병합 가능성 |
| 이미지 모듈 | **348 passed**, 7.06초 | 외부 네트워크를 차단한 단위·Mock·로컬 합성 시험 |
| 기존 dev HTTP 계약 | **19 passed**, 0.35초 | 기존 11개 HTTP 동작과 Mock 파일 다운로드 |
| 팀 계약 자료 | 통과 | 합성 fixture 8개, 문서 13개의 링크·구조 |
| 이번 유료 이미지 호출 | **0회** | 새 실생성은 하지 않음 |

기존 dev HTTP 시험에는 TestClient의 HTTPX 사용 중단 예고 경고 1건이 있었다.
실패는 없었다. 이 결과는 새 이미지 기능의 실제 웹 E2E 인수를 뜻하지 않는다.

재현 중 발견한 시험 오류도 고쳤다.
기존 검사는 예외 전체에서 `private`라는 단어를 금지했다.
이 때문에 macOS의 `/private/` 경로를 민감 정보로 오인했다.
이제 시험용 키·프롬프트·URL 문자열을 정확히 검사한다.
예외 코드, 요청 횟수, 원인 예외 제거 검사와 런타임 코드는 유지했다.

세부 기록은 [PR 검증 기록](validation/image-mvp-pr-20261030.json)에 있다.
실제 MPO·Linux 저장 검증의 범위는 [업로드 문서](imageAssetPortability.md)에 있다.
Windows 실환경, 팀원 원본 전체 경로, 실제 생성 품질과 실서비스 인수는 이 검사에 포함하지 않았다.

## 8. 문서와 다음 연결 작업

| 필요한 정보 | 문서 |
|---|---|
| 현재 기능·버전·MVP 상태 | 이 문서 |
| 서빙이 연결할 함수와 예시 | [servingMvpAlignment.md](servingMvpAlignment.md) |
| 공통 팀 계약 | [interface_spec.md](interface_spec.md), [계약 인덱스](contracts/README.md) |
| 이미지 담당 계약 | [IMAGE_COMPOSER.md](contracts/partners/IMAGE_COMPOSER.md) |
| A 좌표·폰트 크기·카피 작성안 | [imageATemplate.md](imageATemplate.md) |
| MPO·Windows·실제 시험 범위 | [imageAssetPortability.md](imageAssetPortability.md) |
| 시도 원장·예약·재조회·기록 재처리 | [imageReceiptAndReplay.md](imageReceiptAndReplay.md) |
| 재현 패키지와 폰트 | [시험 의존성](../tests/image_generation/requirements.txt), [폰트 출처](../tests/image_generation/fixtures/fonts/provenance.json) |
| 원본 담당 TODO | [plan/models의 imageTodo.md](https://github.com/uyt5041-lab/beauty-ai-models/blob/1589f8717d2a6b700c76e242384cb37bddb2a48e/docs/imageTodo.md) |

1. 텍스트 담당과 카피 작성안 및 실제 AdCopyOutput을 맞춘다.
2. 서빙 담당이 소유권·승인 snapshot·이미지 호출·최종 바이트 저장을 연결한다.
3. 프론트 담당과 운영 폰트·줄바꿈·미리보기·파일 다운로드를 확인한다.
4. 이미지 담당이 원본 대비 제품 보존과 실제 카피 가독성을 판정한다.
5. 모델·단가·사용량 근거로 추정 비용을 계산하고 실제 청구액과 분리한다.

공통 HTTP 계약 변경이 필요하면 기존 담당 합의 절차를 따른다.
이 문서나 PR 게시만으로 상대의 동의·운영 배포·서비스 인수가 완료되지는 않는다.
