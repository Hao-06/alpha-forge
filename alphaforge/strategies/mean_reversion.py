"""均值回归：RSI 极值反转。"""
from __future__ import annotations

from alphaforge.data import MarketSnapshot

from .base import Strategy, StrategySignal


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"
    display_name = "🔁 均值回归"
    description = "RSI 超买 / 超卖反转。震荡市最有效；强趋势中容易被打脸。"

    def evaluate(self, snap: MarketSnapshot) -> StrategySignal:
        rsi = snap.indicators.get("rsi14", 50.0)
        # RSI 30 / 70 为传统阈值。线性映射到 [-1, 1]：30→+1（超卖看多），70→-1（超买看空）
        score = max(-1.0, min(1.0, (50 - rsi) / 20))
        if rsi >= 70:
            note = f"RSI={rsi:.1f} 超买，反转看空"
        elif rsi <= 30:
            note = f"RSI={rsi:.1f} 超卖，反转看多"
        else:
            note = f"RSI={rsi:.1f} 中性，信号弱"
        return StrategySignal(
            name=self.name,
            score=score,
            rationale=note,
            suits_regime=["ranging", "high_volatility"],
        )
