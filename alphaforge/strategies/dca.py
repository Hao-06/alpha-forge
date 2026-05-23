"""定投策略：固定节奏买入。本身是中性偏多策略，但在熊市末端权重应放大。"""
from __future__ import annotations

from alphaforge.data import MarketSnapshot

from .base import Strategy, StrategySignal


class DCAStrategy(Strategy):
    name = "dca"
    display_name = "💧 DCA 定投"
    description = "无视短期波动按节奏买入。长期看跑赢择时；在恐慌 / 熊市末端尤其有效。"

    def evaluate(self, snap: MarketSnapshot) -> StrategySignal:
        pct = snap.pct_change_24h
        # 24h 跌得越多、DCA 信号越强（"恐慌就是机会"）
        score = max(0.1, min(1.0, 0.3 - pct * 0.04))
        return StrategySignal(
            name=self.name,
            score=score,
            rationale=f"24h {pct:+.2f}%，按 DCA 节奏稳进；恐慌越强信号越强",
            suits_regime=["trending_down", "panic", "ranging"],
        )
