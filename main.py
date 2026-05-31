import yfinance as yf
import pandas as pd
import numpy as np
import itertools
from datetime import timedelta
import os

# ==========================================
# 1. CORE LOGIC & EARNINGS SAFETY
# ==========================================

def apply_earnings_blackout(df, ticker_symbol, buffer_days=3):
    """Blocks trading immediately before and after earnings calls."""
    tkr = yf.Ticker(ticker_symbol)
    earnings_data = tkr.get_earnings_dates(limit=10)
    df['Safe_To_Trade'] = 1 
    
    if earnings_data is not None:
        earnings_dates = pd.to_datetime(earnings_data.index).tz_localize(None).date
        blackout_dates = set()
        for e_date in earnings_dates:
            for i in range(-buffer_days, buffer_days + 1):
                blackout_dates.add(e_date + timedelta(days=i))
                
        df['Safe_To_Trade'] = [
            0 if pd.to_datetime(idx).tz_localize(None).date() in blackout_dates else 1 
            for idx in df.index
        ]
    return df

def generate_signals(df, short_window, long_window):
    """Calculates signals based on dynamic moving average windows."""
    df[f'SMA_{short_window}'] = df['close'].rolling(window=short_window).mean()
    df[f'SMA_{long_window}'] = df['close'].rolling(window=long_window).mean()
    
    df['Golden_Cross'] = (df[f'SMA_{short_window}'] > df[f'SMA_{long_window}']) & \
                         (df[f'SMA_{short_window}'].shift(1) <= df[f'SMA_{long_window}'].shift(1))
    
    df['Death_Cross'] = (df[f'SMA_{short_window}'] < df[f'SMA_{long_window}']) & \
                        (df[f'SMA_{short_window}'].shift(1) >= df[f'SMA_{long_window}'].shift(1))
    
    df['Signal'] = 0
    
    buy_condition = df['Golden_Cross'] & (df['Safe_To_Trade'] == 1)
    entering_blackout = (df['Safe_To_Trade'] == 0) & (df['Safe_To_Trade'].shift(1) == 1)
    sell_condition = df['Death_Cross'] | entering_blackout
    
    df.loc[buy_condition, 'Signal'] = 1
    df.loc[sell_condition, 'Signal'] = -1
    
    return df

# ==========================================
# 2. PARAMETER SWEEP
# ==========================================

def optimize_parameters(ticker, data):
    """Finds optimal MA combination."""
    short_windows = [20, 50, 80]
    long_windows = [100, 150, 200]
    
    best_return = -np.inf
    best_params = (50, 200)
    
    for short_win, long_win in itertools.product(short_windows, long_windows):
        if short_win >= long_win:
            continue
            
        test_df = data.copy()
        test_df = generate_signals(test_df, short_win, long_win)
        
        # MODERN PANDAS OPTIMIZATION
        test_df['Position'] = test_df['Signal'].replace(0, np.nan).ffill().fillna(0)
        test_df['Daily_Return'] = test_df['close'].pct_change()
        test_df['Strategy_Return'] = test_df['Position'].shift(1) * test_df['Daily_Return']
        
        cumulative_return = test_df['Strategy_Return'].cumsum().iloc[-1]
        
        if cumulative_return > best_return:
            best_return = cumulative_return
            best_params = (short_win, long_win)
            
    print(f"Optimal parameters for {ticker}: {best_params}")
    return best_params

# ==========================================
# 3. ROBINHOOD AGENT
# ==========================================

class RobinhoodAgent:
    def __init__(self):
        self.api_key = os.getenv("RH_AGENTIC_API_KEY")
        if not self.api_key:
            print("WARNING: Robinhood API Key not found. Running in simulation mode.")
            self.live = False
        else:
            self.live = True
            
    def get_current_position(self, ticker):
        return 0

    def execute_trade(self, ticker, action, quantity=1):
        print(f"[{'LIVE' if self.live else 'SIMULATION'}] Executed: {action} {quantity} shares of {ticker}")
        return True

# ==========================================
# 4. MAIN EXECUTION LOOP
# ==========================================

def run_trading_bot():
    agent = RobinhoodAgent()
    watchlist = ['NVDA', 'AAPL', 'TLYS'] 
    
    for ticker in watchlist:
        print
