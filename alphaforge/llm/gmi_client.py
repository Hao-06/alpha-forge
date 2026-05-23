"""GMI Cloud Inference Engine 客户端。

GMI 提供 OpenAI 兼容 API，因此直接复用官方 `openai` SDK，只需替换 base_url。
所有调用统一通过本模块，方便在 UI 上展示"GMI API 调用日志"——这是提交清单
第 6 项「产品后端截图体现 GMI Inference Engine 平台 API 接入」的素材源。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from openai import OpenAI

from config import settings


@dataclass
class CallLog:
    """单次 GMI API 调用记录，供决策驾驶舱「开发者面板」展示。"""
    ts: float
    model: str
    agent: str                    # 哪个 Agent 发起的调用
    prompt_preview: str           # 仅截首 80 字，避免日志爆炸
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    status: str                   # "ok" / "error: ..."
    response_preview: str = ""


class GMIClient:
    """对 GMI Inference Engine 的薄包装，统一记录调用日志。"""

    def __init__(self) -> None:
        if not settings.llm.configured:
            # 允许在 mock 模式启动（开发者面板能展示一条"未配置"提示）
            self._client: OpenAI | None = None
        else:
            self._client = OpenAI(
                api_key=settings.llm.api_key,
                base_url=settings.llm.base_url,
            )
        self._logs: list[CallLog] = []
        self._lock = Lock()

    # ------------------------------------------------------------------ #
    # 调用入口
    # ------------------------------------------------------------------ #
    def chat(
        self,
        *,
        agent: str,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 1500,
    ) -> str:
        """同步调用，返回模型回复文本，并把这条调用记入日志。"""
        ts = time.time()
        prompt_preview = self._preview(messages[-1].get("content", "")) if messages else ""

        if self._client is None:
            # mock 模式：返回一个明显的占位符，方便 UI 调试
            mock = f"[MOCK · GMI_API_KEY 未配置 · agent={agent} · model={model}]"
            self._append_log(CallLog(
                ts=ts, model=model, agent=agent,
                prompt_preview=prompt_preview, latency_ms=0,
                prompt_tokens=None, completion_tokens=None,
                status="mock", response_preview=mock[:80],
            ))
            return mock

        t0 = time.perf_counter()
        try:
            kwargs: dict[str, Any] = dict(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response_format is not None:
                kwargs["response_format"] = response_format

            resp = self._client.chat.completions.create(**kwargs)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            text = resp.choices[0].message.content or ""
            usage = getattr(resp, "usage", None)
            self._append_log(CallLog(
                ts=ts, model=model, agent=agent,
                prompt_preview=prompt_preview, latency_ms=latency_ms,
                prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
                completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
                status="ok", response_preview=self._preview(text),
            ))
            return text

        except Exception as exc:
            # 余额不足 / 配额错误 → 优雅降级到 mock，让 UI 流程不中断
            msg = str(exc).lower()
            is_quota = ("insufficient" in msg or "quota" in msg
                        or "402" in msg or "429" in msg)
            status = ("quota_exhausted → mock" if is_quota
                      else f"error: {exc.__class__.__name__}: {exc}")
            self._append_log(CallLog(
                ts=ts, model=model, agent=agent,
                prompt_preview=prompt_preview,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                prompt_tokens=None, completion_tokens=None,
                status=status,
                response_preview=f"[QUOTA-FALLBACK] agent={agent}" if is_quota else "",
            ))
            if is_quota:
                # 返回符合 mock 协议的占位字符串，让上层 agents 走友好 mock 分支
                return f"[MOCK · quota_exhausted · agent={agent} · model={model}]"
            raise

    # ------------------------------------------------------------------ #
    # 日志只读访问
    # ------------------------------------------------------------------ #
    def get_logs(self) -> list[CallLog]:
        with self._lock:
            return list(self._logs)

    def clear_logs(self) -> None:
        with self._lock:
            self._logs.clear()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _append_log(self, log: CallLog) -> None:
        with self._lock:
            self._logs.append(log)

    @staticmethod
    def _preview(text: Any, limit: int = 80) -> str:
        s = str(text).replace("\n", " ")
        return s if len(s) <= limit else s[:limit] + "…"


# 全局单例：UI 多组件共享一份调用日志
_client_singleton: GMIClient | None = None


def get_client() -> GMIClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = GMIClient()
    return _client_singleton
