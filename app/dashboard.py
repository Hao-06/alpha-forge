"""AlphaForge 决策驾驶舱（Streamlit）—— 4 Agent + OKX dry-run 升级版。

设计语言：深炭灰 + 古金色，金融终端风。
布局：
  ① 顶部 metric 卡片：行情 / regime / action / risk
  ② 三 Agent 矩阵（行情判断 / 策略选择 / 风险审核）
  ③ 综合决策 + JSON
  ④ ★ NEW ★ 资金费率套利 Agent 面板
  ⑤ ★ NEW ★ OKX dry-run 订单预览（主订单 + funding 套利订单）
  ⑥ 开发者面板：GMI API 调用日志
"""
from __future__ import annotations

import json as _json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from alphaforge.llm import get_client
from alphaforge.pipeline import TradingPipeline
from alphaforge.strategies import ALL_STRATEGIES
from config import settings

# ---------------------------------------------------------------------- #
# 页面配置 + 全局样式
# ---------------------------------------------------------------------- #
st.set_page_config(
    page_title="AlphaForge · 多 Agent 加密策略官",
    page_icon="⚡",
    layout="wide",
)

st.markdown(
    """
    <style>
      .stApp { background-color: #0e1117; }
      div[data-testid="stMetricValue"] { color: #d4af37; font-family: 'JetBrains Mono', monospace; }
      .agent-card {
        background: linear-gradient(135deg, #1a1d24, #14171c);
        border: 1px solid #2a2f3a;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
      }
      .agent-card.active { border-color: #d4af37; box-shadow: 0 0 16px rgba(212,175,55,0.18); }
      .agent-card h4 { color: #d4af37; margin: 0 0 6px 0; font-size: 0.95rem; }
      .agent-card .model-badge {
        font-size: 0.7rem; color: #888; font-family: 'JetBrains Mono', monospace;
        background: #0e1117; padding: 2px 8px; border-radius: 4px; display: inline-block;
        margin-bottom: 6px;
      }
      .agent-card .content { color: #c9d1d9; font-size: 0.85rem; line-height: 1.5; }
      .pipeline-step { color: #888; font-size: 0.85rem; padding: 2px 0; }
      .pipeline-step.done { color: #2ea043; }
      .pipeline-step.active { color: #d4af37; font-weight: 600; }
      .verdict-approve { color: #2ea043; font-weight: 700; }
      .verdict-warn    { color: #d4af37; font-weight: 700; }
      .verdict-veto    { color: #f85149; font-weight: 700; }
      .funding-row.long { color: #2ea043; }
      .funding-row.short { color: #f85149; }
      .dry-run-badge {
        background: #b3500024; color: #d4af37; border: 1px solid #b35000;
        padding: 2px 8px; border-radius: 4px; font-size: 0.75rem;
        font-family: 'JetBrains Mono', monospace; margin-left: 8px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------- #
# 侧栏
# ---------------------------------------------------------------------- #
with st.sidebar:
    st.title("⚡ AlphaForge")
    st.caption("Global Crypto · Multi-Agent · Live Strategy Officer")

    if not settings.llm.configured:
        st.error("⚠️ GMI_API_KEY 未配置\n\n复制 `.env.example` 为 `.env` 并填入 Key 后重启。")

    st.markdown("**币种**")
    symbol = st.selectbox("symbol", settings.market.symbols, label_visibility="collapsed")
    with_funding = st.toggle("启用资金费率 Agent", value=True,
                              help="扫全市场永续合约费率，找 Delta-Neutral 套利机会")
    run_btn = st.button("🚀 启动多 Agent 决策", use_container_width=True, type="primary")

    st.markdown("---")
    st.markdown("**Agent 团队**")
    st.markdown(f"📊 行情判断 · `{settings.llm.model_regime}`")
    st.markdown(f"🎯 策略选择 · `{settings.llm.model_strategy}`")
    st.markdown(f"🛡️ 风险审核 · `{settings.llm.model_risk}`")
    st.markdown(f"💱 资金费率 · `{settings.llm.model_strategy}`")

    st.markdown("---")
    st.markdown("**内置策略库（5）**")
    for s in ALL_STRATEGIES.values():
        st.caption(f"{s.display_name} — {s.description}")

# ---------------------------------------------------------------------- #
# 主区域
# ---------------------------------------------------------------------- #
st.markdown("### 决策驾驶舱")
st.caption(f"目标用户：全球加密交易者　│　实时数据：{settings.market.exchange.upper()}"
           f" + OKX funding 　│　提交日期：{datetime.utcnow().strftime('%Y-%m-%d UTC')}")

if "result" not in st.session_state:
    st.session_state.result = None
if "stream_steps" not in st.session_state:
    st.session_state.stream_steps = []

# ---------------------------------------------------------------------- #
# 跑 pipeline
# ---------------------------------------------------------------------- #
if run_btn:
    st.session_state.result = None
    st.session_state.stream_steps = []
    # 清理之前的中间态
    for k in list(st.session_state.keys()):
        if k.startswith("_"):
            del st.session_state[k]

    pipe = TradingPipeline(exchange=settings.market.exchange)
    placeholder = st.empty()

    steps_meta = [
        ("① 抓取实时行情", "snapshot"),
        ("② 行情判断 Agent (R1)", "regime"),
        ("③ 策略选择 Agent (Claude)", "plan"),
        ("④ 风险审核 Agent (GPT)", "risk"),
        ("⑤ 决策官综合", "decision"),
    ]
    if with_funding:
        steps_meta += [
            ("⑥ 资金费率套利 Agent", "funding"),
            ("⑦ OKX dry-run 订单生成", "funding_orders"),
        ]

    for stage, payload in pipe.run_streaming(symbol, with_funding=with_funding):
        st.session_state.stream_steps.append((stage, time.time()))
        with placeholder.container():
            steps_done = {s for s, _ in st.session_state.stream_steps}
            html = []
            for label, key in steps_meta:
                klass = "done" if key in steps_done and key != stage else (
                    "active" if key == stage else "")
                html.append(f'<div class="pipeline-step {klass}">{label}</div>')
            placeholder.markdown("".join(html), unsafe_allow_html=True)

        if stage == "decision":
            st.session_state.result = payload
        else:
            st.session_state[f"_{stage}"] = payload

# ---------------------------------------------------------------------- #
# 结果展示
# ---------------------------------------------------------------------- #
decision = st.session_state.result
if decision is not None:
    snap = st.session_state.get("_snapshot")
    regime = decision.regime
    plan = decision.plan
    risk = decision.risk
    funding = st.session_state.get("_funding")
    funding_orders = st.session_state.get("_funding_orders") or []
    main_order = st.session_state.get("_main_order")

    # 顶部 行情卡片
    cols = st.columns(4)
    cols[0].metric(decision.symbol, f"${snap.last_price:,.2f}" if snap else "-",
                   f"{snap.pct_change_24h:+.2f}%" if snap else "-")
    cols[1].metric("Regime", regime.dominant, f"{regime.probs[regime.dominant]:.0%}")
    cols[2].metric("Action", decision.action.upper(), f"{decision.confidence:.0%} conf")
    verdict_color = {"approve": "#2ea043", "warn": "#d4af37", "veto": "#f85149"}[risk.verdict]
    cols[3].markdown(
        f"<div data-testid='stMetric'>"
        f"<div style='color:#888;font-size:0.8rem;'>Risk</div>"
        f"<div style='color:{verdict_color};font-size:1.5rem;font-weight:700;'>"
        f"{risk.risk_score}/10 · {risk.verdict.upper()}</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Agent 工作矩阵（3 + 1，funding 单独一行更突出）
    a, b, c = st.columns(3)
    with a:
        st.markdown(
            f"""<div class="agent-card active">
              <h4>📊 行情判断 Agent</h4>
              <div class="model-badge">{settings.llm.model_regime}</div>
              <div class="content">
                <b>Dominant:</b> {regime.dominant}<br/>
                <b>Probs:</b> {' · '.join(f'{k[:6]}={v:.0%}' for k,v in regime.probs.items())}<br/>
                <b>推理:</b> {regime.rationale}
              </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with b:
        weights_str = "<br/>".join(
            f"• {ALL_STRATEGIES[k].display_name}: <b>{v:.0%}</b><br/><span style='color:#888'>↳ {plan.tweaks.get(k, '')}</span>"
            for k, v in sorted(plan.weights.items(), key=lambda kv: -kv[1]) if v > 0.01
        )
        st.markdown(
            f"""<div class="agent-card active">
              <h4>🎯 策略选择 Agent</h4>
              <div class="model-badge">{settings.llm.model_strategy}</div>
              <div class="content">
                {weights_str}<br/>
                <span style='color:#888'>{plan.rationale}</span>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c:
        verdict_class = {"approve": "verdict-approve", "warn": "verdict-warn", "veto": "verdict-veto"}[risk.verdict]
        notes_html = "<br/>".join(f"• {n}" for n in risk.notes) or "（无）"
        st.markdown(
            f"""<div class="agent-card active">
              <h4>🛡️ 风险审核 Agent</h4>
              <div class="model-badge">{settings.llm.model_risk}</div>
              <div class="content">
                <span class="{verdict_class}">{risk.verdict.upper()}</span> · 风险评分 <b>{risk.risk_score}/10</b><br/>
                {notes_html}
              </div>
            </div>""",
            unsafe_allow_html=True,
        )

    st.markdown("### 🧠 综合决策")
    st.markdown(f"> {decision.rationale}")
    st.code(_json.dumps(decision.to_json(), ensure_ascii=False, indent=2), language="json")

    # ------------------------------------------------------------------ #
    # ★ NEW ★ 资金费率套利 Agent 面板
    # ------------------------------------------------------------------ #
    if funding is not None:
        st.markdown("---")
        st.markdown("### 💱 资金费率套利 Agent（OKX 全市场扫描）")
        st.caption(f"📡 实时拉取 OKX `/api/v5/public/funding-rate` · {len(funding.snapshots)} 个合约 9 小时内即将结算")
        if funding.summary:
            st.markdown(f"**市场态势**：{funding.summary}")

        # LLM 精选的 top 3 套利机会
        if funding.top_picks:
            pick_cols = st.columns(len(funding.top_picks))
            for i, pick in enumerate(funding.top_picks):
                with pick_cols[i]:
                    color = "#2ea043" if pick.direction == "long" else "#f85149"
                    st.markdown(
                        f"""<div class="agent-card active">
                          <h4>{pick.inst_id}</h4>
                          <div class="content">
                            <div style='color:{color};font-size:1.6rem;font-weight:700;'>
                              {pick.direction.upper()}
                            </div>
                            费率 <b>{pick.rate_pct:+.4f}%</b><br/>
                            置信 {pick.confidence:.0%}<br/>
                            <span style='color:#888'>{pick.rationale}</span>
                          </div>
                        </div>""",
                        unsafe_allow_html=True,
                    )

        # 全市场费率排行榜
        with st.expander(f"📋 全市场资金费率排行（前 {min(len(funding.snapshots), 20)}）", expanded=False):
            df = pd.DataFrame([
                {
                    "合约": s.inst_id,
                    "费率(%)": round(s.rate_pct, 4),
                    "套利方向": s.direction_hint,
                    "距结算(min)": s.minutes_to_settle,
                }
                for s in funding.snapshots[:20]
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------ #
    # ★ NEW ★ OKX dry-run 订单预览
    # ------------------------------------------------------------------ #
    if main_order or funding_orders:
        st.markdown("---")
        st.markdown(
            "### 🔌 OKX 执行层 · Dry-Run 订单预览"
            "<span class='dry-run-badge'>DRY-RUN（不真下单）</span>",
            unsafe_allow_html=True,
        )
        st.caption("基于 Agent 决策与 funding 推荐，已生成可发送的 OKX 订单（含 HMAC-SHA256 签名）。"
                   "默认 dry-run 模式只展示不发送——路演安全。")

        tabs = []
        previews: list = []
        if main_order:
            tabs.append(f"📈 主策略订单：{main_order.inst_id}")
            previews.append(main_order)
        for fo in funding_orders:
            tabs.append(f"💱 套利：{fo.inst_id}")
            previews.append(fo)

        if tabs:
            tab_objs = st.tabs(tabs)
            for t, p in zip(tab_objs, previews):
                with t:
                    disp = p.to_display()
                    cc = st.columns([2, 3])
                    with cc[0]:
                        st.markdown(f"**方向**：{disp['side'].upper()} / `posSide={disp['pos_side']}`")
                        st.markdown(f"**杠杆**：{disp['leverage']}x · `tdMode=isolated`")
                        st.markdown(f"**张数**：{disp['size_contracts']}")
                        if disp['tp_price'] and disp['sl_price']:
                            st.markdown(f"**TP / SL**：${disp['tp_price']} / ${disp['sl_price']}")
                        st.markdown(f"**Endpoint**：`POST {disp['request_path']}`")
                        st.markdown("**Headers（签名已脱敏）**：")
                        st.json(disp["headers"], expanded=False)
                    with cc[1]:
                        st.markdown("**Body（完整可发送的 OKX 订单 JSON）**：")
                        st.code(_json.dumps(disp["body"], indent=2, ensure_ascii=False), language="json")

else:
    st.info("👈 在左边选币种，点击 **启动多 Agent 决策** 开始。")
    st.markdown("#### Agent 协作流程")
    st.markdown("""
1. **抓取实时行情**（CCXT · Binance / OKX）
2. **行情判断 Agent**（DeepSeek-R1）输出 regime 概率分布
3. **策略选择 Agent**（Claude 4.6）从 5 策略库分配权重并给微调建议
4. **风险审核 Agent**（GPT）做合规与逻辑把关
5. **决策官**综合三方意见 → JSON 交易信号
6. ★ **资金费率套利 Agent**（Claude）扫 OKX 全市场永续合约费率 → Delta-Neutral 套利推荐
7. ★ **OKX dry-run 订单生成**——把决策与套利推荐翻成可发送的真实订单 JSON（默认不真下单）
""")

# ---------------------------------------------------------------------- #
# 开发者面板：GMI API 调用日志
# ---------------------------------------------------------------------- #
st.markdown("---")
with st.expander("🔧 开发者面板 · GMI Cloud Inference Engine API 调用日志", expanded=False):
    logs = get_client().get_logs()
    if not logs:
        st.caption("尚无调用记录。点击「启动多 Agent 决策」后这里会列出每一次 GMI API 调用。")
    else:
        df = pd.DataFrame([
            {
                "时间": datetime.fromtimestamp(l.ts).strftime("%H:%M:%S"),
                "Agent": l.agent,
                "模型": l.model,
                "延时(ms)": l.latency_ms,
                "prompt_tokens": l.prompt_tokens,
                "completion_tokens": l.completion_tokens,
                "状态": l.status,
                "prompt 预览": l.prompt_preview,
                "response 预览": l.response_preview,
            }
            for l in logs
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(f"共 {len(logs)} 次 GMI API 调用 · 该面板供提交清单第 6 项「后端截图体现 GMI 平台 API 接入」使用。")
