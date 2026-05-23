# AlphaForge · 全球加密多 Agent 智能策略官

> **2026「头号 Builder · 出海 AI Agent」大赛参赛作品**
> 一个为全球加密交易者打造的、由多个 LLM Agent 协同决策、能在实时行情下**自动选择 / 微调交易策略**的 24/7 策略助手。

## 🎯 产品定位

| 维度 | 内容 |
|---|---|
| **目标用户** | 全球加密交易者（北美 / 东南亚 / 欧洲为主） |
| **场景** | 24/7 行情持续监控，策略选择疲劳，跨指标分析能力不足 |
| **核心能力** | 实时行情 → 多 Agent 分析 → 自动选择 / 微调策略 → 输出可解释的交易信号 |
| **关键差异** | 不是单一策略机器人，而是 **Agent 团队 + 策略库 + 策略自进化** |

## 🧠 Agent 团队

```
[实时行情：BTC / ETH / SOL]
              ↓
┌────────────────────────────────────────┐
│ 📊 行情判断 Agent      ← DeepSeek-R1   │
│    输出：市场 regime + 概率分布          │
├────────────────────────────────────────┤
│ 🎯 策略选择 Agent      ← Claude 4.5    │
│    输出：从 5 策略库中选/混合 + 权重    │
├────────────────────────────────────────┤
│ 🛡️ 风险审核 Agent     ← GPT-5         │
│    输出：风险评分 + 否决/通过             │
└────────────────────────────────────────┘
              ↓
🧠 决策官（综合）→ 交易信号 JSON + R1 思维链
```

## 📚 内置策略库

- **Momentum** —— 动量趋势跟踪
- **Mean Reversion** —— 均值回归
- **Grid** —— 网格交易
- **Breakout** —— 突破策略
- **DCA** —— 定投策略

Agent 会根据实时 regime **动态混合**这些策略并微调参数。

## 🔌 技术栈

- **Python 3.13** + **Streamlit**（演示看板）
- **GMI Cloud Inference Engine API** —— 多模型协作核心
  - DeepSeek-R1 / Claude 4.5 / GPT-5 / Qwen3-VL
- **CCXT** —— 加密行情统一接口（Binance / OKX）

## 🚀 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 GMI Token
cp .env.example .env
# 编辑 .env，填入 GMI_API_KEY

# 3. 启动看板
streamlit run app/dashboard.py
```

## 📜 学术诚信声明

本作者曾在前期「驼灵智能体大赛」中开发多 Agent 投研系统，积累的**架构经验**（多 Agent 协作模式、LLM 客户端抽象、R1 思维链可视化）启发了本项目的设计思路。

但本项目：
- **场景全新**（A 股投研 → 全球加密交易）
- **代码全新**（本仓库 `git init` 时间为 2026-05-23，所有代码为本次活动期间新开发）
- **数据源全新**（AkShare → CCXT）
- **目标用户全新**（中国 A 股投资者 → 全球加密交易者）

符合大赛规则 1.3 "作品须为本次活动期间新开发，可复用开源框架"。

## 🏗️ 项目结构

```
alpha-forge/
├── alphaforge/
│   ├── llm/         # GMI Cloud 客户端抽象层
│   ├── data/        # 实时加密行情（CCXT）
│   ├── strategies/  # 5 个内置策略
│   └── agents/      # 3 个 Agent + 决策官
├── app/
│   └── dashboard.py # Streamlit 决策驾驶舱
├── config/          # 全局配置
└── main.py          # CLI 入口
```

---

**赛事**：2026「头号 Builder · 出海 AI Agent」大赛
**提交日期**：2026-05-23
**代码仓库**：https://atomgit.com/Hao_Sun/alpha-forge
