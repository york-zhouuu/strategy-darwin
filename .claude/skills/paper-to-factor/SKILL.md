---
name: paper-to-factor
description: 论文/研报→可测因子spec流水线——读一篇PDF/URL/文本,抽干全部因子,钉成可计算spec,过三道预闸(分类/可行/泄漏安全),再交给 /strategy 验证。用户给论文让"抽因子/验证这篇论文/paper-to-factor"时触发。
---

# /paper-to-factor —— 论文/研报 → 因子 spec → 接 /strategy

蒸馏自 RD-Agent 的 D 层(拆解见 `~/GitHub/tradeagent4/RD-Agent拆解-可搬资产.md`),**裁判换成 valkit**。它的反馈环(年化收益爬山)是毒,已弃;抽取链是金,在此。

## 流水线

### 0. 分类闸(先滤输入)
这文档是不是"含可计算因子/信号"的量化材料?不是(纯宏观叙事/新闻/无公式无规则)→ 直接告知,结束。

### 1. Pass A 抽干因子(别漏表格!)
通读全文,抽**全部**因子/信号:`{因子名: 一句话描述}`。
- 因子常藏在**表格、附录、稳健性检验**里——显式扫这些区域;
- 长文档分段抽,每段提醒自己"忽略已抽,继续找漏网的",直到一轮抽不出新的为止(RD-Agent 的 follow-up 循环)。

### 2. Pass B 钉成可计算 spec
每个因子产出:
```json
{"factor_name": {"description": "[类型]描述", "formulation": "LaTeX 公式",
  "variables": {"变量/函数": "定义"}, "data_mapping": "映射到下面哪个资产的哪些列"}}
```
**公式必须落在我们的数据资产上**(这是 spec 是否成立的判据):
| 资产 | 列 |
|---|---|
| 美股日线 `~/GitHub/tradeagent3/data/prices/*.csv` | date, close(仅收盘!无量无高低) |
| Binance `data_cache/binance/*.pkl` | date, OHLCV |
| Polymarket `tradeagent2/p0_fade/data/pm_hist.json` | 日级价格序列+结局+量带 |
| 韩国散户流 `tradeagent3/data/flows/` | 日×ISIN 净买/买/卖额 |
| Form4 底账 `runs/form4_purchases.jsonl` | 内部人买入流水 |
映射不上(要财务报表/分析师预期/高频tick) → 标 `data_gap`,别硬造。

### 3. 三道预闸(实现前,每因子)
- **可行**:能按日、按标的、用上表数据算出?拒绝要给实据(缺什么列)。
- **泄漏安全**:纯数学运算可得(→ /strategy 走机械路径)?还是要 LLM 逐事件定性(→ agent 路径,leakage/cutoff/pit 必审)?**在 spec 里标明路径**。
- **重复**:机制库/shadow 里已测过等价物?→ 标 duplicate 不烧 shot。

### 4. 挑实现顺序
按"最易实现+最不同机制"挑 1-3 个先做(带失败历史:反复实现失败的因子考虑放弃并记录原因)。

### 5. 实现(CoSTEER 修复模式)
写 adapter/因子代码;**失败时按此优先级组织下一轮上下文**:①上次代码+错误反馈(只改错的部分)②机制库里相似错误的 修复前→后 样例 ③相似因子的成功代码。验收 = 跑通 + 输出与因子描述自洽 + 任何异常都算代码的错;成功/失败样例记进机制库。

### 6. 交棒 /strategy
每个存活 spec = 一个 thesis → 走 /strategy 全流水线(冻结 prereg → 杀戮道 → 评级 → 影子登记)。**基线预期是 NO-GO**(McLean-Pontiff:发表后衰减 ~58%,多数因子不复现)——本 skill 的价值是把"验证任意论文 claim"的边际成本压到接近零,不是保证捞到金子。

## 铁律
- 抽取忠实于原文;公式含糊处标 `ambiguous` 请用户裁决,不脑补。
- LLM 读过这些论文 = 选择被污染 → 显著性判据靠 valkit 的 OOS/latest_period 闸,不靠"论文说有效"。
- 每篇论文的抽取结果(含 data_gap/duplicate)落一份 `runs/paper_<slug>.md`,机制库计一笔。
