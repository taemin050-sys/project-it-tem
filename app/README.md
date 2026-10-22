# app — React 프론트엔드 (권혁상)

React + Vite + TypeScript, 라우팅(react-router), 상태(Zustand), 서버 상태(TanStack Query), mock(MSW), 렌더러(html-to-image), 폰트(Pretendard).

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
| `npm test` | 업로드 검사·좌표 변환 단위 테스트 (Node 내장 테스트) |

## 현재 상태

- 화면 6개 라우트: 홈 / 제품 정보 / 광고 설정 / 기획·카피 / 이미지 시안 / 검증·내보내기(준비 중)
- mock 흐름: 제품 정보 → 광고 설정 → 생성 요청 → 상태 폴링 → 결과 표시 → 시안 PNG(1080×1350) 저장
- `src/types/draft.ts`, `src/api/jobs.ts`, `src/config.ts`의 필드명·엔드포인트·프리셋은 **합의 전 임시값**입니다.
