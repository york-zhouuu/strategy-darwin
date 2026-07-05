---
name: strategy-status
description: 驾驶舱仪表盘——汇总当前引擎状态:shot 台账/判决历史/影子登记待结算/前向采集进展/机制库/待办。用户说"策略状态/仪表盘/现在什么情况"时触发。
---

# /strategy-status —— 驾驶舱仪表盘

读以下数据源,汇成**一屏**状态(表格),末尾给"需要注意的事":

1. **shot 台账**: `runs/lane_journal.jsonl` → 按 thesis_id 统计 register/verdict,累计 shot 数,当前 Bonferroni 门槛 `bonferroni_z(shots)`。
2. **判决史**: 各 `runs/lane_*.md` / `runs/valkit_*.md` → thesis / 判定 / 死因 一行一个。
3. **影子登记**: `runs/shadow.jsonl`(若存在)→ 已登记 GO/KILL 数、已结算数;若有到期未结算的提醒跑 settle;结算够多则跑 `recall_audit` 报候选误杀。
4. **前向采集(Form4)**: `runs/forward_paper.jsonl` → 有效/pipeline_only/pending 数;`runs/form4_purchases.jsonl` 底账规模;提醒:合格事件低频,需在美东可交易时段定时跑 `watch_form4.py --live`。
5. **机制库**: `~/GitHub/tradeagent3/data/mechanism_library.json` → confirmed/rejected/insights 计数 + 最新几条 insights。
6. **战场记分板**(从 memory/文档): 美股-证伪 / crypto-评级KILL(资金费) / Polymarket-衰减+弹跳 / 韩国流-证伪 / Form4-前向累积中。

## 需要注意的事(按急迫排)
- 当前是否美东可交易时段 → 是则提示可跑 `watch_form4.py --live`;
- shadow 有到期未结算 → 提示 settle;
- 有 thesis 卡在"评级长期观察" → 列出;
- shot 数逼近预算 → 提醒。

**只读,不改任何状态。** 输出保持一屏内,细节给文件路径不贴全文。
