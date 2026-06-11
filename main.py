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
def get_top_liquid_us_watchlist(target_count=1000):
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
# 2. ADVANCED CHART PATTERN SCANNER
# ==========================================
def scan_chart_patterns(df):
    if len(df) < 60:
        return "No Pattern", 1.0

    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    prev_20_max = np.max(high[-21:-1])
    prev_20_min = np.min(low[-21:-1])
    current_close = close[-1]
    
    if current_close > prev_20_max: return "Channel Breakout", 1.3
    elif current_close < prev_20_min: return "Channel Breakdown", 1.3

    lookback = 45
    window_lows = low[-lookback:]
    window_highs = high[-lookback:]
    
    troughs = []
    for i in range(5, len(window_lows) - 5):
        if window_lows[i] == np.min(window_lows[i-5:i+6]): troughs.append(window_lows[i])
            
    peaks = []
    for i in range(5, len(window_highs) - 5):
        if window_highs[i] == np.max(window_highs[i-5:i+6]): peaks.append(window_highs[i])

    if len(troughs) >= 2:
        if abs(troughs[-1] - troughs[-2]) / troughs[-2] < 0.015:
            if current_close > troughs[-1] * 1.01:
                return "Double Bottom", 1.4

    if len(peaks) >= 2:
        if abs(peaks[-1] - peaks[-2]) / peaks[-2] < 0.015:
            if current_close < peaks[-1] * 0.99:
                return "Double Top", 1.4

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
    
    daily_sma = df['close'].rolling(200).mean().iloc[-1]
    weekly_sma = weekly_df['close'].rolling(40).mean().iloc[-1]
    
    daily_bull = current_price > daily_sma
    weekly_bull = weekly_df['close'].iloc[-1] > weekly_sma
    daily_bear = current_price < daily_sma
    weekly_bear = weekly_df['close'].iloc[-1] < weekly_sma
    
    if daily_bull and weekly_bull: trade_dir = 'CALL'
    elif daily_bear and weekly_bear: trade_dir = 'PUT'
    else: return None
        
    pattern_name, pattern_multiplier = scan_chart_patterns(df)
    
    if trade_dir == 'CALL' and "Breakdown" in pattern_name: return None
    if trade_dir == 'PUT' and "Breakout" in pattern_name: return None
    if trade_dir == 'CALL' and "Top" in pattern_name: return None
    if trade_dir == 'PUT' and "Bottom" in pattern_name: return None

    return {
        'ticker': ticker,
        'type': trade_dir,
        'chart_pattern': pattern_name,
        'stock_entry': round(current_price, 2)
    }

# ==========================================
# 4. UNUSUAL OPTIONS ACTIVITY ENGINE
# ==========================================
def detect_uoa(ticker, current_price, trade_dir):
    try:
        tkr = yf.Ticker(ticker)
        dates = tkr.options
        if not dates: return None
        
        uoa_alerts = []
        for date in dates[:3]:
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
        
        return best_alert
    except: return None

# ==========================================
# 5. PIPELINE EXECUTOR & SCORING COMPILER
# ==========================================
def process_symbol(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        
        setup = calculate_conviction_score(ticker, df, w_df)
        
        if setup is not None:
            uoa_data = detect_uoa(ticker, setup['stock_entry'], setup['type'])
            if uoa_data:
                setup.update(uoa_data)
                
                # Calculate 1-100 Confidence Score (Recalibrated for No News)
                confidence = 0
                
                # 1. Technicals (Max 50 pts)
                if "Double" in setup['chart_pattern']: confidence += 50
                elif "Channel" in setup['chart_pattern']: confidence += 35
                else: confidence += 20
                
                # 2. Options Flow (Max 50 pts - caps at 10x Vol/OI ratio)
                flow_score = min(50, (setup['vol_to_oi_ratio'] * 5))
                confidence += flow_score
                
                # Ensure bounded between 1 and 100
                setup['confidence_1_100'] = int(min(100, max(1, confidence)))
                
                return setup
        return None
    except: return None

if __name__ == "__main__":
    print("Initializing Multi-Exchange Chart Pattern & UOA Scanner...")
    
    watchlist = get_top_liquid_us_watchlist(target_count=1000)
    
    print(f"\nScanning {len(watchlist)} stocks for aligned Patterns + UOA...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(process_symbol, watchlist))
    
    rankings = pd.DataFrame([r for r in results if r is not None])
    
    if not rankings.empty:
        # Sort by the new 1-100 confidence score
        rankings = rankings.sort_values(by='confidence_1_100', ascending=False)
        
        pd.set_option('display.max_colwidth', 35)
        display_cols = [
            'ticker', 'type', 'confidence_1_100', 'chart_pattern', 
            'opt_strike', 'opt_expiry', 'vol_to_oi_ratio'
        ]
        
        print("\n" + "="*100)
        print(" HIGH CONVICTION SETUPS (SCORED 1-100) ".center(100, "="))
        print("="*100)
        print(rankings[display_cols].to_string(index=False))
        
        rankings.to_csv('scored_confirmed_trades.csv', index=False)
        print("\n>> Full dataset exported to 'scored_confirmed_trades.csv'")
    else:
        print("No tickers established confluence between patterns and options flow today.")
