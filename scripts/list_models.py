"""列出 GMI Cloud 上当前账号可用的所有模型 id。

用法：
    .venv/bin/python scripts/list_models.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import OpenAI

from config import settings


def main() -> int:
    if not settings.llm.configured:
        print("❌ GMI_API_KEY 未配置")
        print("   请先：cp .env.example .env  再填入真 Key")
        return 1

    print(f"Base URL : {settings.llm.base_url}")
    print(f"Key      : {settings.llm.api_key[:8]}…")
    print("-" * 70)

    try:
        client = OpenAI(api_key=settings.llm.api_key, base_url=settings.llm.base_url)
        models = client.models.list().data
    except Exception as e:
        print(f"❌ 拉取模型列表失败：{type(e).__name__}: {e}")
        return 2

    if not models:
        print("（GMI 返回空列表）")
        return 3

    # 按 provider 前缀分组
    groups: dict[str, list[str]] = {}
    for m in models:
        prefix = m.id.split("/")[0] if "/" in m.id else "(no-prefix)"
        groups.setdefault(prefix, []).append(m.id)

    total = len(models)
    print(f"共 {total} 个模型，按 provider 分组：\n")
    for prefix in sorted(groups):
        ids = sorted(groups[prefix])
        print(f"📦 {prefix} ({len(ids)})")
        for mid in ids:
            print(f"   · {mid}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
