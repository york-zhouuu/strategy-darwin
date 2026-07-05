"""泄漏审计 —— 把 agent 回测变成「扣除泄漏底噪后的上界」。杀戮道的核心。

背景(见 openspec define-agent-validation-protocol design.md):agent 回测被 C1 权重前视 /
C2 检索污染灌水,永不能证明干净,故只当**上界**。但上界仍是绝佳的**证伪器**:
被泄漏灌水的上界都没 edge = 稳健杀死。本模块不假设干净,去**测量**关不掉的泄漏,
再把它从表观 edge 里扣掉。扣完仍无 edge → 廉价 NO-GO,连前向都不必上。

用法:调用方给一个 `predict(event, mode) -> p∈[0,1]`(p = 该事件"正结局"的预测概率),
mode ∈ {"real","strip","corrupt"}:
  real    = 喂 t0 及之前的真实输入(表观表现)
  strip   = 只给 ticker+date、抽掉一切资料(测 C1:模型是不是在背题)
  corrupt = 喂打乱/假的输入(测 C2 及残留:喂垃圾还准=有东西在漏)
判据:leakage_floor = max(strip, corrupt 的判别力);edge_above_floor = real − floor。
floor 应≈无判别(AUC≈0.5);floor 高=在泄漏;real 不显著高于 floor=表观 edge 全是泄漏。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

# predict(event, mode) -> 概率 p∈[0,1];label = 该事件真实结局 ∈ {0,1}
PredictFn = Callable[[object, str], float]


def auc(scores: Sequence[float], labels: Sequence[int]) -> float:
    """无阈值判别力(Mann-Whitney AUC)。0.5=无判别,1=完美,<0.5=反向。"""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return 0.5
    wins = 0.0
    for a in pos:
        for b in neg:
            wins += 1.0 if a > b else 0.5 if a == b else 0.0
    return wins / (len(pos) * len(neg))


def auc_z(a: float, n_pos: int, n_neg: int) -> float:
    """AUC 偏离 0.5 的正态近似 z(Mann-Whitney)。用于判显著。"""
    if n_pos == 0 or n_neg == 0:
        return 0.0
    u = a * n_pos * n_neg
    mu = n_pos * n_neg / 2
    sd = math.sqrt(n_pos * n_neg * (n_pos + n_neg + 1) / 12) or 1e-9
    return (u - mu) / sd


@dataclass(frozen=True)
class LeakageAudit:
    n: int
    real_auc: float
    strip_auc: float          # C1 权重前视底噪
    corrupt_auc: float        # C2 及残留泄漏底噪
    floor: float              # max(strip, corrupt) 相对 0.5 的偏离幅度映射回 AUC
    edge_above_floor: float   # real_auc − floor_auc
    edge_z: float             # edge_above_floor 的近似显著性
    verdict: str              # "leakage" / "clean-ish" / "no-edge"

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def audit(events: Sequence, labels: Sequence[int], predict: PredictFn,
          *, min_edge_auc: float = 0.03, min_edge_z: float = 2.0) -> LeakageAudit:
    """跑三种 mode,算扣除泄漏底噪后的上界判据。

    floor_auc:把 strip/corrupt 的判别力都折成"距 0.5 的绝对偏离",取最大,再加回 0.5——
    因为反向泄漏(AUC<0.5)一样是信息泄漏。edge = real 相对该 floor 还高出多少。
    """
    n = len(events)
    ys = list(labels)
    real = [predict(e, "real") for e in events]
    strip = [predict(e, "strip") for e in events]
    corrupt = [predict(e, "corrupt") for e in events]

    ra, sa, ca = auc(real, ys), auc(strip, ys), auc(corrupt, ys)
    n_pos = sum(1 for y in ys if y == 1)
    n_neg = n - n_pos
    # 泄漏底噪:strip/corrupt 距 0.5 的最大绝对偏离(反向也算漏)
    floor_dev = max(abs(sa - 0.5), abs(ca - 0.5))
    floor_auc = 0.5 + floor_dev
    edge = ra - floor_auc
    # edge 显著性:real 的 z 减去 floor 的 z(粗略保守)
    real_z = auc_z(ra, n_pos, n_neg)
    floor_z = max(abs(auc_z(sa, n_pos, n_neg)), abs(auc_z(ca, n_pos, n_neg)))
    edge_z = real_z - floor_z

    if floor_dev >= 0.05 and edge < min_edge_auc:
        verdict = "leakage"          # 底噪高且 real 没超出 → 表观 edge 是泄漏
    elif edge >= min_edge_auc and edge_z >= min_edge_z:
        verdict = "clean-ish"        # real 显著高于底噪 → 上界确有 edge(仍只是上界)
    else:
        verdict = "no-edge"          # 扣完就没了 → 廉价杀死
    return LeakageAudit(n=n, real_auc=ra, strip_auc=sa, corrupt_auc=ca,
                        floor=floor_auc, edge_above_floor=edge, edge_z=edge_z, verdict=verdict)


# ── 探针自身的正控:不接 API 也能确认审计器是对的 ────────────────────────────
def _self_test() -> None:
    """合成三个预测器,确认 audit 能:识出泄漏、放行干净 edge、杀死纯噪声。

    用确定性伪随机(基于事件索引),不依赖 Math.random——保证可复现。
    """
    N = 400
    # 事件 = 索引;label 由一个"真实信号" s_i 决定
    def sig(i):   # 真实可在 t0 观测的信号 ∈ {0,1},与 label 相关
        return (i * 2654435761 % 1000) / 1000.0
    events = list(range(N))
    labels = [1 if (sig(i) + ((i * 40503 % 1000) / 1000.0 - 0.5) * 0.6) > 0.5 else 0
              for i in events]

    # 1) 干净预测器:real 用真实信号;strip/corrupt 无信息(返回 0.5 附近噪声)
    def clean(e, mode):
        if mode == "real":
            return sig(e)
        return 0.5 + ((e * 2246822519 % 1000) / 1000.0 - 0.5) * 0.02   # ≈无判别
    # 2) 泄漏预测器:哪怕 strip 也"知道" label(模拟背题)
    def leaky(e, mode):
        base = labels[e] * 0.9 + 0.05          # strip 也能看穿 label
        if mode == "real":
            return base
        return base                             # strip/corrupt 一样准 = 在漏
    # 3) 纯噪声预测器:任何 mode 都无判别
    def noise(e, mode):
        return 0.5 + ((e * 3266489917 % 1000) / 1000.0 - 0.5) * 0.02

    for name, fn, want in [("clean", clean, "clean-ish"),
                           ("leaky", leaky, "leakage"),
                           ("noise", noise, "no-edge")]:
        r = audit(events, labels, fn)
        ok = "✅" if r.verdict == want else "❌"
        print(f"{ok} {name:6s}: real_auc={r.real_auc:.3f} strip={r.strip_auc:.3f} "
              f"corrupt={r.corrupt_auc:.3f} floor={r.floor:.3f} edge={r.edge_above_floor:+.3f} "
              f"z={r.edge_z:+.2f} → {r.verdict} (期望 {want})")


if __name__ == "__main__":
    _self_test()
