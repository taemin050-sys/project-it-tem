"""제품 사진 분석 (VLM) : 제품 사진 2~5장 → ProductAnalysis"""

import base64
import io
import logging

from PIL import Image

from .config import MODEL_VISION
from .llm_client import LLMError, call_structured
from .schemas import ProductAnalysis, ProductAnalysisResult

logger = logging.getLogger(__name__)

MAX_SIDE = 1536

INSTRUCTIONS = """너는 화장품 제품 사진을 분석하는 도우미야.
사용자가 올린 사진 여러 장은 한 제품을 여러 각도에서 찍은 것이야. 모든 사진을 함께 보고 하나의 결과로 답해.

- is_cosmetic : 사진의 주인공이 화장품(스킨케어, 색조, 바디, 헤어 제품)이면 true, 아니면 false
- product_type : 스킨케어 / 색조(립, 아이, 베이스 메이크업 등) / 바디 / 헤어 / 기타 중 하나
- container_type : 용기 모양. 보기 중 가장 가까운 것 하나. 튜브는 짜서 쓰는 말랑한 용기, 어플리케이터는 뚜껑에 바르는 팁이 달린 용기(립글로스·틴트·컨실러), 스틱은 돌려서 올리는 용기(립스틱·립밤), 맞는 게 없으면 기타
- colors : 제품 용기와 뚜껑의 실제 색상 1~3개를 한국어로 (예: 흰색, 연두색). 배경·벽·바닥·소품 색은 넣지 마. "투명"은 색이 아니니까 넣지 마
- label_text : 사진에서 실제로 읽히는 글자만 그대로 적어. 안 보이거나 흐린 글자는 추측하지 말고 빼. 제품명·브랜드·용량 위주로 최대 15개. "기능성 화장품", "미백", "주름개선", "자외선 차단" 같은 기능성 표시 문구가 보이면 반드시 포함해
- mood : 제품 디자인에서 느껴지는 분위기 2~3개를 한국어 한 단어로 (예: 미니멀, 청량, 내추럴)
- is_transparent : 용기나 뚜껑이 투명·반투명이라 안이 비쳐 보이면 true (투명 여부는 여기에만 표시)

배경에 다른 물건이 있으면 무시하고, 사진 가운데 가장 크게 나온 제품만 분석해."""


def _to_data_url(image_bytes: bytes) -> str:
    """사진을 긴 변 MAX_SIDE 이하 JPEG로 줄여서 data URL로 변환"""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def default_analysis() -> ProductAnalysis:
    """분석 실패 시 기본값 (화장품이 아니라고 막지 않도록 is_cosmetic=True)"""
    return ProductAnalysis(
        is_cosmetic=True,
        product_type="기타",
        container_type="기타",
        colors=[],
        label_text=[],
        mood=[],
        is_transparent=False,
    )


def analyze_product(
    images: list[bytes], model: str = MODEL_VISION
) -> ProductAnalysisResult:
    """제품 사진 분석 (VLM) : 제품 사진 2~5장 → ProductAnalysisResult"""
    if not 2 <= len(images) <= 5:
        raise ValueError(f"제품 사진은 2~5장이어야 합니다. (받은 장수: {len(images)})")

    try:
        content = [
            {
                "type": "input_text",
                "text": f"제품 사진 {len(images)}장입니다. 분석해줘.",
            }
        ]
        content += [
            {"type": "input_image", "image_url": _to_data_url(b)} for b in images
        ]
        analysis = call_structured(
            [{"role": "user", "content": content}],
            ProductAnalysis,
            instructions=INSTRUCTIONS,
            model=model,
        )
        return ProductAnalysisResult(analysis=analysis, analysis_succeeded=True)
    except (LLMError, OSError) as e:
        logger.warning("제품 분석 실패, 기본값 반환: %s", e)
        return ProductAnalysisResult(
            analysis=default_analysis(), analysis_succeeded=False, error=str(e)
        )
