"""AlphaForge 命令行入口。

用法：
    python main.py check                       # 自检（不调 LLM）
    python main.py decide --symbol BTC/USDT    # 调用完整 pipeline 输出 JSON 信号
"""
from __future__ import annotations

import argparse
import json
import sys

from config import settings


def cmd_check(_args: argparse.Namespace) -> int:
    print("AlphaForge · 系统自检")
    print("-" * 50)
    print(f"项目根目录   : {settings.root}")
    print(f"GMI Base URL : {settings.llm.base_url}")
    print(f"Regime 模型  : {settings.llm.model_regime}")
    print(f"Strategy 模型: {settings.llm.model_strategy}")
    print(f"Risk 模型    : {settings.llm.model_risk}")
    print(f"GMI Key      : {'✓ 已配置' if settings.llm.configured else '✗ 未配置 (.env 缺 GMI_API_KEY)'}")
    print(f"行情交易所   : {settings.market.exchange}")
    print(f"币种         : {', '.join(settings.market.symbols)}")

    missing: list[str] = []
    for mod in ("openai", "ccxt", "pandas", "numpy", "streamlit"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        print(f"依赖缺失     : ✗ {', '.join(missing)} —— pip install -r requirements.txt")
        return 1
    print("依赖检查     : ✓ 全部就绪")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    # 延迟导入：check 不需要这些
    from alphaforge.pipeline import TradingPipeline

    pipe = TradingPipeline(exchange=settings.market.exchange)
    result = pipe.run(args.symbol)

    print(f"\n# {args.symbol} 决策 JSON")
    print(json.dumps(result.decision.to_json(), ensure_ascii=False, indent=2))

    if args.verbose:
        print(f"\n# Regime 推理：{result.regime.rationale}")
        print(f"# 策略权重：{result.plan.weights}")
        print(f"# 策略微调：{result.plan.tweaks}")
        print(f"# 风险评注：{result.risk.notes}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="alphaforge", description="AlphaForge 多 Agent 加密策略官")
    sub = p.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("check", help="环境与依赖自检")
    pc.set_defaults(func=cmd_check)

    pd = sub.add_parser("decide", help="对单个币种跑一次完整决策")
    pd.add_argument("--symbol", default="BTC/USDT", help="如 BTC/USDT")
    pd.add_argument("--verbose", action="store_true")
    pd.set_defaults(func=cmd_decide)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    sys.exit(args.func(args))
