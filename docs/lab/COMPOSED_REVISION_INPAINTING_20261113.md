# 승인된 합성형 수정본 부분 수정

원본 합성형의 이미지 승인이 아직 없더라도, 카피를 직접 수정하고 새 F09·Copy 승인·Image 승인을 모두 완료한 합성형 수정본에는 최종 광고 부분 수정 도구를 제공한다. 기존 Konva 마스크 편집기·FinalInpainting Worker·독립 검수·다운로드를 재사용한다.

`GET /demo/api/live/jobs/{job}/final-inpainting?source_edit_id={edit}`로 해당 수정본을 불러오고, POST에도 같은 `source_edit_id`와 정확한 이미지·카피·승인 SHA를 전달한다. `source` GET도 수정 ID를 결속한다. 원본 최종 광고의 기존 요청과 경로는 그대로 유지한다. 서로 다른 수정본과 원본의 목록·React Query 캐시는 분리한다.

서버는 원본 Job의 Signed Actor ACL 및 F09, 수정본의 별도 F09 비용 Receipt·Copy 승인, COMPLETED 상태, 최종 PNG·Caption·Receipt SHA 및 시각 검수 기록을 검증한다. 요청·Worker·검수·다운로드 시 같은 원본 맥락을 다시 확인한다. 파생 Receipt의 source_context에는 APPROVED_COMPOSED_COPY_EDIT, source_edit_id, source_edit_revision 및 수정본의 Copy/Approval/Receipt SHA를 기록한다. 새 이미지나 카피 승인을 원본 Job에 자동 반영하지 않는다.

원본이 아닌 수정본을 조용히 선택하는 fallback은 없다. 선택한 수정본이 미승인·거절·변조됐거나 F09/승인 맥락이 바뀌면 유료 전송 전에 차단한다. 새 요청은 기존 Worker-only 모델 연결과 UNKNOWN/idempotency 규칙을 따른다. 원본과 승인된 수정본은 덮어쓰지 않는다. DB 스키마는 변경하지 않는다.

배포·복귀 후보는 이 선택 계약을 모두 지원하는 소스로 고정한다. 새 source_edit_id 요청 후 해당 계약을 모르는 구형 Worker로 복귀하지 않는다. MockTransport 검증은 실제 추가 유료 생성·사람 수용과 구별한다. 제품은 NOT_RELEASE_READY이다.
