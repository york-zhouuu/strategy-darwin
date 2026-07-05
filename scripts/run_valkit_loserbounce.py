"""策略 loop 第 2 圈:从反转 NO-GO 的诊断洞察("输家反弹+63bps,赢家动量毒空头腿")
派生新假设——**只做多短期输家反弹**——开新 prereg 诚实再验(非 retrofit)。
require_latest_period=True 强制 2026 也要成立,防止跨迭代 p-hacking。
"""
import sys, csv, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from valkit import Prereg, bonferroni_z, tradeability_audit
from valkit.study import Event
from valkit.lane import KillLane

PRICES = Path(__file__).resolve().parents[1] / "data/us_prices"
LOOKBACK, HORIZONS, REBAL, DECILE = 5, [1,3,5], 5, 0.2
series = {}
for f in sorted(PRICES.glob("*.csv")):
    ds, cs = [], []
    for row in csv.DictReader(open(f)):
        try: cs.append(float(row["close"])); ds.append(row["date"])
        except: pass
    if len(cs) > 60: series[f.stem] = (ds, cs)
ref = max(series, key=lambda t: len(series[t][0])); cal = series[ref][0]
pos = {t: {d:i for i,d in enumerate(series[t][0])} for t in series}
unix = lambda d: dt.datetime.strptime(d,"%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()

events = []; maxh = max(HORIZONS)
for i in range(LOOKBACK, len(cal)-maxh-1, REBAL):
    d = cal[i]; ranked = []
    for t,(ds,cs) in series.items():
        p = pos[t].get(d)
        if p is None or p < LOOKBACK or p+maxh+1 >= len(cs): continue
        ranked.append((cs[p]/cs[p-LOOKBACK]-1.0, t, p))
    if len(ranked) < 20: continue
    ranked.sort(); k = max(1, int(len(ranked)*DECILE))
    for past,t,p in ranked[:k]:      # 只取输家,做多
        events.append(Event(entity=t, t0=unix(d), bucket="loser-long", reaction_sign=+1, meta={"tk":t,"p":p}))
print(f"只做多输家事件: {len(events)}")

def _ret(e,h,off):
    t,p = e.meta["tk"], e.meta["p"]; cs = series[t][1]; en=p+off; ex=en+h
    return None if ex>=len(cs) or en>=len(cs) else (cs[ex]/cs[en]-1.0)
ret = lambda e,h: _ret(e,h,0)

prereg = Prereg(thesis_id="loserbounce-longonly", primary_bucket="loser-long", primary_horizon=5,
    hypothesis="只做多5日输家、持有5日,净成本后正收益且最近一期(2026)仍成立",
    min_net_return=0.0, cost=0.002, min_sign_z=bonferroni_z(3), min_hit=0.52, min_n=200,
    require_oos=True, require_latest_period=True)
lane = KillLane(Path(__file__).resolve().parents[1]/"runs"/"lane_journal.jsonl")
lane.register(prereg)
trade = tradeability_audit(events, ret, 5, side=lambda e:+1,
    ret_delayed=lambda e,h,off:_ret(e,h,off), cost_tradeable=0.002, na_checks=frozenset({"short_dependence"}))
print(f"a': {trade.verdict} — {trade.reason}")
for n,c in trade.checks.items():
    print(f"   {'✅' if c['passed'] else '❌' if c['passed'] is False else '—'} {n}: {c['detail']}")
res = lane.run(events, ret, HORIZONS, is_agent=False, control_ok=lambda:True, tradeability=trade, costs=(0.002,0.005))
v = res["verdict"]
print(f"\n判决: {'🟢GO' if v['passed'] else '🔴NO-GO'} — {v['reason']}")
for h in HORIZONS:
    s=res["full"].get(h)
    if s: print(f"  HD{h}: n={s.n} 命中={s.hit:.0%} signZ={s.sign_z:+.2f} 均值={s.mean:+.4f} 净@20bps={s.net(0.002):+.4f}")
print("  时间衰减:")
for k in sorted(res["by_period"],key=str):
    s=res["by_period"][k].get(5)
    if s and s.n>=30: print(f"    {k}: n={s.n} signZ={s.sign_z:+.2f} 净@20bps={s.net(0.002):+.4f}")
