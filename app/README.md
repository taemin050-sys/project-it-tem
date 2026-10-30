# app — React 프론트엔드 (권혁상)

React + Vite + TypeScript, 라우팅(react-router), 상태(Zustand), 서버 상태(TanStack Query), mock(MSW), 폰트(Pretendard).

> 폴더 위치(`app/`)는 PM·이형기 님 확인 전 임시 배치입니다.

## 실행

```bash
cd app
npm ci
cp .env.example .env.local   # VITE_USE_MOCK=true면 서버 없이 mock으로 동작
npm run dev
```

| 명령 | 내용 |
|---|---|
| `npm run dev` | 개발 서버 |
| `npm run build` | 타입체크 + 빌드 |
| `npm run lint` | oxlint |
| `npm test` | 입력 검사·단계 진행·하이라이트·mock 단위 테스트 (Node 내장 테스트) |

## 현재 상태

- `/` 서비스 소개 랜딩, 우측 상단 "광고 만들기" → `/create/*` 단계 진행
- 단계: 제품 정보 → 기획·카피 검토 → 이미지 검토 → 최종 결과 (10/23·10/26 회의 기준). 지나온 단계만 되돌아갈 수 있음
- 흐름: 업로드 → 사진 분석(화장품 여부) → 사전 조사 → 카피·검수 → **카피 승인** → 이미지 생성 → **이미지 승인** → 합성 → PNG(1080×1350) + 게시글 본문·해시태그 저장. 단계 요청은 사용자 클릭에서만 보내고 자동 재시도하지 않음 (`src/api/useJob.ts`의 `advance`)
- mock에서 분기 확인: 제품명에 `비화장품` → 사진 분석 실패, `검색실패` → 검색 없이 진행, 제품 특징에 `재생` → 위반 의심으로 승인 차단
- 디자인 토큰은 `src/index.css` 상단 `:root`에 모여 있음 (아이보리 중심, 라임은 CTA·번호에만)
- 폰트: 본문 Pretendard, 로고·제목 Noto Serif KR, 번호·영문 레이블만 IBM Plex Mono. 광고 결과물은 Pretendard
- 랜딩의 시안 이미지(`public/mock/*.svg`)는 설명용 예시이며 화면에도 "예시 시안"으로 표시
- 서비스명 `IT-TEM`은 레포명 기준 가칭 (`src/config.ts`의 `SERVICE_NAME`)
- 텍스트 모듈 입출력 타입은 `src/types/textSchema.ts` (김다혜 스키마 v0.5 회의 스냅샷 기준, 원본 대조 전)
- `src/types/draft.ts`(Job·상태), `src/api/jobs.ts`(엔드포인트)는 통합 계약 v0.2의 레거시 경로·신규 Wire 제안 기준 **가정값**입니다 (`grep -rn "shortcut:" src`).
