"""确认道前端:致命闸评级器 —— 把活过杀戮道的幸存者分级(毙/长期观察/重点观察)。

杀戮道回答"信号真不真";本模块回答"**真了也能不能真做**"——全口径成本、容量、可做空性、
资金费/carry、尾部/爆仓、regime 一致性、拥挤、运营。**坐标轴通用,每轴的值由战场约束模型填**
(crypto 填资金费,美股填借券费……),与 valkit 一贯的"solid 在 WHETHER、灵活在 HOW"一致。

分级不是决策,是队列:毙→回杀戮道;长期观察→放着;重点观察→进模拟操盘(验执行,非验 edge)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Constraints:
    """战场约束模型(每战场/每 thesis 填)。数值可为估计,标注来源;真值由模拟操盘周核实。"""
    all_in_cost: float          # 全口径成本(点差+费+滑点+carry),对 primary horizon
    capacity_usd: float         # 容量估计:塞多少钱才不吃掉 edge
    target_capital: float       # 你的资金规模
    shortable: str = "yes"      # 所需方向能否建仓:yes / partial / no
    ruin_risk: str = "bounded"  # bounded / unbounded(空头无上限=unbounded)
    crowding: str = "unknown"   # low / medium / high / unknown
    operational: str = "ok"     # ok / note:<...> / severe:<...>
    cost_source: str = "估计"   # 成本数字来源(估计/实测),影响可信度


@dataclass
class Axis:
    name: str
    status: str                 # pass / warn / fail
    detail: str
    fatal: bool = False         # fail 且 fatal → 直接毙


@dataclass
class GradeResult:
    tier: str                   # kill / long-watch / priority-watch
    axes: list = field(default_factory=list)
    reason: str = ""

    def show(self) -> str:
        m = {"pass": "✅", "warn": "🟡", "fail": "❌"}
        lines = [f"分级: {self.tier.upper()} — {self.reason}"]
        for a in self.axes:
            lines.append(f"  {m[a.status]} {a.name}: {a.detail}" + ("  [致命]" if a.fatal and a.status == 'fail' else ""))
        return "\n".join(lines)


def grade(primary, by_period: Optional[dict], c: Constraints, *, side_is_short: bool = False) -> GradeResult:
    """primary = 主持有期 Summary(需 .mean/.median/.hit/.sign_z/.n);by_period = {期:Summary}。"""
    axes = []

    # 1) 全口径成本(致命):净掉真实成本后仍为正
    net = primary.mean - c.all_in_cost
    axes.append(Axis("全口径成本", "pass" if net > 0 else "fail",
                     f"mean={primary.mean:+.4f} − 成本{c.all_in_cost:.4f}({c.cost_source}) = {net:+.4f}",
                     fatal=True))

    # 2) 容量(致命下限 + 警戒)
    if c.capacity_usd < 0.1 * c.target_capital:
        axes.append(Axis("容量", "fail", f"容量${c.capacity_usd:,.0f} < 资金${c.target_capital:,.0f} 的10%,几乎塞不进", fatal=True))
    elif c.capacity_usd < c.target_capital:
        axes.append(Axis("容量", "warn", f"容量${c.capacity_usd:,.0f} < 资金${c.target_capital:,.0f},需缩仓"))
    else:
        axes.append(Axis("容量", "pass", f"容量${c.capacity_usd:,.0f} ≥ 资金${c.target_capital:,.0f}"))

    # 3) 可做空性(致命):所需方向建不了仓 = 死
    if side_is_short:
        st = {"yes": "pass", "partial": "warn", "no": "fail"}[c.shortable]
        axes.append(Axis("可做空性", st, f"做空可得性={c.shortable}", fatal=(c.shortable == "no")))

    # 4) 尾部/爆仓
    if c.ruin_risk == "unbounded":
        sev = "warn" if primary.hit >= 0.6 else "fail"
        axes.append(Axis("尾部/爆仓", sev, f"无上限亏损(可被逼空),命中={primary.hit:.0%}"
                         + ("(命中偏低,单次可毁户)" if sev == "fail" else ""), fatal=(sev == "fail")))
    else:
        axes.append(Axis("尾部/爆仓", "pass", "亏损有界"))

    # 5) regime 一致性(通用,读 by_period)
    if by_period:
        neg = [str(p) for p, s in by_period.items() if s and s.sign_z <= -1.5]
        strong = [p for p, s in by_period.items() if s and s.sign_z >= 1.5 and s.mean > 0]
        if neg:
            axes.append(Axis("regime一致性", "warn", f"存在亏损 regime {neg}(edge 非跨期稳健)"))
        elif len([p for p in by_period if by_period[p]]) >= 3 and len(strong) <= 1:
            axes.append(Axis("regime一致性", "warn", "edge 集中在单一期,疑 regime 幻觉"))
        else:
            axes.append(Axis("regime一致性", "pass", "多期方向一致"))

    # 6) 拥挤
    axes.append(Axis("拥挤/衰减", {"low": "pass", "medium": "warn", "high": "fail", "unknown": "warn"}[c.crowding],
                     f"拥挤度={c.crowding}"))

    # 7) 运营/法律
    if c.operational.startswith("severe"):
        axes.append(Axis("运营/法律", "fail", c.operational, fatal=True))
    elif c.operational.startswith("note"):
        axes.append(Axis("运营/法律", "warn", c.operational))
    else:
        axes.append(Axis("运营/法律", "pass", c.operational))

    # 定级
    fatal_fail = any(a.status == "fail" and a.fatal for a in axes)
    any_fail = any(a.status == "fail" for a in axes)
    warns = sum(1 for a in axes if a.status == "warn")
    if fatal_fail:
        tier, reason = "kill", "有致命闸红(" + ",".join(a.name for a in axes if a.status == "fail" and a.fatal) + ")→ 回杀戮道/毙"
    elif any_fail or warns >= 2:
        tier, reason = "long-watch", f"{warns} 项存疑,放长期观察,勿急推模拟"
    else:
        tier, reason = "priority-watch", "各致命闸皆过,进重点观察→可上模拟操盘(验执行)"
    return GradeResult(tier=tier, axes=axes, reason=reason)


# ── 正控 ─────────────────────────────────────────────────────────────────────
class _S:
    def __init__(self, mean, median, hit, sign_z, n=300):
        self.mean, self.median, self.hit, self.sign_z, self.n = mean, median, hit, sign_z, n


def _self_test():
    good_bp = {2024: _S(.02, .01, .63, 3.0), 2025: _S(.018, .01, .62, 2.8), 2026: _S(.02, .01, .64, 3.1)}
    conc_bp = {2024: _S(-.01, -.01, .45, -2.0), 2025: _S(.005, 0, .52, 1.2), 2026: _S(.02, .01, .66, 5.0)}

    # 1) 重点观察:强信号 + 约束全好
    g1 = grade(_S(.02, .012, .65, 3.0), good_bp,
               Constraints(all_in_cost=.005, capacity_usd=1e6, target_capital=5e4,
                           shortable="yes", ruin_risk="bounded", crowding="low", operational="ok"))
    print(f"{'✅' if g1.tier=='priority-watch' else '❌'} 强+约束好 → {g1.tier} (期望 priority-watch)")

    # 2) 毙:全口径成本致命(资金费吃掉边缘 edge)
    g2 = grade(_S(.0033, .04, .66, 5.3), conc_bp,
               Constraints(all_in_cost=.01, capacity_usd=5e3, target_capital=5e4,
                           shortable="partial", ruin_risk="unbounded", crowding="medium",
                           operational="note:24/7+离岸", cost_source="估计(含资金费)"),
               side_is_short=True)
    print(f"{'✅' if g2.tier=='kill' else '❌'} 边缘+资金费致命 → {g2.tier} (期望 kill)")

    # 3) 长期观察:成本过但多项存疑(regime集中+容量+partial)
    g3 = grade(_S(.02, .012, .64, 3.0), conc_bp,
               Constraints(all_in_cost=.005, capacity_usd=2e4, target_capital=5e4,
                           shortable="partial", ruin_risk="bounded", crowding="medium", operational="ok"),
               side_is_short=True)
    print(f"{'✅' if g3.tier=='long-watch' else '❌'} 成本过但多项存疑 → {g3.tier} (期望 long-watch)")
    print("\n示例(边缘 crypto 短信号):\n" + g2.show())


if __name__ == "__main__":
    _self_test()
