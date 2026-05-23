"""OKX 资金费率（funding rate）数据源 —— 加密永续合约套利的核心信号。

funding rate（资金费率）是永续合约多空双方互相支付的费用：
- rate > 0  → 多头付费给空头（市场过热看多，可做空套利）
- rate < 0  → 空头付费给多头（市场过度看空，可做多套利）
- |rate| 越大 → 套利机会越显著

本模块拉 OKX 公开端点 /api/v5/public/funding-rate，不需要 API key。
为路演稳定性，所有网络调用带超时 + mock fallback。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

OKX_FUNDING_URL = "https://www.okx.com/api/v5/public/funding-rate?instId=ANY"


@dataclass
class FundingRateSnapshot:
    inst_id: str            # 如 BTC-USDT-SWAP
    rate_pct: float         # 费率百分比（已 × 100，例如 0.05 表示 0.05%）
    abs_rate_pct: float     # 绝对值，用于排序
    funding_time_ms: int    # 下次结算时间戳（毫秒）
    minutes_to_settle: int  # 距下次结算的分钟数

    @property
    def base_asset(self) -> str:
        """从 inst_id 解析基础币种，如 BTC-USDT-SWAP → BTC"""
        return self.inst_id.split("-")[0]

    @property
    def direction_hint(self) -> str:
        """套利方向提示。"""
        if self.rate_pct > 0.05:
            return "做空套利（收资金费）"
        if self.rate_pct < -0.05:
            return "做多套利（收资金费）"
        return "费率温和，套利价值低"


class FundingRateProvider:
    """拉 OKX 永续合约资金费率，过滤即将结算的 USDT 合约。"""

    def __init__(self, timeout: float = 8.0, window_hours: int = 9) -> None:
        self.timeout = timeout
        self.window_hours = window_hours

    def fetch_all(self) -> list[FundingRateSnapshot]:
        """拉全市场费率。失败时返回 mock 数据。"""
        try:
            # httpx 会自动尊重 HTTPS_PROXY / ALL_PROXY 环境变量
            resp = httpx.get(OKX_FUNDING_URL, timeout=self.timeout)
            resp.raise_for_status()
            payload = resp.json()
            data = payload.get("data", [])
        except Exception:
            return self._mock()

        now_ms = int(time.time() * 1000)
        window_ms = self.window_hours * 60 * 60 * 1000
        out: list[FundingRateSnapshot] = []
        for row in data:
            inst_id = row.get("instId", "")
            if "USDT-SWAP" not in inst_id:
                continue
            try:
                rate = float(row.get("fundingRate", 0))
                fts = int(row.get("fundingTime", 0))
            except (TypeError, ValueError):
                continue
            dt_ms = fts - now_ms
            if dt_ms > window_ms:
                continue
            pct = rate * 100
            out.append(FundingRateSnapshot(
                inst_id=inst_id,
                rate_pct=pct,
                abs_rate_pct=abs(pct),
                funding_time_ms=fts,
                minutes_to_settle=max(0, dt_ms // (60 * 1000)),
            ))
        return out

    def fetch_top_opportunities(self, n: int = 10) -> list[FundingRateSnapshot]:
        """按绝对值排序，返回前 N 个最显著的套利机会。"""
        snaps = self.fetch_all()
        snaps.sort(key=lambda s: s.abs_rate_pct, reverse=True)
        return snaps[:n]

    # ------------------------------------------------------------------ #
    # mock：网络挂时也能演示
    # ------------------------------------------------------------------ #
    @staticmethod
    def _mock() -> list[FundingRateSnapshot]:
        now_ms = int(time.time() * 1000)
        # 接下来 4 小时即将结算的样例（数值参考真实分布）
        samples = [
            ("ONDO-USDT-SWAP", 0.187),
            ("DOGE-USDT-SWAP", 0.142),
            ("PEPE-USDT-SWAP", -0.098),
            ("SOL-USDT-SWAP", 0.062),
            ("BTC-USDT-SWAP", 0.011),
            ("ETH-USDT-SWAP", 0.009),
            ("ARB-USDT-SWAP", -0.075),
            ("XRP-USDT-SWAP", 0.043),
            ("WIF-USDT-SWAP", 0.213),
            ("LINK-USDT-SWAP", -0.024),
        ]
        out = []
        for inst, pct in samples:
            fts = now_ms + 2 * 60 * 60 * 1000   # 假设 2 小时后结算
            out.append(FundingRateSnapshot(
                inst_id=inst, rate_pct=pct, abs_rate_pct=abs(pct),
                funding_time_ms=fts, minutes_to_settle=120,
            ))
        return out
