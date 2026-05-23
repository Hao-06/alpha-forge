"""项目冒烟测试：不调 LLM，验证所有模块能 import + 关键类能实例化 + mock 数据能跑通。

用法：
    python scripts/smoke_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# 让脚本从子目录运行也能找到包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    print("=" * 60)
    print("AlphaForge · Smoke Test")
    print("=" * 60)
    ok = True

    # 1. 配置
    try:
        from config import settings
        print(f"✓ config 加载成功")
        print(f"  GMI Key configured: {settings.llm.configured}")
        print(f"  Symbols: {settings.market.symbols}")
    except Exception as e:
        print(f"✗ config 失败：{e}"); ok = False

    # 2. 数据层
    try:
        from alphaforge.data import MarketDataProvider
        provider = MarketDataProvider()
        snap = provider.fetch("BTC/USDT")
        print(f"✓ 行情拉取成功（{'mock 数据' if snap.ohlcv['volume'].iloc[0] < 2000 else '真实数据'}）")
        print(f"  BTC/USDT last: ${snap.last_price:,.2f}, 24h: {snap.pct_change_24h:+.2f}%")
        print(f"  Indicators: ma7={snap.indicators.get('ma7', 0):.2f}, "
              f"rsi14={snap.indicators.get('rsi14', 0):.1f}")
    except Exception as e:
        print(f"✗ 行情层失败：{e}"); ok = False; snap = None

    # 3. 策略库
    try:
        from alphaforge.strategies import ALL_STRATEGIES
        if snap is not None:
            for name, strat in ALL_STRATEGIES.items():
                sig = strat.evaluate(snap)
                print(f"  · {strat.display_name}: score={sig.score:+.2f} — {sig.rationale}")
            print(f"✓ 5 个策略全部跑通")
    except Exception as e:
        print(f"✗ 策略库失败：{e}"); ok = False

    # 4. Agent（mock 模式，不真调 LLM）
    try:
        from alphaforge.pipeline import TradingPipeline
        pipe = TradingPipeline()
        result = pipe.run("BTC/USDT")
        print(f"✓ Pipeline 跑通")
        print(f"  Regime: {result.regime.dominant}")
        print(f"  Top weights: {sorted(result.plan.weights.items(), key=lambda kv:-kv[1])[:2]}")
        print(f"  Decision: {result.decision.action.upper()} · conf={result.decision.confidence:.0%}")
    except Exception as e:
        print(f"✗ Pipeline 失败：{e}"); ok = False

    # 5. GMI 调用日志
    try:
        from alphaforge.llm import get_client
        logs = get_client().get_logs()
        print(f"✓ GMI client 调用日志：共 {len(logs)} 条")
        if logs:
            print(f"  最新一条：agent={logs[-1].agent}, model={logs[-1].model}, status={logs[-1].status}")
    except Exception as e:
        print(f"✗ GMI client 失败：{e}"); ok = False

    print("=" * 60)
    print("✅ 全部通过" if ok else "❌ 有失败项，看上面")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
