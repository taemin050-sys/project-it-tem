"""하이라이트 위치값 확인 (API 호출 없음) : python -m scripts.test_highlight

- 터미널 : 검수 결과의 start, end로 문구에 【】 표시, text[start:end]가 맞는지 자동 확인
- 이모지가 있을 때 자바스크립트(UTF-16) 기준 위치가 얼마나 어긋나는지 표시
- HTML 미리보기 : 위험도별 색으로 칠한 화면 (outputs/highlight_preview.html, 브라우저로 열기)
"""

import html
import webbrowser
from pathlib import Path

from src.text_generation.compliance.report_builder import review_copy
from src.text_generation.compliance.rule_checker import copy_fields
from src.text_generation.schemas import (
    AdCopyOutput,
    AdPlan,
    ComplianceIssue,
    ComplianceReport,
    CopySet,
    ProductAnalysis,
    ProductInput,
)

OUT_PATH = Path("outputs/highlight_preview.html")

FIELD_NAMES = {
    "headline": "헤드",
    "subline": "서브",
    "cta": "CTA",
    "caption": "본문",
    "hashtags": "해시태그",
}
COLORS = {
    "위반 의심": ("#ffd6d6", "#d93025"),
    "근거 확인 필요": ("#fff1b8", "#b58105"),
}

PRODUCT = ProductInput(
    brand_name="테스트",
    product_name="테스트 크림",
    features="테스트",
    ad_purpose="테스트",
    is_functional=False,
    photo_verified=True,
    product_image_count=2,
)
ANALYSIS = ProductAnalysis(
    is_cosmetic=True,
    product_type="스킨케어",
    container_type="병",
    colors=[],
    label_text=[],
    mood=[],
    is_transparent=False,
)
COPY = AdCopyOutput(
    plan=AdPlan(target="-", concept="-", key_message="-", tone="-", mood=[]),
    ad_copy=CopySet(
        headline="최고의 미백 크림",
        subline="✨피부 재생✨부터 주름 개선까지",
        cta="지금 만나보세요",
    ),
    caption="테스트 크림으로 2주 만에 피부결 20% 개선! 🌿진정 효과까지.\n의사가 추천한 크림이에요.",
    hashtags=["#필수템", "#토너추천", "#줄기세포"],
)


def js_index(text: str, py_index: int) -> int:
    """파이썬 위치 → 자바스크립트(UTF-16) 위치"""
    return len(text[:py_index].encode("utf-16-le")) // 2


def mark(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + "【" + text[start:end] + "】" + text[end:]
    return text


def print_terminal(report: ComplianceReport, fields: dict[str, str]) -> bool:
    all_ok = True
    for field, text in fields.items():
        issues = [i for i in report.issues if i.field == field]
        print(f"\n[{field}] {mark(text, [(i.start, i.end) for i in issues])}")
        for i in issues:
            ok = text[i.start : i.end] == i.text
            all_ok &= ok
            js = (js_index(text, i.start), js_index(text, i.end))
            shift = (
                ""
                if js == (i.start, i.end)
                else f" | JS 기준 {js[0]}~{js[1]} (이모지로 밀림)"
            )
            print(
                f"  {'OK ' if ok else 'BAD'} '{i.text}' {i.start}~{i.end} [{i.risk_level}]{shift}"
            )
    return all_ok


def highlight_html(text: str, issues: list[ComplianceIssue]) -> str:
    parts, pos = [], 0
    for i in sorted(issues, key=lambda x: x.start):
        bg, line = COLORS[i.risk_level]
        tip = f"{i.risk_level} · {i.category}\n{i.reason}\n대체 : {i.suggestion or '삭제 권장'}\n근거 : {i.basis or '-'}"
        parts.append(html.escape(text[pos : i.start]))
        parts.append(
            f'<mark style="background:{bg};border-bottom:2px solid {line}" '
            f'title="{html.escape(tip)}">{html.escape(text[i.start : i.end])}</mark>'
        )
        pos = i.end
    parts.append(html.escape(text[pos:]))
    return "".join(parts).replace("\n", "<br>")


def write_html(report: ComplianceReport, fields: dict[str, str]) -> None:
    rows = []
    for field, text in fields.items():
        issues = [i for i in report.issues if i.field == field]
        rows.append(
            f"<tr><th>{FIELD_NAMES[field]}</th><td>{highlight_html(text, issues)}</td></tr>"
        )
    issue_rows = "".join(
        f"<tr><td>{FIELD_NAMES[i.field]}</td>"
        f"<td><mark style='background:{COLORS[i.risk_level][0]}'>{html.escape(i.text)}</mark></td>"
        f"<td>{i.risk_level}</td><td>{i.category}</td>"
        f"<td>{html.escape(i.suggestion or '삭제 권장')}</td></tr>"
        for i in report.issues
    )
    checklist = "".join(f"<li>{html.escape(c)}</li>" for c in report.checklist)
    status = "통과" if report.passed else "승인 차단 (위반 의심 표현 수정 필요)"
    status_color = "#1e8e3e" if report.passed else "#d93025"

    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>검수 하이라이트 미리보기</title>
<style>
body {{ font-family: sans-serif; max-width: 760px; margin: 32px auto; padding: 0 16px; line-height: 1.7; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 10px; text-align: left; vertical-align: top; }}
th {{ background: #f6f6f6; width: 80px; }}
mark {{ padding: 0 2px; border-radius: 3px; cursor: help; }}
.legend span {{ margin-right: 16px; }}
</style></head><body>
<h2>카피 검수 미리보기</h2>
<p style="color:{status_color};font-weight:bold">{status}</p>
<p class="legend">
<span><mark style="background:{COLORS["위반 의심"][0]}">위반 의심</mark> 승인 차단</span>
<span><mark style="background:{COLORS["근거 확인 필요"][0]}">근거 확인 필요</mark> 경고</span>
(표시된 부분에 마우스를 올리면 이유·대체 문구가 보임)
</p>
<table>{"".join(rows)}</table>
<h3>문제 표현</h3>
<table><tr><th>위치</th><th>표현</th><th>위험도</th><th>유형</th><th>대체 문구</th></tr>{issue_rows}</table>
<h3>게시 전 확인</h3><ul>{checklist}</ul>
<p style="color:#777;font-size:13px">{html.escape(report.notice)}</p>
</body></html>"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page, encoding="utf-8")


def main():
    report = review_copy(COPY, PRODUCT, ANALYSIS)
    fields = copy_fields(COPY)
    all_ok = print_terminal(report, fields)
    print(f"\n위치값 일치 : {'전부 일치' if all_ok else '불일치 있음'}")
    write_html(report, fields)
    print(f"미리보기 저장 : {OUT_PATH}")
    webbrowser.open(OUT_PATH.resolve().as_uri())


if __name__ == "__main__":
    main()
