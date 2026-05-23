"""加密行情数据提供方。

通过 CCXT 拉公共行情（无需 API key），计算简易技术指标供 Agent 使用。
为了路演稳定，所有网络调用都带超时 + 退化到 mock 数据。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

try:
    import ccxt  # type: ignore
except ImportError:  # 部署环境若缺包，至少不会让 UI 崩
    ccxt = None  # type: ignore


@dataclass
class MarketSnapshot:
    symbol: str
    last_price: float
    pct_change_24h: float
    volume_24h: float
    ohlcv: pd.DataFrame      # 最近 N 根 K 线，columns: ts, open, high, low, close, volume
    indicators: dict[str, float]

    def to_brief(self) -> dict[str, Any]:
        """提供给 LLM 的精简字典（避免 token 浪费）。"""
        return {
            "symbol": self.symbol,
            "last_price": round(self.last_price, 4),
            "pct_change_24h": round(self.pct_change_24h, 2),
            "indicators": {k: round(v, 4) for k, v in self.indicators.items()},
        }


class MarketDataProvider:
    def __init__(self, exchange_id: str = "binance") -> None:
        self.exchange_id = exchange_id
        self._exchange: Any | None = None
        if ccxt is not None and hasattr(ccxt, exchange_id):
            ex_cls = getattr(ccxt, exchange_id)
            # enableRateLimit=True 让 CCXT 自己处理限频
            self._exchange = ex_cls({"enableRateLimit": True, "timeout": 8000})

    # ------------------------------------------------------------------ #
    # 公共 API
    # ------------------------------------------------------------------ #
    def fetch(self, symbol: str, timeframe: str = "1h", limit: int = 100) -> MarketSnapshot:
        """拉一个币种的最近 K 线 + 计算指标。失败时回落到 mock。"""
        try:
            if self._exchange is None:
                raise RuntimeError("ccxt 不可用")
            ohlcv_raw = self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            ticker = self._exchange.fetch_ticker(symbol)
            ohlcv = pd.DataFrame(ohlcv_raw, columns=["ts", "open", "high", "low", "close", "volume"])
            return MarketSnapshot(
                symbol=symbol,
                last_price=float(ticker["last"]),
                pct_change_24h=float(ticker.get("percentage") or 0.0),
                volume_24h=float(ticker.get("quoteVolume") or 0.0),
                ohlcv=ohlcv,
                indicators=self._compute_indicators(ohlcv),
            )
        except Exception:
            return self._mock_snapshot(symbol, limit)

    # ------------------------------------------------------------------ #
    # 指标
    # ------------------------------------------------------------------ #
    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> dict[str, float]:
        if df.empty:
            return {}
        close = df["close"].astype(float)
        # 简易实现：避免重依赖 ta 库导致部署慢
        ma_fast = close.rolling(7).mean().iloc[-1]
        ma_slow = close.rolling(25).mean().iloc[-1]
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        vol = close.pct_change().rolling(20).std().iloc[-1] * np.sqrt(24)
        return {
            "ma7": float(ma_fast) if pd.notna(ma_fast) else 0.0,
            "ma25": float(ma_slow) if pd.notna(ma_slow) else 0.0,
            "rsi14": float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else 50.0,
            "vol_24h": float(vol) if pd.notna(vol) else 0.0,
            "last": float(close.iloc[-1]),
        }

    # ------------------------------------------------------------------ #
    # 降级 mock —— 让 demo 在断网时也能跑
    # ------------------------------------------------------------------ #
    @staticmethod
    def _mock_snapshot(symbol: str, limit: int) -> MarketSnapshot:
        rng = np.random.default_rng(seed=hash(symbol) & 0xFFFF)
        base = {"BTC/USDT": 68000, "ETH/USDT": 3400, "SOL/USDT": 165}.get(symbol, 100)
        prices = base + np.cumsum(rng.normal(0, base * 0.005, limit))
        df = pd.DataFrame({
            "ts": pd.date_range(end=pd.Timestamp.utcnow(), periods=limit, freq="h").astype("int64") // 10**6,
            "open": prices,
            "high": prices * 1.003,
            "low": prices * 0.997,
            "close": prices,
            "volume": rng.uniform(100, 1000, limit),
        })
        return MarketSnapshot(
            symbol=symbol,
            last_price=float(prices[-1]),
            pct_change_24h=float((prices[-1] / prices[-24] - 1) * 100) if limit >= 24 else 0.0,
            volume_24h=float(df["volume"].sum()),
            ohlcv=df,
            indicators=MarketDataProvider._compute_indicators(df),
        )
