from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .schemas import EvalSuiteResult


def write_markdown_report(result: EvalSuiteResult, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# NexusAI Eval Report")
    lines.append("")
    lines.append(f"生成时间：{datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    lines.append("## 1. 总览")
    lines.append("")
    lines.append("| 指标 | 值 |")
    lines.append("|---|---:|")
    lines.append(f"| Total | {result.total} |")
    lines.append(f"| Passed | {result.passed} |")
    lines.append(f"| Failed | {result.failed} |")
    lines.append(f"| Pass Rate | {result.pass_rate:.2%} |")
    lines.append("")

    lines.append("## 2. 分类指标")
    lines.append("")
    lines.append("| Category | Total | Passed | Failed | Pass Rate | Avg Score |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for category, summary in sorted(result.category_summary.items()):
        lines.append(
            "| {category} | {total} | {passed} | {failed} | {pass_rate:.2%} | {avg_score:.2f} |".format(
                category=category,
                total=summary["total"],
                passed=summary["passed"],
                failed=summary["failed"],
                pass_rate=summary["pass_rate"],
                avg_score=summary["avg_score"],
            )
        )
    lines.append("")

    failed_results = [item for item in result.results if not item.passed]
    lines.append("## 3. 失败 Case")
    lines.append("")
    if not failed_results:
        lines.append("无失败 case。")
    else:
        for item in failed_results:
            lines.append(f"### {item.case_id}")
            lines.append("")
            lines.append(f"- Category: `{item.category}`")
            lines.append(f"- Score: `{item.score}`")
            lines.append(f"- Reasons: `{item.reasons}`")
            lines.append(f"- Metrics: `{item.metrics}`")
            lines.append(f"- Route: `{item.output.route_decision}`")
            lines.append(f"- Tools: `{item.output.tool_calls}`")
            lines.append(f"- Latency: `{item.output.latency_ms}` ms")
            lines.append("")

    lines.append("## 4. Case 明细")
    lines.append("")
    lines.append("| Case | Category | Passed | Score | Latency |")
    lines.append("|---|---|---:|---:|---:|")
    for item in result.results:
        lines.append(
            f"| {item.case_id} | {item.category} | {str(item.passed)} | {item.score:.2f} | {item.output.latency_ms or 0} |"
        )
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
