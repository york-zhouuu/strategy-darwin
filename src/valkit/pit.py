"""cutoff-aware + PIT 约束 —— 硬化 agent 回测上界(治 C1 权重前视 / C2 检索污染)。

agent 回测只当上界;本模块把上界榨得更干净:
  - cutoff 闸(C1):声明模型训练截止 model_cutoff,把事件切成 post(截止之后,权重前视结构上不可能)
    vs pre(可背题)。edge 必须在 **post 子集**里活着才可信;若只在 pre → contaminated(表观 edge 是背题)。
  - PIT 校验(C2):每条输入带时间戳,任一晚于 t0 = 泄漏,拒之;非结构化输入无法证明干净则诚实标 unknown。

非结构化网络的真·PIT 几乎不可能 → 残留污染永远假设存在,故回测**结论仍是上界**,本模块只把上界收紧。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

try:
    from .leakage import auc, auc_z
except ImportError:
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    from valkit.leakage import auc, auc_z


# ── cutoff 闸(C1) ──────────────────────────────────────────────────────────
@dataclass(frozen=True)
class CutoffAudit:
    model_cutoff: float
    n_total: int
    n_post: int
    n_pre: int
    post_auc: float
    pre_auc: float
    verdict: str            # clean / contaminated / insufficient / no-edge
    reason: str

    def as_dict(self):
        return self.__dict__.copy()


def cutoff_audit(events: Sequence, labels: Sequence[int], predict: Callable,
                 model_cutoff: float, *, min_post_n: int = 100,
                 min_auc_edge: float = 0.03) -> CutoffAudit:
    """edge 必须在 post-cutoff(C1 不可能泄漏)子集里活着。predict(e,"real")->p∈[0,1]。"""
    post_i = [i for i, e in enumerate(events) if e.t0 > model_cutoff]
    pre_i = [i for i, e in enumerate(events) if e.t0 <= model_cutoff]
    ys = list(labels)
    post_auc = auc([predict(events[i], "real") for i in post_i], [ys[i] for i in post_i]) if post_i else 0.5
    pre_auc = auc([predict(events[i], "real") for i in pre_i], [ys[i] for i in pre_i]) if pre_i else 0.5

    post_edge = post_auc - 0.5
    pre_edge = pre_auc - 0.5
    if len(post_i) < min_post_n:
        verdict = "insufficient"
        reason = f"post-cutoff 样本不足(n={len(post_i)}<{min_post_n}),C1-干净窗太小,不足以采信"
    elif post_edge >= min_auc_edge:
        verdict = "clean"
        reason = f"edge 在 C1-干净窗(post)存活 post_auc={post_auc:.3f}"
    elif pre_edge >= min_auc_edge and post_edge < min_auc_edge:
        verdict = "contaminated"
        reason = f"edge 只在可背题窗(pre_auc={pre_auc:.3f}),post 塌到 {post_auc:.3f} → 表观 edge 疑为 C1 背题"
    else:
        verdict = "no-edge"
        reason = f"pre/post 均无 edge(post_auc={post_auc:.3f})"
    return CutoffAudit(model_cutoff=model_cutoff, n_total=len(events), n_post=len(post_i),
                       n_pre=len(pre_i), post_auc=post_auc, pre_auc=pre_auc,
                       verdict=verdict, reason=reason)


# ── PIT 输入校验(C2) ───────────────────────────────────────────────────────
@dataclass(frozen=True)
class PITAudit:
    n_total: int
    n_clean: int
    n_violated: int
    n_unknown: int
    verdict: str            # pit-clean / pit-violated / pit-unknown
    reason: str

    def as_dict(self):
        return self.__dict__.copy()


def pit_check(events: Sequence, input_times: Callable[[object], Optional[Sequence[float]]]) -> PITAudit:
    """input_times(e)-> 该事件 agent 所见输入的时间戳列表;None=无法核验(非结构化)。任一晚于 t0 = 泄漏。"""
    clean = violated = unknown = 0
    for e in events:
        ts = input_times(e)
        if ts is None:
            unknown += 1
        elif any(t > e.t0 for t in ts):
            violated += 1
        else:
            clean += 1
    if violated > 0:
        verdict, reason = "pit-violated", f"{violated} 条事件的输入含晚于 t0 的信息(C2 前视),拒采信"
    elif unknown > 0:
        verdict, reason = "pit-unknown", f"{unknown} 条无法核验 PIT(非结构化),残留污染假设存在,上界仅供参考"
    else:
        verdict, reason = "pit-clean", "全部输入时间戳 ≤ t0"
    return PITAudit(n_total=len(events), n_clean=clean, n_violated=violated,
                    n_unknown=unknown, verdict=verdict, reason=reason)


# ── 正控:合成确认两闸抓得住 ─────────────────────────────────────────────────
def _self_test():
    from valkit.study import Event
    CUT = 1000.0
    N = 400
    # 一半 pre(t0<CUT)一半 post(t0>CUT)
    ev = [Event(entity=f"s{i}", t0=(500.0 + i) if i < 200 else (1100.0 + i), bucket="all")
          for i in range(N)]
    lab = [i % 2 for i in range(N)]

    # 1) clean:真信号,pre/post 都判别得动 → clean
    def clean(e, mode):
        i = int(e.entity[1:])
        return 0.75 if lab[i] == 1 else 0.25
    a1 = cutoff_audit(ev, lab, clean, CUT)
    print(f"{'✅' if a1.verdict=='clean' else '❌'} cutoff clean       : {a1.verdict} (post_auc={a1.post_auc:.3f}) 期望 clean")

    # 2) contaminated:只在 pre(可背题)准,post 塌回 0.5 → contaminated
    def leaky_pre(e, mode):
        i = int(e.entity[1:])
        if e.t0 <= CUT:
            return 0.9 if lab[i] == 1 else 0.1     # pre 背题
        return 0.5 + ((i * 2246822519 % 1000) / 1000.0 - 0.5) * 0.02   # post 无判别
    a2 = cutoff_audit(ev, lab, leaky_pre, CUT)
    print(f"{'✅' if a2.verdict=='contaminated' else '❌'} cutoff contaminated: {a2.verdict} "
          f"(pre_auc={a2.pre_auc:.3f} post_auc={a2.post_auc:.3f}) 期望 contaminated")

    # 3) insufficient:post 太少
    ev_few = [Event(entity=f"s{i}", t0=(500.0 + i) if i < 390 else (1100.0 + i), bucket="all")
              for i in range(N)]
    a3 = cutoff_audit(ev_few, lab, clean, CUT, min_post_n=100)
    print(f"{'✅' if a3.verdict=='insufficient' else '❌'} cutoff insufficient: {a3.verdict} (n_post={a3.n_post}) 期望 insufficient")

    # 4) PIT clean vs violated
    p_clean = pit_check(ev, lambda e: [e.t0 - 100, e.t0 - 5])           # 全早于 t0
    p_viol = pit_check(ev, lambda e: [e.t0 - 100, e.t0 + 50])           # 有晚于 t0
    p_unk = pit_check(ev, lambda e: None)                               # 无法核验
    print(f"{'✅' if p_clean.verdict=='pit-clean' else '❌'} pit clean          : {p_clean.verdict}")
    print(f"{'✅' if p_viol.verdict=='pit-violated' else '❌'} pit violated       : {p_viol.verdict} ({p_viol.n_violated} 违规)")
    print(f"{'✅' if p_unk.verdict=='pit-unknown' else '❌'} pit unknown        : {p_unk.verdict}")


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _self_test()
