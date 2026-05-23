"""5 个内置策略，每个产出一个 -1.0 ~ 1.0 的信号强度（负 = 卖 / 0 = 观望 / 正 = 买）。"""
from .base import Strategy, StrategySignal
from .momentum import MomentumStrategy
from .mean_reversion import MeanReversionStrategy
from .grid import GridStrategy
from .breakout import BreakoutStrategy
from .dca import DCAStrategy

ALL_STRATEGIES: dict[str, Strategy] = {
    "momentum": MomentumStrategy(),
    "mean_reversion": MeanReversionStrategy(),
    "grid": GridStrategy(),
    "breakout": BreakoutStrategy(),
    "dca": DCAStrategy(),
}

__all__ = ["Strategy", "StrategySignal", "ALL_STRATEGIES"]
