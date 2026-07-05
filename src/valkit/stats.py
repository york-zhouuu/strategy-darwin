"""战场无关的纪律统计核心。所有战场共用这一套,别再手搓。

设计原则:肥尾下均值 t 弱,故同时给符号检验 z;所有分层/切片检验都要能报 Bonferroni 量级。
"""
from __future__ import annotations

import math
import statistics as st
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class Summary:
    """一组每事件收益的统计摘要。"""

    n: int
    mean: float
    median: float
    hit: float            # >0 占比
    t: float              # 均值 t vs 0(肥尾下弱)
    sign_z: float         # 符号检验 z vs 抛硬币(肥尾下更稳)
    std: float

    def net(self, cost: float) -> float:
        """减去每笔成本后的均值。"""
        return self.mean - cost

    def as_row(self, costs: Sequence[float] = ()) -> dict:
        d = {"n": self.n, "hit": self.hit, "mean": self.mean, "median": self.median,
             "t": self.t, "sign_z": self.sign_z}
        for c in costs:
            d[f"net@{c}"] = self.net(c)
        return d


def summarize(returns: Sequence[float]) -> Optional[Summary]:
    """把一列每事件收益压成 Summary。样本 <2 或全等返回 None。"""
    xs = [x for x in returns if x is not None]
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    std = st.pstdev(xs)
    k = sum(1 for x in xs if x > 0)
    sign_z = (k - n / 2) / (math.sqrt(n) / 2)
    t = mean / (std / math.sqrt(n)) if std > 0 else 0.0
    return Summary(n=n, mean=mean, median=st.median(xs), hit=k / n, t=t, sign_z=sign_z, std=std)


def bonferroni_z(n_tests: int, alpha: float = 0.05) -> float:
    """n 个检验的 Bonferroni 校正后双侧 z 临界值(正态近似)。

    例:100 检验 α=.05 → z≈3.48。报告分层结果时,signZ 要过这个才算数。
    """
    from statistics import NormalDist
    p = alpha / max(n_tests, 1) / 2
    return NormalDist().inv_cdf(1 - p)


def winsorize(returns: Sequence[float], limit: float = 0.05) -> list[float]:
    """双侧 winsorize 到 [limit, 1-limit] 分位,压肥尾/脏数据的杠杆。"""
    xs = sorted(x for x in returns if x is not None)
    if not xs:
        return []
    lo = xs[int(limit * len(xs))]
    hi = xs[min(len(xs) - 1, int((1 - limit) * len(xs)))]
    return [min(max(x, lo), hi) for x in returns if x is not None]


def hard_drop(returns: Sequence[float], abs_max: float) -> list[float]:
    """硬弃 |收益|>abs_max 的脏数据(如拆股未调整的假 +1700%)。"""
    return [x for x in returns if x is not None and abs(x) <= abs_max]
