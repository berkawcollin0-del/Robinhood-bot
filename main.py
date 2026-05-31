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
# 2. STRICT CONVICTION ENGINE
# ==========================================
def calculate_conviction_score(ticker, df, weekly_df, regime_score):
    if len(df) < 200 or len(weekly_df) < 40 or is_earnings_near(ticker): return None
    
    for d in [df, weekly_df]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        d.columns = [c.lower() for c in d.columns]
        
    # Gates
    daily_trend = df['close'].iloc[-1] > df['close'].rolling(200).mean().iloc[-1]
    weekly_trend = weekly_df['close'].iloc[-1] > weekly_df['close'].rolling(40).mean().iloc[-1]
    if not (daily_trend and weekly_trend): return None
    
    vol_avg = df['volume'].rolling(20).mean()
    if df['volume'].iloc[-1] <= (vol_avg.iloc[-1] * 1.5): return None
    
    # Levels (ATR)
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    entry = df['close'].iloc[-1]
    
    return {
        'ticker': ticker,
        'score': ((abs(entry - df['close'].iloc[-2]) / atr) * 100) * regime_score,
        'entry': round(entry, 2),
        'stop_loss': round(entry - (1.5 * atr), 2),
        'take_profit': round(entry + (3.0 * atr), 2)
    }

# ==========================================
# 3. PIPELINE
# ==========================================
def process_symbol(ticker, regime_score):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        return calculate_conviction_score(ticker, df, w_df, regime_score)
    except: return None

if __name__ == "__main__":
    regime = get_market_regime_score()
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda t: process_symbol(t, regime), WATCHLIST))
    
    rankings = pd.DataFrame([r for r in results if r is not None])
    if not rankings.empty:
        rankings = rankings.sort_values(by='score', ascending=False)
        rankings.to_csv('high_conviction_setups.csv', index=False)
        print(rankings.head(20))
