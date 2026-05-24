"""风险审核 Agent：对策略组合做最后一道把关。可以否决 / 警告 / 通过。

使用 GPT（保守 + 合规感强的模型最适合做风险官）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from alphaforge.data import MarketSnapshot
from alphaforge.llm import get_client
from config import settings

from .strategy import StrategyPlan
from .regime import RegimeReading


@dataclass
class RiskReading:
    verdict: str            # "approve" / "warn" / "veto"
    risk_score: int         # 1-10，10 最危险
    notes: list[str]        # 警示点
    raw: str


class RiskAgent:
    name = "risk"
    display_name = "🛡️ 风险审核 Agent"
    model = settings.llm.model_risk

    SYSTEM_PROMPT = (
        "You are a crypto risk officer. Given the market snapshot, regime, and the "
        "proposed strategy allocation, return a verdict (approve/warn/veto), risk_score 1-10, "
        "and 1-3 short notes (in Chinese). Veto only when allocation is clearly wrong "
        "for the regime (e.g., heavy momentum long during panic). "
        'Output ONLY JSON: {"verdict": "...", "risk_score": N, "notes": ["...", ...]}'
    )

    def audit(self, snap: MarketSnapshot, regime: RegimeReading, plan: StrategyPlan) -> RiskReading:
        payload = {
            "market": {
                "symbol": snap.symbol,
                "last_price": round(snap.last_price, 4),
                "pct_change_24h": round(snap.pct_change_24h, 2),
                "indicators": {k: round(v, 4) for k, v in snap.indicators.items()},
            },
            "regime": {"dominant": regime.dominant, "probs": regime.probs},
            "plan": {"weights": plan.weights, "rationale": plan.rationale},
        }
        client = get_client()
        raw = client.chat(
            agent=self.name,
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return self._parse(raw)

    def _parse(self, raw: str) -> RiskReading:
        try:
            data = json.loads(raw)
            verdict = str(data.get("verdict", "warn")).lower()
            if verdict not in ("approve", "warn", "veto"):
                verdict = "warn"
            return RiskReading(
                verdict=verdict,
                risk_score=int(data.get("risk_score", 5)),
                notes=[str(n) for n in data.get("notes", [])][:3],
                raw=raw,
            )
        except Exception:
            mock_mode = (not raw.strip()) or raw.startswith("[MOCK")
            return RiskReading(
                verdict="warn",
                risk_score=5,
                notes=(["📍 MOCK 模式 —— 真模式下由 GPT-4o-mini 输出 verdict/risk_score/notes"]
                        if mock_mode else ["（风险 Agent 解析失败，默认警告）"]),
                raw=raw,
            )
