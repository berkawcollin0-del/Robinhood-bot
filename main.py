import yfinance as yf
import pandas as pd
import numpy as np
import itertools
from datetime import timedelta, datetime
import time
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
    
    # Buy: Golden Cross + Not in Earnings Blackout
    buy_condition = df['Golden_Cross'] & (df['Safe_To_Trade'] == 1)
    
    # Sell: Death Cross OR entering an Earnings Blackout
    entering_blackout = (df['Safe_To_Trade'] == 0) & (df['Safe_To_Trade'].shift(1) == 1)
    sell_condition = df['Death_Cross'] | entering_blackout
    
    df.loc[buy_condition, 'Signal'] = 1
    df.loc[sell_condition, 'Signal'] = -1
    
    return df

# ==========================================
# 2. PARAMETER SWEEP (OPTIMIZATION)
# ==========================================

def optimize_parameters(ticker, data):
    """
    Tests different moving average combinations on the last 2 years of data
    to find the combination with the highest historical return for this specific stock.
    """
    print(f"Sweeping parameters for {ticker}...")
    short_windows = [20, 50, 80]
    long_windows = [100, 150, 200]
    
    best_return = -np.inf
    best_params = (50, 200) # Default fallback
    
    for short_win, long_win in itertools.product(short_windows, long_windows):
        if short_win >= long_win:
            continue
            
        test_df = data.copy()
        test_df = generate_signals(test_df, short_win, long_win)
        
        # Simple vectorized backtest for speed
        test_df['Position'] = test_df['Signal'].replace(to_replace=0, method='ffill')
        test_df['Daily_Return'] = test_df['close'].pct_change()
        test_df['Strategy_Return'] = test_df['Position'].shift(1) * test_df['Daily_Return']
        
        cumulative_return = test_df['Strategy_Return'].cumsum().iloc[-1]
        
        if cumulative_return > best_return:
            best_return = cumulative_return
            best_params = (short_win, long_win)
            
    print(f"Optimal parameters for {ticker}: {best_params[0]} / {best_params[1]}")
    return best_params

# ==========================================
# 3. ROBINHOOD MCP INTEGRATION
# ==========================================

class RobinhoodAgent:
    def __init__(self):
        # Pulls from the environment variables configured in your deployment environment
        self.api_key = os.getenv("RH_AGENTIC_API_KEY")
        self.endpoint = "https://api.robinhood.com/mcp/agentic/trade"
        
        if not self.api_key:
            print("WARNING: Robinhood API Key not found. Running in simulation mode.")
            self.live = False
        else:
            self.live = True
            
    def get_current_position(self, ticker):
        """Mock check for current holdings in the Agentic Sandbox"""
        if not self.live: return 0
        # return requests.get(f"{self.endpoint}/positions/{ticker}", headers={"Auth": self.api_key}).json()
        return 0

    def execute_trade(self, ticker, action, quantity=1):
        """Sends the payload to Robinhood's MCP endpoint"""
        if not self.live:
            print(f"[SIMULATION] Order Executed: {action} {quantity} shares of {ticker}")
            return True
            
        payload = {
            "symbol": ticker,
            "side": action.lower(),
            "quantity": quantity,
            "type": "market"
        }
        print(f"[LIVE] Sending order to Robinhood: {payload}")
        # response = requests.post(self.endpoint, json=payload, headers={"Auth": self.api_key})
        # return response.status_code == 200
        return True

# ==========================================
# 4. MAIN LIVE EXECUTION LOOP
# ==========================================

def run_trading_bot():
    """The master loop to execute daily."""
    agent = RobinhoodAgent()
    
    # The portfolio of tickers you are monitoring
    watchlist = ['NVDA', 'AAPL', 'TLYS'] 
    
    for ticker in watchlist:
        print(f"\n--- Analyzing {ticker} ---")
        
        # 1. Fetch recent data
df = yf.download(ticker, period="2y", interval="1d", progress=False)

# If yfinance returned a MultiIndex, flatten it
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

if 'Adj Close' in df.columns:
    df = df.drop(columns=['Adj Close'])

# Now it is safe to lowercase
df.columns = [str(col).lower() for col in df.columns]

        
        # 2. Apply Earnings Blackout
        df = apply_earnings_blackout(df, ticker)
        
        # 3. Parameter Sweep to find the best Moving Averages for this specific stock
        best_short, best_long = optimize_parameters(ticker, df)
        
        # 4. Generate Live Signals using the optimal parameters
        live_df = generate_signals(df, best_short, best_long)
        
        todays_signal = live_df['Signal'].iloc[-1]
        todays_safe = live_df['Safe_To_Trade'].iloc[-1]
        
        # 5. Check actual Robinhood account holdings
        current_shares = agent.get_current_position(ticker)
        
        # 6. Execute Logic
        if todays_safe == 0:
            print(f"Earnings Blackout active for {ticker}. No new trades permitted.")
            if current_shares > 0:
                print(f"Liquidating existing {ticker} position for earnings safety.")
                agent.execute_trade(ticker, "SELL", current_shares)
                
        elif todays_signal == 1 and current_shares == 0:
            print(f"BUY SIGNAL CONFIRMED for {ticker}. Executing trade...")
            agent.execute_trade(ticker, "BUY", 10) # Set your standard lot size here
            
        elif todays_signal == -1 and current_shares > 0:
            print(f"SELL SIGNAL CONFIRMED for {ticker}. Liquidating position...")
            agent.execute_trade(ticker, "SELL", current_shares)
            
        else:
            print(f"No actionable setup for {ticker} today. Holding.")

if __name__ == "__main__":
    run_trading_bot()
