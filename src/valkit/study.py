"""战场无关的事件研究引擎。

一个 Event = 决策时点已知的一切(实体、t0、分桶键、初始反应方向)。
一个 Adapter 提供 `ret(event, horizon) -> Optional[float]` = 该策略在该事件该持有期的**每单位可交易收益**
(fade 就是反向持有收益,underreaction 就是 sign(反应)×异常收益;策略含义在适配器里,引擎不关心)。

引擎只做纪律:分桶 / 时间衰减切片 / IS-OOS 切分 / 成本敏感 / 显著性。
这次 Polymarket P0 栽在没做时间切片——`by_period` 是一等公民。
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from .stats import Summary, summarize


@dataclass(frozen=True)
class Event:
    entity: str                 # 标的/市场 id
    t0: float                   # 决策时点 unix 秒(入场基准,严格之后才可交易)
    bucket: str = "all"         # 分桶键(流动性桶/事件类型…)
    reaction_sign: int = 0      # 初始反应方向 +1/-1/0(方向性度量用)
    meta: dict = field(default_factory=dict)


# ret(event, horizon_index) -> 每单位可交易收益; None=该期无数据
RetFn = Callable[[Event, int], Optional[float]]


def _returns(events: Sequence[Event], ret: RetFn, h: int) -> list[float]:
    out = []
    for e in events:
        r = ret(e, h)
        if r is not None:
            out.append(r)
    return out


def study(events: Sequence[Event], ret: RetFn, horizons: Sequence[int]) -> dict[int, Optional[Summary]]:
    """全样本:每个持有期一个 Summary。"""
    return {h: summarize(_returns(events, ret, h)) for h in horizons}


def by_bucket(events, ret, horizons) -> dict[str, dict[int, Optional[Summary]]]:
    """按 bucket 分层(只信可交易的液体桶,别被鬼盘小桶骗)。"""
    groups: dict[str, list[Event]] = defaultdict(list)
    for e in events:
        groups[e.bucket].append(e)
    return {b: study(evs, ret, horizons) for b, evs in sorted(groups.items())}


def by_period(events, ret, horizons, period: Callable[[float], object] = None
              ) -> dict[object, dict[int, Optional[Summary]]]:
    """时间衰减切片。默认按 t0 的年份切——检验 edge 是否被套利磨平。

    ⚠️ 这是 Polymarket P0 漏掉、导致把'2024-25 老肉'误当'现在还活'的那一步。任何 edge 都要过这关。
    """
    if period is None:
        period = lambda t: dt.datetime.utcfromtimestamp(t).year
    groups: dict[object, list[Event]] = defaultdict(list)
    for e in events:
        groups[period(e.t0)].append(e)
    return {k: study(evs, ret, horizons) for k, evs in sorted(groups.items(), key=lambda kv: str(kv[0]))}


def oos_split(events, ret, horizons, cutoff_t0: Optional[float] = None
              ) -> tuple[dict, dict, float]:
    """样本内发现 / 样本外确认。cutoff 默认取 t0 中位数,前半 IS 后半 OOS。

    纪律:规则在 IS 上挑,只认 OOS 仍成立的。返回 (is_result, oos_result, cutoff)。
    """
    ts = sorted(e.t0 for e in events)
    if not ts:
        return {}, {}, 0.0
    cut = cutoff_t0 if cutoff_t0 is not None else ts[len(ts) // 2]
    is_ev = [e for e in events if e.t0 < cut]
    oos_ev = [e for e in events if e.t0 >= cut]
    return study(is_ev, ret, horizons), study(oos_ev, ret, horizons), cut


def cost_curve(summary: Optional[Summary], costs: Sequence[float]) -> dict[float, float]:
    """成本敏感:每个成本水平下的净均值。看 edge 能扛到多高的费/价差。"""
    if summary is None:
        return {}
    return {c: summary.net(c) for c in costs}
