---
name: strategy-loop
description: 自挖掘自迭代——机器自己提出下一个假设并走完整验证,一次调用跑一圈(或N圈)。配合 /loop 或 schedule 可无人值守。用户说"自动挖/自迭代/跑一圈策略loop"时触发。
---

# /strategy-loop —— 自挖掘自迭代一圈

每圈 = **读记忆 → 生成一个有依据的假设 → 走 /strategy 全流水线 → 回喂**。你(Claude)兼任生成器(R)和实现者(D),valkit 是不可绕过的裁判。参数 `args` 可给圈数(默认 1)或方向约束。

## 每圈步骤

### 1. 读状态(生成必须 grounded,这是花过钱买的教训)
- shot 台账: `runs/lane_journal.jsonl`(register 计数→Bonferroni 累计门槛)
- 已测/已杀: `runs/shadow.jsonl`、`~/GitHub/tradeagent3/data/mechanism_library.json`(insights 是老师)
- 最近的 NO-GO 诊断(报告在 `runs/lane_*.md`)——**上一圈的死因是这一圈最好的线索来源**

### 2. 生成下一个假设(纪律)
- **必须是机制洞察的派生**("赢家动量毒空头腿→试只做多输家"这类),或已确认机制的相邻探索,或全新机制类;**禁止旋钮追分**(同假设换参数/窗口/阈值直到过)。
- **必须落在现有数据资产上**(资产清单见 /strategy 第2节)——不可测的宇宙提了必然作废,LLM 盲提烧过 5/5 全空的钱。
- **代码级查重**: 与 shadow/机制库里已测的 (宇宙×方向×机制) 语义重复 → 换一个,重复不烧 shot。
- 陪跑多样性: 连续几圈别都在同一机制类里打转。

### 3. 走 /strategy 流水线(全部闸,无省略)
非交互跑:准入5闸→冻结prereg(累计Bonferroni)→adapter→杀戮道→(GO则)评级→影子登记→报告。

### 4. 回喂
- 判定+死因 → shadow + 机制库(rejected/insights);机制级教训该进闸的**改代码并跑正控**。
- 记一行到本圈小结:假设 / 判定 / 死因 / 派生出的下一个线索。

### 5. 停机条件(自主判断,别无限烧)
- 本 session 预算:默认最多 **3 圈**或用户指定;
- **连续 2 圈无信息增量**(全是 too_few/重复度高的 reject 且无新机制线索)→ 停,报告"当前数据资产已挖干,天花板是数据广度,建议接新数据源而非继续转";
- 出现活过评级的候选 → 停,汇报,等用户决定(重点观察/模拟盘是人的决定)。

## 无人值守用法(告诉用户,不擅自设)
- 半自动: 用户 `/loop /strategy-loop` 让 Claude 自 pace;
- 定时: `schedule` 建 cron 例程每日一圈 + 交易时段跑 `watch_form4.py --live`(前向采集);
- 前向结算: 每周跑 `ShadowRegistry.settle` + `recall_audit`(召回审计:引擎有没有误杀,tradeability 类误杀→校准 grade 成本)。

## 铁律
同 /strategy。外加:**loop 的收敛(宣布赢家)只能发生在前向数据上;历史圈只产生"值得前向的候选",永不产生"验证通过"。**
