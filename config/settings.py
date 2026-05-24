"""集中读取环境变量。所有模块通过 `from config import settings` 拿配置。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# 在 import 时一次性加载 .env（不存在也无所谓，CI/部署环境下变量已经在 env 里）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str
    model_regime: str
    model_strategy: str
    model_risk: str

    @property
    def configured(self) -> bool:
        """判断 API Key 是否真配置。
        强壮版：只要长度 ≥16 且不是占位符就算 configured。
        GMI 的 JWT key 约 233 字符；OpenAI 兼容 sk- 开头 key 也 >= 40。
        """
        if not self.api_key or len(self.api_key) < 16:
            return False
        placeholders = ("sk-your-", "your-", "demo", "placeholder", "xxxx")
        lower = self.api_key.lower()
        return not any(lower.startswith(p) for p in placeholders)


@dataclass(frozen=True)
class MarketSettings:
    exchange: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings
    market: MarketSettings
    root: Path


def _load() -> Settings:
    return Settings(
        llm=LLMSettings(
            api_key=os.getenv("GMI_API_KEY", ""),
            base_url=os.getenv("GMI_BASE_URL", "https://api.gmi-serving.com/v1"),
            model_regime=os.getenv("MODEL_REGIME", "deepseek-ai/DeepSeek-R1-0528"),
            model_strategy=os.getenv("MODEL_STRATEGY", "anthropic/claude-opus-4.6"),
            model_risk=os.getenv("MODEL_RISK", "openai/gpt-4o-mini"),
        ),
        market=MarketSettings(
            exchange=os.getenv("EXCHANGE", "binance"),
            symbols=tuple(
                s.strip() for s in os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT").split(",")
                if s.strip()
            ),
        ),
        root=Path(__file__).resolve().parent.parent,
    )


settings = _load()
