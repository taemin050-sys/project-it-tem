# S5-I0 — 이미지팀 Offline Serving 통합 사전검증

> 본 문서는 **이미지 담당자 원본 소스 재사용**과 **서버 승인·무과금 경계**의 재현 가능한 검증 기록입니다. 정식 Text AI·Compliance·React Owner 인수나 실제 유료 이미지 생성 완료를 뜻하지 않습니다.

## 고정 기준 및 작업 범위

- 공식 통합 기준: `dev@b5e227e83e7ce0989f4573845909de66ea942da8`
- 이미지 담당자 브랜치: `feat/image-generation@65c2e84bb3a408a8bca123528b3ad3305b55c677`. 이미지 소스는 이 PR에 복제하지 않습니다.
- 기존 PR #6·#7·#9는 별개 미병합 작업이며, 현재 S5-I0 코드에 포함된 것으로 간주하지 않습니다. 결합 검증은 임시 복제본에서만 실행합니다.
- 서빙의 기존 외부 B0 HTTP API **11개를 변경하지 않습니다**. 새 모델 HTTP Wire 7개는 승인되지 않았습니다.
- 기본 B0 `create_app()`은 변경 없이 유지합니다. `OfflineImageFlow`는 신뢰된 서버 내부 시험 코드에서만 명시적으로 생성하는 **비공개 Offline 브리지**입니다. 인증, B1-R Compliance, 실제 사용자 승인을 대신하지 않습니다.

## 구현 및 신뢰 경계

| 구현 | 동작 |
|---|---|
| `image_offline_bridge.py` | 저장된 Job·Asset을 기반으로 전체 `plan/ad_copy/caption/hashtags`와 한국어 이미지 프롬프트를 이미지팀 원본 DTO에 연결 |
| `stage_copy / approve_fixture_copy` | 실제 Text Owner 결과 대신 **고정 Fake Fixture 전체 Copy**를 서버에 저장. 인위적인 승인 스냅샷·카피 revision 타입·전체 Copy canonical hash 결속 |
| `JobStore._s5_mutation_observer` | 명시적 Offline 모드에서만 변경·원복 시 입력 세대 증가, 승인 이후 카피 변경 차단. 기본 B0에서는 없음 |
| `generate` | 상태 `COPY_APPROVED`와 전체 스냅샷·Asset 파일 SHA를 확인한 뒤 이미지팀 `BackendImageAdapter.generate()` 재사용. MockTransport 및 `live_calls=False` 필수 |
| `approve_image` | 상태 `IMAGE_REVIEW_REQUIRED`에서 저장된 실제 이미지 바이트 SHA-256와 카피 hash/revision 확인 후 승인 |
| `compose` | 상태 `IMAGE_APPROVED`, 승인 이미지 바이트·카피 전체 스냅샷으로 이미지팀 `compose_ad_png()` 재사용. 기존 JobStore의 최종 PNG/UTF-8 Caption 저장·다운로드 엔드포인트 재사용 |

**중요:** S5-I0의 `approve_fixture_copy()`는 **내부 Offline Fixture 확인**일 뿐 실제 B1-R 검수·실사용자 승인 기록이 아닙니다. PR #9의 Fake Compliance 검증 계약을 임의로 확장하거나 복제하지 않았습니다. 따라서 성공한 Offline 결과를 `B1-L/B2 Live PASS`로 보고하지 않습니다.

### 재작업 방지 불변조건

- 생성 전에 전체 `CopyOutput`을 저장하고 승인 스냅샷과 동일한 hash를 사용합니다.
- `copy_revision`은 불투명한 타입별 식별자입니다. 숫자 `1`과 문자열 `"1"`은 서로 다르게 취급합니다.
- 카피 변경→원복 사이 실제 JobStore 변이가 있으면 generation이 증가해 이전 staged copy 승인이 재활성화되지 않습니다.
- 이미지 승인 시 저장된 바이트 SHA-256을 확인합니다. 승인 이전 합성 및 승인 후 입력 변경을 거부합니다.
- 최종 생성과 다운로드는 동일 Job의 등록 Artifact와 승인된 카피 해시·이미지 해시에 결속됩니다.
- 외부 네트워크는 소켓 수준에서 테스트 차단하고 `httpx.MockTransport`만 허용합니다. 공급자 호출, 자동 재시도 및 실제 과금은 **0건**입니다.
- 응답 유실/Job 파일 기록 실패 후에도 **동일 Job ID + 고정 Project UUID + 이미지팀 기존 attempt DB**를 이용합니다. 새 ID로 재호출하지 않습니다.
- 이미지팀 attempt/예산 보호가 전체 Text·Image 팀 비용 보호를 대신하지 않습니다.

## 재현 및 합격 범위

단독 공식 `dev`에는 아직 `src/image_generation`이 없습니다. 그 상태에서는 S5-I0 Owner 통합 테스트가 명시적으로 **SKIP**되며, 완료 판정할 수 없습니다.

1. 이미지팀 공식 301개 테스트는 변경 없는 브랜치 `65c2e84`에서 격리 의존성으로 실행합니다.
2. S5-I0 Serving 통합 테스트는 이미지팀 커밋과 현재 브랜치를 **임시 별도 복제본에서 결합한 뒤** 실행합니다.
3. 기본 B0 및 PR #6·#7·#9 호환성을 임시 복제본에서 추가 검증합니다. 가능하면 Chrome 실제 Browser B0-H도 다시 실행합니다.

```bash
# 이미지팀 소스가 들어 있는 임시 통합 복제본에서:
IT_TEM_KOREAN_FONT=/path/to/licensed/KoreanFont.ttf \
  .venv/bin/python -m pytest -q tests/test_s5i0_offline_image_serving.py

IT_TEM_KOREAN_FONT=/path/to/licensed/KoreanFont.ttf \
  .venv/bin/python -m pytest -q

.venv/bin/python docs/contracts/validate_package.py
```

### 제한·후속 게이트

- 실제 Text Owner `ProductAnalysisResult` 공식 SHA/Mapper, `ImagePromptOutput`, 전체 `AdCopyOutput` 소스 연결은 별도 수용조건입니다.
- 현재 저장·승인은 단일 프로세스 파일 기반의 Offline Fixture입니다. 인증·운영 DB 원자성·멀티프로세스·영속 전역 CostGuard 완료 증거가 아닙니다.
- 최종 이미지 레이아웃은 고정 Fake 제품을 위한 시험 좌표입니다. 실제 고객 제품의 안전 영역과 카피 오버플로·광고 규제 적합성은 미검증입니다.
- 정식 권혁상 님 React B0-O Browser E2E는 최우선이며, 본 시험 모듈은 이를 대체하지 않습니다.

**병합 정책:** Owner 소스 PR·현재 PR의 계약 검증, 독립 감사, PM 승인 전 공식 `dev/main`에 병합하지 않습니다.
