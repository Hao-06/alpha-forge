"""一站式调用：行情 → 三 Agent → 决策。供 UI / CLI 复用。"""
from __future__ import annotations

from dataclasses import dataclass

from alphaforge.agents import (
    Decision, DecisionOfficer, RegimeAgent, RegimeReading,
    RiskAgent, RiskReading, StrategyAgent, StrategyPlan,
)
from alphaforge.data import MarketDataProvider, MarketSnapshot


@dataclass
class PipelineResult:
    snapshot: MarketSnapshot
    regime: RegimeReading
    plan: StrategyPlan
    risk: RiskReading
    decision: Decision


class TradingPipeline:
    """对外暴露的一站式 API。所有阶段都可 yield 中间结果（供 UI 流式展示）。"""

    def __init__(self, exchange: str = "binance") -> None:
        self.data = MarketDataProvider(exchange_id=exchange)
        self.regime_agent = RegimeAgent()
        self.strategy_agent = StrategyAgent()
        self.risk_agent = RiskAgent()
        self.officer = DecisionOfficer()

    def run(self, symbol: str) -> PipelineResult:
        snap = self.data.fetch(symbol)
        regime = self.regime_agent.analyze(snap)
        plan = self.strategy_agent.plan(snap, regime)
        risk = self.risk_agent.audit(snap, regime, plan)
        decision = self.officer.decide(snap, regime, plan, risk)
        return PipelineResult(snap, regime, plan, risk, decision)

    # 流式版：UI 用，可以在每一步刷新画面
    def run_streaming(self, symbol: str):
        snap = self.data.fetch(symbol)
        yield "snapshot", snap

        regime = self.regime_agent.analyze(snap)
        yield "regime", regime

        plan = self.strategy_agent.plan(snap, regime)
        yield "plan", plan

        risk = self.risk_agent.audit(snap, regime, plan)
        yield "risk", risk

        decision = self.officer.decide(snap, regime, plan, risk)
        yield "decision", decision
