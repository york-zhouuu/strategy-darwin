"""确认道:前向影子登记簿 + 召回审计。

两个用途:
  ① 幸存者的前向 paper(唯一能诚实宣布赢家处,协议 ④)。
  ② **召回审计(用户构想)**:被杀的策略也前向影子跑,回头看哪些"误杀"(false negative),
     按**死因聚类**反哺引擎——最值钱的是校准 grade 的成本/资金费估计。

纪律(工具强制):
  - **写入对结局全盲**:register 只记预测+入场,不含结局;结算由独立 settle 追加,物理隔离。
  - **append-only**:register 一条、settle 一条(引 id),召回审计 join,留痕可审。
  - **召回审计防自欺**:影子成功要过显著性+多重检验(按死因组数 Bonferroni);
    且**按死因分层**——死于成本/可交易性的误杀=高价值(你估计错了),死于不显著的=多半噪声。
  - **不对称**:假阳性(放垃圾→亏钱)远贵于假阴性(误杀→少赚)→ 偏向多杀,松闸 bar 高。
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Callable, Optional

try:
    from .stats import summarize, bonferroni_z
except ImportError:
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from valkit.stats import summarize, bonferroni_z

DAY = 86400

# 死因 → 价值类别:tradeability 类误杀高价值(校准成本估计),significance 类多半噪声
REASON_CLASS = {
    "cost": "tradeability", "全口径成本": "tradeability", "容量": "tradeability",
    "可做空性": "tradeability", "尾部/爆仓": "tradeability",
    "min_sign_z": "significance", "latest_period_holds": "significance",
    "min_hit": "significance", "regime一致性": "significance", "oos_holds": "significance",
}


class ShadowRegistry:
    """append-only 影子登记簿。register(盲)→ settle(隔离)→ recall_audit(join)。"""

    def __init__(self, path: str | Path, now: Optional[dt.datetime] = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now

    def _ts(self):
        return (self._now or dt.datetime.now(dt.timezone.utc)).isoformat()

    def _append(self, rec: dict):
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")

    def _read(self):
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    # ① 登记(对结局全盲):GO 和 KILL 都登记,带死因
    def register(self, *, thesis_id: str, verdict: str, kill_reason: str,
                 entity: str, side: int, entry_price: float, entry_t: float,
                 hold_days: int, idx: int = 0) -> str:
        pid = f"{thesis_id}|{entity}|{int(entry_t)}|{idx}"
        self._append({"phase": "register", "id": pid, "ts": self._ts(),
                      "thesis_id": thesis_id, "verdict": verdict, "kill_reason": kill_reason,
                      "reason_class": REASON_CLASS.get(kill_reason, "other" if kill_reason else ""),
                      "entity": entity, "side": side, "entry_price": entry_price,
                      "entry_t": entry_t, "hold_days": hold_days})  # 注意:无结局字段
        return pid

    # ② 结算(独立、晚于到期;评分器此刻才运行 = 与写入物理隔离)
    def settle(self, price_at: Callable[[str, float], Optional[float]], now_t: float) -> int:
        recs = self._read()
        done = {r["id"] for r in recs if r["phase"] == "settle"}
        n = 0
        for r in recs:
            if r["phase"] != "register" or r["id"] in done:
                continue
            exit_t = r["entry_t"] + r["hold_days"] * DAY
            if now_t < exit_t:
                continue                        # 未到期,不结算
            px = price_at(r["entity"], exit_t)
            if px is None:
                continue
            fwd = r["side"] * (px / r["entry_price"] - 1.0)
            self._append({"phase": "settle", "id": r["id"], "ts": self._ts(),
                          "exit_price": px, "fwd_return": fwd})
            n += 1
        return n

    # ③ 召回审计:按死因聚类,标候选误杀
    def recall_audit(self, *, cost_assumed: float = 0.0) -> dict:
        recs = self._read()
        reg = {r["id"]: r for r in recs if r["phase"] == "register"}
        settled = {r["id"]: r for r in recs if r["phase"] == "settle"}
        rows = [{**reg[i], **settled[i]} for i in settled if i in reg]

        # 精确率:GO 幸存者前向表现
        go = [r["fwd_return"] for r in rows if r["verdict"] == "go"]
        prec = summarize(go)

        # 召回:KILL 按死因聚类
        kills = [r for r in rows if r["verdict"] == "kill"]
        groups: dict[str, list] = {}
        for r in kills:
            groups.setdefault(r["kill_reason"], []).append(r)
        z_bar = bonferroni_z(max(len(groups), 1))
        flags = []
        report = {}
        for reason, rs in groups.items():
            s = summarize([r["fwd_return"] for r in rs])
            if not s:
                continue
            rclass = rs[0]["reason_class"]
            # 候选误杀:前向显著为正 且 过 Bonferroni;tradeability 类=高价值可行动
            is_candidate = s.mean > 0 and s.sign_z >= z_bar
            report[reason] = {"class": rclass, "n": s.n, "fwd_mean": s.mean,
                              "sign_z": s.sign_z, "candidate_miss": is_candidate}
            if is_candidate:
                flags.append({"reason": reason, "class": rclass, "sign_z": s.sign_z,
                              "fwd_mean": s.mean,
                              "action": ("校准 grade 成本估计(可能高估)" if rclass == "tradeability"
                                         else "低可信(显著性类误杀多半噪声),勿据此松闸")})
        return {"precision_go": prec, "bonferroni_z": z_bar, "by_reason": report,
                "flags": flags, "n_settled": len(rows)}


# ── 正控:合成确认召回审计能标出高价值误杀、不被噪声骗 ────────────────────────
def _self_test():
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "shadow.jsonl"
    reg = ShadowRegistry(tmp)
    T0 = 1_700_000_000.0
    # 真值:go组前向正;cost组(误杀)前向正(成本高估);not-sig组前向随机
    truth = {}
    def mkprice(entity, base, fwd):
        truth[(entity, "entry")] = base; truth[(entity, "fwd")] = base * (1 + fwd)
    def rng(seed):
        s = {"v": seed}
        def n():
            s["v"] = (s["v"] * 1103515245 + 12345) & 0x7FFFFFFF
            return s["v"] / 0x7FFFFFFF
        return n
    r = rng(1)
    for i in range(120):
        # go: +2%
        e = f"go{i}"; mkprice(e, 100, 0.02)
        reg.register(thesis_id="t", verdict="go", kill_reason="", entity=e, side=1,
                     entry_price=100, entry_t=T0 + i, hold_days=5, idx=i)
        # cost 误杀: +1.5%(成本高估杀的,其实赚)
        e = f"cost{i}"; mkprice(e, 100, 0.015)
        reg.register(thesis_id="t", verdict="kill", kill_reason="cost", entity=e, side=1,
                     entry_price=100, entry_t=T0 + i, hold_days=5, idx=i)
        # not-sig 误杀: 随机 ~0
        e = f"ns{i}"; mkprice(e, 100, (r() - 0.5) * 0.06)
        reg.register(thesis_id="t", verdict="kill", kill_reason="min_sign_z", entity=e, side=1,
                     entry_price=100, entry_t=T0 + i, hold_days=5, idx=i)

    price_at = lambda entity, t: truth.get((entity, "fwd"))
    ns = reg.settle(price_at, now_t=T0 + 10 * DAY)      # 全部到期
    print(f"结算 {ns} 条")
    au = reg.recall_audit()
    print(f"精确率(GO前向): mean={au['precision_go'].mean:+.4f} signZ={au['precision_go'].sign_z:+.2f}")
    print(f"Bonferroni z={au['bonferroni_z']:.2f}")
    for reason, d in au["by_reason"].items():
        print(f"  死因[{reason}]({d['class']}): n={d['n']} fwd={d['fwd_mean']:+.4f} signZ={d['sign_z']:+.2f} "
              f"候选误杀={d['candidate_miss']}")
    flg = {f["reason"] for f in au["flags"]}
    ok1 = "cost" in flg
    ok2 = "min_sign_z" not in flg
    print(f"{'✅' if ok1 else '❌'} cost 误杀被标(高价值校准) | {'✅' if ok2 else '❌'} not-sig 未被误标(噪声不骗人)")
    for f in au["flags"]:
        print(f"    🚩 {f['reason']}({f['class']}) signZ={f['sign_z']:+.2f} → {f['action']}")


if __name__ == "__main__":
    _self_test()
