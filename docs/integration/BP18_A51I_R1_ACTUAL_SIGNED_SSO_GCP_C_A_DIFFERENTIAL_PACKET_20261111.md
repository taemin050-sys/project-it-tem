# IT-TEM P03 Track A — A5-1H-R1 / A5-1I-R1 실제 GCP Signed SSO C-A 차등감사 제출

**2026-11-11 KST · 신규 변경·실제 런타임 C-A 독립 재감사 PENDING**

## 1. 기존 수용과 실제 PM 승인

- C-A5-1H: 실제 GCP A-only 격리 비과금 배포 독립 수용. 제출 HEAD `69ecfd03e6ea54b8222692c0ff23a959b3b00745`, Tree `25ad44496193274d2c37112351dfa03c7f27727a`.
- 기존 예산·리소스 범위의 GCP 개발·테스트 배포 및 모델 API 개발·테스트 비용 사용은 팀에서 **이미 승인**. 새 승인을 중복 요구하지 않음. **기존 승인 = 실제 제품 법적 사용권·서명형 Profile·Worker 과금 안전성 검증이 아님**.
- [GitHub Issue #38](https://github.com/taemin050-sys/project-it-tem/issues/38): PM `@taemin050-sys` 2026-11-11 실제 회신으로 **`REJECT_MULTIFRAME_V1` 채택**. MPO 자동 변환·선택은 이번 베타 제외, JPG 위장 MPO도 *원본의 리사이즈/재인코딩 이전에* 판별·차단. 기존 v2 Owner 입력 경로 불변.
- PM: 실제 제품 형태·색상·로고·라벨 보호 최우선; 업로드 당시 기존 사진 사용권 확인 유지. 실제 생성 전 2회차 권리 재확인은 **검토 의견**이며 확정 기능 아님. 사용자 권한 확인 ≠ 법적 권리 증빙. 실제 사용권/Mask/Font/Profile/Provider 활성화는 승인되지 않음.

## 2. 코드·배포 재현성

| 항목 | 실제 확정값 |
|---|---|
| Lock 결함 수정 | `dcbe41b2fbc598809d3a27c0828d3206cfd48430` |
| A5-1I Signed SSO 신규 코드 | `05ae03f4829d3e93ff4c5524cbded64f31a16ac2` |
| **최신 실제 GCP 실행 코드 HEAD** | **`46a8de353ceae557dd8585481c2028fa9451e17c`** |
| Git Tree | `a62e89927f29bd21007215dbc1692a65b5d6cffc` |
| Serving Lock SHA256 | `4bcf7d6b9a21c46836554dbbdc819e0ad6f2310a4a324d5b521545021458b7af` |
| FE JS | `index-C044IJ-g.js`, SHA `0b5d85ce143c75488b0e142a9584ef0f6f63310bc8a833a42197faa2de807fdd` |
| FE HTML SHA | `5ea71d9ff61829243849892727954be7e2b50419a6d73636332231bdbc03a401` |
| FE CSS SHA | `7eef942a377e371075981b4987fcfd5dbadcabd6426613e31f3389274c5d444e` |
| 고정 Git 소스 전체 | **883/883 GCP 원격 SHA256 PASS** |

실제 누락됐던 `fonttools==4.65.0`을 공식 `configs/requirements-serving-gcp.lock.txt`에 추가. **신규 격리 가상환경에서 잠금 파일만으로** pip install / pip check / `fontTools` import / 한글 폰트 파싱·글리프 측정 / FastAPI Health 모두 PASS. 기존 A5-1H Runtime은 중지·변경하지 않았습니다. 정식 Pretendard 사용권/Owner 승인은 별도 보류됩니다.

## 3. 실제 A-only Signed SSO → GCP 통합

**현재 개발·테스트 URL:** https://macstudio-macstudio.tail17dfff.ts.net:10444/ (**Tailnet only**, Funnel/public exposure 없음).

실제 경로: Tailscale Serve HTTPS `10444` → Mac Studio 별도 인증 게이트웨이 `127.0.0.1:19103` → 전용 SSH 포워드 `127.0.0.1:19102` → GCP `team2-vm` 신규 후보 `127.0.0.1:18564`.

- 신규 GCP 후보: `/home/macstudio/ittem-a51i-signed-sso-devtest-r1-20261111`, PID `196402`(관측 기준), root permission `0700`, 분리된 전용 HMAC 키/Actor Registry `0600`.
- Tailscale Serve로 실제 인증된 사용자 `TAILSCALE_SERVE` → 서명 Actor → FastAPI Session `200` / 실사용자 별도 정책의 B0 Job 생성 `201` / 동일 내용 요청 멱등 재전송 `200` / 조회 `200` / 요청 내용 변조 `409` / MPO-JPG 위장 `422` / 구형 B0 직접 생성 `423`.
- **실제 Tailnet HTTPS 동시 요청 10건:** `201` ×1 / `200` ×9 / **Job 정확히 1개**, 원본 합성 PNG만 사용, 외부 Provider 호출 0.
- 기존 `A51E`의 `/pytest` 테스트 전용 허용조건을 제거하지 않았습니다. 새 `IT_TEM_A51I_GCP_SIGNED_SSO_DEVTEST` 계약은 별도 루트·실행 Source SHA·Signed Host·PM MPO 정책·Worker OFF·Provider Secret 없음·HARD_CAP 비활성 과금 경계를 startup에서 필수 검증합니다. 실제 프로덕션/유료 Worker 실행 승인이 아님.
- 실제 Chrome 390px 홈, 360px 제품 입력 **렌더링 및 Signed 인증 문구 확인**. 수정본 Build `46a8de35`, MPO 거절 및 기술 게이트 HOLD 상단 안내 검증. Chrome 양식 제출 전체 사용자 여정이나 팀 5인 UAT 완료로 오인 금지.
- **별도 UX P2:** `app/src/pages/ProductPage.tsx` 입력 힌트의 기존 ‘MPO는 Owner 승인 전까지 차단’ 문구는 PM 확정 결정과 시간상 어긋납니다. FE Owner 공식 입력 계약과 함께 팀 UAT 이전에 ‘이번 베타에서는 MPO 업로드 불가’로 정정. 서버의 레거시 내부 오류 코드 `A51E_MPO_OWNER_POLICY_PENDING`과 PM 정책 확정 여부를 혼동하지 않음.

## 4. GCP 원장·비과금·복구 증거

GCP R1에 분리된 Upload 원장, Application Image, Queue, Cost, Owner Provider Attempt 원장을 생성·확인. 기존 GCP 운영 `live_image_attempts` 8건과 신규 Provider Attempt 원장을 혼동하거나 기존 운영 DB를 재초기화하지 않았습니다.

| 현재 A5-1I-R1 원장 | 실제 Row |
|---|---:|
| `live/live.sqlite` / `live_image_attempts` | 0 |
| `live/queue.sqlite` / `queued_ops` | 0 |
| `live/cost.sqlite` / `attempts` | 0 |
| `live/owner_image/image_attempts.sqlite` / `provider_attempts` | 0 |

Worker의 기존 `require_preinitialized_candidate_ledgers`로 4개 원장 스키마 및 미대사 거래 없음 확인. **유료 Worker OFF, Provider Key 없음, 실제 모델 과금 0**. `HARD_CAP` 환경 설정은 **실제 승인된 숫자형 상한·최악 비용·실청구 대사 완료 증거가 아님**.

**별도 GCP R1에서 SQLite online backup API로 6개 DB WAL 일관성 백업**, 각각 `PRAGMA integrity_check=ok`, 별도 복구 위치 JobStore에 대해 합성 Actor 소유 Job **2건 재조회 PASS**. **한계:** 독립 DB 스냅샷은 *서로 다른 DB 전체의 동일 시각 원자적 복구*를 증명하지 못합니다. 유료 Worker 가동 전 quiesce/barrier·정합 대사가 필요합니다.

기존 GCP 18096(A) / 18088(Live) / 18095(QA) / 18100(B) 포함 18561·18562·18563·18564의 **8개 Health 전부 200**. 기존 A Source SHA `9879eb0f85747312a224ecd898aaff84d834590b` 보존. 새 18564에 문제 발생 시 **Mac SSH 19102 → GCP 18563으로 재결속**(이전 프로세스·데이터 보존). 기존 Tailnet 10443(A), 10500(B) 및 기타 Serve 라우팅/운영 원장/공식 Owner 소스 불변.

보안 신뢰경계 제한: Mac의 localhost 게이트웨이가 `Tailscale-User-Login`을 전달받는 구조는 로컬 OS에서 **Tailscale Serve 외 다른 로컬 프로세스가 헤더를 위조할 가능성**까지 차단했다는 증거가 아닙니다. 정식 공용 운영 전 게이트웨이 접근 제한·신원 바인딩·nonce 재생 방지 감사가 필요합니다. 이번 검증은 보호된 단일 Mac/GCP 개발·테스트 환경만 수용 대상입니다.

## 5. 실제 회귀 및 증거

- **Python 전체 1,415/1,415 PASS**, Signed SSO 신규·기존 표적 **53/53 PASS**. 전체 Python 실행 이후 수정은 프런트엔드 안내 2개 파일뿐.
- **React 61/61 PASS**(최종 문구 수정 후), Lint 오류·경고 0, Vite Build PASS.
- **GCP 883/883 tracked SHA PASS**, 실제 HTTPS FE JS·HTML SHA 고정. Chrome 실제 390/360px 스크린샷.
- 증거 루트 `docs/integration/evidence/A51I_R1_20261111/`, 총 **11개 원본 + SHA256 Manifest**. 원본 GCP runtime·SQLite backup JSON, Signed Job, 10회 CAS, cutover/rollback, 모바일 Chrome, Python/React/Build 로그, 소스 파일별 해시 포함. 비밀키·원본 24장 미승인 화장품·폰트 바이너리는 포함하지 않음.
- Track B는 다른 작업자의 미커밋 변경 존재: Track A에서 임의 수정/초기화/병합하지 않음.

### C-A 재현

```bash
cd '/Volumes/SSD 4T/z_ai_asset/P03_it-tem/tracks/A-owner-first'
(cd docs/integration/evidence/A51I_R1_20261111 && shasum -a 256 -c A51I_R1_EVIDENCE_SHA256_MANIFEST.txt)
python3 scripts/a3_track_a_guarded_readiness.py
git status --short
```

**차등감사 대상:** `dcbe41b` Lock, `05ae03f` 실제 Signed GCP 계약, `46a8de3` FE 정책 상태, GCP 실행 SHA·프로세스·SQLite·HTTPS·브라우저·접근권한. 기존 A2~A5-1H 독립 수용 코드를 반복 재개발하지 말 것. 신규 C-A의 독립 판정이 나오기 전 개발 self-PASS를 C-A PASS로 기록하지 않음.

## 6. Full-Feature Beta 남은 Hard Gates

| 게이트 | 판정 |
|---|---|
| 기존 A5-1H GCP 격리 | **C-A ACCEPTED** |
| A5-1H-R1 Lock / A5-1I-R1 Signed GCP 비과금 | **실측 개발 PASS / C-A 미감사** |
| 실제 GCP Signed SSO + B0 Job + 10중 동시성 | **실측 개발 PASS / C-A 미감사** |
| Owner/PM 실제 Profile v3·SKU 사용권·Mask·Font | **PRODUCT_CONTRACT_PENDING** |
| 전체 Owner Text→Image→Worker 실운영 | **TECHNICAL_NOT_READY** |
| 실제 모델가격·Signed numeric Hard Cap·Usage/Receipt/청구 대사 | **TECHNICAL_NOT_READY** |
| 실제 모델 Freeform/Composed × 3비율 독립 Job | **0/6** |
| 실제 5인 팀 브라우저 UAT 및 제품·브랜드/라벨 품질 | **HOLD / NOT_AUDITED** |
| Full-Feature Beta / Commercial | **HOLD / NO** |

**최종 시행 상태:** `A51I_R1_REAL_SIGNED_NONBILLABLE_GCP_DEVTEST_READY_FOR_C_A_DIFFERENTIAL_AUDIT / GCP_EXISTING_DEV_TEST_AUTHORIZATION_APPROVED / PAID_API_EXISTING_DEV_TEST_AUTHORIZATION_APPROVED / FULL_FEATURE_BETA_DELIVERY_HOLD / COMMERCIAL_RELEASE_READY=NO`.
