# Track B · 실모델 기반과 첫 4:5 개발 사례

2026-11-09 KST · `NOT_RELEASE_READY` · `integration/bp18-product-complete-20261111`

| 기준 | SHA / Tree |
|---|---|
| B0 소스 | `bd900538887c00b613e37fe9cdd2099fe73dcf7e` / `b3b169a9834fa32eeabaa2f183ab43a3a5df68a7` |
| 실행 안전성 | `a99e5fb10edb00f8821790aa3fa6bb925f243682` / `29949987b29351ae6afea6f510c05dca85a6e555` |
| macOS Export 경쟁 테스트 | `93906fe11fbad4a032be07e63e12629eb0835377` / `c1848b7a518943e9c7cb314909402daeafeae79a` |
| GCP B 개발 후보 | `4baa67eb82a07ccb3a774549346c8f622e04aa7d` / `a4dbe7fe8ab04781eeae9740246da6ddbee1bd50` |

## B1 · B 전용 Worker 기반과 배포

- B0 고정 소스의 P0 네 건을 C가 독립 재현했다. 후보는 Worker 실행 직전 Actor·Job 출처·입력/승인 SHA를 대조하고, Provider 결과 저장 트랜잭션에서도 승인 SHA를 재검증한다. Worker 잠금은 유휴 구간에도 유지한다. 시작 시 Queue와 비용 원장의 중단 상태를 함께 정리하고 자동 재실행을 차단한다.
- 실제 Provider 호출은 서명된 B 세션에서 명시적으로 요청할 때만 Queue에 들어간다. Worker의 모델·Actor·Source SHA 설정이 Web과 일치해야 한다. 사용자가 재사용을 승인한 키는 systemd 임시 자격증명을 통해 Worker에만 전달했다. Web 환경의 키 미존재를 확인했다. 정책은 `MONITOR_ONLY`이며 Worker 서비스는 `Restart=no`다.
- GCP는 기존 B5 경로로 후보와 이전 소스의 prestart, 여섯 SQLite 스냅샷, 소스 교체, Health 검증을 수행했다. 유료 큐가 꺼진 상태에서 Tailnet 서명 세션 200, 직접 미서명 요청 401, FE/Backend 후보 SHA를 확인했다. 활성화 직전 추가 백업 매니페스트 SHA-256은 `f31b5d5a15c544d0c5d4e987fc2c167a2bf364f1a34733b5acf8c082e6ee1e78`다.
- F09 정책은 `bp18-f09-two-stage-policy-v2`, epoch `2`, SHA `d5b1ff2a5beedf76b0fa9cbe9bdc157a33ce2b7be7ebddd9c4237358c1a686b6`로 활성화했다. Web·Worker 공통 실행 정책 SHA는 `78d3f250054c83f787088a1e763120a46eda35dacb9ea3fe98190cb0a1bdaee9`다. F09 계약을 만족하는 소스만 epoch 2에서 시작할 수 있다.
- 활성화 후 읽기 전용 prestart를 실행했다. 기존 `bd900538`은 `LLM_INCOMPATIBLE_RELEASE_DENIED`, 활성 후보의 변경은 Worker 잠금으로 `ACTIVE_PROVIDER_WORKER_BLOCKS_RELEASE`였다. Live18088·QA18095·A18096·B18100의 Health는 모두 200이었다.
- Python 전체 격리 회귀 **1,041 PASS**, React **53 PASS**, lint·TypeScript·고정 Vite 빌드 통과. B0 C가 재현한 macOS 자식의 SQLite 연결 실패를 독립 재현했다. 제품 CLI처럼 테스트를 두 독립 Python 프로세스에서 시작하도록 변경하고, 두 발행자가 같은 목적지에서 경쟁할 때 한쪽만 성공하고 다른 쪽은 기존 결과를 보존한다는 검증을 유지했다.
- 브라우저의 합성 데이터 회귀에서 이전 후보의 승인 POST를 차단하고, PNG·Caption의 503 각각 한 번 뒤 명시적 GET으로만 복구했다. 다운로드 바이트를 원본과 대조했고 Caption의 UTF-8 BOM까지 보존했다. 실제 광고 다운로드 증거와 별개다.

기존 Image #24 및 Integration #18 계보, FE #26의 승인 버전 확인과 B의 정책 결속을 보존했다. Research 인용 및 규칙+LLM 검수는 B에서 추가했다. Text #27의 전체 Owner 평가셋 재실행과 B3 정책 품질 평가는 남아 있다. [B0 Owner 대조](BP18_B0_CODEX_BASELINE_20261109.md)

## B2 · 아나비오스 퓨리톤 샴푸

- 실제 서명 B 관리자 Actor `bp18_b_exobiz7`는 사용자가 개발 사례에 승인했다. Job은 `68306165e96e40a4b09a379e6330804d`다. 사용권을 확인한 동일 300ml 표기의 제품 자료 두 장을 브라우저에 넣었다. 서버 업로드 SHA는 `c2869e39217b8e8d30697af2d4e9433eea41258b5e840591bcf617e3407af9e3`, `8f2ebf44c282a96e04b77aa028b44c1d2f9a78bccd56243e04155db78df71414`로 로컬 파일과 같다. 4:5 합성형 `BP18_PROVISIONAL_SIZE_4_5`를 고정했다.
- 실제 VLM이 화장품으로 분류했고, Research가 검색 출처 3개를 주장에 연결했다. 요약에 출처가 연결되지 않은 문장은 AI 추론으로 표시한다. [BeautyMatter](https://beautymatter.com/articles/the-shifts-defining-hair-care) · [YouGov 미국 조사](https://yougov.com/en-us/articles/52808-us-hair-care-trends-2025-consumer-concerns-routines-and-market) · [THG Labs](https://www.thglabs.com/resources/blog/haircare-report-q-and-a-aurelie)
- `gpt-6-luna` VLM·Research·Copy·F09 각각 실제 영수증 1개를 남겼다. 합계 26,517 토큰이며 실제 청구 금액은 확인 전이다. 최초 대기 약 2초, 분석 처리 약 25초. `BILLING_UNKNOWN`은 0건이다.
- 최초 카피 SHA `6336a7679b814e196dba172c55166e91546a9dbb525b96e7a3506b98874ee746`, 검수 SHA `2a82c9d5a607796d6eb7d4878e6c4a9255db6670a4f5176861236415f3ad0e83`다. 두 단계 검수 결과 통과, 지적 0건. 검수 영수증 SHA `4dd39fd457757316dde1bcf8b9b37a120530f21410610469601abaf8ef579629`가 Copy SHA와 정책 epoch 2에 연결돼 있다. 적용 근거는 [화장품법 제13조](https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0013&lsiSeq=291337&urlMode=lsScJoRltInfoR)에서 확인했다.
- 실제 사람의 카피 승인과 이미지 생성·시각 평가·다운로드 단계는 이어서 기록한다. 광고 품질과 PM·Owner의 최종 수용은 별도다.

검증 로그, Build SHA 목록, 조회한 Attempt·Receipt 및 승인 결속은 Mac 내부 디스크의 [B 실행 증거](/Users/Shared/ittem-bp18-codex-evidence-20261109)에 보존했다.
