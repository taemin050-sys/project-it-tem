"""규제 검수 평가 : 평가셋 문장마다 rule_checker를 돌려 기대 결과와 비교

실행 : python -m scripts.eval_compliance [평가셋 경로]  (기본 : eval_set.jsonl, 홀드아웃 : eval_holdout.jsonl)
- expected : 위반 의심 / 근거 확인 필요 / 정상 (문장에서 나와야 하는 가장 높은 위험도)
- 검출률 : 위반 문장(위반 의심 + 근거 확인 필요) 중 하나라도 걸린 비율
- 오탐률 : 정상 문장 중 하나라도 걸린 비율
- 위험도 일치율 : 걸린 표현 중 가장 높은 위험도가 expected와 같은 비율
- 평가셋에서 생략한 항목은 기본값 (product_type 스킨케어, 일반 화장품, 브랜드명·제품명 없음)
"""

import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from src.text_generation.compliance.rule_checker import RISK_ORDER, check_text

DEFAULT_PATH = Path("src/text_generation/compliance/eval_set.jsonl")
LEVELS = ["위반 의심", "근거 확인 필요", "정상"]


def _predict(item: dict) -> tuple[str, list]:
    """평가셋 한 줄 검수 → (가장 높은 위험도, 걸린 표현 목록)"""
    product = SimpleNamespace(
        brand_name=item.get("brand_name"),
        product_name=item.get("product_name"),
        is_functional=item.get("is_functional", False),
        functional_types=item.get("functional_types", []),
    )
    analysis = SimpleNamespace(product_type=item.get("product_type", "스킨케어"))
    issues = check_text("caption", item["text"], product, analysis)
    if not issues:
        return "정상", []
    top = max(issues, key=lambda i: RISK_ORDER[i.risk_level]).risk_level
    return top, issues


def main(path: Path) -> None:
    items = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    confusion = Counter()
    misses, false_alarms, level_wrong = [], [], []

    for item in items:
        pred, issues = _predict(item)
        exp = item["expected"]
        confusion[(exp, pred)] += 1
        found = ", ".join(f"'{i.text}'({i.risk_level})" for i in issues) or "-"
        line = f"[{item['id']:>3}] {item['text']} | 기대 {exp} | 결과 {pred} | {found} | {item['source']}"
        if exp != "정상" and pred == "정상":
            misses.append(line)
        elif exp == "정상" and pred != "정상":
            false_alarms.append(line)
        elif exp != pred:
            level_wrong.append(line)

    bad = [i for i in items if i["expected"] != "정상"]
    good = [i for i in items if i["expected"] == "정상"]
    detected = sum(confusion[(e, p)] for e in LEVELS[:2] for p in LEVELS[:2])
    false_pos = sum(confusion[("정상", p)] for p in LEVELS[:2])
    exact = sum(confusion[(e, e)] for e in LEVELS)

    print(f"\n===== 규제 검수 평가 : {path} ({len(items)}문장) =====")
    print(f"위반 문장 {len(bad)}개 | 정상 문장 {len(good)}개")
    print(f"검출률 : {detected}/{len(bad)} ({detected / len(bad):.0%})")
    print(f"오탐률 : {false_pos}/{len(good)} ({false_pos / len(good):.0%})")
    print(f"위험도 일치율 : {exact}/{len(items)} ({exact / len(items):.0%})")

    print("\n[혼동 행렬] 행 = 기대, 열 = 결과")
    print(" " * 16 + "".join(f"{p:>14}" for p in LEVELS))
    for e in LEVELS:
        print(f"{e:<14}" + "".join(f"{confusion[(e, p)]:>14}" for p in LEVELS))

    for title, rows in [
        ("놓친 위반", misses),
        ("오탐 (정상인데 걸림)", false_alarms),
        ("위험도 다름", level_wrong),
    ]:
        print(f"\n[{title}] {len(rows)}개")
        for row in rows:
            print(row)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH)
