"""Explicit checkboxes, not a fabricated user transcription."""
import pytest
from demo_staging.live.visual_review import copy_review_valid
COPY={'headline':'헤드','subline':'두 줄\n문구','cta':'확인'}
REQUIRED={'product_matches','label_matches','cta_policy_matches','no_extra_text'}
@pytest.mark.parametrize('value',[False,None,1,'true'])
def test_checkbox_copy_check_must_be_explicit_boolean(value):
 checks={k:True for k in REQUIRED};checks['copy_verified']=value
 assert not copy_review_valid(checks,COPY,REQUIRED)
def test_checklist_and_exact_server_copy_remain_bound_without_transcription():
 checks={k:True for k in REQUIRED};checks['copy_verified']=True
 assert copy_review_valid(checks,COPY,REQUIRED)
 for key in REQUIRED:
  assert not copy_review_valid({**checks,key:False},COPY,REQUIRED)
 assert not copy_review_valid({**checks,'observed_copy':COPY},COPY,REQUIRED)
 assert copy_review_valid({**{k:True for k in REQUIRED},'observed_copy':COPY},COPY,REQUIRED)
 assert not copy_review_valid({**{k:True for k in REQUIRED},'observed_copy':{**COPY,'subline':'다름'}},COPY,REQUIRED)
