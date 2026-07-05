"""valkit —— 战场无关的策略验证工具箱。

把 tradeagent `docs/证伪裁判协议.md` 从文档变成代码:任何战场(股/币/预测市场/资金流)
写一个 adapter(给事件 + 每期收益),核心统一做纪律统计/时间衰减切片/IS-OOS/成本敏感/预注册/报告。

    from valkit.study import Event, study, by_bucket, by_period, oos_split
    from valkit.stats import summarize, bonferroni_z
    from valkit.prereg import Prereg
    from valkit.report import go_no_go
"""
from .study import Event, study, by_bucket, by_period, oos_split, cost_curve
from .stats import summarize, Summary, bonferroni_z, winsorize, hard_drop
from .prereg import Prereg
from .report import go_no_go
from .leakage import audit as leakage_audit, LeakageAudit, auc
from .tradeability import audit as tradeability_audit, TradeabilityAudit
from .pit import cutoff_audit, CutoffAudit, pit_check, PITAudit
from .grade import grade, Constraints, GradeResult
from .paper import ShadowRegistry

__all__ = ["Event", "study", "by_bucket", "by_period", "oos_split", "cost_curve",
           "summarize", "Summary", "bonferroni_z", "winsorize", "hard_drop",
           "Prereg", "go_no_go", "leakage_audit", "LeakageAudit", "auc",
           "tradeability_audit", "TradeabilityAudit",
           "cutoff_audit", "CutoffAudit", "pit_check", "PITAudit",
           "grade", "Constraints", "GradeResult", "ShadowRegistry"]
