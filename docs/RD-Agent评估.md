# RD-Agent 评估 —— 好不好用 / 能偷什么 / 为什么不能当裁判

> 日期：2026-07-04　范围：clone 微软 `microsoft/RD-Agent`，读源码 + 代码级评估（未付费跑 loop）。
> 一句话：**极好的 "D"（把想法/论文极快变成可跑的因子-模型代码 + 回测），按你的标准是弱且危险的 "R" 验证器。当基础设施用，别当真理仲裁者。**

---

## 1. 它是什么

微软 MSRA 的 R&D-Agent。工程质量高，非玩具：NeurIPS 2025（RD-Agent(Q)）/ ICML 2026 论文背书，MLE-bench 上 SOTA，LiteLLM 后端，CoSTEER 代码演化，streamlit 轨迹 UI，更新活跃到 2026。

核心范式 **"R"(提想法) + "D"(实现)** 自迭代循环。对你有关的四个场景入口（`rdagent/app/cli.py`）：

| 命令 | 干什么 | 对应你的想法 |
|---|---|---|
| `rdagent general_model <pdf/arxiv-url>` | 读论文 PDF → 抽模型结构 → CoSTEER 实现成 Qlib 模型代码 | **path 1 论文验证** 最直接 |
| `rdagent fin_factor_report <pdf>` | 读研报 → 抽因子 → 生成 hypothesis → 跑完整因子回测迭代 loop | path 1 + path 2 一锅端 |
| `rdagent fin_factor` | 自动提因子想法 → 实现 → 回测 → 反馈迭代（Automatic Quant Factory） | **path 2 自挖掘因子** |
| `rdagent fin_quant` | 因子-模型交替协同优化 | path 2 自迭代 |

---

## 2. 致命缺口：它的"验证"= 回测数字变大

**整条 loop 驱动迭代的"反馈信号"就是 Qlib 回测的 IC / ARR / 夏普。** 招牌"成本<$10、2× ARR、少 70% 因子"是**中国 A股 CSI300 的回测 ARR**。

它**默认不带**你花三个项目换来的每一样纪律：

| 你的纪律 | RD-Agent 有没有 |
|---|---|
| 预注册门槛（先钉死判据再看结果） | ❌ 它就是奔着把回测数字调高去的 |
| **泄漏铁律**（LLM 读过论文 = 历史被污染） | ❌ 从构造上违反：它读的就是含未来的研报/论文 |
| 样本外闸门（IS 发现 / OOS 确认） | ❌ 反馈直接来自同一段回测 |
| 净成本后的 neglect 梯度 / 微观结构去伪 | ❌ 无（不会帮你分辨"信号 vs 买卖价差弹跳"） |
| 小资金可交易性透镜 | ❌ 无（CSI300 是最被盯的大盘） |
| 多重检验校正 | ❌ 无 |

**结论**：直接拿它当裁判 = 把前三个项目的死法（p-hacking / 过拟合 / 流动因子被套干 / 泄漏）自动化得更快、更会自我说服。它回答的是"agent 能不能把这个因子实现出来、让回测好看"，**不是**"这个 edge 扛不扛得住 OOS、成本，小资金能不能真交易"。

---

## 3. 能偷的设计（折进你自己的纪律 harness）

读 `scenarios/qlib/factor_experiment_loader/prompts.yaml` + `components/coder/CoSTEER/` 抄出来的，这些是真有用的脚手架：

1. **两段式因子抽取**（`extract_factors` → `extract_factor_formulation`）：先从论文抽因子名+描述，再逼它产出 **LaTeX 公式 + 每个变量/函数的定义**，且必须落在一份**显式列出的可用数据源清单**上。把论文里含糊的一句话"信号"钉成可计算、可证伪的具体 spec。→ **你做论文验证时的第一道工序应照抄：不让任何 claim 停在自然语言,必须落成"用我手上这些列写得出的公式"。**

2. **实现前的双预闸门**（cheap pre-filter，省钱省算力）：
   - `factor_viability`：这因子能不能按日/按股、用现有数据算出来？算不出的当场毙。
   - `factor_relevance`：要求因子"只由数学运算得出，不靠主观判断/自然语言分析"。→ 注意这条其实是**泄漏安全属性**：纯机械可算的东西才能干净回测。你可以复用它当"这条能不能进 L1 机械层"的闸门。
   - `classify`：这文档到底是不是选股类量化研报？先滤垃圾输入。

3. **结构化 hypothesis 对象**（`generate_hypothesis`）：强制字段 `hypothesis / reason / concise_observation / concise_justification / concise_knowledge`——**先articulate 为什么、再测**。这正是你"预注册"想要的落地形态，可以直接借这个 schema。

4. **CoSTEER**（`components/coder/CoSTEER/`）：带**知识累积**的代码生成——跨迭代记住哪种实现写法成/败，evaluator 给反馈再演化。这是"把论文变成能跑的代码"的 D 层引擎，**这一块可以整段当工具用**，只要你把它的 evaluator 从"回测好不好看"换成"实现对不对 + 是否通过我的 OOS/成本闸门"。

**正确用法**：RD-Agent 当 D（论文→可跑代码，极快）；外面套你自己的 R 裁判（预注册、OOS 切分、成本模型、泄漏铁律、可交易性）。**因子从哪来无所谓，能不能活着出 OOS 才算数——这道闸必须是你的,不是它的。**

---

## 4. 跑它的现实门槛（当前这台机器全部未满足）

| 卡点 | 现状 | 要什么 |
|---|---|---|
| Python | 3.9.6 | 需 ≥3.10，建新解释器（uv/pyenv/conda） |
| **Docker** | 未安装 | 硬依赖——生成代码 + Qlib 回测都在容器里跑 |
| **LLM API key** | 无 | LiteLLM 需按量付费 key，**用不了 Claude Code 订阅**，要花钱（官方称 quant 全流程 <$10/次） |
| Qlib 数据 | 无 | 下 CSI300 日线（几百 MB）；官方仅标 Linux，macOS 非官方 |

Live Demo（rdagent.azurewebsites.net）当前 **403 已停**，别等它。

---

## 5. 判断与下一步

- **不建议**把 RD-Agent 当第四个 edge 战场的裁判——它优化的正是你学会不信的东西。
- **建议**把它当"D 层工具库 + 设计参照"：偷第 3 节那四样脚手架，折进你已有的机械验证 harness（tradeagent 的引擎）。
- 若仍想亲身体感"读论文→自动实现因子"的魔力：提供一个付费 key（DeepSeek 最便宜），装 Docker + py3.10 + Qlib 数据，跑一次 `general_model` 喂一篇 arXiv 因子论文即可——但记住那只是验证"D 好不好用"，不构成任何 edge 结论。

> 关联：tradeagent `docs/L1-latency-investigation.md`（edge↔可交易性墙 / 泄漏铁律）；tradeagent2 未跑完的 fade-news P0（三条线里唯一闪过绿光的活口）。
