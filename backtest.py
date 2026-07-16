import collections
import collections.abc
# Hotfix for Backtrader in modern Python versions (used by GitHub Actions)
collections.Iterable = collections.abc.Iterable

import backtrader as bt
import yfinance as yf

class SmaCross(bt.Strategy):
    # Default parameters (These are overridden dynamically in the loop below)
    params = dict(
        fast_period=10,
        slow_period=30
    )

    def __init__(self):
        sma_fast = bt.ind.SMA(period=self.p.fast_period)
        sma_slow = bt.ind.SMA(period=self.p.slow_period)
        self.crossover = bt.ind.CrossOver(sma_fast, sma_slow)

    def next(self):
        if not self.position:
            if self.crossover > 0:  # Buy signal
                self.buy()
        elif self.crossover < 0:    # Sell signal
            self.close()

def run_multi_backtest(ticker):
    print(f"\n{'='*65}")
    print(f"🚀 STOCK: {ticker}")
    print(f"{'='*65}")
    
    # 1. Fetch data ONCE per stock to avoid rate limits from Yahoo Finance
    stock = yf.Ticker(ticker)
    df = stock.history(start='2022-01-01', end='2024-01-01')
    
    if df.empty:
        print(f"⚠️ Failed to fetch data for {ticker}. Skipping.")
        return

    # Remove timezone data to prevent Backtrader errors
    df.index = df.index.tz_localize(None)

    # 2. Define 10 Different Strategy Combinations (Fast SMA, Slow SMA)
    strategies = [
        (5, 20),   # 1. Very Fast
        (10, 30),  # 2. Standard Short-term
        (10, 50),  # 3. Short-to-Medium
        (15, 50),  # 4. Slightly slower short-to-medium
        (20, 50),  # 5. Medium-term
        (20, 100), # 6. Medium-to-Long
        (30, 100), # 7. Slower Medium-to-Long
        (50, 100), # 8. Standard Long-term
        (50, 200), # 9. The "Golden Cross" (Classic)
        (100, 200) # 10. Very Slow, Long-term
    ]

    initial_cash = 10000.0
    print(f"Starting Portfolio Value: ${initial_cash:,.2f}\n")
    print(f"{'Strat':<7} | {'Fast':<4} | {'Slow':<4} | {'Final Value':<13} | {'Net P/L':<10}")
    print("-" * 65)

    # 3. Loop through all 10 combinations
    for i, (fast, slow) in enumerate(strategies, 1):
        cerebro = bt.Cerebro()
        
        # Inject the custom parameters into the strategy
        cerebro.addstrategy(SmaCross, fast_period=fast, slow_period=slow)

        # Feed the downloaded data into Backtrader
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)

        # Set up broker conditions
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.001) 
        
        # Run the backtest
        cerebro.run()
        
        # Calculate results
        final_cash = cerebro.broker.getvalue()
        profit = final_cash - initial_cash
        
        # Format profit string to show + or - clearly
        profit_str = f"+${profit:,.2f}" if profit >= 0 else f"-${abs(profit):,.2f}"
        
        # Print the row for this specific strategy
        print(f"#{i:<5} | {fast:<4} | {slow:<4} | ${final_cash:<12,.2f} | {profit_str}")

if __name__ == '__main__':
    tickers = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK-B', 'TSLA', 'AVGO', 'JPM',
    'V', 'UNH', 'JNJ', 'PG', 'MA', 'HD', 'CVX', 'MRK', 'ABBV', 'KO', 'PEP', 'XOM',
    'ADBE', 'COST', 'WMT', 'BAC', 'CRM', 'AMD', 'NFLX', 'CSCO', 'TMO', 'DHR', 'INTC',
    'CMCSA', 'DIS', 'ABT', 'PFE', 'VZ', 'WFC', 'ORCL', 'LIN', 'UPS', 'INTU', 'MCD',
    'QCOM', 'CAT', 'GE', 'BA', 'RTX', 'TXN', 'AMGN', 'HON', 'GS', 'IBM', 'PLD',
    'AMAT', 'UNP', 'LOW', 'DE', 'NEE', 'AXP', 'ISRG', 'BKNG', 'SPGI', 'BLK', 'MDLZ',
    'SYK', 'GILD', 'ADP', 'CB', 'MMC', 'LRCX', 'ADI', 'CI', 'BDX', 'REGN', 'C', 'EL',
    'MU', 'CSX', 'FISV', 'SNPS', 'KLAC', 'PNC', 'ZTS', 'ITW', 'EOG', 'MCK', 'AON',
    'SHW', 'PH', 'CNC', 'WM', 'MS', 'USB', 'ETN', 'FDX', 'APD', 'NSC', 'CDNS', 'MMM',
    'CL', 'GD', 'SNY', 'TGT', 'SO', 'BSX', 'PGR', 'CME', 'DUK', 'CBRE', 'PYPL', 'ADSK',
    'MDT', 'MRVL', 'TEAM', 'KHC', 'DXCM', 'BIIB', 'CTAS', 'IT', 'HCA', 'HUM', 'IDXX',
    'ECL', 'FTNT', 'ROK', 'AFL', 'WEC', 'FCX', 'O', 'PAYX', 'D', 'NXPI', 'CPT', 'VRSK',
    'AJG', 'CTSH', 'MNST', 'EXC', 'YUM', 'MTD', 'CARR', 'PPL', 'PHM', 'AMP', 'FAST',
    'TEL', 'ANSS', 'MSI', 'PPG', 'KMB', 'GLW', 'WBA', 'GWW', 'SWK', 'WST', 'DHI',
    'JCI', 'BKR', 'LEN', 'HLT', 'CMI', 'ZBH', 'NVR', 'TDG', 'ED', 'PCAR', 'TSN',
    'STZ', 'IFF', 'MCHP', 'PSX', 'ROST', 'FITB', 'AEE', 'RMD', 'VMC', 'XYL', 'HPQ',
    'SRE', 'FE', 'AEP', 'CINF', 'NTRS', 'EXPD', 'KEYS', 'MTB', 'DFS', 'HIG', 'HBAN',
    'KEY', 'CF', 'WRB', 'DOV', 'CHD', 'SJM', 'TT', 'SYY', 'QRVO', 'KMI', 'DAL',
    'LUV', 'UAL', 'KSU', 'WDC', 'STT', 'BBY', 'JBHT', 'LEG', 'POOL', 'TER', 'DXC']
    for t in tickers:
        run_multi_backtest(t)
