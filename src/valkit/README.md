# valkit —— 战场无关的策略验证工具箱

把 `docs/证伪裁判协议.md` 从文档变成代码。任何战场(股/币/预测市场/资金流/论文因子)只写一个 **adapter**,核心统一做纪律统计、时间衰减切片、IS-OSS 切分、成本敏感、预注册判定、go/no-go 报告。**目的:下一个策略验证不再手搓骨架。**

## 职责切分

- **adapter(每战场一个,`adapters/`)**:只回答"给我一批 `Event`(实体/t0/分桶/初始反应)+ 一个 `ret(event, 持有期)` = 该策略每单位可交易收益"。策略含义(fade / follow / underreaction)封在适配器,引擎不关心。
- **核心(战场无关)**:
  - `stats.py` — `summarize`(均值 t + **符号检验 z** + 命中)、`bonferroni_z`、`winsorize`、`hard_drop`。
  - `study.py` — `study` / `by_bucket`(只信液体桶) / **`by_period`(时间衰减切片,一等公民)** / `oos_split` / `cost_curve`。
  - `prereg.py` — `Prereg`:看结果前钉死门槛并哈希;`evaluate()` 判定,含 `require_latest_period`(最近一期须单独过关)。
  - `report.py` — `go_no_go` 统一 markdown 报告。

## 用法

```python
from valkit import Event, study, by_period, oos_split, Prereg, go_no_go, bonferroni_z
from valkit.adapters import polymarket as pm

events, ret = pm.load("pm_hist.json", dedup=True, only_up=True, liquid_only=True)
full = study(events, ret, [1,3,7])
per  = by_period(events, ret, [1,3,7])          # 按年切,看 edge 是否被磨平
prereg = Prereg(thesis_id="...", primary_horizon=7, min_net_return=0,
                cost=0.02, min_sign_z=bonferroni_z(12), require_latest_period=True, ...)
verdict = prereg.evaluate(full[7], oos=..., latest=per[max(per)][7])
```

冒烟测试见 `scripts/run_valkit_pm.py`(复现 Polymarket fade-P0),报告落 `runs/valkit_pm_report.md`。

## 两条用血换来的铁律(已编码)

1. **时间衰减切片是一等检验**,不是可选项。Polymarket P0 混年(2023-26)看着 signZ +8,按年切才发现 2026 掉到 +2.1——被套利磨平。任何 edge 先过 `by_period`。
2. **中位数 OOS 会掩盖衰减**。它把强旧段和弱新段混进一个桶,仍显著。故 `require_latest_period`:**最近一期须单独过 Bonferroni**,否则 NO-GO。加固前混年给假 GO,加固后正确 NO-GO。

## 杀戮道 vs 确认道(建造优先级)

见 `openspec/changes/define-agent-validation-protocol/`(design.md 定位):**本套主用途是证伪**。故:

- **`lane.py` KillLane —— 强制流水线(把散零件变成不能跳步/retrofit 的杀戮道)**:必须先 `register(prereg)` 冻结门槛(先于任何数据)→ 跑正控(不过拒判)→ 强制 full/by_bucket/**by_period**/oos → agent thesis 无泄漏审计够不到 GO → 只用冻结门槛判 → 判决+报告+append-only 账本原子留痕。**这实现 design 的 "solid=工具强制不靠自觉"**。自证 `python src/valkit/lane.py`(5 条纪律拦截全过)。
- **杀戮道零件**:`study/by_bucket/by_period/prereg/report`(③A 机械)+ **`leakage.py`(agent thesis 上界审计)** + **`tradeability.py`(a' 可交易性闸:抓尾部/做空依赖/入场弹跳/成本吞噬四种"判断准但吃不到")**。覆盖 ~95% thesis,便宜出 NO-GO。**都自带正控**:`control.py`(机械引擎)、`leakage.py`(泄漏,clean/leaky/noise)、`tradeability.py`(a',clean/tail/thin/short-dep/coverage 五合成)。三个 `python src/valkit/*.py` 均不接 API 自证。
  - a' 顺序 = a 判断 → **a' 可交易性** → b 策略;lane 强制:a' 跳过(None)够不到 GO、untradeable→NO-GO、unverified→带 caveat 放行。通用检查(尾部/成本)总跑,做空依赖/入场弹跳需适配器给 `side`/`ret_delayed` hook,缺则诚实标 unverified,战场不适用可 `na_checks` 标记。
- **`pit.py` cutoff+PIT 硬化 agent 上界(C1/C2)**:`cutoff_audit`(声明 model_cutoff,edge 须在 post-cutoff C1-不可能窗存活,否则 contaminated/insufficient)、`pit_check`(输入时间戳任一晚于 t0=pit-violated 拒采信,非结构化=pit-unknown)。接进 lane agent 路径:cutoff 污染 / PIT 违规 → 够不到 GO。正控 6 合成 `python src/valkit/pit.py`。
  - 端到端:`scripts/run_valkit_pm.py` 把 Polymarket P0 走一遍强制 lane → 复现 signZ 衰减 + 🔴NO-GO,账本 `runs/lane_journal.jsonl` 记 register→control→verdict。
  - `leakage.py`:给 `predict(event, mode)`(mode∈real/strip/corrupt),用无输入/反事实探针**测量**关不掉的泄漏,输出 `leakage`(表观 edge 全是背题)/`clean-ish`(上界确有 edge)/`no-edge`(廉价杀死)。自带正控 `python src/valkit/leakage.py`(clean/leaky/noise 三合成自证,不接 API)。
- **确认道(仅给幸存者)**:
  - **`grade.py`(已建)** —— 致命闸评级器:活过杀戮道的幸存者过全口径成本/容量/可做空性/资金费/尾部爆仓/regime一致性/拥挤/运营 → 定级 kill/long-watch/priority-watch。**坐标轴通用,值由 `Constraints` 战场模型填**(crypto 填资金费、美股填借券费)。分级不是决策,是队列:毙→回杀戮道;重点观察→上模拟操盘(验执行非验edge)。自证 `python src/valkit/grade.py`(3 合成)。
  - **`paper.py`(已建)** —— 前向影子登记簿 + 召回审计。`ShadowRegistry`:register(对结局全盲)→ settle(独立、晚于到期、物理隔离)→ recall_audit。**GO 和 KILL 都登记**,前向影子跑,`recall_audit` 按**死因聚类**标候选误杀:tradeability 类(成本/容量/可做空)误杀=高价值→校准 grade 成本估计;significance 类误杀=多半噪声→勿据此松闸;过 Bonferroni(按死因组数)。精确率查 GO 幸存者前向是否真赚。自证 `python src/valkit/paper.py`(标出 cost 误杀、不被 not-sig 噪声骗)。**它验召回(引擎有没有漏),不需要幸存者就有活干;真实数据靠前向时间累积。**
  - 未建:skill 库、skill 归因(仅当有 thesis 进重点观察+前向足够样本才需)。

## 还没建

- `paper.py` 前向 harness、skill 库、匹配空模型归因 —— 挂起,懒建(见上)。
- 更多 adapter:Kalshi(下一战场,一个文件)、复用主仓 SEC 引擎、crypto、韩国资金流。
- `pip install -e .` 打包(当前脚本用 `sys.path` 注入 `src/` 即可跑)。
