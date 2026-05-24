"""集中读取环境变量。所有模块通过 `from config import settings` 拿配置。

⚠️ **lazy property 实现**：所有字段每次访问时实时读 os.environ。
这样在 Streamlit Cloud 上即使 st.secrets 注入到 env 发生在 settings 之后，
代码也能正确读到最新值（避免 frozen dataclass 单例的 snapshot 陷阱）。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# 在 import 时一次性加载 .env（不存在也无所谓，CI/部署环境下变量已经在 env 里）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


class LLMSettings:
    """LLM 相关配置 —— 每个 property 实时读 os.environ。"""

    @property
    def api_key(self) -> str:
        return os.getenv("GMI_API_KEY", "")

    @property
    def base_url(self) -> str:
        return os.getenv("GMI_BASE_URL", "https://api.gmi-serving.com/v1")

    @property
    def model_regime(self) -> str:
        return os.getenv("MODEL_REGIME", "deepseek-ai/DeepSeek-R1-0528")

    @property
    def model_strategy(self) -> str:
        return os.getenv("MODEL_STRATEGY", "anthropic/claude-opus-4.6")

    @property
    def model_risk(self) -> str:
        return os.getenv("MODEL_RISK", "openai/gpt-4o-mini")

    @property
    def configured(self) -> bool:
        """判断 API Key 是否真配置。
        强壮版：只要长度 ≥16 且不是占位符就算 configured。
        GMI 的 JWT key 约 233 字符；OpenAI 兼容 sk- 开头 key 也 ≥ 40。
        """
        k = self.api_key
        if not k or len(k) < 16:
            return False
        placeholders = ("sk-your-", "your-", "demo", "placeholder", "xxxx")
        lower = k.lower()
        return not any(lower.startswith(p) for p in placeholders)


class MarketSettings:
    """实时行情数据源配置。"""

    @property
    def exchange(self) -> str:
        return os.getenv("EXCHANGE", "binance")

    @property
    def symbols(self) -> tuple[str, ...]:
        raw = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT")
        return tuple(s.strip() for s in raw.split(",") if s.strip())


class Settings:
    """根配置 —— lazy 持有子配置实例。"""

    def __init__(self) -> None:
        self.llm = LLMSettings()
        self.market = MarketSettings()
        self.root = Path(__file__).resolve().parent.parent


settings = Settings()
