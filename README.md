# strategy-darwin — 策略的进化机器

> **变异 × 选择 × 遗传:LLM 生成策略假设(变异),工具强制的证伪流水线杀掉 95%(选择),机制库把每次死亡的教训传给下一代(遗传)。**
> A self-iterating strategy machine built on natural selection: LLM proposes (variation), a tool-enforced falsification engine — **valkit** — kills what doesn't survive (selection), and a mechanism library inherits every lesson (heredity). Backtests are upper bounds; when it says GO, it's true.

个人量化最大的敌人不是找不到信号,是**自欺**——p-hacking、LLM 泄漏(权重前视)、幸存者偏差、成本幻觉。这台机器的选择压(裁判引擎 `valkit`)把"不许自欺"从纪律变成**会拒绝执行的代码**:进化只在真实的适应度上发生,不在被污染的回测数字上。

## 30 秒看懂(一代进化)

```
变异  策略假设(手输 / 论文抽取 / LLM 自挖掘,受机制库既往教训引导)
   ↓ 冻结预注册(看结果前钉死门槛,retrofit 会被工具拒绝)
选择【杀戮道】仪器正控 → 强制检验组(含时间衰减切片) → LLM泄漏三闸(探针/cutoff/PIT) → 可交易性四检
   ↓ 95% 在此 NO-GO —— 但每次死亡都附带机制诊断
选择【确认道】致命闸评级(全口径成本/容量/爆仓/…) → 影子登记+召回审计(选择压自查有没有误杀)
   ↓ 极少数幸存者 → 前向 paper(唯一能宣布赢家的地方)
遗传  死因+机制洞察回喂机制库 → 引导下一代假设;教训升级为新闸门(选择压自身也在进化)
```

## 24 小时阵亡名单(全部真实判决)

机器连续运转至今:**26 个策略,横跨 4 个战场(预测市场/美股/加密/韩国散户流)、6 条矿脉(经典论文 / 人工直觉 / 模板枚举 / 外部攻略 / LLM 自创 / 尸检报告派生的第二代),全部阵亡,零幸存。** 死因分布在流水线每一道关卡:机制预审 4、统计审判 9、时间体检 3、落地体检 5、落地评级 1、可行性 5——包括唯一通过统计审判的那个(加密冷门币做空,命中率 71%),也被落地评级以"资金费+滑点把 +0.33% 吃成 -0.57%"拦下。完整名单(具体规则+死亡关卡+死因数字)见 [`产品说明文档.md`](./产品说明文档.md) §5,每条判决书可在 `runs/`、`docs/` 复查。

**我们没找到能赚钱的策略——这是真话,也是这台机器存在的意义:它不肯为了让你开心而放水。哪天它说"通过",那句话才有分量。**

## 快速开始(核心引擎零依赖,系统 Python≥3.9 即可)

```bash
# 1. 引擎自证(32+ 项正控:先证明引擎能测出真信号、不把噪声当信号、抓得住泄漏)
python3 src/valkit/control.py       # 机械引擎正控(注入漂移测得回/噪声不显著/衰减被抓)
python3 src/valkit/leakage.py       # LLM 泄漏审计正控(clean/leaky/noise 三合成)
python3 src/valkit/tradeability.py  # 可交易性闸正控(尾部/做空依赖/入场弹跳/成本)
python3 src/valkit/pit.py           # cutoff+PIT 正控
python3 src/valkit/grade.py         # 致命闸评级正控
python3 src/valkit/lane.py          # 强制流水线正控(10 项纪律拦截)
python3 src/valkit/paper.py         # 影子登记+召回审计正控

# 2. 真实数据端到端(数据已含在 data/,全公开来源)
python3 scripts/run_valkit_pm.py          # Polymarket fade → NO-GO(衰减+入场弹跳双死因)
python3 scripts/run_valkit_reversal.py    # 论文因子·短期反转 → NO-GO(死于成本;诊断出多空不对称)
python3 scripts/run_valkit_loserbounce.py # 由上一诊断派生的新假设 → NO-GO(策略loop不自毁的演示)
python3 scripts/run_valkit_momentum.py    # 12-1 动量(引擎过度杀校准) → NO-GO(无显著base)
```

每次运行:判决+报告落 `runs/`,append-only 账本记录 register→control→verdict 全程可审计。

## 目录

```
src/valkit/          引擎(纯标准库):stats/study/prereg/report + control/leakage/tradeability/pit + lane/grade/paper
src/valkit/adapters/ 战场适配器(每个市场一个文件;策略含义封在适配器,纪律在引擎)
scripts/             端到端验证脚本(4个自包含 + extra/crypto 需完整工作区)
data/                演示数据(Polymarket 7718市场 / 美股日线235票 / Binance 145币,全公开API来源)
docs/                证伪裁判协议 / 引擎总览 / RD-Agent 拆解与排毒记录
.claude/skills/      Claude Code 驾驶舱(4个斜杠命令:/strategy /strategy-loop /strategy-status /paper-to-factor)
```

## Claude Code 驾驶舱(AI 的用法)

在 Claude Code 中打开本仓库,四个按钮即入口:`/strategy <想法>`(手动验证)、`/strategy-loop`(LLM 自挖掘自迭代,带停机条件与 shot 预算)、`/paper-to-factor <论文>`(论文→可测因子 spec)、`/strategy-status`(仪表盘)。Claude 兼任 R(生成假设)与 D(实现代码),**valkit 是它绕不过的裁判**——冻结先于结果、泄漏审计缺失够不到 GO、判决算术不由 LLM 说了算。

详见 `docs/valkit-验证基建总览.md`(全貌)与 `产品说明文档.md`(黑客松提交说明)。

## 第三方与致谢

- 设计灵感部分来自 Microsoft [RD-Agent](https://github.com/microsoft/RD-Agent)(MIT):借其"R+D 分工/两段式因子抽取/修复循环"思想,**弃其回测数字驱动的反馈环**(拆解与排毒记录见 `docs/RD-Agent拆解-可搬资产.md`)。未复制其代码。
- 数据来源:Polymarket Gamma/CLOB 公开 API、Binance 公开 API、Stooq/Nasdaq 公开日线、SEC EDGAR。仅用于研究演示。

**免责声明:本项目是验证方法论工具,不构成投资建议;所有示例判决均为 NO-GO 正是其诚实性的体现。**
