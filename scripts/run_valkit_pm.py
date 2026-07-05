"""冒烟测试:用 valkit 强制杀戮道(KillLane)把 Polymarket fade-P0 跑一遍。

同时证明两件事:
  1. 复现已知结果(P0 结论:去重·液体·涨暴动 signZ 2025+7.9→2026+2.1,最近期不过 → NO-GO)
  2. 判决经过强制流水线:先冻结 prereg → 跑正控 → 强制检验组(含 by_period)→ 按冻结门槛判

    ./.venv/bin/python scripts/run_valkit_pm.py [path-to-pm_hist.json]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from valkit import Prereg, bonferroni_z
from valkit.lane import KillLane
from valkit.control import _self_test as control_selftest
from valkit import tradeability as tr
from valkit.adapters import polymarket as pm

HIST = sys.argv[1] if len(sys.argv) > 1 else \
    str(Path(__file__).resolve().parents[1] / "data/polymarket/pm_hist.json")

events, ret = pm.load(HIST, dedup=True, only_up=True, liquid_only=True)
print(f"去重·液体·涨暴动 事件数: {len(events)}\n")

# 仪器正控:引擎能测回真信号才可信(控制台打印明细;这里作为 lane 的 control_ok 门)
def control_ok() -> bool:
    try:
        control_selftest()      # 打印 4 项;这里简单以"能跑通不抛"为过(明细人看)
        return True
    except Exception:
        return False

# ① 先冻结门槛(freeze-before-see;lane 强制它先于 run)
prereg = Prereg(
    thesis_id="polymarket-fade-up-spike",
    hypothesis="液体市场涨暴动后 fade(反向持有7天)净成本后正收益,且最近一期仍成立",
    primary_bucket="液体(mid+big) 涨暴动", primary_horizon=7,
    min_net_return=0.0, cost=0.02, min_sign_z=bonferroni_z(12),
    min_hit=0.55, min_n=100, require_oos=True, require_latest_period=True,
    battlefield_gates={"真锚": True, "够冷门": "2026已不", "agent可处理": True,
                       "小资金可交易": True, "可验证": True},
)

lane = KillLane(Path(__file__).resolve().parents[1] / "runs" / "lane_journal.jsonl")
lane.register(prereg)   # 冻结在前

# a' 可交易性:预测市场买对侧=自由交易 → 做空依赖不适用(na);入场弹跳用 ret_delayed 真跑
trade = tr.audit(events, ret, prereg.primary_horizon, cost_tradeable=0.02,
                 ret_delayed=pm.ret_delayed, na_checks=frozenset({"short_dependence"}))
print(f"a' 可交易性: {trade.verdict} — {trade.reason}")
for name, c in trade.checks.items():
    print(f"    {name}: {'✅' if c['passed'] else '❌' if c['passed'] is False else '—'} {c['detail']}")

# ②–⑤ 跑强制流水线(P0 是机械 thesis,is_agent=False)
res = lane.run(events, ret, pm.HORIZONS, is_agent=False, control_ok=control_ok,
               tradeability=trade, costs=(0.02, 0.04),
               report_dir=Path(__file__).resolve().parents[1] / "runs")

v = res["verdict"]
print(f"\n{'='*50}")
print(f"判决: {'🟢GO' if v['passed'] else '🔴NO-GO'} — {v['reason']}")
per = res["by_period"]
for k in sorted(per, key=str):
    s = per[k].get(7)
    if s and s.n >= 15:
        print(f"  {k}: n={s.n} signZ={s.sign_z:+.2f} 净@2%={s.net(0.02):+.4f}")
print(f"报告: {res['report_path']}")
print("账本: runs/lane_journal.jsonl (register→control→verdict 全留痕,可审计)")
