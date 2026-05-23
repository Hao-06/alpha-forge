"""一站式调用：行情 → 4 Agent → 决策 → OKX dry-run 订单。供 UI / CLI 复用。"""
from __future__ import annotations

from dataclasses import dataclass

from alphaforge.agents import (
    Decision, DecisionOfficer, FundingArbAgent, FundingReading,
    RegimeAgent, RegimeReading, RiskAgent, RiskReading,
    StrategyAgent, StrategyPlan,
)
from alphaforge.data import MarketDataProvider, MarketSnapshot
from alphaforge.execution import OKXClient, OrderPreview


@dataclass
class PipelineResult:
    snapshot: MarketSnapshot
    regime: RegimeReading
    plan: StrategyPlan
    risk: RiskReading
    decision: Decision
    funding: FundingReading | None = None      # 资金费率 Agent 输出（可选）
    main_order: OrderPreview | None = None     # 基于决策的 dry-run 订单
    funding_orders: list[OrderPreview] | None = None  # 基于 funding 套利推荐的订单


class TradingPipeline:
    """主 pipeline：4 Agent + OKX dry-run。"""

    def __init__(self, exchange: str = "binance") -> None:
        self.data = MarketDataProvider(exchange_id=exchange)
        self.regime_agent = RegimeAgent()
        self.strategy_agent = StrategyAgent()
        self.risk_agent = RiskAgent()
        self.funding_agent = FundingArbAgent()
        self.officer = DecisionOfficer()
        # OKX 客户端默认 dry-run；live=True 也只有在 OKX_LIVE=true 环境变量下才会真下单
        self.okx = OKXClient(live=False)

    # ------------------------------------------------------------------ #
    # 主决策（行情驱动的策略）
    # ------------------------------------------------------------------ #
    def run(self, symbol: str, with_funding: bool = True) -> PipelineResult:
        snap = self.data.fetch(symbol)
        regime = self.regime_agent.analyze(snap)
        plan = self.strategy_agent.plan(snap, regime)
        risk = self.risk_agent.audit(snap, regime, plan)
        decision = self.officer.decide(snap, regime, plan, risk)

        funding = None
        funding_orders: list[OrderPreview] | None = None
        if with_funding:
            funding = self.funding_agent.analyze()
            # 为 funding 套利推荐生成 dry-run 订单
            funding_orders = []
            for pick in funding.top_picks:
                preview = self.okx.open_position(
                    inst_id=pick.inst_id,
                    pos_side=pick.direction,
                    size_contracts="1",       # 最小张数演示，路演专用
                    current_price=None,        # funding 套利不带 TP/SL，靠费率结算
                ).preview
                funding_orders.append(preview)

        # 主订单：把决策的 action 翻成 OKX 订单（如果是 buy/sell）
        main_order: OrderPreview | None = None
        if decision.action in ("buy", "sell"):
            # symbol 形如 BTC/USDT → OKX 永续 BTC-USDT-SWAP
            okx_inst = symbol.replace("/", "-") + "-SWAP"
            pos_side = "long" if decision.action == "buy" else "short"
            main_order = self.okx.open_position(
                inst_id=okx_inst,
                pos_side=pos_side,
                size_contracts="1",
                current_price=snap.last_price,
            ).preview

        return PipelineResult(
            snapshot=snap, regime=regime, plan=plan, risk=risk,
            decision=decision, funding=funding,
            main_order=main_order, funding_orders=funding_orders,
        )

    # 流式版：UI 用，可以在每一步刷新画面
    def run_streaming(self, symbol: str, with_funding: bool = True):
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

        if with_funding:
            funding = self.funding_agent.analyze()
            yield "funding", funding

            funding_orders = []
            for pick in funding.top_picks:
                preview = self.okx.open_position(
                    inst_id=pick.inst_id, pos_side=pick.direction,
                    size_contracts="1", current_price=None,
                ).preview
                funding_orders.append(preview)
            yield "funding_orders", funding_orders

        if decision.action in ("buy", "sell"):
            okx_inst = symbol.replace("/", "-") + "-SWAP"
            pos_side = "long" if decision.action == "buy" else "short"
            main_order = self.okx.open_position(
                inst_id=okx_inst, pos_side=pos_side,
                size_contracts="1", current_price=snap.last_price,
            ).preview
            yield "main_order", main_order
