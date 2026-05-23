"""行情判断 Agent：基于实时指标输出 regime 概率分布 + 简短推理。

使用 GMI 上的 DeepSeek-R1（强推理）。承认不确定性 —— 输出概率而非单一标签。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from alphaforge.data import MarketSnapshot
from alphaforge.llm import get_client
from config import settings

REGIMES = ["trending_up", "trending_down", "ranging", "high_volatility", "panic"]


@dataclass
class RegimeReading:
    probs: dict[str, float]        # 5 种 regime 的概率，和为 1
    dominant: str                   # 概率最大者
    rationale: str                  # 一段话推理（保留 R1 思维链）
    raw: str                        # 原始 LLM 返回，用于审计


class RegimeAgent:
    name = "regime"
    display_name = "📊 行情判断 Agent"
    model = settings.llm.model_regime

    SYSTEM_PROMPT = (
        "You are a crypto market regime analyst. Given current price, 24h change, "
        "moving averages and RSI, output a probability distribution over 5 regimes: "
        "trending_up, trending_down, ranging, high_volatility, panic. "
        "Probabilities must sum to 1. Respond ONLY with valid JSON: "
        '{"probs": {"trending_up": 0.x, ...}, "rationale": "<one sentence in Chinese>"}'
    )

    def analyze(self, snap: MarketSnapshot) -> RegimeReading:
        user_payload = {
            "symbol": snap.symbol,
            "last_price": round(snap.last_price, 4),
            "pct_change_24h": round(snap.pct_change_24h, 2),
            "indicators": {k: round(v, 4) for k, v in snap.indicators.items()},
        }
        client = get_client()
        raw = client.chat(
            agent=self.name,
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return self._parse(raw)

    # ------------------------------------------------------------------ #
    def _parse(self, raw: str) -> RegimeReading:
        try:
            data: dict[str, Any] = json.loads(raw)
            probs_raw = data.get("probs", {})
            probs = {r: float(probs_raw.get(r, 0.0)) for r in REGIMES}
            s = sum(probs.values()) or 1.0
            probs = {k: v / s for k, v in probs.items()}
            dominant = max(probs, key=probs.get)  # type: ignore[arg-type]
            return RegimeReading(
                probs=probs,
                dominant=dominant,
                rationale=str(data.get("rationale", "")),
                raw=raw,
            )
        except Exception:
            # 退化：均匀分布 + 标记 raw 让 UI 能看到
            uniform = {r: 1 / len(REGIMES) for r in REGIMES}
            note = ("📍 MOCK 模式（GMI_API_KEY 未配置）—— 真模式下此处为 R1 思维链推理"
                   if not raw.strip() or raw.startswith("[MOCK")
                   else "（解析失败，回退到均匀分布）")
            return RegimeReading(
                probs=uniform,
                dominant="ranging",
                rationale=note,
                raw=raw,
            )
