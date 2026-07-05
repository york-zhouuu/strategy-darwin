"""a' 可交易性闸 —— "判断准 ≠ 吃得到"。四个项目最常见的死法。

判断校准(a)过了,肉却可能长在:①尾部/幸存者灌水 ②做空依赖 ③入场时点弹跳 ④成本吞噬。
本模块把这四种死法做成一组拆解:通用检查(尾部/成本)总跑,其余有适配器 hook 才跑,
**诚实报告哪些没跑**。判 tradeable / untradeable / unverified,像 leakage 一样插进 lane。

顺序:a 判断校准 → **a' 本闸** → b 策略 P&L。a' 不过直接 NO-GO,不烧后续前向额度。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

try:
    from .stats import summarize, Summary
except ImportError:
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from valkit.stats import summarize, Summary


@dataclass(frozen=True)
class TradeabilityAudit:
    n: int
    checks: dict = field(default_factory=dict)   # name -> {ran, passed, detail}
    verdict: str = "unverified"                   # tradeable / untradeable / unverified
    reason: str = ""

    def as_dict(self) -> dict:
        return {"n": self.n, "verdict": self.verdict, "reason": self.reason, "checks": self.checks}


def audit(events: Sequence, ret: Callable, primary_h: int, *,
          side: Optional[Callable] = None,          # side(e)->+1 需做多 / -1 需做空
          ret_delayed: Optional[Callable] = None,   # ret_delayed(e,h,offset)-> 延迟 offset 期入场的收益
          cost_tradeable: float = 0.02,
          long_only: bool = True,
          na_checks: frozenset = frozenset(),
          base_t_min: float = 1.96, base_z_min: float = 1.96) -> TradeabilityAudit:
    """跑可交易性拆解。通用检查(尾部/成本)必跑;side/ret_delayed 缺则该检查标 unverified;
    na_checks 里的检查 = 本战场不适用(如预测市场双向自由交易→做空依赖不适用),记为 passed 不算 unverified。

    **base 门**:base 信号本身不显著(正且 mean-t 达标)→ 返回 no-base-edge,可交易性无从谈起,
    死因交还给显著性闸(不误报成'弹跳/成本')。用 mean-t 而非 sign_z——否则误杀 tail-driven(mean 显著但 sign 背离)。"""
    xs = [ret(e, primary_h) for e in events]
    xs = [x for x in xs if x is not None]
    s = summarize(xs)
    checks: dict = {}
    n = 0 if s is None else s.n

    if s is None:
        return TradeabilityAudit(n=0, checks={"n": {"ran": True, "passed": False, "detail": "样本不足"}},
                                 verdict="untradeable", reason="样本不足")

    # base 门:base 不显著为正 → 可交易性无从谈起(死因在显著性闸,不在 a')
    # 肥尾感知:mean-t 或 signZ 任一显著即算有 base(crypto 等肥尾下 mean-t 弱、符号检验更有力)
    base_sig = (s.std == 0 and s.mean > 0) or (s.mean > 0 and (s.t >= base_t_min or s.sign_z >= base_z_min))
    if not base_sig:
        return TradeabilityAudit(
            n=n, verdict="no-base-edge", reason="base 信号不显著(mean-t 与 signZ 均不达标),不进入可交易性拆解(死因在显著性闸)",
            checks={"base_edge": {"ran": True, "passed": False,
                    "detail": f"base 不显著(mean={s.mean:+.4f} t={s.t:+.2f} signZ={s.sign_z:+.2f}),弹跳/成本无从谈起"}})

    # ── 检查1 尾部/幸存者灌水(通用):mean>0 但 hit<50% 或 median≤0 → 靠少数暴涨,靠不住
    tail_bad = s.mean > 0 and (s.hit < 0.50 or s.median <= 0)
    checks["tail_driven"] = {"ran": True, "passed": not tail_bad,
                             "detail": f"mean={s.mean:+.4f} median={s.median:+.4f} hit={s.hit:.0%}"
                                       + ("(尾部驱动,小资金靠不住)" if tail_bad else "")}

    # ── 检查2 成本吞噬(通用):可交易 size 现实成本后仍为正
    net = s.net(cost_tradeable)
    cost_bad = net <= 0
    checks["cost"] = {"ran": True, "passed": not cost_bad,
                      "detail": f"net@{cost_tradeable}={net:+.4f}" + ("(成本后归零)" if cost_bad else "")}

    # ── 检查3 做空依赖(需 side):肉只在空头腿、多头腿≤0 → 小资金现货/只做多吃不到
    if "short_dependence" in na_checks:
        checks["short_dependence"] = {"ran": True, "passed": True, "detail": "不适用(本战场双向自由交易)"}
    elif side is not None:
        longs = [ret(e, primary_h) for e in events if side(e) > 0]
        shorts = [ret(e, primary_h) for e in events if side(e) < 0]
        sl = summarize([x for x in longs if x is not None])
        ss = summarize([x for x in shorts if x is not None])
        ml = sl.mean if sl else 0.0
        ms = ss.mean if ss else 0.0
        short_dep = long_only and ml <= 0 and ms > 0
        checks["short_dependence"] = {"ran": True, "passed": not short_dep,
                                      "detail": f"多头腿={ml:+.4f} 空头腿={ms:+.4f}"
                                                + ("(edge 只在空头,只做多吃不到)" if short_dep else "")}
    else:
        checks["short_dependence"] = {"ran": False, "passed": None, "detail": "无 side hook,未检"}

    # ── 检查4 入场时点弹跳(需 ret_delayed):改入场即垮 = 买卖价差,不是真 edge
    if "entry_bounce" in na_checks:
        checks["entry_bounce"] = {"ran": True, "passed": True, "detail": "不适用(本战场)"}
    elif ret_delayed is not None:
        base = summarize([ret_delayed(e, primary_h, 0) for e in events if ret_delayed(e, primary_h, 0) is not None])
        delayed = summarize([ret_delayed(e, primary_h, 1) for e in events if ret_delayed(e, primary_h, 1) is not None])
        b = base.mean if base else 0.0
        d = delayed.mean if delayed else 0.0
        # 延迟一期后 edge 掉过半 或 反号 → 弹跳
        bounce = b > 0 and (d <= 0 or d < 0.5 * b)
        checks["entry_bounce"] = {"ran": True, "passed": not bounce,
                                  "detail": f"即时入场={b:+.4f} 延迟1期={d:+.4f}"
                                            + ("(改入场即垮,微观结构弹跳)" if bounce else "")}
    else:
        checks["entry_bounce"] = {"ran": False, "passed": None, "detail": "无 ret_delayed hook,未检"}

    ran_failed = [k for k, c in checks.items() if c["ran"] and c["passed"] is False]
    not_run = [k for k, c in checks.items() if not c["ran"]]
    if ran_failed:
        verdict, reason = "untradeable", "未过:" + ",".join(ran_failed)
    elif not_run:
        verdict, reason = "unverified", "通用检查过,但未检:" + ",".join(not_run)
    else:
        verdict, reason = "tradeable", "全部可交易性检查通过"
    return TradeabilityAudit(n=n, checks=checks, verdict=verdict, reason=reason)


# ── 正控:合成三种死法,确认 a' 抓得住 ──────────────────────────────────────
def _rng(seed):
    st = {"s": (seed * 2654435761 + 12345) & 0xFFFFFFFF}
    def nxt():
        st["s"] = (st["s"] * 1103515245 + 12345) & 0x7FFFFFFF
        return st["s"] / 0x7FFFFFFF
    return nxt


def _self_test():
    from valkit.study import Event
    N = 400
    ev = [Event(entity=f"s{i}", t0=float(i), bucket="all", reaction_sign=1) for i in range(N)]

    # 1) 干净宽基:多数为正、mean≈median、成本后仍正 → tradeable
    r = _rng(1); clean = [0.04 + 0.03 * (r() - 0.5) for _ in range(N)]
    # 2) 尾部驱动:多数小负 + 少数暴涨 → mean>0 但 hit<50% median<0 → untradeable
    r = _rng(2); tail = [(-0.01 if r() < 0.7 else +0.25) for _ in range(N)]
    # 3) 成本吞噬:mean 小正但 <2% → 成本后归零 → untradeable
    r = _rng(3); thin = [0.01 + 0.02 * (r() - 0.5) for _ in range(N)]

    def mk(v):
        return lambda e, h: v[int(e.entity[1:])]

    # clean 且四检全给 hook 且全过 → tradeable
    cret = mk(clean)
    a = audit(ev, cret, 1, cost_tradeable=0.02,
              side=lambda e: 1,                                  # 全做多,多头腿>0
              ret_delayed=lambda e, h, off: clean[int(e.entity[1:])] * (1.0 if off == 0 else 0.9))
    print(f"{'✅' if a.verdict=='tradeable' else '❌'} {'clean':10s}: {a.verdict:12s} ({a.reason})  期望 tradeable")

    for name, vals, want in [("tail", tail, "untradeable"), ("thin-cost", thin, "untradeable")]:
        a = audit(ev, mk(vals), 1, cost_tradeable=0.02)
        ok = "✅" if a.verdict == want else "❌"
        print(f"{ok} {name:10s}: {a.verdict:12s} ({a.reason})  期望 {want}")

    # 4) 做空依赖:多头腿≤0、空头腿>0 → untradeable(带 side hook)
    r = _rng(4)
    ev2 = [Event(entity=f"s{i}", t0=float(i), bucket="all",
                 reaction_sign=(1 if i % 2 == 0 else -1)) for i in range(N)]
    vals2 = [(-0.005 if i % 2 == 0 else +0.06) for i in range(N)]  # 偶=多头亏,奇=空头赚

    def ret2(e, h):
        return vals2[int(e.entity[1:])]
    a4 = audit(ev2, ret2, 1, side=lambda e: e.reaction_sign, long_only=True, cost_tradeable=0.0)
    ok = "✅" if a4.verdict == "untradeable" and a4.checks["short_dependence"]["passed"] is False else "❌"
    print(f"{ok} short-dep  : {a4.verdict:12s} ({a4.checks['short_dependence']['detail']})  期望 untradeable")

    # 5) 覆盖诚实:显著 base + 无 hook → unverified 而非假 tradeable
    a5 = audit(ev, mk(clean), 1, cost_tradeable=0.02)
    ok = "✅" if a5.verdict == "unverified" else "❌"
    print(f"{ok} coverage   : {a5.verdict:12s} ({a5.reason})  期望 unverified(未检 side/bounce 诚实标注)")

    # 6) base 门:base 不显著 → no-base-edge(死因交还显著性闸,不误报弹跳/成本)
    r = _rng(9); flat = [0.001 * (r() - 0.5) for _ in range(N)]   # 均值≈0 不显著
    a6 = audit(ev, mk(flat), 1, ret_delayed=lambda e, h, off: mk(flat)(e, h), cost_tradeable=0.02)
    ok = "✅" if a6.verdict == "no-base-edge" else "❌"
    print(f"{ok} base-gate  : {a6.verdict:12s} ({a6.reason})  期望 no-base-edge")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _self_test()
