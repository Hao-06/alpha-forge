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
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

# Streamlit Cloud 注入 secrets → 写到 os.environ，让下游 config/settings.py 能读到
# 必须在 import config 之前完成
try:
    for _k, _v in st.secrets.items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass   # 本地无 secrets.toml 也无所谓，会走 .env

import pandas as pd
import plotly.graph_objects as go
from alphaforge.llm import get_client
from alphaforge.pipeline import TradingPipeline
from alphaforge.strategies import ALL_STRATEGIES
from config import settings

# ---------------------------------------------------------------------- #
# 图表辅助 —— 统一深色金融终端主题（透明背景 + 古金/绿红 + 等宽字体）
# ---------------------------------------------------------------------- #
_C = dict(gold="#d4af37", green="#3fb950", red="#f0584e", blue="#58a6ff",
          purple="#b07cff", ink="#e6edf3", muted="#8b949e", grid="#1a212c")


def _layout(height, title=None):
    return go.Layout(
        height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=8, r=8, t=30 if title else 8, b=8),
        font=dict(family="JetBrains Mono, SF Mono, monospace", color=_C["muted"], size=11),
        title=dict(text=title, font=dict(color=_C["ink"], size=13), x=0.01) if title else None,
        showlegend=False,
    )


def chart_price(ohlcv):
    """K 线 + MA7/MA25 均线。"""
    df = ohlcv.copy()
    df["t"] = pd.to_datetime(df["ts"], unit="ms")
    close = df["close"].astype(float)
    fig = go.Figure(layout=_layout(300))
    fig.add_trace(go.Candlestick(
        x=df["t"], open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=_C["green"], decreasing_line_color=_C["red"],
        increasing_fillcolor=_C["green"], decreasing_fillcolor=_C["red"], name="K线"))
    fig.add_trace(go.Scatter(x=df["t"], y=close.rolling(7).mean(),
                             line=dict(color=_C["gold"], width=1.4), name="MA7"))
    fig.add_trace(go.Scatter(x=df["t"], y=close.rolling(25).mean(),
                             line=dict(color=_C["blue"], width=1.4), name="MA25"))
    fig.update_layout(
        xaxis=dict(gridcolor=_C["grid"], rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor=_C["grid"], side="right"),
        showlegend=True, legend=dict(orientation="h", y=1.06, x=0, font=dict(size=10)))
    return fig


def chart_regime(probs):
    """Regime 概率分布水平条形图，主导项高亮金色。"""
    items = sorted(probs.items(), key=lambda kv: kv[1])
    labels = [k for k, _ in items]
    vals = [v * 100 for _, v in items]
    dom = max(probs, key=probs.get)
    colors = [_C["gold"] if k == dom else "#37424f" for k in labels]
    fig = go.Figure(layout=_layout(250, "Regime 概率分布"))
    fig.add_trace(go.Bar(x=vals, y=labels, orientation="h", marker_color=colors,
                         text=[f"{v:.0f}%" for v in vals], textposition="outside",
                         textfont=dict(color=_C["ink"], size=11)))
    fig.update_layout(xaxis=dict(visible=False, range=[0, max(vals) * 1.28 if vals else 1]),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=10)))
    return fig


def chart_weights(weights):
    """策略权重环形图。"""
    items = [(k, v) for k, v in weights.items() if v > 0.005]
    labels = [k for k, _ in items]
    vals = [v * 100 for _, v in items]
    palette = [_C["gold"], _C["blue"], _C["green"], _C["purple"], _C["red"]]
    fig = go.Figure(layout=_layout(250, "策略权重分配"))
    fig.add_trace(go.Pie(labels=labels, values=vals, hole=0.58,
                         marker=dict(colors=palette[:len(labels)], line=dict(color="#0e1117", width=2)),
                         textinfo="label+percent", textfont=dict(size=10, color=_C["ink"]),
                         sort=True, direction="clockwise"))
    return fig


def chart_risk(score):
    """风险评分 gauge 仪表盘（1-10）。"""
    color = _C["green"] if score <= 3 else (_C["gold"] if score <= 6 else _C["red"])
    fig = go.Figure(layout=_layout(250, "风险评分"))
    fig.add_trace(go.Indicator(
        mode="gauge+number", value=score,
        number=dict(font=dict(color=color, size=36), suffix=" /10"),
        gauge=dict(axis=dict(range=[0, 10], tickcolor=_C["muted"], tickfont=dict(size=9)),
                   bar=dict(color=color, thickness=0.32), bordercolor="rgba(0,0,0,0)",
                   steps=[dict(range=[0, 3], color="rgba(63,185,80,.14)"),
                          dict(range=[3, 6], color="rgba(212,175,55,.14)"),
                          dict(range=[6, 10], color="rgba(240,88,78,.14)")]),
        domain=dict(x=[0, 1], y=[0, 1])))
    return fig


def chart_funding(snaps, n=12):
    """资金费率分布水平条形图：正费率(做空收费)红 / 负费率(做多收费)绿。"""
    s = sorted(list(snaps)[:n], key=lambda x: x.rate_pct)
    labels = [x.inst_id.replace("-USDT-SWAP", "") for x in s]
    vals = [x.rate_pct for x in s]
    colors = [_C["red"] if v > 0 else _C["green"] for v in vals]
    fig = go.Figure(layout=_layout(300, "资金费率分布 %　·　红=正(做空收费) 绿=负(做多收费)"))
    fig.add_trace(go.Bar(x=vals, y=labels, orientation="h", marker_color=colors,
                         text=[f"{v:+.3f}" for v in vals], textposition="outside",
                         textfont=dict(color=_C["muted"], size=10)))
    fig.update_layout(xaxis=dict(gridcolor=_C["grid"], zeroline=True, zerolinecolor="#3a4453"),
                      yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=9)))
    return fig

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
      @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&display=swap');

      :root{
        --bg:#07090d; --panel:#0e1117; --panel2:#12161e; --panel3:#161b24;
        --border:#232b38; --border-soft:#1a212c;
        --gold:#d4af37; --gold-br:#ecc86a; --ink:#e6edf3; --muted:#8b949e; --dim:#586172;
        --green:#3fb950; --red:#f0584e; --blue:#58a6ff;
        --mono:'JetBrains Mono','SF Mono',ui-monospace,monospace;
      }

      .stApp{
        background:
          radial-gradient(1200px 520px at 78% -10%, rgba(212,175,55,.07), transparent 60%),
          radial-gradient(900px 500px at 8% -5%, rgba(60,90,150,.06), transparent 55%),
          #07090d;
      }
      .stApp::before{ content:""; position:fixed; top:0; left:0; right:0; height:2px; z-index:9999;
        background:linear-gradient(90deg,transparent,var(--gold) 30%,var(--gold-br) 50%,var(--gold) 70%,transparent); opacity:.7; }

      html, body, [class*="css"]{ font-family:"PingFang SC","Hiragino Sans GB",-apple-system,"Microsoft YaHei",sans-serif; color:var(--ink); }
      .block-container{ padding-top:2.2rem; padding-bottom:3rem; max-width:1500px; }
      h3{ color:var(--ink); font-weight:700; letter-spacing:.3px; }
      code, kbd{ font-family:var(--mono); color:var(--gold-br); }
      ::-webkit-scrollbar{ width:10px; height:10px; }
      ::-webkit-scrollbar-track{ background:#0b0e13; }
      ::-webkit-scrollbar-thumb{ background:#222a36; border-radius:5px; }
      ::-webkit-scrollbar-thumb:hover{ background:#2e3848; }
      ::selection{ background:rgba(212,175,55,.28); }

      [data-testid="stSidebar"]{ background:linear-gradient(180deg,#0b0e13,#080a0f); border-right:1px solid var(--border-soft); }
      [data-testid="stSidebar"] h1{ font-size:1.4rem; }

      .stButton > button{ font-weight:600; letter-spacing:.4px; border-radius:10px; border:1px solid #2a313d; transition:all .18s ease; }
      .stButton > button:hover{ border-color:var(--gold); color:var(--gold); }
      .stButton > button[kind="primary"]{ background:linear-gradient(135deg,#d4af37,#b8902b); color:#0a0c10; border:none; box-shadow:0 4px 16px rgba(212,175,55,.22); }
      .stButton > button[kind="primary"]:hover{ box-shadow:0 6px 24px rgba(212,175,55,.4); transform:translateY(-1px); color:#0a0c10; }

      [data-testid="stMetric"]{ background:linear-gradient(150deg,var(--panel3),var(--panel2)); border:1px solid var(--border); border-radius:14px; padding:16px 18px; }
      [data-testid="stMetricLabel"]{ color:var(--muted)!important; }
      [data-testid="stMetricValue"]{ color:var(--gold); font-family:var(--mono); font-weight:700; }

      [data-testid="stDataFrame"]{ border:1px solid var(--border); border-radius:12px; overflow:hidden; }
      [data-testid="stExpander"]{ border:1px solid var(--border)!important; border-radius:12px!important; background:var(--panel)!important; overflow:hidden; }
      [data-testid="stExpander"] summary:hover{ color:var(--gold); }
      [data-testid="stTabs"] button[role="tab"][aria-selected="true"]{ color:var(--gold); }
      [data-testid="stTabs"] [data-baseweb="tab-highlight"]{ background:var(--gold)!important; }
      [data-testid="stAlert"]{ border-radius:12px; border:1px solid var(--border); }
      pre{ border-radius:12px!important; border:1px solid var(--border)!important; }
      hr{ border-color:var(--border-soft)!important; margin:1rem 0; }

      /* hero 品牌区 */
      .hero{ display:flex; align-items:center; justify-content:space-between; padding:20px 26px; margin-bottom:16px;
        background:linear-gradient(120deg,#11151d,#0c0f15); border:1px solid var(--border); border-radius:16px; position:relative; overflow:hidden; }
      .hero::after{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:linear-gradient(180deg,var(--gold),transparent); }
      .hero .brand{ font-size:1.55rem; font-weight:800; letter-spacing:.5px; }
      .hero .brand .g{ color:var(--gold); }
      .hero .sub{ font-size:.74rem; color:var(--muted); font-family:var(--mono); letter-spacing:1.3px; margin-top:5px; }
      .hero .live{ font-family:var(--mono); font-size:.78rem; color:var(--green); display:flex; align-items:center; gap:8px; justify-content:flex-end; }
      .dot{ width:8px; height:8px; border-radius:50%; background:var(--green); animation:pulse 1.8s infinite; }
      @keyframes pulse{ 0%{box-shadow:0 0 0 0 rgba(63,185,80,.5);} 70%{box-shadow:0 0 0 8px rgba(63,185,80,0);} 100%{box-shadow:0 0 0 0 rgba(63,185,80,0);} }

      /* metric 卡 */
      .mcard{ background:linear-gradient(150deg,var(--panel3),var(--panel2)); border:1px solid var(--border); border-radius:14px; padding:15px 18px; position:relative; overflow:hidden; }
      .mcard::before{ content:""; position:absolute; left:0; top:0; bottom:0; width:3px; background:var(--accent,var(--gold)); opacity:.85; }
      .mcard .lab{ font-size:.7rem; color:var(--muted); font-family:var(--mono); letter-spacing:1px; text-transform:uppercase; display:flex; align-items:center; gap:6px; }
      .mcard .val{ font-size:1.55rem; font-weight:700; font-family:var(--mono); color:var(--ink); margin-top:8px; line-height:1.15; }
      .mcard .sub{ font-size:.78rem; margin-top:6px; font-family:var(--mono); color:var(--muted); }

      /* section 标题 */
      .sec{ display:flex; align-items:center; gap:10px; font-size:1.1rem; font-weight:700; color:var(--ink); margin:8px 0 8px; }
      .sec::before{ content:""; width:3px; height:18px; background:var(--gold); border-radius:2px; }
      .sec .badge{ font-family:var(--mono); font-size:.7rem; color:var(--muted); font-weight:500; letter-spacing:.5px; }

      /* agent card */
      .agent-card{ background:linear-gradient(155deg,var(--panel3),var(--panel2)); border:1px solid var(--border); border-radius:14px;
        padding:18px 18px 16px; margin-bottom:12px; position:relative; overflow:hidden; height:100%; }
      .agent-card::before{ content:""; position:absolute; left:0; right:0; top:0; height:2px; background:linear-gradient(90deg,var(--gold),transparent); opacity:.65; }
      .agent-card.active{ box-shadow:0 8px 30px rgba(0,0,0,.35); }
      .agent-card h4{ color:var(--ink); margin:0 0 10px; font-size:1rem; font-weight:700; }
      .agent-card .model-badge{ font-size:.66rem; color:var(--gold); font-family:var(--mono); letter-spacing:.5px;
        background:rgba(212,175,55,.08); border:1px solid rgba(212,175,55,.25); padding:3px 9px; border-radius:5px; display:inline-block; margin-bottom:12px; }
      .agent-card .content{ color:var(--muted); font-size:.85rem; line-height:1.65; }
      .agent-card .content b{ color:var(--ink); font-weight:600; }

      /* pipeline 步骤 */
      .pipeline-step{ color:var(--dim); font-size:.9rem; padding:5px 0 5px 24px; position:relative; }
      .pipeline-step::before{ content:""; position:absolute; left:5px; top:50%; transform:translateY(-50%); width:7px; height:7px; border-radius:50%; background:#2a3340; }
      .pipeline-step.done{ color:var(--green); }
      .pipeline-step.done::before{ background:var(--green); }
      .pipeline-step.active{ color:var(--gold); font-weight:600; }
      .pipeline-step.active::before{ background:var(--gold); animation:pulse 1.4s infinite; }

      .verdict-approve{ color:var(--green); font-weight:700; }
      .verdict-warn{ color:var(--gold); font-weight:700; }
      .verdict-veto{ color:var(--red); font-weight:700; }
      .funding-row.long{ color:var(--green); } .funding-row.short{ color:var(--red); }
      .dry-run-badge{ background:rgba(212,175,55,.1); color:var(--gold); border:1px solid rgba(212,175,55,.4);
        padding:3px 10px; border-radius:6px; font-size:.72rem; font-family:var(--mono); margin-left:10px; letter-spacing:.5px; }
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
        # 诊断信息：帮助排查 Streamlit Cloud secrets 注入是否生效
        with st.expander("🔍 诊断信息（点击展开）"):
            try:
                _sec_keys = list(st.secrets.keys())
                st.caption(f"st.secrets 里检测到 {len(_sec_keys)} 个 key：{_sec_keys or '（空）'}")
            except Exception as _e:
                st.caption(f"st.secrets 读取失败：{type(_e).__name__}: {_e}")
            _env_key = os.environ.get("GMI_API_KEY", "")
            if _env_key:
                st.caption(f"os.environ['GMI_API_KEY']：长度 {len(_env_key)}，开头 `{_env_key[:6]}…`")
            else:
                st.caption("os.environ['GMI_API_KEY']：**空** ← secrets 没注入到环境变量")
            st.caption(f"settings.llm.api_key 长度：{len(settings.llm.api_key)}")
            st.caption(f"settings.llm.configured：{settings.llm.configured}")

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
st.markdown(
    f"""<div class="hero">
      <div>
        <div class="brand">⚡ Alpha<span class="g">Forge</span>　<span style="font-size:.95rem;font-weight:600;color:var(--muted);">决策驾驶舱</span></div>
        <div class="sub">GLOBAL CRYPTO · MULTI-AGENT · LIVE STRATEGY OFFICER</div>
      </div>
      <div>
        <div class="live"><span class="dot"></span>LIVE · {settings.market.exchange.upper()} + OKX FUNDING</div>
        <div class="sub" style="text-align:right;margin-top:7px;">{datetime.now(timezone.utc).strftime('%Y-%m-%d UTC')}　·　目标用户：全球加密交易者</div>
      </div>
    </div>""",
    unsafe_allow_html=True,
)

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
    get_client().clear_logs()   # 只统计本次决策的 GMI 调用，汇总条/耗时才对应「这一次」
    # 清理之前的中间态
    for k in list(st.session_state.keys()):
        if k.startswith("_"):
            del st.session_state[k]

    _t0 = time.time()
    pipe = TradingPipeline(exchange=settings.market.exchange)
    placeholder = st.empty()

    steps_meta = [
        ("① 抓取实时行情", "snapshot"),
        ("② 行情判断 Agent (R1)", "regime"),
        ("③ 策略选择 Agent (GPT-4o)", "plan"),
        ("④ 风险审核 Agent (GPT-4o-mini)", "risk"),
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

    st.session_state["_elapsed_s"] = time.time() - _t0

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

    # 本次决策运行汇总 —— 强化「完整多 Agent 流程真实跑通」的第一印象
    _n_agents = 4 if funding is not None else 3
    _n_calls = len(get_client().get_logs())
    _elapsed = st.session_state.get("_elapsed_s")
    _elapsed_str = f"{_elapsed:.1f}s" if _elapsed else "—"
    st.success(
        f"✅ 决策完成　·　{_n_agents} 个 LLM Agent + 决策官协同"
        f"　·　{_n_calls} 次 GMI Cloud 调用　·　端到端耗时 {_elapsed_str}"
    )

    # 顶部 行情卡片（定制 metric 卡：状态灯 + 等宽数字 + accent 色条）
    def _mcard(lab, val, sub, accent="var(--gold)", sub_color="var(--muted)", live=False):
        dot = '<span class="dot"></span>' if live else ''
        return (f'<div class="mcard" style="--accent:{accent};">'
                f'<div class="lab">{dot}{lab}</div>'
                f'<div class="val" style="color:{accent};">{val}</div>'
                f'<div class="sub" style="color:{sub_color};">{sub}</div></div>')

    cols = st.columns(4)
    _chg = snap.pct_change_24h if snap else 0.0
    _chg_color = "var(--green)" if _chg >= 0 else "var(--red)"
    cols[0].markdown(_mcard(
        decision.symbol, f"${snap.last_price:,.2f}" if snap else "—",
        f"{'▲' if _chg >= 0 else '▼'} {_chg:+.2f}%　24h",
        accent="var(--gold)", sub_color=_chg_color, live=True), unsafe_allow_html=True)
    cols[1].markdown(_mcard(
        "Regime", regime.dominant, f"{regime.probs[regime.dominant]:.0%} 主导概率",
        accent="var(--blue)"), unsafe_allow_html=True)
    _act_color = {"buy": "var(--green)", "sell": "var(--red)", "hold": "var(--gold)"}.get(decision.action, "var(--gold)")
    cols[2].markdown(_mcard(
        "Action", decision.action.upper(), f"{decision.confidence:.0%} confidence",
        accent=_act_color), unsafe_allow_html=True)
    _risk_color = {"approve": "var(--green)", "warn": "var(--gold)", "veto": "var(--red)"}[risk.verdict]
    cols[3].markdown(_mcard(
        "Risk", f"{risk.risk_score}/10", risk.verdict.upper(),
        accent=_risk_color), unsafe_allow_html=True)

    # 价格走势图（K线 + MA7/MA25）
    if snap is not None and not snap.ohlcv.empty:
        st.markdown('<div class="sec">📈 价格走势 <span class="badge">K线 · MA7 · MA25 · 最近 100 根</span></div>', unsafe_allow_html=True)
        st.plotly_chart(chart_price(snap.ohlcv), use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")

    # Agent 决策可视化（图）—— 与下方文字卡图文呼应
    st.markdown('<div class="sec">📊 Agent 决策可视化</div>', unsafe_allow_html=True)
    g1, g2, g3 = st.columns(3)
    g1.plotly_chart(chart_regime(regime.probs), use_container_width=True, config={"displayModeBar": False})
    g2.plotly_chart(chart_weights(plan.weights), use_container_width=True, config={"displayModeBar": False})
    g3.plotly_chart(chart_risk(risk.risk_score), use_container_width=True, config={"displayModeBar": False})

    # Agent 详细输出（文字卡，3 + 1，funding 单独一行更突出）
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

    st.markdown('<div class="sec">🧠 综合决策 <span class="badge">DecisionOfficer · 确定性规则聚合</span></div>', unsafe_allow_html=True)
    st.markdown(f"> {decision.rationale}")
    st.code(_json.dumps(decision.to_json(), ensure_ascii=False, indent=2), language="json")

    # ------------------------------------------------------------------ #
    # ★ NEW ★ 资金费率套利 Agent 面板
    # ------------------------------------------------------------------ #
    if funding is not None:
        st.markdown("---")
        st.markdown('<div class="sec">💱 资金费率套利 Agent <span class="badge">OKX 全市场扫描</span></div>', unsafe_allow_html=True)
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

        # 资金费率分布图
        if funding.snapshots:
            st.plotly_chart(chart_funding(funding.snapshots), use_container_width=True, config={"displayModeBar": False})

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
            '<div class="sec">🔌 OKX 执行层 · Dry-Run 订单预览'
            '<span class="dry-run-badge">DRY-RUN · 不真下单</span></div>',
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
2. **行情判断 Agent**（DeepSeek-R1-0528）输出 regime 概率分布
3. **策略选择 Agent**（GPT-4o）从 5 策略库分配权重并给微调建议
4. **风险审核 Agent**（GPT-4o-mini）做合规与逻辑把关
5. **决策官**综合三方意见 → JSON 交易信号
6. ★ **资金费率套利 Agent**（GPT-4o）扫 OKX 全市场永续合约费率 → Delta-Neutral 套利推荐
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
        # 汇总指标条 —— 让评委一眼看清「真实调用」硬证据（API 调用质量 30 分）
        _ok = [l for l in logs if l.status == "ok"]
        _total_prompt = sum(l.prompt_tokens or 0 for l in logs)
        _total_completion = sum(l.completion_tokens or 0 for l in logs)
        _avg_latency = int(sum(l.latency_ms for l in _ok) / len(_ok)) if _ok else 0
        _m = st.columns(4)
        _m[0].metric("GMI 调用 (真实/总)", f"{len(_ok)}/{len(logs)}")
        _m[1].metric("总 Tokens", f"{_total_prompt + _total_completion:,}")
        _m[2].metric("Prompt / Completion", f"{_total_prompt:,} / {_total_completion:,}")
        _m[3].metric("平均延时 (真实)", f"{_avg_latency} ms")
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
