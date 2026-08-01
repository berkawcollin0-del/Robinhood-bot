# walk_forward.py
"""
Walk-Forward Analysis for the Swing Options strategy
(Stock proxy version – educational / research use)
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from technicals import add_indicators
from fundamentals import score_fundamentals
from data import get_fundamentals
import config
import numpy as np

def run_walk_forward(
    ticker: str,
    start_date: str = "2021-01-01",
    end_date: str = None,
    in_sample_months: int = 9,
    out_sample_months: int = 3,
    step_months: int = 3
):
    """
    Performs walk-forward analysis.
    
    - Trains (filters) on in-sample window
    - Tests on the following out-of-sample window
    - Rolls forward by step_months
    """

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\n=== Walk-Forward Analysis: {ticker} ===")
    print(f"In-sample: {in_sample_months} months | Out-of-sample: {out_sample_months} months | Step: {step_months} months\n")

    # Download full data
    df = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=True)
    if df.empty or len(df) < 300:
        print("Not enough data")
        return None

    df = df.rename(columns=str.lower)
    df = add_indicators(df)
    df.dropna(inplace=True)

    fund = get_fundamentals(ticker)
    fund_score, _ = score_fundamentals(fund)

    # Convert to datetime index if needed
    df.index = pd.to_datetime(df.index)

    results = []
    current_start = pd.to_datetime(start_date)

    while True:
        in_sample_end = current_start + pd.DateOffset(months=in_sample_months)
        out_sample_end = in_sample_end + pd.DateOffset(months=out_sample_months)

        if out_sample_end > df.index[-1]:
            break

        # Split data
        is_data = df[(df.index >= current_start) & (df.index < in_sample_end)]
        oos_data = df[(df.index >= in_sample_end) & (df.index < out_sample_end)]

        if len(is_data) < 60 or len(oos_data) < 20:
            current_start += pd.DateOffset(months=step_months)
            continue

        # === In-sample: simple parameter check / filter strength ===
        # (In a real system you would optimize parameters here)
        is_signals = generate_signals(is_data, fund_score)
        is_trades = simulate_trades(is_data, is_signals)

        # === Out-of-sample test ===
        oos_signals = generate_signals(oos_data, fund_score)
        oos_trades = simulate_trades(oos_data, oos_signals)

        is_pnl = sum(t["pnl"] for t in is_trades) if is_trades else 0
        oos_pnl = sum(t["pnl"] for t in oos_trades) if oos_trades else 0
        oos_winrate = (sum(1 for t in oos_trades if t["pnl"] > 0) / len(oos_trades) * 100) if oos_trades else 0

        results.append({
            "IS_Start": current_start.date(),
            "IS_End": in_sample_end.date(),
            "OOS_Start": in_sample_end.date(),
            "OOS_End": out_sample_end.date(),
            "IS_Trades": len(is_trades),
            "IS_PnL": round(is_pnl, 2),
            "OOS_Trades": len(oos_trades),
            "OOS_PnL": round(oos_pnl, 2),
            "OOS_WinRate": round(oos_winrate, 1)
        })

        current_start += pd.DateOffset(months=step_months)

    # Summary
    if not results:
        print("No valid walk-forward windows")
        return None

    results_df = pd.DataFrame(results)
    print(results_df.to_string(index=False))

    total_oos_pnl = results_df["OOS_PnL"].sum()
    avg_oos_winrate = results_df["OOS_WinRate"].mean()
    profitable_windows = (results_df["OOS_PnL"] > 0).mean() * 100

    print(f"\n--- Walk-Forward Summary ---")
    print(f"Total OOS PnL: ${total_oos_pnl:.2f}")
    print(f"Average OOS Win Rate: {avg_oos_winrate:.1f}%")
    print(f"% of profitable OOS windows: {profitable_windows:.1f}%")

    return results_df

def generate_signals(df: pd.DataFrame, fund_score: float) -> pd.Series:
    """Generate long/short signals (1 = long, -1 = short, 0 = flat)"""
    signals = pd.Series(0, index=df.index)

    if fund_score < 12:
        return signals

    for i in range(1, len(df)):
        row = df.iloc[i]
        # Long
        if (row["close"] > row["ema_50"] > row["ema_200"] and
            config.RSI_BULL_LOW <= row["rsi"] <= config.RSI_BULL_HIGH and
            row["volume"] > row["volume_ma"] * 1.1):
            signals.iloc[i] = 1
        # Short
        elif (row["close"] < row["ema_50"] < row["ema_200"] and
              row["rsi"] >= 55 and
              row["volume"] > row["volume_ma"] * 1.1):
            signals.iloc[i] = -1

    return signals

def simulate_trades(df: pd.DataFrame, signals: pd.Series, risk_per_trade=0.01):
    """Very simple trade simulator"""
    trades = []
    position = 0
    entry_price = 0
    entry_date = None
    capital = config.ACCOUNT_SIZE

    for i in range(len(df)):
        row = df.iloc[i]
        date = df.index[i]
        signal = signals.iloc[i]

        # Exit
        if position != 0:
            hold_days = (date - entry_date).days
            atr_stop = entry_price - position * row["atr"] * config.ATR_STOP_MULTIPLIER

            stop_hit = (position == 1 and row["close"] < atr_stop) or \
                       (position == -1 and row["close"] > atr_stop)
            time_exit = hold_days >= config.MAX_HOLDING_DAYS

            if stop_hit or time_exit or signal == 0:
                exit_price = row["close"]
                pnl = (exit_price - entry_price) * position * (capital * risk_per_trade / (entry_price * 0.02))  # rough
                trades.append({
                    "entry": entry_date,
                    "exit": date,
                    "direction": position,
                    "pnl": pnl
                })
                position = 0

        # Entry
        if position == 0 and signal != 0:
            position = signal
            entry_price = row["close"]
            entry_date = date

    return trades

if __name__ == "__main__":
    # Example usage
    run_walk_forward("AAPL", start_date="2021-01-01", in_sample_months=9, out_sample_months=3, step_months=3)
    run_walk_forward("NVDA", start_date="2021-01-01", in_sample_months=9, out_sample_months=3, step_months=3)