import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. MARKET REGIME FILTER
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

# ==========================================
# 2. PROFESSIONAL SCORING ENGINE
# ==========================================
def calculate_professional_score(df, weekly_df, regime_score):
    if len(df) < 200 or len(weekly_df) < 40: return None
    
    # Clean Columns
    for d in [df, weekly_df]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        d.columns = [c.lower() for c in d.columns]
        
    vol_avg = df['volume'].rolling(20).mean()
    volume_surge = df['volume'].iloc[-1] > (vol_avg.iloc[-1] * 1.5)
    
    daily_trend = df['close'].iloc[-1] > df['close'].rolling(200).mean().iloc[-1]
    weekly_trend = weekly_df['close'].iloc[-1] > weekly_df['close'].rolling(40).mean().iloc[-1]
    
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    price_move = abs(df['close'].iloc[-1] - df['close'].iloc[-2])
    vol_score = (price_move / atr) * 10
    
    rsi = 100 - (100 / (1 + (df['close'].diff().clip(lower=0).rolling(14).mean() / 
                      df['close'].diff().clip(upper=0).abs().rolling(14).mean())))
    
    mom_score = 40 if (daily_trend and volume_surge and (daily_trend == weekly_trend)) else 0
    rev_score = 30 if (rsi.iloc[-1] < 30) else 0
    
    return (mom_score + rev_score + vol_score) * regime_score

def process_symbol(ticker, regime_score):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        score = calculate_professional_score(df, w_df, regime_score)
        return {'ticker': ticker, 'score': score} if score is not None else None
    except: return None

# ==========================================
# 3. EXECUTION
# ==========================================
def generate_signals(ticker_list):
    regime = get_market_regime_score()
    print(f"Market Regime Score: {regime:.2f}")
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda t: process_symbol(t, regime), ticker_list))
    return pd.DataFrame([r for r in results if r is not None]).sort_values(by='score', ascending=False)

if __name__ == "__main__":
    # You will paste the 500 stocks list here
    my_watchlist = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'AMZN', 'META', 'TSLA'] 
    rankings = generate_signals(my_watchlist)
    print(rankings.head(20))
