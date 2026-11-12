# 시각 검수 체크박스 및 글자 영역 맞춤

호환 브리지·복귀 소스: `bea6f36349cf70315f84e184e0edd309cc372aa7` (Tree `aaa207e19f50b5f1a4e568c3b5f654e971ed35d6`). 이후 전진 후보는 이 문서에 기준점을 추가한 동일 구현이다. 새 교정 버전 또는 체크박스 승인 기록 생성 이후 구형 소스로 복귀하지 않는다. 실제 복귀 실행 성공을 주장하지 않는다.

로컬 검증: 관련 Python 103 PASS, 최종 글자 맞춤/수정 API 49 PASS, React 86 PASS, TypeScript/Vite build PASS. Lint는 기존 FinalInpaintingPanel의 effect 내 setState 경고 1건을 유지한다. 실제 서버 결과와 사람 품질 승인은 별도로 수집한다.

합성형 직접 수정본, 자유형 원본 및 자유형 교정본의 승인 과정에서 문구를 다시 입력하지 않는다. 제품·라벨·CTA·승인 문구를 실제 이미지와 대조한 체크박스로 승인 의사를 기록한다. 기존 정확한 문구 전사 방식은 과거 API 호환성을 위해 지원하되 새 화면에서 요구하지 않는다.

서버는 필수 검수 값이 실제 boolean true인지 확인하고, `copy_verified: true`를 사용자 시각 대조 확인으로 기록한다. 이것은 OCR 또는 자동 문자 검증 결과가 아니다. 승인 Copy SHA, F09, Actor ACL, 이미지 SHA 및 승인 CAS는 유지한다. 새 이미지 SHA가 표시되면 체크박스 상태를 초기화한다.

## 자유형 AI 글자 맞춤

기존 방식은 모델이 생성한 글자를 요청 영역에서 그대로 잘라 복사했다. 모델의 문구가 그 영역보다 커지면 글자 일부가 잘렸다. 새 `fit-bounded-matte-text-edit-v7`은 분리된 원문 글자 표본을 제공하고, 모델이 만든 글자 전체를 추출하여 원문 크기 및 선택 영역 내부 여백에 맞게 비율을 유지하며 축소한다. 새 폰트로 문구를 재작성하지 않는다.

모델이 반환한 글자가 추출 범위 경계에서 이미 잘렸으면 오류로 중단한다. 선택 영역 밖의 픽셀은 변경하지 않는다. 원문 글자가 있던 배경의 국소 복원은 추정이므로 실제 배경·글꼴·철자·굵기·위계는 사람이 다시 검수한다. 범위 안 픽셀 변경만으로 광고 품질 PASS를 선언하지 않는다.

기존 미승인 AI 글자 분리 수정본은 `POST /demo/api/live/jobs/{job}/image-corrections/{id}/fit-text`로 추가 모델 호출 없이 재배치할 수 있다. 요청에는 현재 revision 및 preview SHA가 필요하다. 기존 Provider 결과와 영수증 및 CostLedger를 확인한 뒤 원본 Preview/Receipt를 콘텐츠 SHA 경로에 보존하고 새 Preview/Receipt와 revision을 생성한다. 새 영수증의 `local_text_fit.additional_provider_calls`는 0이며 기존 Provider 비용을 새로 계상하지 않는다. 새 결과도 REVIEW_REQUIRED이다. 완료·거절·오래된·다른 Actor의 수정본에는 적용할 수 없다.

기존 운영 및 사용자 산출물은 공개 Git에 포함하지 않는다. 실제 검증 자료와 배포 SHA는 비공개 로컬 C-B 제출서에서 관리한다. CODE/FIXTURE/REAL/HUMAN/RELEASE는 별도이며 제품 상태는 NOT_RELEASE_READY이다.

Native Owner 저장소의 정규화 PNG는 메타데이터 제거·재압축으로 Provider 응답 PNG와 바이트 SHA가 다를 수 있다. 원본 Provider Attempt 및 request SHA를 확인하고 저장소 AssetRef의 SHA를 검증한 뒤, 같은 정규화 규칙을 적용한 응답 픽셀을 대조한다. 콘텐츠 변경 거부와 메타데이터 차이 허용을 각각 회귀 검증한다. 추가 Provider 호출 없이 기존 미승인 수정본만 파생한다.
