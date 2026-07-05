# valkit 策略验证引擎 · 全貌 / 走一遍 / 运营(单入口收口)

> 一页看懂整台引擎:是什么、一个 thesis 怎么从头走到判决再到运营、凭什么可信。散在各文件的东西收在这里。
> 深层:`docs/证伪裁判协议.md`(协议)、`docs/valkit-x-rdagent-结合.md`(生成器+策略loop)、`openspec/changes/define-agent-validation-protocol/`(agent 验证)。

## 一句话

**一台两级、自证、跨战场的策略研究引擎:前端源源不断喂洞察,杀戮道不被骗地杀掉 95%,确认道拦住"真但做不了"的并自查有没有漏。它保证的是——当它哪天说 Yes,那句话是真的。**

- **主用途是证伪,不是确认**:洞察廉价无限(论文/RD-Agent/诊断自反馈),稀缺的是扛得住证伪的真 edge。
- **灵活在 HOW,solid 在 WHETHER**:每战场写一个 adapter,闸门由会拒绝的工具强制——不可跳、不可 retrofit、不可自证。
- **回测=上界**:agent 回测被泄漏灌水永不能证干净 → 只当上界;但上界是绝佳证伪器(灌水都没肉=稳健杀死)。

## 完整流水线

```
生成:论文 / RD-Agent(D层) / 验证诊断自反馈(策略loop)
  │  写 adapter(events + ret + 可选 side/ret_delayed hook)+ 冻结 Prereg
  ▼
【杀戮道:是不是真】KillLane 强制编排
  ① 仪器正控 control_ok 不过 → 拒判      ② 强制检验组 study/by_bucket/by_period/oos
  ③ agent 三闸 leakage/cutoff/pit → 够不到 GO   ④ a' 可交易性 4 检 → 跳过/untradeable 拦
  ⑤ 只用冻结 prereg 判 → 判决+报告+append-only 账本
  │  GO 和 KILL 都往下登记
  ▼
【确认道:能不能真做 + 有没有漏】
  grade   致命闸评级:全口径成本(含资金费)/容量/可做空/爆仓/regime/拥挤/运营 → kill / 长期观察 / 重点观察
  paper   影子登记簿:GO+KILL 都登记(盲写)→ settle(隔离)→ 召回审计(按死因聚类标误杀)
  │
  ├─ kill / 误杀噪声 → 归档 or 回杀戮道
  ├─ 重点观察 → 模拟操盘 1 周/月(验执行/成本真实性,非验 edge)→ 才决定实盘
  └─ 召回审计:tradeability 类误杀 → 校准 grade 成本估计(引擎自我迭代)
```

## 模块地图(都能不接 API 自证)

| 文件 | 作用 | 自证 |
|---|---|---|
| `stats/study/prereg/report` | 机械 ③A:signZ/Bonferroni、by_period 衰减、冻结哈希、报告 | — |
| `control.py` | 机械引擎仪器正控 | `python …/control.py` 5✅ |
| `leakage.py` | agent 泄漏上界审计(C1/C2 探针) | 3✅ |
| `tradeability.py` | a' 可交易性(尾部/做空/弹跳/成本 + base 门肥尾感知) | 6✅ |
| `pit.py` | cutoff(C1)+ PIT(C2)硬化 agent 上界 | 6✅ |
| `lane.py` | **KillLane** 强制编排(全部串成不可跳/retrofit) | 10✅ |
| `grade.py` | **致命闸评级器**(轴通用,值由 `Constraints` 战场模型填) | 3✅ |
| `paper.py` | **影子登记 + 召回审计**(GO+KILL 双登记,按死因标误杀) | ✅ |
| `adapters/polymarket.py` | 适配器示例 | — |

端到端脚本:`scripts/run_valkit_{pm,reversal,momentum,loserbounce,crypto}.py`。

## 从 thesis 到判决到运营 · 走一遍(以 crypto 短信号为例,每一站都真跑过)

1. **生成**:洞察=原始调查里"冷门币下砸继续跌"。我(当 D 层)用缓存 binance 日线复现,写成 events(下砸事件)+ ret(做空收益,size 匹配基准)。
2. **冻结 Prereg**:先钉死门槛(HD5、净成本后>0、signZ 过 Bonferroni、命中>53%、最近期须成立),`lane.register()` 哈希入账本——**先于任何结果**,retrofit 被拒。
3. **杀戮道**:跑正控(过)→ 强制检验组 → a'(base 门肥尾感知放行 → 尾部/成本/做空/弹跳全跑)→ 判决。结果 **🟢GO**(HD5 命中66% signZ+5.29,最近期 2026 强)。→ **证明 lane 不是 NO-GO 机器,会放行真信号。**
4. **grade 评级**:一算**全口径成本**(估计资金费~90bps),+33bps edge 变 -57bps → **致命闸红 → KILL**,外加 5 项黄灯(容量/partial可做空/爆仓/regime集中2026/运营)。→ **"第一个幸存者"是 HD5 资金费幻觉,连重点观察都没进。**
5. **若它进了重点观察**(没进):`paper` 登记 → 模拟 1 周/月验真实资金费/滑点/执行 → 才谈实盘。
6. **召回审计(运营)**:这个 KILL 连同所有 reject 进 `paper` 影子跑;几周后若"死于成本"这类系统性前向赚钱 → 说明成本估计高估 → 回头校准 `grade`。

## 凭什么可信(solid 的支点)

1. **每个闸自带正控**:先证明它能测出真信号/抓出泄漏/识别不可交易,再用它证伪。
2. **freeze-before-see 工具强制**:register 必须先于 run,run 后 register 被拒。
3. **闸门不可跳**:by_period、a'、agent 三闸、grade 致命闸都强制。
4. **append-only 账本**:register→control→agent_audit→a'→verdict 顺序留痕可审。
5. **召回审计防自欺**:误杀认定要过显著性+多重检验;按死因分层;假阳性远贵于假阴性→偏向多杀。

## 跨战场(不是币圈专用)

同一核心已验 **3 个资产类别**:Polymarket(预测市场)/ 美股(反转·动量)/ crypto(下砸做空)。判断层通用,每战场只写一个 adapter。因战场而异的是**数据可得性 + 地形**(有没有 edge),不是验证器。grade 的**轴通用、值由 `Constraints` 战场模型填**。

## 驾驶舱(Claude Code 入口,2026-07-05)

引擎的入口不是某个脚本,是 **Claude Code 本身 + 三个斜杠命令**(`.claude/skills/`):

- **`/strategy <想法>`** —— 手动入口:自然语言策略 → 准入5闸 → 冻结prereg → adapter → 杀戮道 → 评级 → 影子登记 → 报告+回喂。Claude 当 D 层(想法→代码),valkit 当不可绕过的裁判。
- **`/strategy-loop`** —— 自挖掘自迭代一圈:读机制库/shot台账 → 生成 grounded 假设(机制洞察派生,查重,禁旋钮) → 全流水线 → 回喂;自带停机条件(预算/连续无增量/出现候选)。配合 `/loop` 或 `schedule` 可无人值守。
- **`/strategy-status`** —— 仪表盘:shot 台账/判决史/影子待结算/Form4 前向进展/机制库/战场记分板。
- **`/paper-to-factor <论文>`** —— 论文/研报→抽干因子→钉成落在本地数据资产上的可计算 spec→三道预闸(分类/可行/泄漏安全)→CoSTEER 式实现修复→交棒 /strategy。RD-Agent 的 D 层蒸馏版(拆解见 `tradeagent4/RD-Agent拆解-可搬资产.md`,其毒反馈环已弃,repo 从此可删)。

角色分工:**Claude=R(生成)+D(实现),valkit=不可协商的裁判,subagent=独立红队,Monitor/后台=前向采集,schedule=定时运营,memory=跨session机制库。** Microsoft RD-Agent repo 只当零件架(其因子抽取思想已吸收),不是入口——它的 loop 朝回测数字优化,是本协议排毒的对象。

## 已完成 / 属运营非 build

- ✅ **两级引擎全齐**:杀戮道(机械+agent)+ 确认道前端(grade + paper 召回审计),全自证,跨 3 战场。
- ⏳ **属运营**:把 `paper.py` 挂着前向跑,时间累积出召回审计的真实产出 + 任何幸存者的前向确认。
- 🔧 **按需**:`adapters/rdagent.py` 骨架、更肥的战场(找够格幸存者)、skill 库(仅当有 thesis 进重点观察才需)。

## 路上用血换来、已编码进引擎的教训

- **中位数 OOS 掩盖衰减** → `require_latest_period`。
- **只测暴动当刻入场掩盖弹跳** → a' `ret_delayed`(抓出 Polymarket 第二死因)。
- **a' 在不显著信号上误谈弹跳/成本** → base 门;**base 门只用 mean-t 漏掉肥尾符号信号** → 改 mean-t 或 signZ(crypto 跑出来的)。
- **agent 回测一律当上界**;**召回审计按死因分层**(tradeability 可行动 / significance 噪声)。
- **引擎自我纠错**:这几条 bug 有的靠推理、有的靠真数据跑出来——正证明这台引擎连"自己会不会错"都在自查。
