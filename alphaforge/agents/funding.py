"""资金费率套利 Agent —— 扫全市场永续合约资金费率，LLM 挑出最具套利价值的标的。

这是 AlphaForge 区别于"普通策略机器人"的关键差异化能力：传统选币靠技术面，
资金费率套利是中性 / 准 delta-neutral 策略，在加密圈是真正盈利的玩法。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from alphaforge.data import FundingRateProvider, FundingRateSnapshot
from alphaforge.llm import get_client
from config import settings


@dataclass
class FundingPick:
    inst_id: str
    rate_pct: float
    direction: str        # "short" / "long"
    rationale: str        # LLM 给的一句话理由
    confidence: float     # 0-1


@dataclass
class FundingReading:
    snapshots: list[FundingRateSnapshot]   # 全市场拉取的快照
    top_picks: list[FundingPick]            # LLM 精选的套利机会
    summary: str                            # 总体市场资金费率态势的一句话
    raw: str


class FundingArbAgent:
    name = "funding"
    display_name = "💱 资金费率套利 Agent"
    # 复用策略 Agent 同款模型（综合判断 + 跟随规则强）
    model = settings.llm.model_strategy

    SYSTEM_PROMPT = (
        "You are a crypto funding rate arbitrage analyst on OKX perpetual swaps. "
        "Given a list of inst_id + funding_rate (pct) snapshots that will settle within hours, "
        "pick the 3 most attractive arbitrage opportunities. Higher |rate| = better. "
        "Recommend 'short' if rate>0 (collect funding by shorting), 'long' if rate<0. "
        "Also output a one-sentence summary of the overall market funding sentiment (in Chinese). "
        'Output ONLY JSON: {"picks": [{"inst_id": "...", "rate_pct": N, "direction": "short|long", '
        '"rationale": "<chinese>", "confidence": 0.x}, ...], "summary": "<chinese>"}'
    )

    def analyze(self, top_n: int = 10) -> FundingReading:
        provider = FundingRateProvider()
        snaps = provider.fetch_top_opportunities(n=top_n)

        # 喂给 LLM 的精简版
        payload = {
            "candidates": [
                {"inst_id": s.inst_id, "rate_pct": round(s.rate_pct, 4),
                 "minutes_to_settle": s.minutes_to_settle}
                for s in snaps
            ]
        }
        client = get_client()
        raw = client.chat(
            agent=self.name,
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        return self._parse(raw, snaps)

    def _parse(self, raw: str, snaps: list[FundingRateSnapshot]) -> FundingReading:
        try:
            data = json.loads(raw)
            picks = []
            for p in data.get("picks", [])[:3]:
                direction = str(p.get("direction", "")).lower()
                if direction not in ("short", "long"):
                    direction = "short" if float(p.get("rate_pct", 0)) > 0 else "long"
                picks.append(FundingPick(
                    inst_id=str(p.get("inst_id", "")),
                    rate_pct=float(p.get("rate_pct", 0)),
                    direction=direction,
                    rationale=str(p.get("rationale", "")),
                    confidence=float(p.get("confidence", 0.5)),
                ))
            return FundingReading(
                snapshots=snaps,
                top_picks=picks,
                summary=str(data.get("summary", "")),
                raw=raw,
            )
        except Exception:
            # 退化：按 abs_rate_pct 取前 3
            mock_mode = (not raw.strip()) or raw.startswith("[MOCK")
            top3 = snaps[:3]
            return FundingReading(
                snapshots=snaps,
                top_picks=[
                    FundingPick(
                        inst_id=s.inst_id, rate_pct=s.rate_pct,
                        direction="short" if s.rate_pct > 0 else "long",
                        rationale=("📍 MOCK · 真模式下由 Claude 输出套利推荐"
                                    if mock_mode else "（LLM 解析失败，按绝对值取前 3）"),
                        confidence=min(0.95, 0.4 + s.abs_rate_pct * 2),
                    )
                    for s in top3
                ],
                summary=("📍 MOCK 模式（GMI_API_KEY 未配置）—— 真模式下此处为市场态势总结"
                         if mock_mode else "（LLM 解析失败）"),
                raw=raw,
            )
