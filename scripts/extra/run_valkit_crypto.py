"""校准+edge测试:把已知真信号(冷门币下砸继续跌=做空)喂进 valkit 杀戈道。
目的:①会不会冒出第一个幸存者 ②lane 面对真信号会否过度杀。
复用 tradeagent 的 make_crypto_volspike_events + build_event_frame(size匹配基准)。
crypto:24/7 无隔夜跳空→entry_bounce 不适用;永续可做空→long_only=False。
"""
import sys, glob, importlib.util, datetime as dt
from pathlib import Path
import pandas as pd, numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tradeagent.validation.drift import build_event_frame
_spec = importlib.util.spec_from_file_location("rc", ROOT / "scripts" / "run_crypto_l1.py")
_rc = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_rc)
from valkit import Prereg, bonferroni_z, tradeability_audit
from valkit.study import Event
from valkit.lane import KillLane

# 直接用 156 个缓存币当 universe(避开联网选币)
prices, caps = {}, {}
for f in glob.glob(str(ROOT / "data_cache/binance/*.pkl")):
    sym = Path(f).stem.upper()
    df = pd.read_pickle(f)
    if len(df) >= 120:
        prices[sym] = df; caps[sym] = float(df["volume"].median())
print(f"universe(缓存币): {len(prices)}")

events, capmap = _rc.make_crypto_volspike_events(prices, caps, since=dt.date(2023, 1, 1))
ev_df, _ = build_event_frame(events, prices, capmap, windows=(3, 5, 10))
print(f"放量异动事件: {len(ev_df)}  | 列: {[c for c in ev_df.columns if c.startswith(('abn','react','dvol'))]}")

# 只取下砸事件(react_sign<0),做空 → ret = -abn_h(继续跌则空头赚)
dn = ev_df[ev_df["react_sign"] < 0].reset_index(drop=True)
# 冷门度:dvol_pre 低=冷门,取最冷 1/3
dn["illq"] = pd.qcut((-dn["dvol_pre"].fillna(dn["dvol_pre"].median())).rank(method="first"), 3, labels=False)
cold = dn[dn["illq"] == 2].reset_index(drop=True)   # 最冷门三分之一
print(f"下砸事件: {len(dn)}  其中最冷门1/3: {len(cold)}")

unix = lambda d: dt.datetime.combine(d, dt.time()).replace(tzinfo=dt.timezone.utc).timestamp()
rows = cold
events_v = [Event(entity=r["ticker"], t0=unix(r["date"]), bucket="cold-downspike",
                  reaction_sign=-1, meta={"i": i}) for i, r in rows.iterrows()]

def ret(e, h):
    v = rows.loc[e.meta["i"], f"abn_{h}"]
    return None if pd.isna(v) else -float(v)   # 做空:继续跌(abn<0)→ 空头正收益

prereg = Prereg(thesis_id="crypto-cold-downspike-short", primary_bucket="cold-downspike", primary_horizon=5,
    hypothesis="冷门币下砸后做空(永续),持有5日 size匹配异常收益net后正,最近期仍成立",
    min_net_return=0.0, cost=0.003, min_sign_z=bonferroni_z(6), min_hit=0.53, min_n=150,
    require_oos=True, require_latest_period=True)
lane = KillLane(ROOT / "runs" / "lane_journal.jsonl")
lane.register(prereg)
trade = tradeability_audit(events_v, ret, 5, side=lambda e: -1, cost_tradeable=0.003,
    long_only=False, na_checks=frozenset({"entry_bounce"}))  # 永续可空 + 无隔夜跳空
print(f"\na': {trade.verdict} — {trade.reason}")
for n, c in trade.checks.items():
    print(f"   {'✅' if c['passed'] else '❌' if c['passed'] is False else '—'} {n}: {c['detail']}")
res = lane.run(events_v, ret, [3, 5, 10], is_agent=False, control_ok=lambda: True, tradeability=trade, costs=(0.003, 0.006))
v = res["verdict"]
print(f"\n判决: {'🟢GO' if v['passed'] else '🔴NO-GO'} — {v['reason']}")
for h in [3, 5, 10]:
    s = res["full"].get(h)
    if s: print(f"  HD{h}: n={s.n} 命中={s.hit:.0%} signZ={s.sign_z:+.2f} 均值(空头abn)={s.mean:+.4f} 净@30bps={s.net(0.003):+.4f}")
print("  时间衰减:")
for k in sorted(res["by_period"], key=str):
    s = res["by_period"][k].get(5)
    if s and s.n >= 30: print(f"    {k}: n={s.n} signZ={s.sign_z:+.2f} 净@30bps={s.net(0.003):+.4f}")

# ── 确认道前端:即使 GO,也要过致命闸评级 ──────────────────────────────────
if v["passed"]:
    from valkit import grade, Constraints
    p5 = res["full"][5]; p10 = res["full"][10]
    bp = {k: res["by_period"][k].get(5) for k in res["by_period"]}
    print(f"\n成本敏感性: HD5 edge={p5.mean:+.4f}→死于总成本>{p5.mean*1e4:.0f}bps | "
          f"HD10 edge={p10.mean:+.4f}→死于>{p10.mean*1e4:.0f}bps")
    # 约束模型:冷门 alt 永续做空(数值=估计,待模拟操盘周核实)
    cons = Constraints(
        all_in_cost=0.009,            # 估计:资金费(~10bps/日×5)+滑点/点差(冷门入场)≈90bps
        capacity_usd=5_000, target_capital=50_000,
        shortable="partial",          # 最冷门1/3永续未必上市
        ruin_risk="unbounded", crowding="medium",
        operational="note:24/7盯盘+离岸交易所对手方", cost_source="估计(含资金费,待模拟核实)")
    g = grade(p5, bp, cons, side_is_short=True)
    print("\n" + g.show())
