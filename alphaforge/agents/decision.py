"""决策官：把三 Agent 的输出综合成一个可执行的交易信号。"""
from __future__ import annotations

from dataclasses import dataclass

from alphaforge.data import MarketSnapshot

from .regime import RegimeReading
from .strategy import StrategyPlan
from .risk import RiskReading


@dataclass
class Decision:
    symbol: str
    action: str                # "buy" / "sell" / "hold"
    confidence: float           # 0-1
    composite_score: float      # -1.0 ~ 1.0
    rationale: str              # 给用户看的中文一段话
    regime: RegimeReading
    plan: StrategyPlan
    risk: RiskReading

    def to_json(self) -> dict:
        return {
            "symbol": self.symbol,
            "action": self.action,
            "confidence": round(self.confidence, 3),
            "composite_score": round(self.composite_score, 3),
            "regime": self.regime.dominant,
            "weights": {k: round(v, 3) for k, v in self.plan.weights.items()},
            "risk_verdict": self.risk.verdict,
            "risk_score": self.risk.risk_score,
            "rationale": self.rationale,
        }


class DecisionOfficer:
    """聚合 regime + plan + risk → 单一可执行信号。这一步本身不调 LLM（节省成本）。"""

    THRESHOLD_BUY = 0.25
    THRESHOLD_SELL = -0.25

    def decide(
        self,
        snap: MarketSnapshot,
        regime: RegimeReading,
        plan: StrategyPlan,
        risk: RiskReading,
    ) -> Decision:
        # composite = Σ weight_i * signal_i.score
        signal_map = {s.name: s.score for s in plan.signals}
        composite = sum(plan.weights.get(n, 0) * signal_map.get(n, 0) for n in plan.weights)

        # 风险否决直接 hold
        if risk.verdict == "veto":
            action, confidence = "hold", 0.3
        elif composite >= self.THRESHOLD_BUY:
            action, confidence = "buy", min(0.95, 0.5 + composite * 0.5)
        elif composite <= self.THRESHOLD_SELL:
            action, confidence = "sell", min(0.95, 0.5 + abs(composite) * 0.5)
        else:
            action, confidence = "hold", 0.5

        # 风险等级削减置信度
        confidence *= max(0.4, 1.0 - risk.risk_score * 0.05)

        top_strats = sorted(plan.weights.items(), key=lambda kv: kv[1], reverse=True)[:2]
        top_str = " + ".join(f"{n}({w:.0%})" for n, w in top_strats if w > 0)
        rationale = (
            f"行情判定为 {regime.dominant}（{regime.probs.get(regime.dominant, 0):.0%}），"
            f"主策略组合 {top_str}；综合信号 {composite:+.2f}，"
            f"风险评级 {risk.risk_score}/10（{risk.verdict}）。"
        )
        return Decision(
            symbol=snap.symbol,
            action=action,
            confidence=confidence,
            composite_score=composite,
            rationale=rationale,
            regime=regime,
            plan=plan,
            risk=risk,
        )
