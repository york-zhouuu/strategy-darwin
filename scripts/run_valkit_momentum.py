"""校准测试:12-1 动量(文献里最稳的真异象)走 valkit 杀戮道 —— 检验 lane 会不会"过度杀"。
若连动量都 NO-GO,拆清是地形(universe弱)还是 lane 太严。
12-1: 信号=close[t-21]/close[t-252]-1(过去12月除最近1月);买赢家/卖输家;月度调仓。
"""
import sys, csv, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from valkit import Prereg, bonferroni_z, tradeability_audit
from valkit.study import Event
from valkit.lane import KillLane

PRICES = Path(__file__).resolve().parents[1] / "data/us_prices"
LB, SKIP, REBAL, DECILE = 252, 21, 21, 0.2
HORIZONS = [21, 42, 63]; PRIM = 21
series = {}
for f in sorted(PRICES.glob("*.csv")):
    ds, cs = [], []
    for row in csv.DictReader(open(f)):
        try: cs.append(float(row["close"])); ds.append(row["date"])
        except: pass
    if len(cs) > LB + max(HORIZONS) + 30: series[f.stem] = (ds, cs)
print(f"载入标的(够长做12-1): {len(series)}")
ref = max(series, key=lambda t: len(series[t][0])); cal = series[ref][0]
pos = {t: {d:i for i,d in enumerate(series[t][0])} for t in series}
unix = lambda d: dt.datetime.strptime(d,"%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()

events = []; maxh = max(HORIZONS)
for i in range(LB, len(cal)-maxh-1, REBAL):
    d = cal[i]; ranked = []
    for t,(ds,cs) in series.items():
        p = pos[t].get(d)
        if p is None or p < LB or p+maxh+1 >= len(cs): continue
        mom = cs[p-SKIP]/cs[p-LB]-1.0     # 过去12月除最近1月
        ranked.append((mom, t, p))
    if len(ranked) < 20: continue
    ranked.sort(); k = max(1, int(len(ranked)*DECILE))
    for mom,t,p in ranked[-k:]:  # 赢家做多
        events.append(Event(entity=t, t0=unix(d), bucket="winner-long", reaction_sign=+1, meta={"tk":t,"p":p}))
    for mom,t,p in ranked[:k]:   # 输家做空
        events.append(Event(entity=t, t0=unix(d), bucket="loser-short", reaction_sign=-1, meta={"tk":t,"p":p}))
print(f"动量事件: {len(events)}  (赢家做多 + 输家做空)")

def _ret(e,h,off):
    t,p,side = e.meta["tk"], e.meta["p"], e.reaction_sign; cs=series[t][1]; en=p+off; ex=en+h
    return None if ex>=len(cs) or en>=len(cs) else side*(cs[ex]/cs[en]-1.0)
ret = lambda e,h: _ret(e,h,0)

prereg = Prereg(thesis_id="paper-12-1-momentum", primary_bucket="all", primary_horizon=PRIM,
    hypothesis="12-1横截面动量(买赢家/卖输家)持有1月净成本后正,最近期仍成立",
    min_net_return=0.0, cost=0.002, min_sign_z=bonferroni_z(6), min_hit=0.52, min_n=200,
    require_oos=True, require_latest_period=True)
lane = KillLane(Path(__file__).resolve().parents[1]/"runs"/"lane_journal.jsonl")
lane.register(prereg)
trade = tradeability_audit(events, ret, PRIM, side=lambda e:e.reaction_sign,
    ret_delayed=lambda e,h,off:_ret(e,h,off), cost_tradeable=0.002, long_only=True)
print(f"\na': {trade.verdict} — {trade.reason}")
for n,c in trade.checks.items():
    print(f"   {'✅' if c['passed'] else '❌' if c['passed'] is False else '—'} {n}: {c['detail']}")
res = lane.run(events, ret, HORIZONS, is_agent=False, control_ok=lambda:True, tradeability=trade, costs=(0.002,0.005))
v = res["verdict"]
print(f"\n判决: {'🟢GO' if v['passed'] else '🔴NO-GO'} — {v['reason']}")
for h in HORIZONS:
    s=res["full"].get(h)
    if s: print(f"  HD{h}: n={s.n} 命中={s.hit:.0%} signZ={s.sign_z:+.2f} 均值={s.mean:+.4f} 净@20bps={s.net(0.002):+.4f}")
print("  分腿(多空):")
for b,r in res["buckets"].items():
    s=r.get(PRIM)
    if s: print(f"    {b}: n={s.n} signZ={s.sign_z:+.2f} 均值={s.mean:+.4f}")
print("  时间衰减:")
for k in sorted(res["by_period"],key=str):
    s=res["by_period"][k].get(PRIM)
    if s and s.n>=30: print(f"    {k}: n={s.n} signZ={s.sign_z:+.2f} 净@20bps={s.net(0.002):+.4f}")
