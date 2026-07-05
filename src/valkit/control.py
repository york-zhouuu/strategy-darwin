"""仪器正控 —— 用它证伪任何 thesis 之前,先证明引擎能测出真信号、且不把噪声当信号。

原始铁律(tradeagent L1):向合成数据注入已知漂移,确认引擎测得回;喂纯噪声,确认判 no-edge。
`leakage.py` 已自证;本模块给机械引擎 `study/by_period/prereg` 配同款正控,
使整条杀戮道(机械 + 泄漏)两半都自证。不接任何外部数据/API,确定性可复现。

跑:`./.venv/bin/python src/valkit/control.py`
"""
from __future__ import annotations

import math

try:                       # 允许 `python src/valkit/control.py` 直接跑
    from .stats import summarize
    from .study import Event, study, by_period
    from .prereg import Prereg
except ImportError:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from valkit.stats import summarize
    from valkit.study import Event, study, by_period
    from valkit.prereg import Prereg


def _rng(seed: int):
    """确定性伪随机(LCG),避开被禁的 random/Date。返回 [0,1)。"""
    state = {"s": (seed * 2654435761 + 12345) & 0xFFFFFFFF}

    def nxt() -> float:
        state["s"] = (state["s"] * 1103515245 + 12345) & 0x7FFFFFFF
        return state["s"] / 0x7FFFFFFF
    return nxt


def _normal(u1: float, u2: float) -> float:
    """Box-Muller 取一个标准正态。"""
    return math.sqrt(-2 * math.log(max(u1, 1e-9))) * math.cos(2 * math.pi * u2)


def _make(n: int, drift: float, noise: float, seed: int, year_of=None):
    """造 n 个合成事件 + ret。ret = 注入 drift + 正态噪声。

    year_of(i)->t0:控制事件落在哪年,用于测 by_period 的时间衰减探测。
    """
    r = _rng(seed)
    events, rets = [], []
    for i in range(n):
        t0 = year_of(i) if year_of else float(i)
        events.append(Event(entity=f"syn{i}", t0=t0, bucket="all", reaction_sign=1))
        rets.append(drift + noise * _normal(r(), r()))

    def ret(e: Event, h: int):
        return rets[int(e.entity[3:])]
    return events, ret


# 年份边界(unix 秒),给 by_period 测衰减用
Y2024, Y2025, Y2026 = 1704067200.0, 1735689600.0, 1767225600.0


def _self_test() -> None:
    print("== 仪器正控:机械引擎 ==")

    # 1) 注入已知漂移 → 必须测得回(mean≈drift, signZ 大)
    INJ = 0.05
    ev, ret = _make(600, drift=INJ, noise=0.08, seed=1)
    s = study(ev, ret, [1])[1]
    ok = "✅" if (abs(s.mean - INJ) < 0.01 and s.sign_z > 3) else "❌"
    print(f"{ok} 注入漂移 {INJ:+.3f}: 测得 mean={s.mean:+.4f} signZ={s.sign_z:+.2f} (应≈{INJ}, signZ大)")

    # 2) 纯噪声(drift=0)→ 必须判不显著(signZ 小),否则引擎在无中生有
    ev0, ret0 = _make(600, drift=0.0, noise=0.08, seed=2)
    s0 = study(ev0, ret0, [1])[1]
    ok = "✅" if abs(s0.sign_z) < 2.0 else "❌"
    print(f"{ok} 纯噪声: mean={s0.mean:+.4f} signZ={s0.sign_z:+.2f} (应 |signZ|<2 不显著)")

    # 3) 预注册判定:真信号 GO、噪声 NO-GO
    pr = Prereg(thesis_id="control", hypothesis="注入漂移>0", primary_bucket="all",
                primary_horizon=1, min_net_return=0.0, cost=0.0, min_sign_z=3.0,
                min_hit=0.52, min_n=100, require_oos=False, require_latest_period=False)
    v1 = pr.evaluate(s)
    v0 = pr.evaluate(s0)
    ok = "✅" if (v1["passed"] and not v0["passed"]) else "❌"
    print(f"{ok} 预注册: 真信号={'GO' if v1['passed'] else 'NO-GO'} 噪声={'GO' if v0['passed'] else 'NO-GO'} (应 GO / NO-GO)")

    # 4) by_period 时间衰减探测:信号只在 2025,2026 应测不到(验证抓 Polymarket 衰减的那把刀)
    def yof(i):
        # 前 300 事件在 2025(有漂移),后 300 在 2026(无漂移)——见 ret 覆盖
        return Y2025 + 1000.0 if i < 300 else Y2026 + 1000.0
    r = _rng(7)
    evd, retd_vals = [], []
    for i in range(600):
        t0 = Y2025 + i * 1000.0 if i < 300 else Y2026 + i * 1000.0
        evd.append(Event(entity=f"syn{i}", t0=t0, bucket="all", reaction_sign=1))
        d = INJ if i < 300 else 0.0        # 漂移只在早期
        retd_vals.append(d + 0.08 * _normal(r(), r()))

    def retd(e, h):
        return retd_vals[int(e.entity[3:])]
    per = by_period(evd, retd, [1])
    s25 = per.get(2025, {}).get(1)
    s26 = per.get(2026, {}).get(1)
    ok = "✅" if (s25 and s26 and s25.sign_z > 3 and abs(s26.sign_z) < 2.5) else "❌"
    print(f"{ok} by_period 衰减探测: 2025 signZ={s25.sign_z:+.2f}(应大) / "
          f"2026 signZ={s26.sign_z:+.2f}(应小) — 早有晚无被抓到")

    print("\n如全 ✅:机械引擎测得回真信号、不把噪声当信号、by_period 能抓衰减 → 杀戮道机械半可信。")


if __name__ == "__main__":
    _self_test()
