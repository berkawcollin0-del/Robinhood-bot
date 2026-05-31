import yfinance as yf
import pandas as pd
import numpy as np
from concurrent.futures import ThreadPoolExecutor

# ==========================================
# 1. MARKET REGIME FILTER (MACRO)
# ==========================================
def get_market_regime_score():
    """Calculates % of sample index trading above 200 SMA."""
    sp500_sample = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'JPM', 'V', 'JNJ', 'WMT', 'PG']
    above_200 = 0
    for ticker in sp500_sample:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        if not df.empty and df['Close'].iloc[-1] > df['Close'].rolling(200).mean().iloc[-1]:
            above_200 += 1
    return above_200 / len(sp500_sample)

# ==========================================
# 2. PROFESSIONAL SCORING ENGINE
# ==========================================
def calculate_professional_score(ticker, df, weekly_df, regime_score):
    """Multi-factor institutional signal generator."""
    if len(df) < 200 or len(weekly_df) < 40: return None
    
    # Volume Confirmation
    vol_avg = df['Volume'].rolling(20).mean()
    volume_surge = df['Volume'].iloc[-1] > (vol_avg.iloc[-1] * 1.5)
    
    # Confluence (Daily vs Weekly trend)
    daily_trend = df['Close'].iloc[-1] > df['Close'].rolling(200).mean().iloc[-1]
    weekly_trend = weekly_df['Close'].iloc[-1] > weekly_df['Close'].rolling(40).mean().iloc[-1]
    confluence = (daily_trend == weekly_trend)
    
    # ATR Volatility Score
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    price_move = abs(df['Close'].iloc[-1] - df['Close'].iloc[-2])
    vol_score = (price_move / atr) * 10
    
    # RSI for Mean Reversion
    delta = df['Close'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = delta.clip(upper=0).abs().rolling(14).mean()
    rsi = 100 - (100 / (1 + (gain / loss)))
    
    # Scores
    mom_score = 40 if (daily_trend and volume_surge and confluence) else 0
    rev_score = 30 if (rsi.iloc[-1] < 30) else 0
    
    return (mom_score + rev_score + vol_score) * regime_score

# ==========================================
# 3. PARALLELIZED PIPELINE
# ==========================================
def process_symbol(ticker, regime_score):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        score = calculate_professional_score(ticker, df, w_df, regime_score)
        return {'ticker': ticker, 'score': score} if score else None
    except: return None

def generate_signals(ticker_list):
    regime = get_market_regime_score()
    print(f"Market Regime Score: {regime:.2f}")
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda t: process_symbol(t, regime), ticker_list))
    
    df_rankings = pd.DataFrame([r for r in results if r is not None])
    return df_rankings.sort_values(by='score', ascending=False)

# ==========================================
# 4. EXECUTION
# ==========================================
if __name__ == "__main__":
    # Add your list of 1000 tickers here
    my_watchlist = ['AAPL', 'MSFT', 'NVDA', 'AMD', 'GOOGL', 'AMZN', 'META', 'TSLA'] 
    
    rankings = generate_signals(my_watchlist)
    print("\n--- TOP 10 SWING SETUPS ---")
    print(rankings.head(10))
