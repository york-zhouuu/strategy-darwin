"""强制杀戮道(KillLane)—— 把散着的 solid 零件变成不能跳步、不能 retrofit 的流水线。

design.md 立身之本:solid = 闸门由**工具强制**,不靠约定/skill 文字。本对象强制:
  ① 必须先 register(prereg) 冻结门槛(哈希+ts 写 append-only 账本)→ 先于任何数据接触
     没冻结就 run() → 拒绝执行(防 freeze-before-see 被绕过 / retrofit p-hacking)
  ② 自动跑仪器正控;引擎不可信 → 拒绝出判决
  ③ 强制检验组 full/by_bucket/by_period/oos 一个不少(by_period 抓衰减不可跳)
  ④ agent thesis 无泄漏审计 → 够不到 GO,只能"仅机械、未验 agent"
  ⑤ 只用冻结那份 prereg 判,retrofit 不了;判决+报告+账本一条原子记录,可审计

a'(可交易性)、cutoff/PIT 以后都只是往这条 lane 里加一个强制 stage。
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from pathlib import Path
from typing import Callable, Optional, Sequence

try:
    from .study import study, by_bucket, by_period, oos_split
    from .report import go_no_go
    from .prereg import Prereg
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from valkit.study import study, by_bucket, by_period, oos_split
    from valkit.report import go_no_go
    from valkit.prereg import Prereg


class LaneError(RuntimeError):
    """流水线纪律被违反时抛出(工具拒绝执行,而非默默放行)。"""


class KillLane:
    def __init__(self, journal_path: str | Path, *, now: Optional[dt.datetime] = None):
        self.journal_path = Path(journal_path)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now
        self.run_id = uuid.uuid4().hex[:12]
        self._prereg: Optional[Prereg] = None
        self._prereg_hash: Optional[str] = None
        self._ran = False

    def _ts(self) -> str:
        return (self._now or dt.datetime.now(dt.timezone.utc)).isoformat()

    def _log(self, rec: dict) -> None:
        rec = {"run_id": self.run_id, "ts": self._ts(), **rec}
        with open(self.journal_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    # ── ① 冻结门槛(必须先于 run) ─────────────────────────────────────────
    def register(self, prereg: Prereg) -> str:
        """冻结预注册门槛,哈希+ts 落账本。返回哈希。必须在 run() 之前调用。"""
        if self._ran:
            raise LaneError("已出过结果,不允许再 register(retrofit 门槛=p-hacking)")
        self._prereg = prereg
        self._prereg_hash = prereg.hash()
        self._log({"phase": "register", "prereg_hash": self._prereg_hash,
                   "thesis_id": prereg.thesis_id, "prereg": prereg.__dict__})
        return self._prereg_hash

    # ── ②–⑤ 跑流水线 ────────────────────────────────────────────────────
    def run(self, events: Sequence, ret: Callable, horizons: Sequence[int], *,
            is_agent: bool = False,
            control_ok: Optional[Callable[[], bool]] = None,
            leakage=None,
            cutoff=None,
            pit=None,
            tradeability=None,
            costs: Sequence[float] = (0.02, 0.04),
            report_dir: str | Path = None) -> dict:
        """跑强制杀戮道,返回 {verdict, report_path, ...}。
        缺 register / 正控不过 / agent 缺泄漏审计 / a' 可交易性被跳或 untradeable 都会被拦。"""
        if self._prereg is None:
            raise LaneError("必须先 register(prereg) 冻结门槛,再 run()")
        pr = self._prereg
        self._ran = True

        # ② 仪器正控:不过拒绝出判决
        if control_ok is not None:
            ok = bool(control_ok())
            self._log({"phase": "control", "passed": ok})
            if not ok:
                v = {"passed": False, "reason": "仪器正控未过,引擎不可信,拒绝出判决",
                     "checks": {"instrument_trusted": False}, "prereg_hash": self._prereg_hash}
                self._log({"phase": "abort", "verdict": v})
                return {"verdict": v, "report_path": None, "aborted": True}

        # ③ 强制检验组(一个不少)
        full = study(events, ret, horizons)
        buckets = by_bucket(events, ret, horizons)
        per = by_period(events, ret, horizons)
        is_r, oos_r, cut = oos_split(events, ret, horizons)
        H = pr.primary_horizon
        latest_key = max(per.keys(), key=lambda k: str(k)) if per else None
        latest = per.get(latest_key, {}).get(H) if latest_key is not None else None

        # ④ agent thesis:无泄漏审计 / cutoff 污染 / PIT 违规 都够不到 GO(上界不可信)
        agent_block = None
        if is_agent:
            lv = getattr(leakage, "verdict", None)
            cv = getattr(cutoff, "verdict", None)
            pv = getattr(pit, "verdict", None)
            if leakage is None:
                agent_block = "agent thesis 未做泄漏审计,上界不可信 → 够不到 GO"
            elif lv in ("leakage", "no-edge"):
                agent_block = f"泄漏审计判 {lv}(表观 edge 是泄漏/无 edge)"
            elif cutoff is not None and cv in ("contaminated", "insufficient", "no-edge"):
                agent_block = f"cutoff 闸判 {cv}:{getattr(cutoff, 'reason', '')}"
            elif pit is not None and pv == "pit-violated":
                agent_block = f"PIT 校验判 {pv}:{getattr(pit, 'reason', '')}"
            self._log({"phase": "agent_audit", "leakage": lv, "cutoff": cv, "pit": pv,
                       "blocked": agent_block})

        # a' 可交易性闸(强制,不得跳过):None=跳过→不得 GO;untradeable→NO-GO;unverified→带 caveat 放行
        trade_block = None
        if tradeability is None:
            trade_block = "a' 可交易性未检(不得跳过)→ 够不到 GO"
        elif getattr(tradeability, "verdict", None) == "untradeable":
            trade_block = f"a' 判 untradeable:{getattr(tradeability, 'reason', '')}"
        self._log({"phase": "tradeability", "verdict": getattr(tradeability, "verdict", None),
                   "blocked": trade_block})

        # ⑤ 只用冻结的 prereg 判
        verdict = pr.evaluate(full.get(H), oos=oos_r.get(H), latest=latest)
        if agent_block:
            verdict["passed"] = False
            verdict["reason"] = agent_block + " | " + verdict.get("reason", "")
            verdict["checks"]["agent_leakage_clear"] = False
        if trade_block:
            verdict["passed"] = False
            verdict["reason"] = trade_block + " | " + verdict.get("reason", "")
            verdict["checks"]["tradeability_clear"] = False
        elif getattr(tradeability, "verdict", None) == "unverified":
            verdict["checks"]["tradeability_caveat"] = f"a' unverified: {tradeability.reason}"

        self._log({"phase": "verdict", "prereg_hash": self._prereg_hash,
                   "passed": verdict["passed"], "reason": verdict["reason"],
                   "cutoff_t0": cut})

        # 报告
        rep = go_no_go(pr, verdict, full=full, by_period=per, costs=costs,
                       coverage=f"{len(events)} 事件 · is_agent={is_agent} · "
                                f"泄漏={getattr(leakage,'verdict',None)}",
                       limitations=[f"OOS cutoff t0={cut:.0f}",
                                    "a'(可交易性)/cutoff-PIT 尚未接入本 lane"])
        report_path = None
        if report_dir:
            report_path = Path(report_dir) / f"lane_{pr.thesis_id}_{self.run_id}.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rep, encoding="utf-8")

        return {"verdict": verdict, "report_path": str(report_path) if report_path else None,
                "full": full, "by_period": per, "oos": (is_r, oos_r, cut),
                "buckets": buckets, "report": rep, "aborted": False}


# ── 自证:强制纪律真的拦得住(合成数据,不接 API) ───────────────────────────
def _ok_trade():
    from valkit.tradeability import TradeabilityAudit
    return TradeabilityAudit(n=400, verdict="tradeable", reason="(自证)全过")


def _bad_trade():
    from valkit.tradeability import TradeabilityAudit
    return TradeabilityAudit(n=400, verdict="untradeable", reason="(自证)尾部驱动")


class _V:  # 简易审计桩(只需 verdict/reason)
    def __init__(self, verdict, reason="(自证)"):
        self.verdict, self.reason = verdict, reason


def _self_test() -> None:
    import tempfile
    from valkit.study import Event
    tmp = Path(tempfile.mkdtemp()) / "lane_journal.jsonl"

    # 合成:注入漂移的真信号
    ev = [Event(entity=f"s{i}", t0=1735689600.0 + i * 1000, bucket="all", reaction_sign=1)
          for i in range(400)]
    vals = [0.05 + (0.08 if i % 3 else -0.08) for i in range(400)]  # 均值+0.05 的伪信号

    def ret(e, h):
        return vals[int(e.entity[1:])]
    pr = Prereg(thesis_id="lane-selftest", hypothesis="注入漂移>0", primary_bucket="all",
                primary_horizon=1, min_net_return=0.0, cost=0.0, min_sign_z=3.0,
                min_hit=0.52, min_n=100, require_oos=False, require_latest_period=False)

    # 1) 未 register 就 run → 必须被拒
    lane = KillLane(tmp)
    try:
        lane.run(ev, ret, [1]); print("❌ 未register竟能run")
    except LaneError:
        print("✅ 未 register 就 run → 被拒(freeze-before-see 强制)")

    # 2) 正控不过 → 拒绝出判决
    lane2 = KillLane(tmp); lane2.register(pr)
    r2 = lane2.run(ev, ret, [1], control_ok=lambda: False)
    print(f"{'✅' if r2['aborted'] else '❌'} 正控不过 → 拒绝出判决(aborted={r2['aborted']})")

    # 3) agent thesis 无泄漏审计 → 够不到 GO
    lane3 = KillLane(tmp); lane3.register(pr)
    r3 = lane3.run(ev, ret, [1], is_agent=True, leakage=None, control_ok=lambda: True,
                   tradeability=_ok_trade())
    print(f"{'✅' if not r3['verdict']['passed'] else '❌'} agent 无泄漏审计 → 够不到 GO")

    # 3b) agent cutoff 污染 → 够不到 GO
    lane3b = KillLane(tmp); lane3b.register(pr)
    r3b = lane3b.run(ev, ret, [1], is_agent=True, control_ok=lambda: True, tradeability=_ok_trade(),
                     leakage=_V("clean-ish"), cutoff=_V("contaminated"), pit=_V("pit-clean"))
    print(f"{'✅' if not r3b['verdict']['passed'] else '❌'} agent cutoff 污染 → 够不到 GO")

    # 3c) agent PIT 违规 → 够不到 GO
    lane3c = KillLane(tmp); lane3c.register(pr)
    r3c = lane3c.run(ev, ret, [1], is_agent=True, control_ok=lambda: True, tradeability=_ok_trade(),
                     leakage=_V("clean-ish"), cutoff=_V("clean"), pit=_V("pit-violated"))
    print(f"{'✅' if not r3c['verdict']['passed'] else '❌'} agent PIT 违规 → 够不到 GO")

    # 3d) agent 全干净(泄漏 clean-ish + cutoff clean + PIT clean + a' ok)→ GO
    lane3d = KillLane(tmp); lane3d.register(pr)
    r3d = lane3d.run(ev, ret, [1], is_agent=True, control_ok=lambda: True, tradeability=_ok_trade(),
                     leakage=_V("clean-ish"), cutoff=_V("clean"), pit=_V("pit-clean"))
    print(f"{'✅' if r3d['verdict']['passed'] else '❌'} agent 全干净 → GO")

    # 4) a' 被跳过(tradeability=None)→ 够不到 GO
    lane4 = KillLane(tmp); lane4.register(pr)
    r4 = lane4.run(ev, ret, [1], control_ok=lambda: True, tradeability=None)
    print(f"{'✅' if not r4['verdict']['passed'] else '❌'} a' 可交易性被跳过 → 够不到 GO")

    # 5) a' 判 untradeable → NO-GO
    lane5 = KillLane(tmp); lane5.register(pr)
    r5 = lane5.run(ev, ret, [1], control_ok=lambda: True, tradeability=_bad_trade())
    print(f"{'✅' if not r5['verdict']['passed'] else '❌'} a' 判 untradeable → NO-GO")

    # 6) 快乐路径:机械真信号 + 正控过 + a' tradeable → GO
    lane6 = KillLane(tmp); lane6.register(pr)
    r6 = lane6.run(ev, ret, [1], control_ok=lambda: True, tradeability=_ok_trade())
    print(f"{'✅' if r6['verdict']['passed'] else '❌'} 真信号+正控+a'过 → GO(reason={r6['verdict']['reason']})")

    # 7) register-after-run → 被拒
    try:
        lane6.register(pr); print("❌ run后竟能register")
    except LaneError:
        print("✅ run 后再 register → 被拒(retrofit 门槛被拦)")

    print(f"\n账本留痕:{tmp}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    _self_test()
