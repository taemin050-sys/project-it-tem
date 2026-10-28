"""텍스트 모듈 스키마 (v0.8)

흐름 : 사용자 입력 → 제품 분석(VLM) → 기획 AI 사전 조사 → 콘셉트·카피 생성 → 규제 검수
      → (이미지 생성·합성은 이미지/서비스 파트) → 최종 출력(이미지 + 게시글 본문 + 해시태그)

- ProductInput       : 사용자 입력 (브랜드명, 제품명, 카테고리, 특징, 광고 목적, 기능성 여부, 사진 검증)
- ProductAnalysis    : VLM 제품 분석 결과 (제품 사진 2~5장을 함께 분석)
- ProductAnalysisResult : ProductAnalysis + 분석 성공 여부 + 실패 이유 (코드에서 조립)
- ResearchOutput     : 기획 AI 사전 조사 + 광고 방향 + 화면용 요약 (LLM 출력)
- ResearchResult     : ResearchOutput + 실제 인용 출처 + 검색 수행 여부 + 실패 이유 (코드에서 조립)
- AdCopyOutput       : 광고 콘셉트 + 카피 1개 + 게시글 본문 + 해시태그
- ImagePromptOutput  : 서빙을 거쳐 이미지 담당에게 넘길 배경 생성 프롬프트
- ComplianceReport   : 규제 검수 리포트 (4단계 사용자 카피 검토 때 경고로 표시)

* LLM이 직접 출력하는 스키마(ProductAnalysis, ResearchOutput, AdCopyOutput, ImagePromptOutput, LLMIssue)는
  Structured Outputs용이라 기본값 없이 모든 필드를 필수로 둠 (값이 없으면 None 또는 빈 리스트)

변경 이력
- v0.4 : AdCopyOutput.copy → ad_copy (Pydantic BaseModel.copy와 이름 충돌)
- v0.5 : 10/26 회의 반영
    · ProductInput에 brand_name, product_category 추가
    · ProductAnalysis.is_same_product 고도화로 이동 (MVP는 화장품 여부만 판단)
    · SourceType : "사진 분석"·"AI 추정" → "AI 추론"으로 통합 (사실 / 의견 구분)
    · Insight.url 제거 → 출처는 OpenAI 응답의 실제 인용 정보(url_citation)에서 코드로 추출 (ResearchResult.citations)
    · ResearchOutput에 display_summary(카피 검토 화면용 요약) 추가
    · ImagePromptOutput : 한국어 프롬프트, negative_prompt 제거 (금지 문구는 이미지 쪽에서 고정으로 붙임)
    · ComplianceReport.notice에 사용자 최종 확인 책임 문구 추가
- v0.6 : ContainerType에 "어플리케이터"(립글로스·틴트 등 팁으로 바르는 용기), "스틱"(립스틱·립밤 등) 추가
- v0.7 : ProductAnalysisResult 추가 (제품 분석 성공 여부·실패 이유를 서빙에 함께 전달)
- v0.8 : ResearchResult에 error 추가 (기획 AI 조사·검색 실패 이유를 서빙에 함께 전달)
"""

from typing import Literal

from pydantic import BaseModel, Field

# ---------- 공통 선택값 ----------

ProductType = Literal[
    "스킨케어", "색조", "바디", "헤어", "기타"
]  # 사용자 입력 X, VLM이 판단
ContainerType = Literal[
    "병",
    "튜브",
    "펌프",
    "스포이드",
    "자",
    "콤팩트",
    "스프레이",
    "파우치",
    "어플리케이터",
    "스틱",
    "기타",
]

# 화장품법 시행규칙 제2조 기능성화장품의 범위 (여드름 완화는 인체세정용 제품만 해당)
FunctionalType = Literal[
    "미백",
    "주름개선",
    "태닝",
    "자외선차단",
    "모발색상변화",
    "체모제거",
    "탈모완화",
    "여드름완화",
    "가려움개선",
    "튼살붉은선완화",
]

SourceType = Literal[
    "사용자 입력", "검색 결과", "AI 추론"
]  # AI 추론 = 사진 분석 + AI 판단

RiskLevel = Literal["정상", "근거 확인 필요", "위반 의심"]
RiskCategory = Literal[
    "의약품 오인",
    "기능성 오인",
    "효능 과장",
    "소비자 오인",
    "수치·임상 표현",
    "순위·최상급 표현",
    "전문가·매체 추천",
    "가상 후기",
    "확정 정보 불일치",
    "기타",
]
CopyField = Literal[
    "product_name", "headline", "subline", "cta", "caption", "hashtags", "user_text"
]


# ---------- 1. 사용자 입력 (1단계) ----------


class ProductInput(BaseModel):
    brand_name: str | None = Field(None, description="브랜드명 (필수 여부 미정)")
    product_name: str
    product_category: str | None = Field(
        None, description="제품 카테고리 (선택지·필수 여부 미정, SOT 2.4 수정 필요)"
    )
    features: str = Field(
        ..., description="제품 특징 (자유 입력, 사용자가 쓴 효능도 여기 포함)"
    )
    ad_purpose: str = Field(
        ..., description="광고 목적 (자유 입력, 예: 신제품 홍보, 겨울 할인 이벤트)"
    )
    is_functional: bool = Field(
        ...,
        description="기능성 화장품 여부 (MVP는 종류를 모르므로 기능성 표현은 '근거 확인 필요'로 처리)",
    )
    # functional_types: list[FunctionalType]  → 고도화 때 추가 (기능성 종류별 허용 표현 분기)
    photo_verified: bool = Field(
        ..., description="사진 검증 체크박스 (직접 촬영했거나 사용 권한이 있는 사진)"
    )
    product_image_count: int = Field(..., ge=2, le=5, description="제품 사진 장수")
    reference_image_count: int = Field(0, ge=0, le=5, description="배경 참고 사진 장수")


# ---------- 2. 제품 분석 결과 (VLM 출력, 제품 사진 2~5장 함께 분석) ----------


class ProductAnalysis(BaseModel):
    is_cosmetic: bool = Field(
        ..., description="화장품 사진인지 (False면 재업로드 안내)"
    )
    # is_same_product: bool  → 고도화 때 추가 (여러 장이 같은 제품인지, 처리 방식은 고도화 때 결정)
    product_type: ProductType = Field(..., description="색조 예외 규칙 적용에 사용")
    container_type: ContainerType
    colors: list[str] = Field(..., description="용기 주요 색상, 예: ['흰색', '연분홍']")
    label_text: list[str] = Field(
        ..., description="라벨에서 읽은 글자 (후면 사진 포함), 없으면 빈 리스트"
    )
    mood: list[str] = Field(
        ..., description="제품에서 느껴지는 분위기, 예: ['미니멀', '청량']"
    )
    is_transparent: bool = Field(
        ..., description="투명·반투명 용기 여부 (누끼 난이도 참고)"
    )


class ProductAnalysisResult(BaseModel):
    """코드에서 조립 (LLM 출력 아님) → 서빙에 넘기는 값"""

    analysis: ProductAnalysis
    analysis_succeeded: bool = Field(
        ..., description="분석 성공 여부 (False면 analysis는 기본값)"
    )
    error: str | None = Field(None, description="실패 이유 (성공하면 None)")


# ---------- 3. 기획 AI 사전 조사 (2단계) ----------


class Insight(BaseModel):
    text: str
    source: SourceType


class SummaryLine(BaseModel):
    text: str = Field(..., description="카피 검토 화면에 보여줄 요약 한 줄 (40자 이내)")
    source: SourceType


class ResearchOutput(BaseModel):
    """기획 AI(LLM) 출력"""

    product_summary: str = Field(
        ..., description="① 기본 조사 : 입력 정보 + 사진 분석 요약"
    )
    functional_notes: str = Field(
        ..., description="기능성 여부에 따라 쓸 수 있는 효능 표현 범위"
    )
    market_insights: list[Insight] = Field(..., description="② 시장 조사")
    similar_products: list[Insight] = Field(
        ..., description="③ 유사 제품 조사 (방향 참고만, 문구 인용 금지)"
    )
    ad_direction: str = Field(..., description="④ 광고 방향")
    display_summary: list[SummaryLine] = Field(
        ..., description="카피 검토 화면용 조사 요약 3~5줄"
    )


class Citation(BaseModel):
    title: str | None = None
    url: str


class ResearchResult(BaseModel):
    """코드에서 조립 (LLM 출력 아님) → 서빙에 넘기는 값"""

    research: ResearchOutput
    citations: list[Citation] = Field(
        default_factory=list,
        description="OpenAI 응답의 실제 인용 정보(url_citation)에서 추출한 출처",
    )
    research_performed: bool = Field(
        ..., description="웹 검색 성공 여부 (실패 시 False, 조사 내용은 전부 AI 추론)"
    )
    error: str | None = Field(None, description="실패 이유 (성공하면 None)")


# ---------- 4. 콘셉트·카피 출력 (3단계) ----------


class AdPlan(BaseModel):
    target: str
    concept: str
    key_message: str
    tone: str = Field(..., description="기획 AI가 정한 톤 (사용자 입력 아님)")
    mood: list[str] = Field(..., description="배경 무드 (이미지 프롬프트와 공유)")


class CopySet(BaseModel):
    # 카피 모양(필드 분리 여부)·글자 수는 실험 후 확정
    headline: str
    subline: str
    cta: str


class AdCopyOutput(BaseModel):
    plan: AdPlan
    ad_copy: CopySet
    caption: str
    hashtags: list[str]


# ---------- 5. 이미지 프롬프트 (LLM 출력 → 이미지 담당) ----------


class ImagePromptOutput(BaseModel):
    concept: str = Field(..., description="AdPlan.concept와 같은 값")
    prompt: str = Field(
        ..., description="한국어 배경 프롬프트 (길이는 이미지 담당 기준에 맞춤)"
    )
    mood: list[str] = Field(
        ..., description="AdPlan.mood와 같은 값 (VisualBrief.mood로 전달)"
    )


# 금지 문구(글씨·워터마크·다른 로고)와 제품 보존 문구는 이미지 쪽에서 고정으로 붙임
# VisualBrief.negative_constraints는 빈 목록([])으로 전달


# ---------- 6. 규제 검수 리포트 (4단계 경고 표시) ----------


class LLMIssue(BaseModel):
    """LLM 2차 판단 출력용 (위치는 코드에서 계산)"""

    field: CopyField
    text: str = Field(..., description="위험 표현 원문 (카피에 있는 그대로)")
    category: RiskCategory
    risk_level: RiskLevel
    reason: str
    suggestion: str | None = Field(..., description="대체 문구, 삭제 권장이면 None")


class ComplianceIssue(BaseModel):
    field: CopyField = Field(..., description="문제가 있는 위치")
    text: str = Field(..., description="위험 표현 원문")
    start: int = Field(
        ..., description="해당 필드 안 시작 글자 위치 (하이라이트용, 코드에서 계산)"
    )
    end: int
    category: RiskCategory
    risk_level: RiskLevel
    reason: str
    suggestion: str | None = Field(None, description="대체 문구, 삭제 권장이면 None")
    basis: str | None = Field(
        None, description="근거 출처, 예: '지침 별표1 p.9', 'FAQ'"
    )
    detected_by: Literal["rule", "llm"]
    auto_fixed: bool = Field(
        False, description="생성 단계에서 자동으로 대체 문구로 바꿨는지"
    )


class ComplianceReport(BaseModel):
    passed: bool = Field(
        ...,
        description="'위반 의심'이 하나도 없으면 True (False면 카피 승인 버튼 차단)",
    )
    issues: list[ComplianceIssue]
    revised_fields: dict[str, str] = Field(
        default_factory=dict,
        description="대체 문구 반영본, 예: {'headline': '...', 'caption': '...'}",
    )
    checklist: list[str] = Field(
        default_factory=list, description="게시 전 사용자가 직접 확인할 항목"
    )
    notice: str = "검수 결과는 참고용이며 법적 판단이 아닙니다. 게시 전 최종 확인 책임은 사용자에게 있습니다."
