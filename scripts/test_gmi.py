"""GMI Cloud 连通性自检——对每个配置的模型发一条 'Hello'，看哪些通、哪些挂。

用法：
    .venv/bin/python scripts/test_gmi.py

输出：每个模型的状态、延时、token 用量、回复预览。
如果某个 model id 在 GMI 上不存在，会清楚地报错。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import OpenAI

from config import settings


def ping(client: OpenAI, model: str, role: str) -> dict:
    """对一个模型发一次最小调用，返回结果摘要。"""
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a concise assistant. Reply in <=10 words."},
                {"role": "user", "content": "Say hello in one short sentence."},
            ],
            max_tokens=40,
            temperature=0.1,
        )
        latency = int((time.perf_counter() - t0) * 1000)
        usage = getattr(resp, "usage", None)
        return {
            "role": role,
            "model": model,
            "status": "✅ OK",
            "latency_ms": latency,
            "prompt_tokens": getattr(usage, "prompt_tokens", "?"),
            "completion_tokens": getattr(usage, "completion_tokens", "?"),
            "reply": (resp.choices[0].message.content or "").strip()[:80],
        }
    except Exception as e:
        return {
            "role": role,
            "model": model,
            "status": f"❌ {type(e).__name__}",
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "prompt_tokens": "-",
            "completion_tokens": "-",
            "reply": str(e)[:120],
        }


def main() -> int:
    print("=" * 70)
    print("GMI Cloud 连通性自检")
    print("=" * 70)

    if not settings.llm.configured:
        print("❌ GMI_API_KEY 未配置")
        print("   请：cp .env.example .env  然后填入真 Key")
        return 1

    print(f"Base URL : {settings.llm.base_url}")
    print(f"Key      : {settings.llm.api_key[:8]}…（长度 {len(settings.llm.api_key)}）")
    print("-" * 70)

    client = OpenAI(api_key=settings.llm.api_key, base_url=settings.llm.base_url)

    results = []
    for role, model in [
        ("Regime  ", settings.llm.model_regime),
        ("Strategy", settings.llm.model_strategy),
        ("Risk    ", settings.llm.model_risk),
    ]:
        print(f"➡️  测试 {role} → {model} …", flush=True)
        results.append(ping(client, model, role))

    print("-" * 70)
    print(f"{'Agent':<10} {'模型':<35} {'状态':<10} {'延时':>8} {'tokens':>12}")
    print("-" * 70)
    for r in results:
        toks = f"{r['prompt_tokens']}/{r['completion_tokens']}"
        print(f"{r['role']:<10} {r['model'][:33]:<35} {r['status']:<10} {r['latency_ms']:>6} ms {toks:>12}")

    print("-" * 70)
    fails = [r for r in results if "OK" not in r["status"]]
    if fails:
        print(f"\n❌ {len(fails)} 个模型失败：")
        for r in fails:
            print(f"\n  [{r['role'].strip()}] {r['model']}")
            print(f"    → {r['reply']}")
        print("\n💡 如何修复：")
        print("   1. 打开 https://console.gmicloud.ai 左侧 Model Hub")
        print("   2. 找到对应模型，复制完整 model id（如 deepseek-ai/DeepSeek-V3）")
        print("   3. 编辑 .env，把 MODEL_XXX 改成正确 id")
        return 2

    print("\n✅ 全部模型连通成功，可以启动 Streamlit 跑真 LLM 决策了")
    print("   .venv/bin/streamlit run app/dashboard.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
