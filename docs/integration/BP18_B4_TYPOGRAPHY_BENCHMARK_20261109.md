# Track B · 광고 타이포그래피 벤치마킹과 비과금 합성

2026-11-09 KST · B4 디자인 개발 단위 완료 · C 시각 감사 대기 · `NOT_RELEASE_READY`

시작 Branch는 `integration/bp18-product-complete-20261111`, HEAD는 `87f9a139df83ba742a6dd4ab7dc51a57093abb52`, Tree는 `a98cb572e203ae3cf8d2381770004feeddb49230`다. 작업은 SSD B에서 수행했다. 구현·회귀·이 보고서는 같은 B 커밋에 고정한다. 이 단위의 산출물은 오프라인 합성 3종이며 B4의 여섯 실모델 조합과 최종 사람 인수는 남아 있다.

## 실제 참조 원본

사용자가 이 Codex 채팅에 직접 제공한 네 Mac PNG를 열어 확인했다. ZIP 절차 대신 새 인계 문서 `00_CODEX_REFERENCE_HANDOFF_FALLBACK_20261109.md`를 적용했다. 원본은 아래 참고 폴더에 바이트 변경 없이 복사하고 읽기 전용으로 보존했다. 네 SHA 모두 준비된 ZIP importer의 기대 SHA와 일치한다.

참고 폴더는 `/Volumes/SSD 4T/z_ai_asset/P03_it-tem/knowledge/benchmarks/2026-11-09-korean-ad-typography/references`이며 출처·크기·SHA는 같은 상위 폴더의 `ATTACHMENT_SOURCE_MANIFEST_20261109.json`에 있다.

| 실제 원본 | 치수 | SHA-256 | 관찰과 적용 |
|---|---|---|---|
| Daleaf | 1274×1396 | `109be1e88d71f44c20fdb5cbe7242ef75e6a3e7e4031b07504e8869d06851fc4` | 가장 큰 무박스 제목, 작은 설명, 제품과 연결된 색 포인트. Bold의 제목 위계와 남색 로고 연결에 적용 |
| UL·OS | 1002×1392 | `1b3c660c3bc763e327476f7e35f3a3dd58e0f4f12beaf3b448a4e3678a1f2d30` | 두꺼운 한글과 강조 구절의 큰 색 대비, 사선 시선 흐름. Graphic의 한 구역 강조와 단단한 글자 조형에 적용 |
| DASHU | 1198×1202 | `81bb49e14f2c4a53d71f9ec65041ae2c03648471446aa257b43c2435ab051359` | 큰 문자가 구조를 만들고 보조 정보가 정렬된다. Graphic의 한 줄 제목과 오른쪽 보조 정보 정렬에 적용 |
| 검은콩 샴푸 | 602×984 | `ce67997b6102613c968a0b33913150001c02d676ba290c9657125b2b04fa2d91` | 중앙 제목의 명확한 크기 차이, 상단 여백, 제품과 주변 재료의 정돈된 관계. Editorial의 중앙 위계와 세이지 사진 여백에 적용 |

산출물의 문구는 기존 승인 Head/Sub/CTA와 Caption이다. 제품 사진도 기존 승인 후보다. 시안에는 순위·할인·가격·효능·모델 등 새 콘텐츠를 추가하지 않았다.

## 구현

- `src/image_generation/composition.py`의 정상 `compose_ad_png` 진입점에 선택적 `typography`를 연결했다. Pydantic 2.14.1의 `exclude_if`로 스타일이 없는 과거 레이아웃의 직렬화 바이트를 보존한다. 기존 v1 렌더 경로를 사용한 네 기준 사례의 레이아웃·PNG·Caption·입력 SHA를 전후 대조했다.
- `src/image_generation/typography.py`는 `display-typography-v1` 계약, 실제 가변 글꼴 `wght` 축, 영역별 굵기·자간·행간·장평·원문 인덱스 줄바꿈·배경 반경을 지원한다. 최대 320px는 스타일이 있는 영역에만 허용된다. 지원하지 않는 굵기, 잘못된 경계, overflow, 누락 glyph는 실패로 처리한다. 큰 문구의 폭을 먼저 측정해 과대 raster 할당을 차단한다.
- 자간과 수동 줄바꿈은 NFC 한글·Latin·CJK·Kana 등 명시적으로 지원되는 문자에 적용한다. contextual shaping이 필요한 문자의 자간·수동 경계는 거부한다. 이 범위는 일반 UAX29 지원 주장과 구별한다.
- 활성 스타일의 영수증은 `korean-composition-v2`이며 기존 전체 Copy/Image/Layout 입력에 스타일을 결속한다. 실제 적용 크기·Weight·축·행·잉크 경계와 문구 SHA를 기록한다. Caption은 승인 본문과 해시태그의 UTF-8 바이트다.
- `src/image_generation/typography_profiles.py`에 세 방향의 오프라인 4:5 프로파일을 추가했다. `scripts/bp18_typography_study.py`가 명시된 입력 파일과 참고 SHA를 확인한 뒤 정상 합성 함수로 결과와 영수증을 생성한다. 출력 디렉터리는 새 경로만 허용한다.

이 변경은 기존 Owner 이미지 합성 엔진의 검증·리사이즈·Caption·영수증 경로를 재사용한다. 새 옵션의 출처는 B의 실제 참조 분석과 로컬 구현이다. 현재 Live 정책에 새 프로파일을 활성화하는 작업은 별도다.

## 동일 입력과 결과

기존 서명 Job은 `68306165e96e40a4b09a379e6330804d`, 개발 Actor는 사용자가 승인한 `bp18_b_exobiz7`다. Copy SHA는 `6336a7679b814e196dba172c55166e91546a9dbb525b96e7a3506b98874ee746`, 승인 이미지 후보 SHA는 `7b80ae12ae05e5bced24b08263291b0ec1078a244ce9da98f974f2acb6679380`다. 오프라인 시안은 source Copy/Image 승인 SHA를 provenance로 기록한다. 새 최종 디자인에 대한 사람 수용은 대기다.

최종 증거 폴더는 `/Users/Shared/ittem-bp18-codex-evidence-20261109/typography-benchmarked-final`이다. 같은 폴더의 `comparison.png`는 기존 결과와 세 시안을 각각 360×450으로 비교한다. 각 시안의 `_360.png`, `_390.png`, `_layout.json`, `_receipt.json`과 `manifest.json`을 함께 보존했다.

| 1080×1350 PNG | SHA-256 |
|---|---|
| 기존 B2 | `c1d7ab6a4cc7a3102258233352b7ef1ec66b86c899f8d932a9d378bcfc191f34` |
| Bold Type Hero | `8659709dac076e869ad3da57ca2155754b5ce1d32cfd81c674aee7d9a360ce21` |
| Editorial Botanical | `5376662e8ca40983cb1c49f92f182a0571986b6fd4265dc87329283193b1b65f` |
| Graphic Layout | `0ba3d106be3881a965575be365ba17fb03942860ab076d5fa76745e55c0ba45e` |

모든 Caption SHA는 기존 다운로드와 같은 `5c929f00213f9a14e8db4ecdf21e7139b6b365a53168867734cc3c28eba8dfe6`다. 손으로 대조해 선언한 제품 영역 `[390,420,710,1184]`의 픽셀은 세 시안 모두 이전 B2 최종 PNG와 동일하다. 이전·신규 텍스트 영역 합집합 바깥 사진 픽셀도 모두 동일하다. 근거는 `cross_environment_pixels.json`이다. 이 결과는 원래 AI 후보의 작은 라벨 정확성을 새로 판정하지 않는다.

## 시각 평가와 선택

| 방향 | 실제 360·390px 관찰 | 남은 평가 |
|---|---|---|
| Bold Type Hero | 두 줄의 굵은 제목이 먼저 읽힌다. 남색 제목·로고·CTA가 연결되고 반복된 미색 박스가 사라졌다. Head/Sub/CTA 위계와 제품 사진의 연속성이 가장 분명하다 | B 우선안. 최종 Owner·PM 수용 필요 |
| Editorial Botanical | 중앙 정렬 제목과 작은 설명, 넓은 여백이 세이지 사진과 어울린다. 채운 녹색 CTA로 초기 외곽선형보다 읽기 쉬워졌다 | 차분한 브랜드 방향의 선호 확인 필요 |
| Graphic Layout | 큰 남색 슬래브와 단독 `루틴` 줄을 없앴다. 한 줄 제목과 오른쪽의 작은 연두색 강조 면으로 제품의 시각적 비중을 살렸다 | 보조 색면의 브랜드 적합성 평가 필요 |

B는 Bold Type Hero를 우선안으로 선택했다. 세 결과 모두 실제 이미지에서 승인 헤드라인 `하루의 샴푸 루틴`, 서브 `매일 만나는 세정 시간`, CTA `루틴에 더하기`를 한 번씩 확인했다. 잘림과 제품 겹침은 관찰되지 않았다. Static 축소본을 본 B 내부 평가이며 실기기 조작·Owner·PM·C의 최종 판정은 별도다.

## 폰트·실행·안전 회귀

기존 로컬 Pretendard 1.3.9 variable TTF를 사용했다. 글꼴 SHA는 `3090ccde0442bb347aa7685d9ba8b17436a60682df6e8f92a9a670de14056e22`, 제공된 OFL-1.1 라이선스 원문 SHA는 `b04538c9abec39a3db75108cf0af0fd9c77032fe8aa2cf38345b4d250e98e38e`다. 라이선스 원문은 결과 폴더에 포함했다. 이 변경의 Git에는 폰트 바이너리를 추가하지 않았다.

실행 환경은 Python 3.12.2, Pillow 13.0.0, FreeType 2.14.3, RAQM false다. GCP의 Pillow 12.3.0과 PNG 파일 SHA가 같다고 가정하지 않는다. 위의 실제 cross-environment 픽셀 대조 결과를 별도로 확인했다.

| 실행 검증 | 결과와 근거 |
|---|---|
| 전체 Python | **1,079 PASS**, 26.40초. 외부 네트워크 차단·Loopback 허용, 실제 키 제거, billable flag 비활성. `typography-python-regression-final.log` |
| 신규 타이포그래피 | **38 PASS**. SHA·입력 버전·static weight 실패·줄바꿈·Indic 경계·overflow·과대 mask·빈 줄·보호 픽셀·결정성 |
| 과거 출력 4건 | 기준 커밋을 임시 추출한 별도 Python과 현재 B에서 같은 환경으로 실행. 기본/A v1/B v3/Owner 4:5의 layout·PNG·Caption·input SHA 모두 일치. `typography-legacy-sha-comparison.json` |
| 실제 시안 | 정상 합성 함수에서 두 번 렌더링한 PNG·Caption 바이트 일치, 1080×1350, 세 필드 원문 SHA와 표시된 행 전체 대조 |
| React·Browser | 이번 변경에 FE 소스 없음. 기존 B2 브라우저 다운로드 근거는 보존. 신규 시안의 Live 브라우저 다운로드는 미수행 |
| Provider·비용 | 새 Provider 호출·Attempt·Usage 0건. 신규 영수증은 로컬 합성 영수증. 기존 B2의 실제 6건 모델 영수증은 별도 |
| Serving·보안 | 전체 Python에서 F09·승인·Worker·Queue·CostLedger·B5·EX12 관련 회귀 통과. 이번 단위는 GCP 배포를 수행하지 않음 |

첫 전체 검사에서 표준입력 `pytest.main` 래퍼의 경로가 `<stdin>`으로 잡혀 macOS spawn 테스트가 시작되지 않았다. 실제 `python -m pytest` 실행으로 정정해 전체 1,079개가 통과했다. 해당 최초 실패 로그도 보존했다. 테스트 코드를 삭제하거나 완화하지 않았다.

## 인수 상태와 C 요청

이번 근거는 V02 한글 타이포·V03 구도·V04 가독성 및 F14/F17 합성 원문·Artifact provenance의 B 구현·오프라인 시각 근거를 보완한다. 실제 모델 조합은 기존 1/6이며 이 단위에서 증가하지 않았다. 38개 정식 최종 인수와 Release는 여전히 대기다.

P1로 남는 항목은 원래 생성 후보의 연청색 원형 표식 작은 문자, 최종 광고의 상업적 품질 사람 평가, 실기기 모바일 UAT, 선택 프로파일의 향후 서명 Live 여정이다. GCP B는 기존 `4baa67eb`와 정책 epoch 2의 운영 상태를 기준으로 한다. 기존 B5 배포·Rollback 계약에 따른 새 후보 검증은 배포 시 필요하다.

C-B는 고정 B 커밋, 원본 네 파일 SHA, 영수증의 Copy/Image/Layout/Font 결속, 과거 출력 바이트 보존, 제품 픽셀·한글·CTA·라이선스·모바일 시각 품질을 독립 확인할 수 있다. 감사 패키지는 위 경로에 보존한다. 제출 메시지와 C의 최종 판정은 별도로 기록한다.
