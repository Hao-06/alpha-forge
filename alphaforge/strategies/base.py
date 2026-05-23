"""策略基类与信号数据结构。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from alphaforge.data import MarketSnapshot


@dataclass
class StrategySignal:
    name: str               # 策略 id
    score: float            # -1.0 ~ 1.0
    rationale: str          # 一句话理由，供 Agent / UI 展示
    suits_regime: list[str] # 这策略适合什么 regime，供 Agent 参考


class Strategy(ABC):
    name: str
    display_name: str
    description: str

    @abstractmethod
    def evaluate(self, snap: MarketSnapshot) -> StrategySignal:
        """计算当前 snapshot 下的信号。"""
