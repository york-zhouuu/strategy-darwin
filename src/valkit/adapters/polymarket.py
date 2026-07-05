"""Polymarket 适配器:把 pm_hist.json 变成 valkit 的 Event + fade 收益函数。

策略含义(fade)封在这里:暴动后反向持有到 t+N,每单位名义收益 = (p_spike - p_forward) * 方向。
引擎不关心这是 fade 还是 follow,只统计这列收益。
"""
from __future__ import annotations

import json
from typing import Callable, Optional

from ..study import Event

DAY = 86400
HORIZONS = [1, 3, 7]


def _band(v: float) -> str:
    return "1small(15-50k)" if v < 50000 else "2mid(50-500k)" if v < 500000 else "3big(>500k)"


def load(path: str, *, spike: float = 0.12, lo: float = 0.10, hi: float = 0.90,
         dedup: bool = True, only_up: bool = False, liquid_only: bool = False
         ) -> tuple[list[Event], Callable[[Event, int], Optional[float]]]:
    """返回 (events, ret)。events 携带 history 与 spike 价于 meta,ret 算 fade 收益。"""
    D = json.load(open(path))
    events: list[Event] = []
    for m in D:
        h = sorted(m["h"])
        band = m.get("band") or _band(m.get("vol", 0))
        for i in range(len(h) - 1):
            t0, p0 = h[i]
            j = i + 1
            while j < len(h) and h[j][0] - t0 < 0.5 * DAY:
                j += 1
            if j >= len(h) or h[j][0] - t0 > 2 * DAY:
                continue
            t1, p1 = h[j]
            if not (lo <= p0 <= hi):
                continue
            if abs(p1 - p0) >= spike:
                d = 1 if p1 > p0 else -1
                events.append(Event(entity=m.get("q", "")[:40], t0=t1, bucket=band,
                                    reaction_sign=d, meta={"h": h, "p1": p1}))
                if dedup:
                    break   # 每市场首个合格暴动(独立化),方向过滤在循环后做
    if only_up:
        events = [e for e in events if e.reaction_sign == 1]
    if liquid_only:
        events = [e for e in events if e.bucket.startswith(("2mid", "3big"))]

    def ret(e: Event, horizon: int) -> Optional[float]:
        h, p1, d = e.meta["h"], e.meta["p1"], e.reaction_sign
        tgt = e.t0 + horizon * DAY
        best = None
        for t, p in h:
            if t > e.t0 and abs(t - tgt) <= 1.5 * DAY:
                if best is None or abs(t - tgt) < abs(best[0] - tgt):
                    best = (t, p)
        if best is None:
            return None
        return (p1 - best[1]) * d      # fade: 反向持有收益

    return events, ret


def _price_at(h, t_target, tol_days: float = 2.0):
    """取离 t_target 最近、且在容差内的点价格。"""
    best = None
    for t, p in h:
        if abs(t - t_target) <= tol_days * DAY:
            if best is None or abs(t - t_target) < abs(best[0] - t_target):
                best = (t, p)
    return best[1] if best else None


def ret_delayed(e: Event, horizon: int, offset: int) -> Optional[float]:
    """a' 入场时点弹跳检查:延迟 offset 天入场的 fade 收益。

    offset=0 ≈ 即时(等价 ret);offset=1 = 暴动后第二天才入场。
    若 edge 只在暴动当刻、延迟即垮 → 买卖价差弹跳,不是真 edge(美股死法)。
    """
    h, d = e.meta["h"], e.reaction_sign
    entry_t = e.t0 + offset * DAY
    p_entry = _price_at(h, entry_t)
    if p_entry is None:
        return None
    p_exit = _price_at(h, entry_t + horizon * DAY)
    if p_exit is None:
        return None
    return (p_entry - p_exit) * d
