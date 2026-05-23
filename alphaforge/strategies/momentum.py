"""动量策略：MA7 / MA25 金叉死叉 + 当前价相对 MA25 的偏离。"""
from __future__ import annotations

from alphaforge.data import MarketSnapshot

from .base import Strategy, StrategySignal


class MomentumStrategy(Strategy):
    name = "momentum"
    display_name = "📈 动量趋势"
    description = "MA7 / MA25 金叉死叉 + 价格偏离度，在单边趋势行情中表现最好。"

    def evaluate(self, snap: MarketSnapshot) -> StrategySignal:
        ind = snap.indicators
        ma7, ma25, last = ind.get("ma7", 0), ind.get("ma25", 0), ind.get("last", 0)
        if ma25 == 0:
            return StrategySignal(self.name, 0.0, "数据不足", ["trending_up", "trending_down"])

        # 偏离度：last 高于 ma25 多少（百分比）；金叉=ma7>ma25
        deviation = (last - ma25) / ma25
        cross = 1 if ma7 > ma25 else -1
        score = max(-1.0, min(1.0, cross * (0.4 + 5 * abs(deviation))))
        direction = "金叉看多" if cross > 0 else "死叉看空"
        return StrategySignal(
            name=self.name,
            score=score,
            rationale=f"{direction}, 价格偏离 MA25 {deviation*100:.2f}%",
            suits_regime=["trending_up", "trending_down"],
        )
