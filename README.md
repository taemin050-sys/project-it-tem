# IT-TEM 고도화 Lab

실제 화장품 사진으로 한국어 광고를 기획하고, 카피를 수정·검수한 뒤 합성형·자유형 시안을 비교·승인·다운로드하는 **Track B 통합 베타 개발 결과**입니다.

검증된 소스 `f2066033f7253859b638be04ffa8674d90114457`를 보존한 독립 Lab입니다. 제품 상태는 **`NOT_RELEASE_READY`**이며, 구현·실모델 검증·사람 평가·최종 릴리스 승인은 구분합니다.

## 독립 관리

| 항목 | 기준 |
|---|---|
| 개발 브랜치 | `lab/ittem-enhancement-20261112` |
| PR 전용 기준 브랜치 | `lab/ittem-enhancement-baseline-20261112` |
| PR 기준 커밋 | `90249b6837a89a76f7ab9ea5cb82c8fdca3009b7` — 기존 공통 조상 |
| 원본 Track B | `integration/bp18-product-complete-20261111` / `f2066033…` 보존 |
| 독립 워크트리 | `tracks/ittem-enhancement-lab-20261112` |

PR도 Lab 기준 브랜치만 대상으로 합니다. `dev`·`main`·Track A를 자동 병합하거나 수정하지 않으며 기존 서버가 Lab을 자동 배포하지 않습니다. Git 객체 저장소는 worktree 특성상 공유하지만 작업 파일·브랜치·의존성 설치 위치는 분리합니다. 운영 DB·사진·키·Job·Queue는 가져오지 않습니다.

## 개발한 핵심 기능

| 영역 | 구현 내용 |
|---|---|
| 업로드·분석 | 제품 사진 2~5장, 참고 사진 0~5장, MPO 첫 프레임·촬영 방향 정규화와 원본 출처 결속, 실제 VLM 분석 |
| AI 기획·카피 | 검색 근거와 AI 추론 구분, Research·AdPlan·한국어 카피, 규칙+실제 LLM 2단계 검수, 수정·복원·재승인 |
| 사용자 확인 | 검수 경고를 보존하면서 현재 카피의 책임 확인으로 제작 진행. 검수 결과를 임의로 PASS로 바꾸지 않음 |
| Dual 시안 | 한 요청에서 동일 비율의 Composed 1개+Freeform 1개, 독립 후보·검수·Receipt·비용·부분 실패 관리 |
| 광고 디자인 | 한국어 Typography·줄바꿈·CTA·안전 영역, 폰트 라이선스, 3:4·4:5·9:16과 이미지 내부 CTA 정책 |
| 제품 보호 | Recipe·Asset Registry·Actor 승인 CAS·파생 원장·credential-free Worker·검수·Export. Pure Freeform과 Hybrid 구분 |
| 텍스트 수정 | Composed 카피 직접 수정, Freeform 제한 영역 AI 교정, 원본 획 정밀 교정, AI 글자 분리 교정 |
| 인페인팅 | MIT React Konva 브러시·지우개·Undo/Redo·숫자 영역 선택. 승인된 최종 광고의 선택 부분 수정과 나머지 RGB 보존 |
| 최종 저장 | 수정본 별도 사람 검수, 실제 PNG·UTF-8 Caption·Receipt 다운로드와 SHA 대조, 구버전·거절·미승인 결과 차단 |
| 보안·운영 | Signed Tailscale SSO, Actor/Job ACL, Worker-only 키, Queue·CAS·Attempt/Usage/Receipt, UNKNOWN 자동 재호출 금지, B5 배포·복귀 자격 |
| 조회 안정성 | 실제 GET 실패 원인인 Mac B 게이트웨이 accept backlog 5→128 수정, 조회 실패 시 편집 내용·기존 결과 보존 |

구현 완료가 모든 입력의 광고 품질 수용을 뜻하지 않습니다. Hybrid의 경계·중복 용기·작은 라벨 판독은 결과별 검수가 필요합니다.

## 검증 범위

- 최신 책임 확인 변경: Python 표적 **80 PASS**, React **86 PASS**, TypeScript/Vite build·lint 통과. 기존 비차단 경고 유지.
- 실제 `gpt-image-2.6-sunburst` 인페인팅: 4:5 두 모드 각각 1회, 사용자 승인 후 PNG·Caption·Receipt **6개 브라우저 다운로드 SHA 일치**. 선택 밖 RGB 차이 0, 경계 보완 추가 호출 0.
- GET 수정 후 브라우저·동시 탭·최종 재조회에서 관측된 **189개 응답의 5xx 0**. 유한 표본이며 장기 SLA가 아닙니다.
- 실제 경고 Job에서 책임 확인 체크→생성 버튼 활성화, 해제→비활성화. 검증 중 현재 카피 승인·유료 생성을 대신 실행하지 않았습니다.

기존 C-B 독립감사 이력과 최신 자체검증은 구분합니다. 전체 팀원 UAT·3개 비율의 실제 검증 범위·라벨 Ground Truth·USD 청구액 대사·최종 F/V/S38 인수는 별도입니다. [고정 스냅샷과 검증 기록](docs/lab/SNAPSHOT_20261112.md)을 확인하세요.

## 소스와 로컬 확인

`app/`: React·TypeScript·Vite UI. `demo_staging/live/`: API·승인·Queue·실모델/파생 Worker. `src/text_generation/`: VLM·Research·기획·카피. `src/image_generation/`: 모델 어댑터·Typography·합성·제품 보호. `scripts/`·`deploy/systemd/`: QA·계약·인벤토리·운영 도구.

다른 워크트리의 쓰기 가능한 의존성이나 운영 환경변수를 연결하지 말고 이 체크아웃 안에 별도 설치합니다.

```bash
cd app
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run lint
npm run build
```

Python은 별도 `.venv`를 구성합니다. `configs/requirements-serving-gcp.lock.txt`는 Linux 운영, `tests/image_generation/requirements.txt`는 별도 이미지 테스트 환경의 이력이므로 한 환경에 겹쳐 설치하는 통합 lockfile로 취급하지 않습니다. 폰트는 `assets/fonts/README.md`를 따릅니다.

실제 AI·Signed SSO 운영은 소스 고정 정책·승인 Actor·Worker 전용 키·Queue·B5 계약을 갖춘 별도 범위입니다. 이 체크아웃만으로 기존 서비스·유료 Worker를 시작하지 않습니다. 실제 제품 사진·광고·운영 원장·인증 자료는 공개 저장소에 포함하지 않습니다.

## 주요 계약

- [최종 광고 인페인팅](docs/BP18_FINAL_AD_INPAINTING_V1.md)
- [사용자 책임 확인](docs/BP18_COPY_USER_RESPONSIBILITY_V1.md)
- [GET 연결 대기열 수정](docs/BP18_B_GATEWAY_GET_BACKLOG_20261112.md)
- [카피·이미지 수정](docs/bp18-result-revision-contract.md)
- [팀 인터페이스](docs/interface_spec.md)

React Konva·Konva의 MIT 고지는 `app/public/licenses/`, Pretendard 라이선스는 `assets/fonts/`에 보존합니다.
