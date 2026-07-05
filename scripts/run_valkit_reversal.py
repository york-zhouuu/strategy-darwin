"""端到端 demo:论文因子 → valkit 杀戮道回测。

我(LLM)当 RD-Agent 的 D 层:实现一个已发表因子——**短期反转**(Lehmann 1990/Jegadeesh 1990):
横截面上,过去 k 日的输家随后反弹、赢家回落 → 买输家、卖赢家。出名的死法=被成本+入场弹跳吃掉。
数据:tradeagent3 本地美股日线 CSV(~149 只,2023–2026,仅 close)。纯机械计算(无逐事件 LLM 判断)→ 走机械路径;
"论文=已知因子"的选择性污染由 OOS/最近期闸防御(不是靠泄漏探针)。

    ./.venv/bin/python scripts/run_valkit_reversal.py
"""
import sys, csv, datetime as dt
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from valkit import Prereg, bonferroni_z, tradeability_audit
from valkit.study import Event
from valkit.lane import KillLane

PRICES = Path(__file__).resolve().parents[1] / "data/us_prices"
LOOKBACK = 5          # 过去 5 日定输赢家
HORIZONS = [1, 3, 5]  # 前向持有
REBAL = 5             # 每 5 交易日调仓
DECILE = 0.2          # 取两端各 20% 为极端事件

# 载入 {ticker: (dates[], closes[])}
series = {}
for f in sorted(PRICES.glob("*.csv")):
    ds, cs = [], []
    with open(f) as fh:
        for row in csv.DictReader(fh):
            try:
                cs.append(float(row["close"])); ds.append(row["date"])
            except (ValueError, KeyError):
                pass
    if len(cs) > 60:
        series[f.stem] = (ds, cs)
print(f"载入标的: {len(series)}")

# 参考日历 = 覆盖最全的标的
ref = max(series, key=lambda t: len(series[t][0]))
cal = series[ref][0]
pos = {t: {d: i for i, d in enumerate(series[t][0])} for t in series}

def unix(d):
    return dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp()

# 构造反转事件:每个调仓日,横截面按过去 5 日收益排序,取两端极端
events = []
maxh = max(HORIZONS)
for i in range(LOOKBACK, len(cal) - maxh - 1, REBAL):
    d = cal[i]
    ranked = []
    for t, (ds, cs) in series.items():
        p = pos[t].get(d)
        if p is None or p < LOOKBACK or p + maxh + 1 >= len(cs):
            continue
        past = cs[p] / cs[p - LOOKBACK] - 1.0
        ranked.append((past, t, p))
    if len(ranked) < 20:
        continue
    ranked.sort()
    k = max(1, int(len(ranked) * DECILE))
    losers = ranked[:k]     # 过去输家 → 反转做多 side=+1
    winners = ranked[-k:]   # 过去赢家 → 反转做空 side=-1
    for past, t, p in losers:
        events.append(Event(entity=t, t0=unix(d), bucket="loser(long)", reaction_sign=+1,
                            meta={"tk": t, "p": p}))
    for past, t, p in winners:
        events.append(Event(entity=t, t0=unix(d), bucket="winner(short)", reaction_sign=-1,
                            meta={"tk": t, "p": p}))
print(f"反转事件: {len(events)}  (输家做多 + 赢家做空)")

def _ret(e, h, offset):
    t, p, side = e.meta["tk"], e.meta["p"], e.reaction_sign
    cs = series[t][1]
    entry = p + offset
    ex = entry + h
    if ex >= len(cs) or entry >= len(cs):
        return None
    return side * (cs[ex] / cs[entry] - 1.0)   # 反转持仓收益(side 已含多空)

def ret(e, h):
    return _ret(e, h, 0)

def ret_delayed(e, h, offset):
    return _ret(e, h, offset)

# 预注册(冻结在前):反转应净成本后正、最近期仍成立
prereg = Prereg(
    thesis_id="paper-short-term-reversal",
    hypothesis="横截面短期反转(买5日输家/卖赢家)持有5日净成本后正收益,最近一期仍成立",
    primary_bucket="all", primary_horizon=5,
    min_net_return=0.0, cost=0.002,              # 20bps/腿,liquid 保守估
    min_sign_z=bonferroni_z(6), min_hit=0.52, min_n=200,
    require_oos=True, require_latest_period=True,
    battlefield_gates={"真锚": "股票有基本面", "够冷门": "否(流动大盘)",
                       "agent可处理": "机械因子无需", "小资金可交易": "待a'验", "可验证": True},
)

lane = KillLane(Path(__file__).resolve().parents[1] / "runs" / "lane_journal.jsonl")
lane.register(prereg)

# a':side(多空拆) + ret_delayed(入场弹跳)都给 hook → 四检全跑
trade = tradeability_audit(events, ret, 5, side=lambda e: e.reaction_sign,
                           ret_delayed=ret_delayed, cost_tradeable=0.002, long_only=True)
print(f"\na' 可交易性: {trade.verdict} — {trade.reason}")
for name, c in trade.checks.items():
    mark = "✅" if c["passed"] else "❌" if c["passed"] is False else "—"
    print(f"    {mark} {name}: {c['detail']}")

res = lane.run(events, ret, HORIZONS, is_agent=False, control_ok=lambda: True,
               tradeability=trade, costs=(0.002, 0.005),
               report_dir=Path(__file__).resolve().parents[1] / "runs")
v = res["verdict"]
print(f"\n{'='*50}\n判决: {'🟢GO' if v['passed'] else '🔴NO-GO'} — {v['reason']}")
for h in HORIZONS:
    s = res["full"].get(h)
    if s:
        print(f"  HD{h}: n={s.n} 命中={s.hit:.0%} signZ={s.sign_z:+.2f} 均值={s.mean:+.4f} 净@20bps={s.net(0.002):+.4f}")
print("  时间衰减:")
for k in sorted(res["by_period"], key=str):
    s = res["by_period"][k].get(5)
    if s and s.n >= 30:
        print(f"    {k}: n={s.n} signZ={s.sign_z:+.2f} 净@20bps={s.net(0.002):+.4f}")
