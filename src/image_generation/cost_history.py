"""Versioned image trial inventory. Sources are evidence labels, never file IO.

One generation can cover several dimensions. Count the generation once, not
once per dimension. Output-only records assume one provider submission per
saved result; unrecorded HTTP retries are not established by this inventory.
"""

from dataclasses import dataclass


TRIAL_INVENTORY_VERSION = "image-trial-inventory-2026-11-10-v1"


@dataclass(frozen=True)
class ImageTrialStage:
    """One disjoint batch; reuse its stage_id for copied reports of that batch."""

    stage_id: str
    label: str
    observed_attempt_count: int
    assumed_attempt_count: int = 0
    usage_priced_attempt_count: int = 0
    usage_based_estimated_usd: str | None = None
    dimensions: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()
    assumption: str | None = None


PRESET_DEVELOPMENT_STAGES: tuple[ImageTrialStage, ...] = (
    ImageTrialStage(
        stage_id='cosmetics_three', label='초기 밝은 색·미니멀·클린 비교',
        observed_attempt_count=3, assumed_attempt_count=0,
        usage_priced_attempt_count=3, usage_based_estimated_usd='0.079995',
        dimensions=('palette', 'tone', 'lighting'),
        source_refs=('beautyAi/outputs/cosmetics-comparison/run-20261023T011517Z-2721464a4524/report.json',),
    ),
    ImageTrialStage(
        stage_id='matte_refinement', label='원본 무광 보존 보강',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.027410',
        dimensions=('material', 'gloss', 'product_color'),
        source_refs=('beautyAi/outputs/cosmetics-matte-refinement/run-20261023T013349Z-1a9a2852/report.json',),
    ),
    ImageTrialStage(
        stage_id='romand-live-20261029', label='롬앤 최초 배경',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.039227',
        dimensions=('concept', 'palette'),
        source_refs=('reports/romand-live-20261029/generation-result.json',),
    ),
    ImageTrialStage(
        stage_id='romand-pink-gel-live-20261102', label='핑크 젤 광고 레퍼런스 시험',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.045810',
        dimensions=('material', 'gloss', 'concept'),
        source_refs=('reports/romand-pink-gel-live-20261102/generation-result.json',),
    ),
    ImageTrialStage(
        stage_id='A0', label='A 배치 · 초기',
        observed_attempt_count=10, assumed_attempt_count=0,
        usage_priced_attempt_count=10, usage_based_estimated_usd='0.412130',
        dimensions=('composition', 'typography', 'attention'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=A0',),
    ),
    ImageTrialStage(
        stage_id='A1', label='A 배치 · 검토 반영',
        observed_attempt_count=10, assumed_attempt_count=0,
        usage_priced_attempt_count=10, usage_based_estimated_usd='0.407115',
        dimensions=('composition', 'typography', 'mobile'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=A1',),
    ),
    ImageTrialStage(
        stage_id='T0', label='테마 · 오리지널',
        observed_attempt_count=0, assumed_attempt_count=6,
        dimensions=('concept', 'palette', 'props', 'typography'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=T0',),
        assumption='저장 결과 1장당 제출 1회로 추정. HTTP 재시도와 usage는 미기록.',
    ),
    ImageTrialStage(
        stage_id='T1R', label='테마 · 재생성',
        observed_attempt_count=0, assumed_attempt_count=6,
        dimensions=('concept', 'geometry', 'typography'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=T1R',),
        assumption='저장 결과 1장당 제출 1회로 추정. HTTP 재시도와 usage는 미기록.',
    ),
    ImageTrialStage(
        stage_id='T1E', label='테마 · 이미지 편집',
        observed_attempt_count=0, assumed_attempt_count=6,
        dimensions=('geometry', 'product_color'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=T1E',),
        assumption='저장 결과 1장당 제출 1회로 추정. HTTP 재시도와 usage는 미기록.',
    ),
    ImageTrialStage(
        stage_id='T2E', label='테마 · 팀 피드백 편집',
        observed_attempt_count=0, assumed_attempt_count=6,
        dimensions=('geometry', 'typography'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=T2E',),
        assumption='저장 결과 1장당 제출 1회로 추정. HTTP 재시도와 usage는 미기록.',
    ),
    ImageTrialStage(
        stage_id='TM', label='테마 · 사용량 재계측',
        observed_attempt_count=6, assumed_attempt_count=0,
        usage_priced_attempt_count=6, usage_based_estimated_usd='0.555493',
        dimensions=('concept', 'geometry', 'typography'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=TM',),
    ),
    ImageTrialStage(
        stage_id='R2', label='R2 · 두 제품 적용',
        observed_attempt_count=12, assumed_attempt_count=0,
        usage_priced_attempt_count=12, usage_based_estimated_usd='1.124376',
        dimensions=('concept', 'geometry', 'props'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=R2',),
    ),
    ImageTrialStage(
        stage_id='R2AB', label='R2 · 조건 비교',
        observed_attempt_count=6, assumed_attempt_count=0,
        usage_priced_attempt_count=6, usage_based_estimated_usd='0.557295',
        dimensions=('concept', 'palette', 'typography'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/analysis.json#batch=R2AB',),
    ),
    ImageTrialStage(
        stage_id='preset-expansion-live-20261103', label='신규 8프리셋',
        observed_attempt_count=8, assumed_attempt_count=0,
        usage_priced_attempt_count=8, usage_based_estimated_usd='0.687188',
        dimensions=('concept', 'palette', 'product_color', 'tone', 'lighting', 'material', 'gloss', 'geometry', 'props', 'place_truth', 'composition', 'attention', 'typography', 'mobile'),
        source_refs=('reports/preset-expansion-live-20261103/summary.json',),
    ),
    ImageTrialStage(
        stage_id='preset-expansion-skinfood-live-20261104', label='스킨푸드 8프리셋',
        observed_attempt_count=8, assumed_attempt_count=0,
        usage_priced_attempt_count=8, usage_based_estimated_usd='0.658209',
        dimensions=('concept', 'palette', 'product_color', 'tone', 'lighting', 'material', 'gloss', 'geometry', 'props', 'place_truth', 'composition', 'attention', 'typography', 'mobile'),
        source_refs=('reports/preset-expansion-skinfood-live-20261104/summary.json',),
    ),
    ImageTrialStage(
        stage_id='skinfood-dimension-refinement-live-20261104', label='필수 디멘션+2레퍼런스 8프리셋 재출력',
        observed_attempt_count=8, assumed_attempt_count=0,
        usage_priced_attempt_count=8, usage_based_estimated_usd='0.639596',
        dimensions=('concept', 'palette', 'product_color', 'tone', 'lighting', 'material', 'gloss', 'geometry', 'props', 'place_truth', 'composition', 'attention', 'typography', 'mobile'),
        source_refs=('reports/skinfood-dimension-refinement-live-20261104/summary.json',),
    ),
    ImageTrialStage(
        stage_id='aspect_ratio', label='비율·합성 카피 배치 최초12+보강3',
        observed_attempt_count=15, assumed_attempt_count=0,
        usage_priced_attempt_count=15, usage_based_estimated_usd='1.109060',
        dimensions=('composition', 'attention', 'typography', 'mobile'),
        source_refs=('reports/aspect-ratio-experiment-20261104/publication-data.json',),
    ),
    ImageTrialStage(
        stage_id='prompt_refinement_recovery', label='프롬프트 보강 PNG 최초 실패·재실행',
        observed_attempt_count=1, assumed_attempt_count=1,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.054406',
        dimensions=('composition', 'geometry', 'typography'),
        source_refs=('reports/ad-prompt-refinement-live-20261105/image/measurement.json', 'reports/ad-prompt-refinement-live-20261105/image-recovery/measurement.json'),
        assumption='최초 FAILED_OR_UNKNOWN 기록을 제출 1회로 추정. 복구 성공 호출과 별도로 집계.',
    ),
    ImageTrialStage(
        stage_id='layout-reference-live-20261105', label='레이아웃 참조 입력',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.067520',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/layout-reference-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='ui-occlusion-reference-live-20261105', label='UI 가림 영역 참조',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.066940',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/ui-occlusion-reference-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='ui-expanded-guide-live-20261105', label='안전 영역 확대',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.067930',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/ui-expanded-guide-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='ui-clearance-live-20261105', label='안전 영역 여유 추가',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.067885',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/ui-clearance-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='ui-person-live-20261105', label='인물 구도의 안전 영역 비교',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.068600',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/ui-person-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='label-text-generation-live-20261105', label='라벨 문자열 지정',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.069800',
        dimensions=('geometry', 'typography'),
        source_refs=('reports/label-text-generation-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='label-text-eight-lines-live-20261105', label='라벨 문자열 8줄 보강',
        observed_attempt_count=1, assumed_attempt_count=0,
        usage_priced_attempt_count=1, usage_based_estimated_usd='0.070060',
        dimensions=('geometry', 'typography'),
        source_refs=('reports/label-text-eight-lines-live-20261105/measurement.json',),
    ),
    ImageTrialStage(
        stage_id='ddak-padding-two-ref-live-20261105', label='받은 프롬프트에 패딩·참조 2장',
        observed_attempt_count=6, assumed_attempt_count=0,
        usage_priced_attempt_count=6, usage_based_estimated_usd='0.418515',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/ddak-padding-two-ref-live-20261105/summary.json',),
    ),
    ImageTrialStage(
        stage_id='ddak-padding-no-platform-live-20261105', label='플랫폼 문구 제거·패딩 비교',
        observed_attempt_count=2, assumed_attempt_count=0,
        usage_priced_attempt_count=2, usage_based_estimated_usd='0.138925',
        dimensions=('composition', 'mobile'),
        source_refs=('reports/ddak-padding-no-platform-live-20261105/summary.json',),
    ),
    ImageTrialStage(
        stage_id='beta-label-padding-six-live-20261105', label='베타 표기·라벨 문자열·패딩 보강',
        observed_attempt_count=6, assumed_attempt_count=0,
        usage_priced_attempt_count=6, usage_based_estimated_usd='0.418815',
        dimensions=('geometry', 'typography'),
        source_refs=('reports/beta-label-padding-six-live-20261105/summary.json',),
    ),
    ImageTrialStage(
        stage_id='composed_dimension_pilot', label='인물 제외 합성형 14디멘션 2제품 검증',
        observed_attempt_count=2, assumed_attempt_count=0,
        usage_priced_attempt_count=2, usage_based_estimated_usd='0.140064',
        dimensions=('concept', 'palette', 'product_color', 'tone', 'lighting', 'material', 'gloss', 'geometry', 'props', 'place_truth', 'composition', 'attention', 'typography', 'mobile'),
        source_refs=('reports/composed-dimensions-pilot-20261109/AV/result.json', 'reports/composed-dimensions-pilot-20261109/MD/result.json'),
    ),
    ImageTrialStage(
        stage_id='romand-typography-20261029', label='고딕·타이포그래피',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('typography', 'mobile'),
        source_refs=('reports/romand-typography-20261029/report.md',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='romand-vue-fabric-20261029', label='뷰 패브릭 편집',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('typography', 'mobile'),
        source_refs=('reports/romand-vue-fabric-20261029/report.md',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='romand-reference-three-20261029', label='브랜드 광고 배치 3안',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('composition', 'typography'),
        source_refs=('reports/romand-reference-three-20261029/report.md',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='romand-three-dimensions-20261029', label='색·각도·굵기·서체',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('palette', 'geometry', 'typography'),
        source_refs=('reports/romand-three-dimensions-20261029/report.md',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='romand-bright-tones-20261029', label='밝은색 톤',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('palette', 'tone'),
        source_refs=('reports/romand-bright-tones-20261029/report.md',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='romand-a-fonts-20261109', label='A 고딕·라운드·명조',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('typography',),
        source_refs=('reports/romand-a-fonts-20261109/validation.json',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='original-label-pixel-composite-20261105', label='원본 라벨 픽셀 합성',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('geometry', 'product_color'),
        source_refs=('reports/original-label-pixel-composite-20261105/report.md',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
    ImageTrialStage(
        stage_id='instagram-ui-safe-20261104', label='UI 가림 시뮬레이션',
        observed_attempt_count=0, assumed_attempt_count=0,
        dimensions=('composition', 'mobile'),
        source_refs=('reports/instagram-ui-safe-20261104/validation.json',),
        assumption='기존 이미지의 로컬 편집으로 추가 이미지 API 호출 0회. 사람 작업과 컴퓨팅 비용은 미계측.',
    ),
)

AD_PRODUCTION_HISTORY_STAGES: tuple[ImageTrialStage, ...] = (
    ImageTrialStage(
        stage_id='avene_geometry', label='아벤느 밝은색 최초+비율 보정',
        observed_attempt_count=2, assumed_attempt_count=0,
        usage_priced_attempt_count=2, usage_based_estimated_usd='0.100846',
        dimensions=('geometry', 'product_color'),
        source_refs=('reports/initial-method-cost-change-20261103/analysis/avene-reuse-analysis.json',),
    ),
)

UNMETERED_TOOL_STAGES: tuple[ImageTrialStage, ...] = (
    ImageTrialStage(
        stage_id='peach_glow_tool', label='피치 글로우 배경·컨셉 재설계',
        observed_attempt_count=0, assumed_attempt_count=2,
        dimensions=('concept', 'palette', 'tone', 'props'),
        source_refs=('reports/romand-peach-glow-live-20261029/generation-result.json', 'reports/romand-peach-glow-v2-live-20261029/status.json'),
        assumption='내장 이미지 도구 결과 1장당 API 동등 시도 1회로 환산. 팀 API 지출이 아님.',
    ),
    ImageTrialStage(
        stage_id='label_builtin', label='라벨 수정 도구 비교',
        observed_attempt_count=0, assumed_attempt_count=4,
        dimensions=('geometry', 'product_color'),
        source_refs=('reports/label-composite-trial-20261105/measurement.json',),
        assumption='내장 이미지 도구 결과 1장당 API 동등 시도 1회로 환산. 팀 API 지출이 아님.',
    ),
)

# This source window is a reproducible inventory, not a lifetime account audit.
# The 16-run Skinfood reference in cost_estimate.py is already counted here as
# two eight-run stages. Historical 4-vs-1 savings is a scenario over some of
# these trials, not another expense. Do not sum the scenario and the inventory.
# GIF, reviewer/text APIs, human labor and undocumented HTTP retries are outside
# the still-image API scope. Local processing rows explicitly have zero calls.
