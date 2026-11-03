# A 중앙 고딕 템플릿 연결

2026-10-30 · 이미지 모듈의 선택형 로컬 helper

## 생성과 합성

`make_a_template()`는 기존 `BackendSafeZone`과 `CompositionLayout`을 함께 반환한다.
외부 입력 스키마에 필수 필드를 추가하지 않는다. 호출자가 A를 선택한 경우에 사용한다.
폰트는 기존 `compose_ad_png(..., font_path=...)`에 서버가 신뢰하는 고딕체 경로를 전달한다.
테스트는 저장소의 OFL NanumGothic fixture를 사용한다. 운영 폰트 자동 선택·다운로드는 하지 않는다.

| 항목 | 영역(left, top, right, bottom) | 최소/최대 글자 크기 |
|---|---|---|
| 생성 상단 safe_zone | 0.06, 0.05, 0.94, 0.25 | 해당 없음 |
| 헤드라인 | 0.08, 0.06, 0.92, 0.14 | 48 / 64 px |
| 서브라인 | 0.08, 0.15, 0.92, 0.25 | 45 / 48 px |
| CTA | 0.08, 0.85, 0.92, 0.94 | 48 / 54 px |

좌표는 최종 1080×1350 기준이다. 이전 초안의 top=0.04는 기존 5% 계약과 맞지 않아 0.05로 교정했다.
세 영역은 중앙 정렬이며 기본 배경판은 없다. 필요한 경우 검토 후 `background="#FFFFFF"`를 명시할 수 있다.
최소 글자 크기로도 들어가지 않는 원문은 `COMPOSITION_TEXT_OVERFLOW`로 거절한다. 잘라내거나 더 작게 줄이지 않는다.

생성 입력 구성 시:

```python
from src.image_generation import make_a_template

safe_zone, _ = make_a_template()
# 기존 BackendImageInput의 선택형 safe_zone 필드에 전달한다.
# body = BackendImageInput(..., safe_zone=safe_zone)
```

실제 결과와 승인된 카피를 합성할 때:

```python
from src.image_generation import make_a_template

_, layout = make_a_template(protected_regions=reviewed_product_regions)
# 기존 CompositionInput에 layout과 승인된 이미지/전체 카피 snapshot을 넣는다.
# result = compose_ad_png(composition_input, font_path=trusted_gothic_font)
# result.image_bytes: 1080×1350 PNG
# result.caption_bytes: UTF-8 caption + hashtags
```

`reviewed_product_regions`는 실제 후보에서 확인한 `CompositionRect` 목록이다.
텍스트와 제품 보호 영역이 겹치면 기존 검증이 거절한다. CTA도 검사 대상이다.
보호 영역을 안 넣으면 기존 `PRODUCT_REGION_NOT_PROVIDED` 경고와 수동 검토 필요 상태를 유지한다.
상단 safe_zone은 CTA까지 예약하지 않는다. 실제 카피/제품이 이 고정 배치에 맞지 않으면 레이아웃을 검토해야 한다.

## 새 작업과 기존 작업

새 safe_zone 작업은 제품·소품, 복잡한 무늬·장식, 강한 반사광을 해당 영역에서 피하도록 지시한다.
지시는 `backend-v02-ko-v3`로 저장한다. 모델 지시는 보장된 마스크가 아니므로 침범·대비·가독성을 확인한다.

기존 입력 fingerprint v1/v2는 유지한다. 동일 작업 재시도는 새 지시를 만들기 전에 저장 요청을 검증·재사용한다.
과거 바인딩을 v3로 덮어쓰거나 자동 재생성하지 않는다. 기존 작업의 입력 변경은 계속 충돌로 거절한다.
safe_zone이 없는 새 작업의 프롬프트 동작과 버전도 유지한다.

## 확인 범위

- 고정된 수정 전 b9d0015 바인딩(v1/v2)의 byte-level 재사용 및 입력 변경 충돌.
- 새 v3 바인딩 재사용, 프롬프트 길이 실패 시 파일/과금 이전 중단.
- 합성 사진과 한글 카피의 중앙 정렬, 최소 글자 크기, 제품 보호 영역 픽셀 보존.
- MockTransport 생성→동일 작업 재사용→로컬 합성→1080×1350 PNG·UTF-8 캡션.
- 합성의 provider_calls=0 및 needs_manual_check=True 유지.

테스트용 카피와 합성 사진의 결과이며 실제 팀원 JSON·실서비스 승인/다운로드 인수 증거는 아니다.
해시 일치는 승인 증명이 아니다. 서빙이 인증·승인 snapshot·다운로드를 관리한다.


## 카피 길이 작성안 · 2026-10-30

아래는 텍스트 담당과 맞출 **잠정 작성 기준**이다.
팀 확정이나 새 코드 제한으로 표시하지 않는다.

| 항목 | 총 글자 수 | 한 줄 작성 가이드 | 최대 줄 수 |
|---|---:|---:|---:|
| 헤드 | 15자 이내 | 15자 이내 | 1줄 |
| 서브 | 25자 이내 | 15자 이내 | 2줄 |
| CTA | 10자 이내 | 10자 이내 | 1줄 |

공백·문장부호는 포함하고 줄바꿈 문자는 제외하는 안이다.
서브는 의미 단위로 나누는 방식을 권장한다.
한 줄 15자는 물리적 최대치가 아니라 여유를 둔 가이드다.

현재 A와 bundled NanumGothic 폰트로 한글·W 반복 문구를 실측했다.
헤드 15자와 CTA 10자는 1줄, 서브 25자는 2줄에 들어갔다.
서브의 명시 줄바꿈 12+13자와 15+10자도 들어갔다.
이 결과를 모든 실제 문구의 가독성 보장으로 확대하지 않는다.

현재 합성기는 픽셀 폭으로 줄바꿈하고 입력된 줄바꿈을 보존한다.
15·25·10자 또는 1·2·1줄을 별도 필드로 강제하지 않는다.
운영 폰트, 실제 카피, API·프론트의 줄바꿈 보존은 추가 확인 대상이다.
검토자는 [MVP dev 검토 안내](imageMvpDevReview.md)와
[실측·PR 검증 기록](validation/image-mvp-pr-20261030.json)을 함께 확인한다.
