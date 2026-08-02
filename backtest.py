# backtest.py
"""
Simple event-based backtest for the swing options strategy
(Uses stock proxies for simplicity – options backtesting is more complex)
"""

import pandas as pd
import yfinance as yf
from technicals import add_indicators
from fundamentals import score_fundamentals
from data import get_fundamentals
import config
from datetime import datetime, timedelta

def simple_stock_backtest(ticker: str, start="2023-01-01", end=None):
    """
    Very simplified backtest using stock as proxy for options direction.
    This is for educational purposes only.
    """
    df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if df.empty:
        print(f"No data for {ticker}")
        return None

    # ---- FIX: Flatten MultiIndex columns if they exist ----
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.lower)
    df = add_indicators(df)
    df.dropna(inplace=True)

    fund = get_fundamentals(ticker)
    fund_score, _ = score_fundamentals(fund)

    capital = config.ACCOUNT_SIZE
    position = 0
    entry_price = 0
    entry_date = None
    trades = []
    equity_curve = []

    for i in range(50, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        date = df.index[i]

        # Exit logic
        if position != 0:
            hold_days = (date - entry_date).days
            pnl_pct = (row["close"] - entry_price) / entry_price * position

            # Simple exits
            stop_hit = False
            if position == 1 and row["close"] < entry_price - (row["atr"] * config.ATR_STOP_MULTIPLIER):
                stop_hit = True
            if position == -1 and row["close"] > entry_price + (row["atr"] * config.ATR_STOP_MULTIPLIER):
                stop_hit = True

            time_exit = hold_days >= config.MAX_HOLDING_DAYS
            rsi_exit = (position == 1 and row["rsi"] > 75) or (position == -1 and row["rsi"] < 25)

            if stop_hit or time_exit or rsi_exit:
                exit_price = row["close"]
                pnl = (exit_price - entry_price) * position * (capital * 0.1 / entry_price)  # rough size
                capital += pnl
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": date,
                    "direction": "Long" if position == 1 else "Short",
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct * 100, 2)
                })
                position = 0

        # Entry logic (simplified)
        if position == 0 and fund_score >= 15:
            # Long
            if (row["close"] > row["ema_50"] > row["ema_200"] and
                config.RSI_BULL_LOW <= row["rsi"] <= config.RSI_BULL_HIGH and
                row["volume"] > row["volume_ma"]):
                position = 1
                entry_price = row["close"]
                entry_date = date

            # Short
            elif (row["close"] < row["ema_50"] < row["ema_200"] and
                  row["rsi"] >= 55 and
                  row["volume"] > row["volume_ma"]):
                position = -1
                entry_price = row["close"]
                entry_date = date

        equity_curve.append({"date": date, "equity": capital})

    # Results
    if not trades:
        print(f"No trades generated for {ticker}")
        return None

    trades_df = pd.DataFrame(trades)
    total_pnl = trades_df["pnl"].sum()
    win_rate = (trades_df["pnl"] > 0).mean() * 100
    avg_win = trades_df[trades_df["pnl"] > 0]["pnl"].mean() if any(trades_df["pnl"] > 0) else 0
    avg_loss = trades_df[trades_df["pnl"] < 0]["pnl"].mean() if any(trades_df["pnl"] < 0) else 0

    print(f"\n=== Backtest Results: {ticker} ===")
    print(f"Total Trades: {len(trades_df)}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Total PnL: ${total_pnl:.2f}")
    print(f"Final Capital: ${capital:.2f}")
    print(f"Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")

    return trades_df

if __name__ == "__main__":
    # Example
    simple_stock_backtest("AAPL", start="2023-01-01")
    simple_stock_backtest("NVDA", start="2023-01-01")