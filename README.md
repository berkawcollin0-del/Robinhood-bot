# Swing Options Bot

Hybrid **Fundamental + Technical** swing trading system for US stocks  
with **Call & Put** recommendations and a transparent **0–100 scoring/ranking system**.

Designed for accounts around **$13,000**.

## Key Features
- Fundamental quality filter
- Technical swing setups (trend + momentum + volume)
- Separate Call and Put idea generation
- Composite scoring system (see below)
- Ranked daily opportunity list
- Position sizing optimized for \~$13k accounts
- Strict risk management

## Scoring System (0–100)
| Component              | Weight | Description                              |
|------------------------|--------|------------------------------------------|
| Fundamental Quality    | 30%    | Earnings growth, revenue, valuation      |
| Trend Strength         | 20%    | EMAs + ADX                               |
| Technical Setup        | 25%    | RSI, MACD, volume, pattern quality       |
| Options Attractiveness | 15%    | Liquidity, IV, spread, delta             |
| Risk / Reward          | 10%    | R:R ratio, stop distance, DTE quality    |

**Score Guide**
- 85–100 → Elite
- 70–84  → Strong
- 55–69  → Acceptable
- < 55   → Skip

## Quick Start
```bash
pip install -r requirements.txt
python main.py