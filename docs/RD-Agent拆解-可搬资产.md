# RD-Agent 最终拆解 —— 可搬资产清单(挖净版)

> 2026-07-05 一次性挖净。此文档 + `.claude/skills/paper-to-factor` 落地后,**repo 本体可弃**(留不留随意)。
> 前置结论见 `RD-Agent评估.md`:好 D 层、毒 R 裁判。本文只记"搬走了什么、怎么用、毒在哪一行"。

## 一、毒心脏(原文为证,永不搬)

`scenarios/qlib/prompts.yaml → factor_feedback_generation`:
> *"Any small improvement should be considered for inclusion as SOTA"* / *"If the new factor shows an improvement in the annualized return, recommend it to replace the current best result."*

反馈环 = 年化收益爬山,连显著性都不看。这是把 p-hacking 写成产品说明书。**我们的替代:反馈 = valkit 判决 + 机制诊断,永不 = 回测数字。**

## 二、搬走的五样(已蒸馏进 skill/流程)

### 1. 两段式因子抽取(`factor_experiment_loader/prompts.yaml`)
- **Pass A** `extract_factors`:抽全部因子(名+描述),显式提醒**别漏表格里的**;有 `follow_user` 续抽循环(报告长时反复"继续抽,忽略已抽")直到抽干。
- **Pass B** `extract_factor_formulation`:每个因子逼出 **LaTeX 公式 + 每个变量/函数定义**,且必须落在**显式列出的数据源清单**上("Here are the sources of data I have: 1.行情表 2.财务表 3.基本面表 4.高频")→ 含糊的一句话被钉成可计算 spec。
- 搬法:数据源清单换成**我们的资产**(见 skill);JSON schema 原样可用。

### 2. 三道预闸(同文件)——实现前廉价过滤
- `classify`:这文档是不是选股类量化研报?(1/0,先滤垃圾输入)
- `factor_viability`:能否按日、按标的、用现有数据算出?**拒绝要有实据**。
- `factor_relevance`:只由数学运算得出、不靠主观判断/自然语言分析 → **这其实是泄漏安全判据**(纯机械=可干净回测=走 valkit 机械路径)。
- 搬法:三道闸合并进 skill 的"落地性审查"步。

### 3. 可实现性挑选(`factor_coder/prompts.yaml → select_implementable_factor`)
带着**历史失败记录**挑最易实现的 N 个:"某因子反复试败 → 考虑放弃"。搬法:进 skill 的实现顺序决策;失败历史记进机制库。

### 4. CoSTEER 修复循环(`evolving_strategy_factor_implementation_*`)——实现失败时的自愈模式
喂给下一轮的四种上下文,优先级明确:
1. **上次失败的代码 + 反馈**("必须基于上次代码改,别动已对的部分");
2. **相似错误的 修复前→修复后 成对样例**(error→fix pairs);
3. **相似因子的成功代码**当参照;
4. 错误摘要批评(error_summary_critics)。
搬法:这就是"带记忆的调试"提示词模式,写代码卡住时按此顺序组织上下文;成功/失败样例落机制库(= 他们 1053 行 knowledge_management 的穷人版,但我们有 memory 系统,天然替代)。

### 5. 评估器裁决逻辑(`evaluator_final_decision_v1`)
多维反馈(执行/代码/值格式)→ 单一 final_decision,规则:有 ground truth 比对 → 高相关即对;**无 ground truth → 跑通 + 与因子描述自洽才算对,任何异常(含主动 raise)都算代码的错**。搬法:进 skill 的"实现验收"步;比对基准 = 我们的仪器正控思想。

## 三、明确不搬的

| 东西 | 为什么 |
|---|---|
| feedback 环(§一) | 毒 |
| Qlib/Docker/CSI300 执行体 | 重、A股耦合;valkit 在自己数据上当唯一裁判 |
| hypothesis 演进策略(`factor_hypothesis_specification`) | "简单→复杂、连败换方向"两条常识已在 /strategy-loop;其余是为爬山服务的 |
| knowledge_management.py(1053行) | 用 Claude Code memory + 机制库天然替代 |
| LiteLLM 后端/UI | 不需要 |

## 四、去向

- 操作入口:`tradeagent/.claude/skills/paper-to-factor/SKILL.md`(§二全部蒸馏在内)
- 落地后接 `/strategy`(prereg→杀戮道→评级),反馈接机制库——**抽取是 RD-Agent 的,裁判是我们的**。
