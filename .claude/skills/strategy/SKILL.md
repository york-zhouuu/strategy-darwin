---
name: strategy
description: 驾驶舱手动入口——用户给一个策略想法(自然语言),走完整证伪流水线:准入闸→预注册冻结→adapter→杀戮道→评级→影子登记→报告+机制库回喂。用户说"验证这个策略/测一下这个想法/strategy XXX"时触发。
---

# /strategy —— 验证一个策略想法(完整流水线)

你是这台策略验证引擎的驾驶员。用户给一个策略想法,你按下面顺序走**完整流水线**,任何一道闸红了就干净止损、归档、给出机制诊断。**裁判是 valkit 工具(会拒绝执行),不是你的判断;你的判断只用在"怎么做"上。**

核心文档(先读,勿跳): `docs/valkit-验证基建总览.md`(引擎全貌+走一遍范例)、`docs/证伪裁判协议.md`(协议)。

## 流水线(顺序执行,前闸不过不进后闸)

### 1. 战场准入 5 闸(纸上快审,不写代码)
真锚 / 够冷门 / agent可处理(若含LLM判断) / 小资金($10k-100k)能真交易 / 可验证(事件率够到达显著)。
任一条纸上就红 → 一句话理由,记入机制库,**不建管道,结束**。

### 2. 数据可得性(用现有资产,别重拉)
| 战场 | 资产 | adapter |
|---|---|---|
| Polymarket | `~/GitHub/tradeagent2/p0_fade/data/pm_hist.json` | `valkit.adapters.polymarket` |
| 美股日线 | `~/GitHub/tradeagent3/data/prices/*.csv`(~235票,2020-2026,幸存者偏差流动票) | 参考 `scripts/run_valkit_reversal.py` |
| Crypto | `data_cache/binance/*.pkl`(145币,2023-2026) | 参考 `scripts/run_valkit_crypto.py`(复用 size匹配基准) |
| 韩国散户流 | `~/GitHub/tradeagent3/data/flows/` | `tradeagent3/src/sm_gates.py`(含冷却去重/成本/recent闸) |
| Form4 内部人 | `runs/form4_purchases.jsonl` + 前向 `runs/forward_paper.jsonl` | `scripts/watch_form4.py`(前向,只可累积不可回测快速窗口) |
需要新数据 → 先向用户报"拉数成本",别擅自开工。

### 3. 冻结预注册(在看任何结果之前!)
```python
sys.path.insert(0, "src")
from valkit import Prereg, bonferroni_z
from valkit.lane import KillLane
# shot 数 = runs/lane_journal.jsonl 里 register 条数 + 1,Bonferroni 用累计
lane = KillLane("runs/lane_journal.jsonl")
lane.register(Prereg(thesis_id=..., hypothesis=一句话含方向, primary_horizon=...,
    min_net_return=0.0, cost=按战场(美股0.002/crypto0.003/PM0.02),
    min_sign_z=bonferroni_z(累计shot数), min_hit=0.53+, min_n=100+,
    require_oos=True, require_latest_period=True))   # latest 闸绝不许关
```
**register 必须先于任何 study/回测结果被看到。lane 会拒绝 retrofit——别试。**

### 4. 写/复用 adapter → 跑杀戮道
- 机械策略(纯数值规则,即使公式来自论文): `is_agent=False`。
- 决策链含 LLM 逐事件定性判断: `is_agent=True` + 必传 `leakage/cutoff/pit` 审计(见 `valkit/leakage.py` `valkit/pit.py`),缺任一够不到 GO。
- a' 可交易性: `tradeability_audit(...)`,能给 `side`/`ret_delayed` hook 就给(入场弹跳杀过 Polymarket),战场不适用用 `na_checks` 显式标。
```python
res = lane.run(events, ret, horizons, is_agent=..., control_ok=正控, tradeability=trade, report_dir="runs")
```

### 5. NO-GO → 诊断;GO → 评级
- **NO-GO**: 从 by_bucket(多空拆)/by_period(衰减)/a'(死因) 提取**机制诊断**——"为什么死"就是下一个假设的线索。写进报告。
- **GO**: 立即 `valkit.grade`(全口径成本含资金费/容量/可做空/爆仓/regime/运营,`Constraints` 按战场填)。分级 kill/长期观察/重点观察。**杀戮道 GO ≠ 能交易,crypto 那个 GO 就被评级毙了(资金费幻觉)。**

### 6. 影子登记(GO 和 KILL 都登记)
`valkit.ShadowRegistry("runs/shadow.jsonl")` —— register 带 verdict+死因,供日后召回审计(引擎有没有误杀)。

### 7. 收尾
- 报告落 `runs/`,一句话判决 + 诊断 + 下一个假设线索。
- 机制库回喂: 教训是**代码级**的(该进闸的进闸)就改 valkit/闸并跑正控;是**知识级**的写进机制库/memory。

## 铁律(违反=流水线作废)
1. 看结果后改门槛 = retrofit,lane 会拒绝;换持有期/换子集 = **新假设新 prereg 新 shot**。
2. 回测数字只当上界;agent 环节历史回放一律不作结论(泄漏铁律)。
3. 机制洞察(关于世界的新假设)可以派生下一轮;**旋钮追分(换参数直到过)禁止**。
4. 假阳性远贵于假阴性——存疑时,杀。
