# IT-TEM BP17 — Copy/Planning/Image Revision 6-case 안전 회귀 매트릭스

2026-11-07 KST · Owned integration QA, not new Text Owner model behavior. Zero billable calls.

| # | 상태 전이 | 신규 Regression Test | 검증한 실제 경계 | 남은 Gate |
|---|---|---|---|---|
| 1 | Copy 변경 | `test_01_copy_edit_invalidates_active_approval_and_image_prompt_binding` | COPY_APPROVED에서 수동 카피 편집→새 Copy/Review SHA, Generation+1, Approval 해제, Prompt/Image/Final 활성 필드 NULL, 구 Review SHA로 재승인 실패 | 현재 이미 PROMPT_READY·완료된 Job의 카피 수정은 별도 계약 필요; 역사적 파일 삭제 금지 |
| 2 | Planning concept/mood 변경 | `test_02_planning_concept_or_mood_change_rebinds_next_prompt` | Copy에 포함된 plan 변경→새 Generation/Review/Approval, Owner Fake가 **새** concept/mood로 Prompt input 수신, Prompt mismatched plan은 기존 검증에서 거절 | 이미 생성된 Prompt의 **독립 기획 수정**/Text Owner Art Direction v3 정식 계약 미완료 |
| 3 | 동일 Copy/동일 검수 정책·결과 | `test_03_same_copy_and_identical_review_stays_same_generation` | Owner no-op→Copy/Review SHA와 Generation 및 Approval 유효성 보존, 이벤트 기록 | 정책 version은 현재 별도 계약 없음 |
| 4 | 동일 Copy/검수 결과 변경 | `test_04_same_copy_changed_compliance_result_invalidates_review` | `strict_review` Fake 새 결과(위반) 입력 시 Copy SHA 유지, Generation+1/Review SHA 갱신, 기존 Approval 제거, 실제 승인 불허 | 정책 **버전만 바뀌고 결과가 동일한 경우**는 미구현, B″ **HOLD** |
| 5 | Image rejection retry | `test_05_image_retry_preserves_approved_text_and_planning_no_model_replay` | 동일 승인 Copy/Planning/Prompt, 새 Attempt v2, 이전 이미지 sha archive, VLM/Research/Copy/Prompt 재호출 **0** | 실제 유료 Provider crash/unknown은 수동 원장 정합화 필요 |
| 6 | 과거 Copy 복원 + 이전 Image Attempt stale | `test_06_restored_old_copy_and_stale_attempt_never_reactivate_approval` | 이전 텍스트 SHA 복원돼도 새 Generation·Review SHA, Approval 복구되지 않음. 이전 거절 이미지 Attempt 새 Key 재사용 불허 | 역사적 Receipt/SHA 보존, 실제 모델 UAT 별도 |

실행: `tests/demo_live/test_bp17_revision_binding_matrix.py`: **6/6 PASS**. 초기 계획 test02에서 FakeOwner가 새 concept/mood를 반영하지 않은 오래된 ImagePromptOutput을 반환해 `PROMPT_PLAN_MISMATCH`가 발생했고, Fixture가 현재 입력을 따르도록 수정한 뒤 PASS. 이 초기 실패는 Owner Model 품질 결함이 아니라 Fake Fixture 부정합이다.

## 모드별 렌더링 기존 회귀 재사용

`tests/demo_live/test_bp14_single_mode.py`는 3:4·4:5·9:16 × Composed/Freeform 6개 완료 Job에 대해 결속된 Copy SHA, 단일 후보, 승인, Final 크기, 다운로드 SHA, Freeform의 `safe_zone=None` 및 이미지 텍스트 Overlay 금지(`FREEFORM_MUST_NOT_COMPOSE_TEXT`), Font SHA 없는 Owner 원본 바이트, Composed의 Server Font 합성을 검증한다. **이전 BP14 통과 계약을 보호하고 불필요하게 재구현하지 않는다.**

현재 `src/text_generation/image_prompt_generator.py`는 배경 전용 Owner 프롬프트이므로 Freeform도 승인 Head/Sub/CTA를 실제 모델 입력에 사용한 텍스트 품질 PASS가 아니다. 새로운 T/V Owner 계약과 Profile Version/SHA 서명 후 새 Fixture/Golden 추가.

## 남은 핵심 안전 결함 / 미확정 요구

- **정책 버전-only 변경:** 동일 Copy/동일 검수 출력이어도 policy SHA/version 바뀌면 이전 Review/Approval의 최신 컨텍스트 재사용 금지. 현재 DB/Owner DTO가 정책 버전을 Review SHA에 함께 결속하지 않으므로 Test04가 이를 완전히 해결한 것으로 단정할 수 없다.
- Text Owner는 `revise_copy`의 product/analysis/research/previous/request **5개 데이터 인자**를 보존하고 기술적 model/reasoning_effort 인자도 하위 호환. Compliance Context DTO는 Proposal이며 Owner가 동등 계약의 다른 인터페이스를 제출할 수 있다.
- 새 Context/PolicyVersion이 Queue context SHA, Text Checkpoint key, Generation CAS 및 Audit Event에 결속돼야 하며 이전 RUNNING/QUEUED 작업이 무단 재사용되지 않도록 Owner Source First 이후 구현/테스트.
- 독립 Planning revision/이미 완료된 Image Prompt 갱신 및 과거 완료 Job의 불변성 재검증은 별도 Versioned Owner 계약이 제출되어야 다음 단계로 진행 가능.
- Freeform은 모델이 원본 승인 카피·Typography를 직접 그리며 서버 텍스트 추가금지, Composed는 안전한 Text 영역만 생성하고 정확한 승인 카피를 서버 합성. 실제 Image Owner v3 Profile/Prompt/Layout/Font 버전·CTA(신규4:5 이미지, 9:16 Owner+PM 결정) 및 사람 검수는 PENDING.

**본 문서는 6개 현재 안전 전이 케이스의 Fixture QA PASS이며, 미확정 Owner Source/정책 Version/상용 Visual Gate 수용을 주장하지 않는다.**
