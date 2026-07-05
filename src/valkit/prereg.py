"""预注册:看结果前钉死 go/no-go 门槛,冻结并哈希。防事后挪门槛(p-hacking)。

用法:先 Prereg(...) 写死,存盘拿到 hash;跑完把 summary 喂 evaluate() 得判定。
hash 进 journal,证明门槛先于结果存在。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from .stats import Summary


@dataclass(frozen=True)
class Prereg:
    thesis_id: str
    hypothesis: str                       # 一句话,含方向
    primary_bucket: str                   # 唯一 go/no-go 依据的桶(须可交易)
    primary_horizon: int                  # 唯一判定持有期
    min_net_return: float                 # 净成本后均值须 ≥ 此(可负,如 fade 深度)
    cost: float                           # 判定用的成本水平
    min_sign_z: float                     # 符号检验 z 须 ≥ 此(建议按检验数取 Bonferroni)
    min_hit: float = 0.55                 # 命中率下限(是倾向不是尾部)
    min_n: int = 100                      # 样本量下限,不够不出判决
    require_oos: bool = True              # 是否要求 OOS 仍成立
    require_latest_period: bool = True    # 是否要求"最近一期(如今年)仍成立"——比中位数OOS更硬,防衰减被掩盖
    battlefield_gates: dict = field(default_factory=dict)  # 真锚/冷门/agent可处理/小资金可交易 四条纸上闸
    notes: str = ""

    def hash(self) -> str:
        blob = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]

    def evaluate(self, s: Optional[Summary], *, oos: Optional[Summary] = None,
                 latest: Optional[Summary] = None) -> dict:
        """对预注册门槛判定。返回 {passed, checks, reason}。

        latest = 最近一期(如今年)的 Summary。中位数 OOS 会把强旧段和弱新段混在一起、
        掩盖衰减(Polymarket P0 的教训),故最近一期须单独过关。
        """
        checks = {}
        if s is None or s.n < self.min_n:
            return {"passed": False, "checks": {"min_n": False},
                    "reason": f"样本不足(n={0 if s is None else s.n}<{self.min_n})", "prereg_hash": self.hash()}
        checks["min_n"] = s.n >= self.min_n
        checks["min_net_return"] = s.net(self.cost) >= self.min_net_return
        checks["min_sign_z"] = abs(s.sign_z) >= self.min_sign_z and (s.sign_z > 0) == (self.min_net_return >= 0 or s.mean >= 0)
        checks["min_hit"] = s.hit >= self.min_hit
        if self.require_oos:
            checks["oos_holds"] = oos is not None and oos.net(self.cost) >= self.min_net_return and abs(oos.sign_z) >= 1.96
        if self.require_latest_period:
            # 最近一期须净成本后仍达标且 signZ 过 Bonferroni——防"混年被老肉撑起"的假 GO
            checks["latest_period_holds"] = (
                latest is not None and latest.net(self.cost) >= self.min_net_return
                and abs(latest.sign_z) >= self.min_sign_z)
        passed = all(checks.values())
        reason = "全部门槛通过" if passed else "未过:" + ",".join(k for k, v in checks.items() if not v)
        return {"passed": passed, "checks": checks, "reason": reason, "prereg_hash": self.hash()}
