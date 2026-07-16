import collections
import collections.abc
# Hotfix for Backtrader compatibility with modern Python versions
collections.Iterable = collections.abc.Iterable

import backtrader as bt
import yfinance as yf
import pandas as pd

# ==========================================
# 1. DEFINE THE DISTINCT STRATEGY ARCHETYPES
# ==========================================

class EmaCross(bt.Strategy):
    params = dict(fast=9, slow=21)
    def __init__(self):
        fast_ema = bt.ind.EMA(period=self.p.fast)
        slow_ema = bt.ind.EMA(period=self.p.slow)
        self.crossover = bt.ind.CrossOver(fast_ema, slow_ema)
    def next(self):
        if not self.position and self.crossover > 0: self.buy()
        elif self.position and self.crossover < 0: self.close()

class RsiReversion(bt.Strategy):
    params = dict(period=14, low=30, high=70)
    def __init__(self):
        self.rsi = bt.ind.RSI(period=self.p.period)
    def next(self):
        if not self.position and self.rsi < self.p.low: self.buy()
        elif self.position and self.rsi > self.p.high: self.close()

class MacdMomentum(bt.Strategy):
    params = dict(f=12, s=26, sig=9)
    def __init__(self):
        self.macd = bt.ind.MACD(period_me1=self.p.f, period_me2=self.p.s, period_ds=self.p.sig)
        self.crossover = bt.ind.CrossOver(self.macd.macd, self.macd.signal)
    def next(self):
        if not self.position and self.crossover > 0: self.buy()
        elif self.position and self.crossover < 0: self.close()

class BollingerBands(bt.Strategy):
    params = dict(period=20, dev=2)
    def __init__(self):
        self.bb = bt.ind.BollingerBands(period=self.p.period, devfactor=self.p.dev)
    def next(self):
        if not self.position and self.data.close[0] < self.bb.lines.bot[0]: self.buy()
        elif self.position and self.data.close[0] > self.bb.lines.top[0]: self.close()

class DonchianBreakout(bt.Strategy):
    params = dict(period=20)
    def __init__(self):
        self.highest = bt.ind.Highest(self.data.high, period=self.p.period)
        self.lowest = bt.ind.Lowest(self.data.low, period=self.p.period)
    def next(self):
        # Buy if we break above the previous X-day high
        if not self.position and self.data.close[0] >= self.highest[-1]: self.buy()
        # Exit if we drop below the previous X-day low
        elif self.position and self.data.close[0] <= self.lowest[-1]: self.close()

# ==========================================
# 2. RUN ENGINE AND CONFIGURATION
# ==========================================

def run_multi_backtest(ticker):
    print(f"\n{'='*75}")
    print(f"🚀 STOCK MARKET ENGINE: {ticker}")
    print(f"{'='*75}")
    
    # Download clean historical chunk
    stock = yf.Ticker(ticker)
    df = stock.history(start='2024-01-01', end='2026-01-01')
    
    if df.empty:
        print(f"⚠️ Failed to fetch data for {ticker}. Skipping.")
        return
    
    df.index = df.index.tz_localize(None)
    initial_cash = 10000.0

    # Calculate exact Buy and Hold metric
    start_price = df['Close'].iloc[0]
    end_price = df['Close'].iloc[-1]
    bh_shares = initial_cash / start_price
    bh_final = bh_shares * end_price
    bh_profit = bh_final - initial_cash

    # FIXED: The line break in the format specifier has been removed
    print(f"🏆 BENCHMARK -> Buy & Hold Final Value: ${bh_final:,.2f} ({bh_profit:+,.2f} Profit)")
    print("-" * 75)
    print(f"{'ID':<3} | {'Strategy Setup Name':<30} | {'Final Value':<14} | {'Net P/L':<12}")
    print("-" * 75)

    # Dictionary configuration for our 10 distinct variations
    strategy_pool = [
        {"class": EmaCross, "kwargs": {"fast": 9, "slow": 21}, "name": "Fast EMA Cross (9/21)"},
        {"class": EmaCross, "kwargs": {"fast": 20, "slow": 50}, "name": "Medium EMA Cross (20/50)"},
        {"class": RsiReversion, "kwargs": {"period": 14, "low": 30, "high": 70}, "name": "Standard RSI Reversion (30/70)"},
        {"class": RsiReversion, "kwargs": {"period": 10, "low": 25, "high": 75}, "name": "Aggressive RSI Reversion (25/75)"},
        {"class": MacdMomentum, "kwargs": {"f": 12, "s": 26, "sig": 9}, "name": "Standard MACD Momentum"},
        {"class": MacdMomentum, "kwargs": {"f": 5, "s": 13, "sig": 5}, "name": "Aggressive Quick-MACD"},
        {"class": BollingerBands, "kwargs": {"period": 20, "dev": 2}, "name": "Bollinger Bands Reversion"},
        {"class": BollingerBands, "kwargs": {"period": 10, "dev": 1.5}, "name": "Tight Bollinger Bands"},
        {"class": DonchianBreakout, "kwargs": {"period": 20}, "name": "20-Day Donchian Breakout"},
        {"class": DonchianBreakout, "kwargs": {"period": 50}, "name": "50-Day Donchian Breakout"},
    ]

    for idx, strat in enumerate(strategy_pool, 1):
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strat["class"], **strat["kwargs"])
        
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        
        cerebro.broker.setcash(initial_cash)
        cerebro.broker.setcommission(commission=0.001) # Realistic trading fees
        
        cerebro.run()
        
        final_cash = cerebro.broker.getvalue()
        profit = final_cash - initial_cash
        profit_str = f"+${profit:,.2f}" if profit >= 0 else f"-${abs(profit):,.2f}"
        
        # Highlight if a strategy successfully matches or beats Buy & Hold
        beat_marker = "🔥 BEATS B&H!" if final_cash >= bh_final else ""
        
        print(f"#{idx:<2} | {strat['name']:<30} | ${final_cash:<13,.2f} | {profit_str:<12} {beat_marker}")

if __name__ == '__main__':
    # You can change or add any tickers you want to test here
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
