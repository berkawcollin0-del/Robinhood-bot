import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import warnings

# Suppress yfinance warnings for clean terminal output
warnings.filterwarnings('ignore')

# Note: Ensure you have your tickers.py file with a WATCHLIST list variable in the same directory.
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
# 2. BI-DIRECTIONAL CONVICTION ENGINE
# ==========================================
def calculate_conviction_score(ticker, df, weekly_df, regime_score):
    if len(df) < 200 or len(weekly_df) < 40 or is_earnings_near(ticker): return None
    
    for d in [df, weekly_df]:
        if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
        d.columns = [c.lower() for c in d.columns]
        
    current_price = df['close'].iloc[-1]
    
    daily_sma = df['close'].rolling(200).mean().iloc[-1]
    weekly_sma = weekly_df['close'].rolling(40).mean().iloc[-1]
    
    daily_bull = current_price > daily_sma
    weekly_bull = weekly_df['close'].iloc[-1] > weekly_sma
    daily_bear = current_price < daily_sma
    weekly_bear = weekly_df['close'].iloc[-1] < weekly_sma
    
    # Identify Macro Trend
    if daily_bull and weekly_bull: trade_dir = 'CALL'
    elif daily_bear and weekly_bear: trade_dir = 'PUT'
    else: return None
        
    vol_avg = df['volume'].rolling(20).mean().iloc[-1]
    if df['volume'].iloc[-1] <= (vol_avg * 1.5): return None
    
    atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]
    base_score = ((abs(current_price - df['close'].iloc[-2]) / atr) * 100)
    
    # Setup Logic depending on Trend
    if trade_dir == 'CALL':
        res_level = df['high'].rolling(20).max().iloc[-2]
        if (current_price / res_level) > 1.05: return None
        is_retesting = abs(current_price - res_level) / res_level < 0.01
        pattern = "Confirmed Retest" if is_retesting else "Breakout"
        stop_loss = current_price - (1.5 * atr)
        take_profit = current_price + (3.0 * atr)
    else: 
        sup_level = df['low'].rolling(20).min().iloc[-2]
        if (sup_level / current_price) > 1.05: return None
        is_retesting = abs(current_price - sup_level) / sup_level < 0.01
        pattern = "Confirmed Retest" if is_retesting else "Breakdown"
        stop_loss = current_price + (1.5 * atr)
        take_profit = current_price - (3.0 * atr)

    final_score = (base_score * 1.5) if is_retesting else base_score
    exit_rule = f"SELL IF Stock Hits ${take_profit:.2f} (TP) or ${stop_loss:.2f} (SL)"
    
    return {
        'ticker': ticker,
        'type': trade_dir,
        'pattern': pattern,
        'score': round(final_score * regime_score, 1),
        'stock_entry': round(current_price, 2),
        'exit_plan': exit_rule
    }

# ==========================================
# 3. OPTIONS LIQUIDITY ENGINE
# ==========================================
def get_optimal_option(ticker, current_price, trade_dir):
    try:
        tkr = yf.Ticker(ticker)
        dates = tkr.options
        if not dates: return None
        
        target_date = datetime.now() + timedelta(days=35)
        best_date = min(dates, key=lambda d: abs((datetime.strptime(d, '%Y-%m-%d') - target_date).days))
        
        chain = tkr.option_chain(best_date)
        opts = chain.calls if trade_dir == 'CALL' else chain.puts
        
        if trade_dir == 'CALL':
            valid = opts[(opts['strike'] >= current_price) & (opts['strike'] <= current_price * 1.10)].copy()
            if valid.empty: valid = opts[opts['strike'] >= current_price].copy()
        else:
            valid = opts[(opts['strike'] <= current_price) & (opts['strike'] >= current_price * 0.90)].copy()
            if valid.empty: valid = opts[opts['strike'] <= current_price].copy()
            
        if valid.empty: return None
        
        valid['dist'] = abs(valid['strike'] - current_price)
        valid = valid.sort_values(by='dist')
        best_opt = valid.iloc[0]
        
        if best_opt['openInterest'] < 100:
            best_opt = valid.loc[valid['openInterest'].idxmax()]
            if best_opt['openInterest'] < 100: return None
            
        return {
            'opt_expiry': best_date,
            'opt_strike': best_opt['strike'],
            'opt_premium': round(best_opt['lastPrice'], 2),
            'opt_iv_pct': round(best_opt['impliedVolatility'] * 100, 1),
            'opt_oi': best_opt['openInterest']
        }
    except: return None

# ==========================================
# 4. PIPELINE
# ==========================================
def process_symbol(ticker, regime_score):
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False)
        w_df = yf.download(ticker, period="2y", interval="1wk", progress=False)
        
        setup = calculate_conviction_score(ticker, df, w_df, regime_score)
        
        if setup is not None:
            opt_data = get_optimal_option(ticker, setup['stock_entry'], setup['type'])
            if opt_data:
                setup.update(opt_data)
                return setup
        return None
    except: return None

if __name__ == "__main__":
    print("Initializing Bi-Directional Options Scanner...")
    regime = get_market_regime_score()
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(lambda t: process_symbol(t, regime), WATCHLIST))
    
    rankings = pd.DataFrame([r for r in results if r is not None])
    if not rankings.empty:
        # Sort from Best (Highest Score) to Worst
        rankings = rankings.sort_values(by='score', ascending=False)
        
        # Format the DataFrame for clean printing
        display_cols = ['ticker', 'score', 'type', 'pattern', 'opt_strike', 'opt_expiry', 'opt_premium', 'exit_plan']
        
        print("\n" + "="*95)
        print(" TOP CONVICTION OPTIONS SETUPS ".center(95, "="))
        print("="*95)
        print(rankings[display_cols].to_string(index=False))
        
        # Save full data to CSV for your records
        rankings.to_csv('high_conviction_options.csv', index=False)
        print("\n>> Full scan data saved to 'high_conviction_options.csv'")
    else:
        print("No valid options setups passed the strict liquidity and volume gates today.")
