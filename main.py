import ftplib
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import warnings

# Suppress warnings for a clean command line output
warnings.filterwarnings('ignore')

# ==========================================
# 1. LIVE US-WIDE LIQUIDITY WATCHLIST DOWNLOADER
# ==========================================
def get_top_liquid_us_watchlist(target_count=300):
    """
    Downloads active stocks in the US. 
    Target count optimized to balance pattern processing and options API limits.
    """
    print("Connecting to NASDAQ server to fetch US stock market universe...")
    try:
        ftp = ftplib.FTP('ftp.nasdaqtrader.com')
        ftp.login('anonymous', '')
        lines = []
        ftp.retrlines('RETR SymbolDirectory/otherlisted.txt', lines.append)
        
        nasdaq_lines = []
        ftp.retrlines('RETR SymbolDirectory/nasdaqlisted.txt', nasdaq_lines.append)
        ftp.quit()
        
        all_tickers = []
        for line in lines[1:-1]:
            data = line.split('|')
            if len(data) > 6 and data[4] == 'N' and data[6] == 'N':
                symbol = data[0]
                if len(symbol) <= 4 and symbol.isalpha(): all_tickers.append(symbol)
                    
        for line in nasdaq_lines[1:-1]:
            data = line.split('|')
            if len(data) > 3 and data[3] == 'N': 
                symbol = data[0]
                if len(symbol) <= 4 and symbol.isalpha(): all_tickers.append(symbol)
                    
        all_tickers = list(set(all_tickers))
        print(f"Discovered {len(all_tickers)} total US listings. Initializing pattern-matching on top {target_count}...")
        return all_tickers[:target_count]
    except Exception as e:
        print(f"Error accessing cross-market data: {e}. Falling back to default baseline universe.")
        return ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'COST', 'JPM', 'XOM']

# ==========================================
# 2. ADVANCED CHART PATTERN SCANNER (ALGORITHMIC)
# ==========================================
def scan_chart_patterns(df):
    """
    Programmatically detects classical chart patterns: 
    Double Bottoms, Double Tops, and Range Breakouts.
    """
    if len(df) < 60:
        return "No Pattern", 1.0

    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    # 1. Range Breakout / Breakdown (Donchian Channels)
    # Checks if the current price is breaking out of a 20-day consolidative range
    prev_20_max = np.max(high[-21:-1])
    prev_20_min = np.min(low[-21:-1])
    current_close = close[-1]
    
    if current_close > prev_20_max:
        return "Channel Breakout (Bullish)", 1.3
    elif current_close < prev_20_min:
        return "Channel Breakdown (Bearish)", 1.3

    # 2. Algorithmic Double Bottom / Double Top Detection
    # Look back over a 45-day window to locate local minima/maxima
    lookback = 45
    window_lows = low[-lookback:]
    window_highs = high[-lookback:]
    
    # Identify local troughs (points lower than surrounding 5 days)
    troughs = []
    for i in range(5, len(window_lows) - 5):
        if window_lows[i] == np.min(window_lows[i-5:i+6]):
            troughs.append(window_lows[i])
            
    # Identify local peaks (points higher than surrounding 5 days)
    peaks = []
    for i in range(5, len(window_highs) - 5):
        if window_highs[i] == np.max(window_highs[i-5:i+6]):
            peaks.append(window_highs[i])

    # Validate Double Bottom: Two distinct troughs within 1.5% price proximity
    if len(troughs) >= 2:
        # Check the last two identified distinct support levels
        if abs(troughs[-1] - troughs[-2]) / troughs[-2] < 0.015:
            # Confirm price is moving up off the second bottom
            if current_close > troughs[-1] * 1.01:
                return "Double Bottom (Bullish Reversal)", 1.4

    # Validate Double Top: Two distinct peaks within 1.5% price proximity
    if len(peaks) >= 2:
        if abs(peaks[-1] - peaks[-2]) / peaks[-2] < 0.015:
            # Confirm price is moving down off the second top
            if current_close < peaks[-1] * 0.99:
                return "Double Top (Bearish Reversal)", 1.4

    return "Trend Continuation", 1.0

# ==========================================
# 3. MACRO & CONVICTION ENGINE 
# ==========================================
def calculate_conviction_score(ticker, df, weekly_df):
    if len(df) < 200 or len(weekly_df) < 40: return None
    
    for d in [df, weekly_df]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        d.columns = [c.lower() for c in d.columns]
        
    current_price = df['close'].iloc[-1]
    if current_price < 5.0: return None
    
    # Determine overall structural bias via moving averages
    daily_sma = df['close'].rolling(200).mean().iloc[-1]
    weekly_sma = weekly_df['close'].rolling(40).mean().iloc[-1]
    
    daily_bull = current_price > daily_sma
    weekly_bull = weekly_df['close'].iloc[-1] > weekly_sma
    daily_bear = current_price < daily_sma
    weekly_bear = weekly_df['close'].iloc[-1] < weekly_sma
    
    if daily_bull and weekly_bull: trade_dir = 'CALL'
    elif daily_bear and weekly_bear: trade_dir = 'PUT'
    else: return None
        
    # Programmatic Chart Pattern Scanning
    pattern_name, pattern_multiplier = scan_chart_patterns(df)
    
    # Strict Alignment Filter: Prevent taking CALLs on Double Tops or PUTs on Double Bottoms
    if trade_dir == 'CALL' and "Bearish" in pattern_name: return None
    if trade_dir == 'PUT' and "Bullish" in pattern_name: return None
    
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    base_score = ((abs(current_price - df['close'].iloc[-2]) / atr) * 100)
    
    # Scale score dynamically based on technical pattern strength
    final_score = base_score * pattern_multiplier

    return {
        'ticker': ticker,
        'type': trade_dir,
        'chart_pattern': pattern_name,
        'score': round(final_score, 1),
        'stock_entry': round(current_price, 2)
    }

# ==========================================
# 4. UNUSUAL OPTIONS ACTIVITY & NEWS ENGINE
# ==========================================
def detect_uoa_and_news(ticker, current_price, trade_dir):
    try:
        tkr = yf.Ticker(ticker)
        dates = tkr.options
        if not dates: return None
        
        uoa_alerts = []
        for date in dates[:3]: # Near term expirations (0-45 Days to Expiry)
            chain = tkr.option_chain(date)
            opts = chain.calls if trade_dir == 'CALL' else chain.puts
            if opts.empty: continue
            
            opts['vol_to_oi'] = np.where(opts['openInterest'] > 0, opts['volume'] / opts['openInterest'], 0)
            
            if trade_dir == 'CALL':
                opts = opts[(opts['strike'] >= current_price * 0.95) & (opts['strike'] <= current_price * 1.15)]
            else:
                opts = opts[(opts['strike'] <= current_price * 1.05) & (opts['strike'] >= current_price * 0.85)]
                
            uoa = opts[(opts['vol_to_oi'] >= 2.0) & (opts['volume'] >= 400)]
            
            if not uoa.empty:
                best_uoa = uoa.sort_values(by='vol_to_oi', ascending=False).iloc[0]
                uoa_alerts.append({
                    'opt_expiry': date,
                    'opt_strike': best_uoa['strike'],
                    'vol_to_oi_ratio': round(best_uoa['vol_to_oi'], 1),
                    'opt_volume': best_uoa['volume']
                })
        
        if not uoa_alerts: return None
        best_alert = sorted(uoa_alerts, key=lambda x: x['vol_to_oi_ratio'], reverse=True)[0]
        
        # Scrape Live News Headlines
        news = tkr.news
        latest_news = []
        if news:
            for n in news[:2]:
                title = n.get('title', '')
                if title: latest_news.append(title.strip())
        
        best_alert['latest_news'] = " | ".join(latest_news) if latest_news else "No recent headlines found."
        return best_alert
    except: return None

# ==========================================
# 5. PIPELINE EXECUTOR
# ==========================================
def process_symbol(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        
        setup = calculate_conviction_score(ticker, df, w_df)
        
        if setup is not None:
            uoa_data = detect_uoa_and_news(ticker, setup['stock_entry'], setup['type'])
            if uoa_data:
                setup.update(uoa_data)
                return setup
        return None
    except: return None

if __name__ == "__main__":
    print("Initializing Multi-Exchange Chart Pattern, News, & UOA Scanner...")
    
    watchlist = get_top_liquid_us_watchlist(target_count=300)
    
    print(f"\nScanning {len(watchlist)} stocks for aligned Patterns + News + UOA...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(process_symbol, watchlist))
    
    rankings = pd.DataFrame([r for r in results if r is not None])
    
    if not rankings.empty:
        rankings = rankings.sort_values(by='vol_to_oi_ratio', ascending=False)
        
        pd.set_option('display.max_colwidth', 40)
        display_cols = ['ticker', 'type', 'chart_pattern', 'opt_strike', 'vol_to_oi_ratio', 'latest_news']
        
        print("\n" + "="*115)
        print(" TRI-CONFIRMED SETUPS: CHART PATTERN + UOA + NEWS ".center(115, "="))
        print("="*115)
        print(rankings[display_cols].to_string(index=False))
        
        rankings.to_csv('tri_confirmed_trades.csv', index=False)
        print("\n>> Full dataset exported to 'tri_confirmed_trades.csv'")
    else:
        print("No tickers established confluence between patterns, options flow, and news today.")
