"""策略选择 Agent：基于 regime + 5 策略各自评分，输出权重分配 + 微调建议。

使用 Claude（综合推理 + 跟随规则能力强）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from alphaforge.data import MarketSnapshot
from alphaforge.llm import get_client
from alphaforge.strategies import ALL_STRATEGIES, StrategySignal
from config import settings

from .regime import RegimeReading


@dataclass
class StrategyPlan:
    weights: dict[str, float]              # 5 策略权重，和为 1
    tweaks: dict[str, str]                 # 对每个非零权重策略的微调建议（自由文本）
    rationale: str                          # 一句话总结
    signals: list[StrategySignal]           # 策略自评（供 UI 展示）
    raw: str


class StrategyAgent:
    name = "strategy"
    display_name = "🎯 策略选择 Agent"
    model = settings.llm.model_strategy

    SYSTEM_PROMPT = (
        "You are a crypto strategy allocator. Given current regime probabilities and "
        "the 5 in-house strategies' self-evaluation signals, decide weight allocation "
        "(sum=1, single strategy <= 0.5) and suggest one-line tweak per non-zero strategy. "
        "Output ONLY JSON: "
        '{"weights": {"momentum": 0.x, ...}, "tweaks": {"momentum": "<chinese tip>", ...}, '
        '"rationale": "<one sentence in Chinese>"}'
    )

    def plan(self, snap: MarketSnapshot, regime: RegimeReading) -> StrategyPlan:
        signals = [s.evaluate(snap) for s in ALL_STRATEGIES.values()]
        payload = {
            "regime_probs": regime.probs,
            "signals": [
                {"name": s.name, "score": round(s.score, 3),
                 "rationale": s.rationale, "suits_regime": s.suits_regime}
                for s in signals
            ],
        }
        client = get_client()
        raw = client.chat(
            agent=self.name,
            model=self.model,
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        return self._parse(raw, signals)

    # ------------------------------------------------------------------ #
    def _parse(self, raw: str, signals: list[StrategySignal]) -> StrategyPlan:
        names = list(ALL_STRATEGIES.keys())
        try:
            data = json.loads(raw)
            w_raw = data.get("weights", {})
            weights = {n: float(w_raw.get(n, 0.0)) for n in names}
            # 单策略 ≤ 0.5 的硬约束 + 归一化
            weights = {k: min(v, 0.5) for k, v in weights.items()}
            s = sum(weights.values()) or 1.0
            weights = {k: v / s for k, v in weights.items()}
            tweaks_raw = data.get("tweaks", {})
            tweaks = {n: str(tweaks_raw.get(n, "")) for n in names if weights[n] > 0}
            return StrategyPlan(
                weights=weights,
                tweaks=tweaks,
                rationale=str(data.get("rationale", "")),
                signals=signals,
                raw=raw,
            )
        except Exception:
            # 退化：基于信号绝对值做权重
            abs_scores = {s.name: abs(s.score) for s in signals}
            total = sum(abs_scores.values()) or 1.0
            weights = {k: v / total for k, v in abs_scores.items()}
            mock_mode = (not raw.strip()) or raw.startswith("[MOCK")
            return StrategyPlan(
                weights=weights,
                tweaks={n: ("📍 MOCK · 真模式下此处为 Claude 微调建议"
                            if mock_mode else "（自动微调建议生成失败）")
                        for n in weights if weights[n] > 0},
                rationale=("📍 MOCK 模式 —— 当前权重基于策略自评信号绝对值；"
                            "真模式下由 Claude 4.5 综合 regime + signals 给出"
                            if mock_mode else "（LLM 解析失败，回退到信号绝对值权重）"),
                signals=signals,
                raw=raw,
            )
