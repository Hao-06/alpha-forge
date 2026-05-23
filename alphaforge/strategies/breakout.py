"""突破策略：新高 / 新低突破，伴随成交量验证。"""
from __future__ import annotations

from alphaforge.data import MarketSnapshot

from .base import Strategy, StrategySignal


class BreakoutStrategy(Strategy):
    name = "breakout"
    display_name = "🚀 突破策略"
    description = "突破 N 期高点 / 低点 + 成交量放大 = 主升 / 主跌起步信号。"

    def evaluate(self, snap: MarketSnapshot) -> StrategySignal:
        df = snap.ohlcv
        if df.empty or len(df) < 30:
            return StrategySignal(self.name, 0.0, "数据不足", ["trending_up", "trending_down"])
        close = df["close"].astype(float)
        vol = df["volume"].astype(float)
        n = 20
        prior_high = close.iloc[-n-1:-1].max()
        prior_low = close.iloc[-n-1:-1].min()
        vol_ratio = vol.iloc[-1] / max(vol.iloc[-n-1:-1].mean(), 1e-9)

        last = snap.last_price
        if last > prior_high and vol_ratio > 1.2:
            return StrategySignal(
                self.name,
                min(1.0, 0.5 + 0.25 * (vol_ratio - 1)),
                f"突破 {n} 期高 {prior_high:.2f}，量比 {vol_ratio:.2f}",
                ["trending_up", "high_volatility"],
            )
        if last < prior_low and vol_ratio > 1.2:
            return StrategySignal(
                self.name,
                max(-1.0, -0.5 - 0.25 * (vol_ratio - 1)),
                f"破位 {n} 期低 {prior_low:.2f}，量比 {vol_ratio:.2f}",
                ["trending_down", "high_volatility"],
            )
        return StrategySignal(self.name, 0.0, "无有效突破", ["trending_up", "trending_down"])
