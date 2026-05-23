"""网格策略：低波震荡市最舒服；价格越接近近期中枢、网格越赚。"""
from __future__ import annotations

from alphaforge.data import MarketSnapshot

from .base import Strategy, StrategySignal


class GridStrategy(Strategy):
    name = "grid"
    display_name = "🪜 网格交易"
    description = "在区间震荡中靠高抛低吸赚价差。波动率适中、无趋势时最佳。"

    def evaluate(self, snap: MarketSnapshot) -> StrategySignal:
        df = snap.ohlcv
        if df.empty or len(df) < 20:
            return StrategySignal(self.name, 0.0, "数据不足", ["ranging"])
        close = df["close"].astype(float)
        recent_high, recent_low = close.tail(48).max(), close.tail(48).min()
        center = (recent_high + recent_low) / 2
        # 越靠近中枢、网格信号越强（绝对值越大）；方向：偏下=看多、偏上=看空
        if recent_high == recent_low:
            return StrategySignal(self.name, 0.0, "区间宽度为零", ["ranging"])
        pos = (snap.last_price - center) / (recent_high - recent_low)  # [-0.5, 0.5]
        score = max(-1.0, min(1.0, -2 * pos))  # 上轨看空、下轨看多
        return StrategySignal(
            name=self.name,
            score=score * 0.7,  # 网格信号本身较弱，权重稍减
            rationale=f"距中枢 {pos*100:.1f}%（区间 {recent_low:.2f}~{recent_high:.2f}）",
            suits_regime=["ranging"],
        )
