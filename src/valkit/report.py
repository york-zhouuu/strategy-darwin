"""统一 go/no-go 报告生成。所有战场同一格式,便于横向比。格式沿用 tradeagent3 的判定表。"""
from __future__ import annotations

from typing import Optional, Sequence

from .prereg import Prereg
from .stats import Summary


def _row(h: int, s: Optional[Summary], costs: Sequence[float]) -> str:
    """一行:持有期 + n/命中/signZ/均值/中位 + 每个成本水平的净值(各自成列)。"""
    if s is None:
        return f"| {h} | 样本不足 |" + " |" * (4 + len(costs))
    nets = "".join(f" {s.net(c):+.4f} |" for c in costs)
    return (f"| {h} | {s.n} | {s.hit:.0%} | {s.sign_z:+.2f} "
            f"| {s.mean:+.4f} | {s.median:+.4f} |" + nets)


def go_no_go(prereg: Prereg, verdict: dict, *,
             full: dict[int, Optional[Summary]],
             by_period: dict[object, dict[int, Optional[Summary]]] = None,
             costs: Sequence[float] = (0.02, 0.04),
             coverage: str = "", limitations: Sequence[str] = ()) -> str:
    """产出 markdown 报告字符串。"""
    L = []
    emoji = "🟢 GO" if verdict["passed"] else "🔴 NO-GO"
    L.append(f"# {prereg.thesis_id} —— 验证结论 (go/no-go)\n")
    L.append(f"> 预注册 hash `{prereg.hash()}` · 假设：{prereg.hypothesis}\n")
    L.append(f"## 判定：{emoji}\n\n{verdict['reason']}\n")

    L.append("### 预注册门槛判定\n")
    L.append("| 门槛 | 通过? |\n|---|---|")
    for k, v in verdict["checks"].items():
        L.append(f"| {k} | {'✅' if v else '❌'} |")
    L.append("")

    ch = "| 持有期 | n | 命中 | signZ | 均值 | 中位 | " + " | ".join(f"净@{c}" for c in costs) + " |"
    sep = "|" + "---|" * (6 + len(costs))
    L.append(f"## 全样本 (主桶 ={prereg.primary_bucket})\n\n{ch}\n{sep}")
    for h, s in full.items():
        L.append(_row(h, s, costs))
    L.append("")

    if by_period:
        L.append("## 时间衰减切片 (edge 是否被套利磨平)\n")
        L.append(f"| 期 | " + f"n | 命中 | signZ | 净@{costs[0]} |")
        L.append("|---|---|---|---|---|")
        H = prereg.primary_horizon
        for k, res in by_period.items():
            s = res.get(H)
            if s is None:
                L.append(f"| {k} | 样本不足 ||||"); continue
            L.append(f"| {k} | {s.n} | {s.hit:.0%} | {s.sign_z:+.2f} | {s.net(costs[0]):+.4f} |")
        L.append("")

    if coverage:
        L.append(f"## 覆盖\n\n{coverage}\n")
    if limitations:
        L.append("## 已知局限\n")
        for x in limitations:
            L.append(f"- {x}")
    return "\n".join(L)
