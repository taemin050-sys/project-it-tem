# 2트랙 이미지 Python 경계

2026-11-05. 구현 중인 이미지 모듈 전용 계약이며 새 HTTP/서빙 배치 계약의 팀 합의나 배포를 뜻하지 않는다.

BackendImageInput.generation_mode는 composed/freeform 또는 생략이다. 생략은 기존 무문구 생성→별도 로컬 합성이다. freeform은 전체 copy_output과 canonical copy_hash, 일치하는 ad_copy/caption/hashtags를 요구한다. safe_zone과 함께 쓸 수 없다. layout_selection은 크기·플랫폼 구분에 사용한다. 같은 후보 job_id로 방식/카피를 바꾸면 충돌한다. 장수·후보ID·동시성·승인·팀 예산은 서빙 소유이며 이미지는 후보 하나만 처리한다. 자유형1~3장+합성형1장은 서로 다른 후보 job_id로 호출한다.

B1: 입력 계약·사전 카피/분석 검증·legacy hash 생략 정책과 12개 모의 계약 시험 완료. 프롬프트 분기/최종 export 구현·전체 회귀는 후속 단계다. 유료 API 호출 없음.
