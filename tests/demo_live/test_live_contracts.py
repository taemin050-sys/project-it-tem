"""Owner schemas, no OpenAI client import, paid calls or network."""
import copy
import json
from pathlib import Path

import pytest

from demo_staging.live.contracts import LiveGateError,strict_review
from demo_staging.live.store import LiveStore

F=Path(__file__).resolve().parents[2]/"docs/contracts/fixtures"

def fixture(name):
    return json.loads((F/name).read_text(encoding="utf8"))

def sample_input(brand="라움",product="데일리 크림"):
    return {"product":{
        "brand_name":brand,"product_name":product,"product_category":"스킨케어",
        "features":"보습과 촉촉한 사용감","ad_purpose":"신제품 홍보",
        "is_functional":False,"photo_verified":True,
        "product_image_count":2,"reference_image_count":0,
    },"customer_request_id":"request-identity-123456"}

def assets():
    return [{"role":"product","asset_id":"a"*32,"sha256":"a"*64},
            {"role":"product","asset_id":"b"*32,"sha256":"b"*64}]

def samples():
    return (
      {"analysis":fixture("product_analysis.json"),"analysis_succeeded":True,"error":None},
      fixture("research_result_no_search.json"),
      fixture("ad_copy_output.json"),
      fixture("image_prompt_output.json")
    )

@pytest.fixture()
def store(tmp_path):
    repo=LiveStore(tmp_path/"live.sqlite")
    repo.create("alice","e"*32,sample_input(),assets())
    return repo

def stage(repo):
    analysis,research,copy_obj,_=samples()
    return repo.store_text("alice","e"*32,analysis,research,copy_obj)

def safe_copy():
    a,r,c,p=samples()
    c["ad_copy"]={"headline":"데일리 크림","subline":"매일 촉촉한 사용감","cta":"지금 만나보세요"}
    c["caption"]="매일 수분감 있는 케어"
    c["hashtags"]=["#데일리","#보습"]
    return a,r,c,p

def test_exact_product_snapshot_persistent_and_no_duplicate(store):
    stored=store.get("alice","e"*32)
    assert stored["input_sha"] and stored["state"]=="INPUT_STORED"
    assert json.loads(stored["input_json"])["product"]["features"]=="보습과 촉촉한 사용감"
    assert store.create("alice","e"*32,sample_input(),assets())["input_sha"]==stored["input_sha"]
    with pytest.raises(LiveGateError,match="LIVE_INPUT_CONFLICT"):
        store.create("alice","e"*32,sample_input(brand="changed"),assets())
    with pytest.raises(LiveGateError,match="LIVE_JOB_NOT_FOUND"):
        store.get("bob","e"*32)

@pytest.mark.parametrize("change",["count","verified","empty","boolean","extra"])
def test_input_invalid_fails_before_image_or_provider(tmp_path,change):
    p=sample_input()
    if change=="count":p["product"]["product_image_count"]=5
    if change=="verified":p["product"]["photo_verified"]=False
    if change=="empty":p["product"]["product_name"]=""
    if change=="boolean":p["product"]["is_functional"]="false"
    if change=="extra":p["product"]["ad_purpose_extra"]="not-approved"
    with pytest.raises(LiveGateError):
        LiveStore(tmp_path/"q.sqlite").create("alice","e"*32,p,assets())

def test_vlm_failed_fails_closed_before_commit(store):
    a,r,c,p=samples()
    for x in [False,"true"]:
        mutated=copy.deepcopy(a)
        mutated["analysis_succeeded"]=x
        with pytest.raises((ValueError,LiveGateError)):
            store.store_text("alice","e"*32,mutated,r,c)
    assert store.get("alice","e"*32)["state"]=="INPUT_STORED"

def test_brand_risk_second_claim_not_exempt():
    a,r,cp,p=safe_copy()
    product=sample_input(brand="치료")["product"]
    cp["ad_copy"]["headline"]="치료 크림으로 치료"
    report=strict_review(cp,product,a)
    assert report["passed"] is False
    assert any(x["risk_level"]=="위반 의심" and x["text"]=="치료" for x in report["issues"])
    assert strict_review(safe_copy()[2],sample_input()["product"],a)["passed"] is True

def test_failed_real_compliance_blocks_approval_and_prompt(store):
    a,r,c,p=samples()
    c["ad_copy"]["headline"]="아토피 치료 크림"
    st=store.store_text("alice","e"*32,a,r,c)
    assert json.loads(st["compliance_json"])["passed"] is False
    with pytest.raises(LiveGateError,match="REAL_COMPLIANCE_BLOCKED"):
        store.approve_copy("alice","e"*32,st["generation"],st["review_sha"])
    with pytest.raises(LiveGateError,match="PROMPT_REQUIRES_COPY_APPROVAL"):
        store.store_prompt("alice","e"*32,p)

def test_copy_change_revert_monotonic_rev_and_no_old_approval(tmp_path):
    s=LiveStore(tmp_path/"live.sqlite")
    s.create("alice","e"*32,sample_input(),assets())
    a,r,c,p=safe_copy()
    st=s.store_text("alice","e"*32,a,r,c)
    assert json.loads(st["compliance_json"])["passed"] is True
    approved=s.approve_copy("alice","e"*32,st["generation"],st["review_sha"])
    orig_generation=approved["generation"]
    orig_approval=approved["approval_sha"]
    changed=copy.deepcopy(c);changed["caption"]="새로운 문구"
    updated=s.edit_copy("alice","e"*32,changed)
    assert updated["approval_sha"] is None
    returned=s.edit_copy("alice","e"*32,c)
    assert returned["copy_sha"]==st["copy_sha"]
    assert returned["generation"]==orig_generation+2
    with pytest.raises(LiveGateError,match="STALE_REVIEW_OR_REVISION"):
        s.approve_copy("alice","e"*32,orig_generation,st["review_sha"])
    latest=s.approve_copy("alice","e"*32,returned["generation"],returned["review_sha"])
    assert latest["approval_sha"]!=orig_approval
    with pytest.raises(ValueError,match="PROMPT_PLAN_MISMATCH"):
        s.store_prompt("alice","e"*32,dict(p,concept="not-the-plan"))

def test_image_owner_dto_and_full_approved_composition_boundary(tmp_path):
    s=LiveStore(tmp_path/"live.sqlite")
    s.create("alice","e"*32,sample_input(),assets())
    a,r,c,p=safe_copy()
    st=s.store_text("alice","e"*32,a,r,c)
    appr=s.approve_copy("alice","e"*32,st["generation"],st["review_sha"])
    ready=s.store_prompt("alice","e"*32,p)
    req=s.image_request("alice","e"*32,[b"png-A",b"png-B"],[])
    assert req.copy_revision==ready["generation"]
    assert req.copy_hash==ready["copy_sha"]
    assert req.image_prompt.concept==c["plan"]["concept"]
    # Offline simulated image bytes are not mistaken for real provider completion.
    with pytest.raises(LiveGateError,match="FINAL_REQUIRES_IMAGE_APPROVAL"):
        s.composed("alice","e"*32,"f"*64,"c"*64)
    s.store_image_candidate("alice","e"*32,"a"*64)
    with pytest.raises(LiveGateError,match="IMAGE_APPROVAL_MISMATCH"):
        s.approve_image("alice","e"*32,"b"*64)
    s.approve_image("alice","e"*32,"a"*64)
    result=s.composed("alice","e"*32,"f"*64,"c"*64)
    assert result["state"]=="COMPLETED"
    assert result["final_sha"]=="f"*64
    assert result["caption_sha"]=="c"*64
    with pytest.raises(LiveGateError):
        s.edit_copy("alice","e"*32,c)

def test_warning_requires_explicit_ack_and_approval_binding(tmp_path):
    s=LiveStore(tmp_path/"a.sqlite")
    s.create("alice","e"*32,sample_input(),assets())
    a,r,c,p=safe_copy()
    c["ad_copy"]["headline"]="임상 테스트 완료 크림"
    row=s.store_text("alice","e"*32,a,r,c)
    report=json.loads(row["compliance_json"])
    assert report["passed"] is True
    assert any(x["risk_level"]=="근거 확인 필요" for x in report["issues"])
    with pytest.raises(LiveGateError,match="EVIDENCE_ACKNOWLEDGEMENT_REQUIRED"):
        s.approve_copy("alice","e"*32,row["generation"],row["review_sha"])
    approved=s.approve_copy("alice","e"*32,row["generation"],row["review_sha"],
                           acknowledge_evidence=True)
    assert approved["evidence_acknowledged"]==1
    assert approved["approval_sha"]
    assert approved["state"]=="COPY_APPROVED"
    assert approved["approval_sha"]==s.approval_binding(approved)


def test_copy_rejection_revision_and_image_rejection_terminal(tmp_path):
    s=LiveStore(tmp_path/"a.sqlite")
    s.create("alice","e"*32,sample_input(),assets())
    a,r,c,p=safe_copy()
    st=s.store_text("alice","e"*32,a,r,c)
    rejected=s.reject_copy("alice","e"*32)
    assert rejected["state"]=="COPY_REJECTED"
    with pytest.raises(LiveGateError):
        s.approve_copy("alice","e"*32,st["generation"],st["review_sha"])
    revised=copy.deepcopy(c)
    revised["caption"]="수정 후 다시 검수되는 내용"
    reevaluated=s.edit_copy("alice","e"*32,revised)
    assert reevaluated["generation"]==st["generation"]+1
    approved=s.approve_copy("alice","e"*32,reevaluated["generation"],reevaluated["review_sha"])
    assert approved["state"]=="COPY_APPROVED"
    s.store_prompt("alice","e"*32,p)
    s.store_image_candidate("alice","e"*32,"a"*64)
    denied=s.reject_image("alice","e"*32,"a"*64)
    assert denied["state"]=="IMAGE_REJECTED"
    with pytest.raises(LiveGateError):
        s.approve_image("alice","e"*32,"a"*64)
    with pytest.raises(LiveGateError):
        s.composed("alice","e"*32,"f"*64,"c"*64)
