import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from tickers import WATCHLIST

# ==========================================
# 1. MACRO & SAFETY GATES
# ==========================================
def get_market_regime_score():
    """Calculates % of sample index trading above 200 SMA."""
    sp500_sample = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'JPM', 'V', 'JNJ', 'WMT', 'PG']
    above_200 = 0
    valid_count = 0
    for ticker in sp500_sample:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if df.empty: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if df['close'].iloc[-1] > df['close'].rolling(200).mean().iloc[-1]:
            above_200 += 1
        valid_count += 1
    return above_200 / valid_count if valid_count > 0 else 0.5

def is_earnings_near(ticker):
    try:
        tkr = yf.Ticker(ticker)
        earnings = tkr.get_earnings_dates(limit=1)
        if earnings is not None and not earnings.empty:
            next_date = earnings.index[0].tz_localize(None)
            return (next_date - datetime.now()).days < 7
    except: pass
    return False

# ==========================================
# 2. STRICT CONVICTION SCORING
# ==========================================
def calculate_conviction_score(ticker, df, weekly_df, regime_score):
    if len(df) < 200 or len(weekly_df) < 40 or is_earnings_near(ticker): return 0
    
    # Pre-process columns
    for d in [df, weekly_df]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        d.columns = [c.lower() for c in d.columns]
        
    # Gate 1: Trend Alignment
    if not (df['close'].iloc[-1] > df['close'].rolling(200).mean().iloc[-1] and 
            weekly_df['close'].iloc[-1] > weekly_df['close'].rolling(40).mean().iloc[-1]):
        return 0
    
    # Gate 2: Volume Quality
    if df['volume'].iloc[-1] <= (df['volume'].rolling(20).mean().iloc[-1] * 1.5):
        return 0
        
    # Gate 3: Volatility Compression
    std = df['close'].rolling(20).std()
    sma = df['close'].rolling(20).mean()
    bb_width = (sma + (2 * std)) - (sma - (2 * std))
    if not (bb_width.iloc[-1] < bb_width.rolling(100).mean().iloc[-1]):
        return 0
        
    # Final Score: ATR-Normalized Breakout
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    score = (abs(df['close'].iloc[-1] - df['close'].iloc[-2]) / atr) * 100
    
    return score * regime_score

# ==========================================
# 3. PARALLEL PIPELINE
# ==========================================
def process_symbol(ticker, regime_score):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        score = calculate_conviction_score(ticker, df, w_df, regime_score)
        return {'ticker': ticker, 'score': score} if score > 0 else None
    except: return None

def generate_signals(ticker_list):
    regime = get_market_regime_score()
    print(f"Market Regime Score: {regime:.2f}")
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda t: process_symbol(t, regime), ticker_list))
    
    df_rankings = pd.DataFrame([r for r in results if r is not None])
    if not df_rankings.empty:
        return df_rankings.sort_values(by='score', ascending=False)
    return pd.DataFrame()

if __name__ == "__main__":
    rankings = generate_signals(WATCHLIST)
    print("\n--- HIGH CONVICTION SWING SETUPS ---")
    if not rankings.empty:
        print(rankings.head(20))
    else:
        print("No high-conviction setups found today.")
