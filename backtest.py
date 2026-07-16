import collections
import collections.abc
# Hotfix for Backtrader compatibility with modern Python versions
collections.Iterable = collections.abc.Iterable

import backtrader as bt
import yfinance as yf
import pandas as pd

# ==========================================
# 1. THE STRATEGIES (NOW WITH "ALL IN" POSITION SIZING)
# ==========================================

class EmaCross(bt.Strategy):
    params = dict(fast=9, slow=21)
    def __init__(self):
        self.fast_ema = bt.ind.EMA(period=self.p.fast)
        self.slow_ema = bt.ind.EMA(period=self.p.slow)
        self.crossover = bt.ind.CrossOver(self.fast_ema, self.slow_ema)
    def next(self):
        if not self.position and self.crossover > 0: 
            self.order_target_percent(target=0.95) # Go 95% All-In
        elif self.position and self.crossover < 0: 
            self.close()

class DipBuyer(bt.Strategy):
    """Buys when the stock is overall bullish (Price > SMA) but temporarily oversold (RSI < Low)"""
    params = dict(sma_period=50, rsi_period=14, rsi_low=30, rsi_high=70)
    def __init__(self):
        self.sma = bt.ind.SMA(period=self.p.sma_period)
        self.rsi = bt.ind.RSI(period=self.p.rsi_period)
    def next(self):
        if not self.position:
            # Bull market dip
            if self.data.close[0] > self.sma[0] and self.rsi[0] < self.p.rsi_low:
                self.order_target_percent(target=0.95)
        else:
            # Sell when the bounce happens
            if self.rsi[0] > self.p.rsi_high or self.data.close[0] < self.sma[0]:
                self.close()

class MacdMomentum(bt.Strategy):
    params = dict(f=12, s=26, sig=9)
    def __init__(self):
        self.macd = bt.ind.MACD(period_me1=self.p.f, period_me2=self.p.s, period_signal=self.p.sig)
        self.crossover = bt.ind.CrossOver(self.macd.macd, self.macd.signal)
    def next(self):
        if not self.position and self.crossover > 0: 
            self.order_target_percent(target=0.95)
        elif self.position and self.crossover < 0: 
            self.close()

class BollingerBands(bt.Strategy):
    params = dict(period=20, dev=2)
    def __init__(self):
        self.bb = bt.ind.BollingerBands(period=self.p.period, devfactor=self.p.dev)
    def next(self):
        if not self.position and self.data.close[0] < self.bb.lines.bot[0]: 
            self.order_target_percent(target=0.95)
        elif self.position and self.data.close[0] > self.bb.lines.top[0]: 
            self.close()

class DonchianBreakout(bt.Strategy):
    params = dict(period=20)
    def __init__(self):
        self.highest = bt.ind.Highest(self.data.high, period=self.p.period)
        self.lowest = bt.ind.Lowest(self.data.low, period=self.p.period)
    def next(self):
        if not self.position and self.data.close[0] >= self.highest[-1]: 
            self.order_target_percent(target=0.95)
        elif self.position and self.data.close[0] <= self.lowest[-1]: 
            self.close()

# ==========================================
# 2. RUN ENGINE AND CONFIGURATION
# ==========================================

def run_multi_backtest(ticker):
    print(f"\n{'='*85}")
    print(f"🚀 STOCK MARKET ENGINE: {ticker}")
    print(f"{'='*85}")
    
    stock = yf.Ticker(ticker)
    df = stock.history(start='2024-01-01', end='2026-01-01')
    
    if df.empty:
        print(f"⚠️ Failed to fetch data for {ticker}. Skipping.")
        return
    
    df.index = df.index.tz_localize(None)
    initial_cash = 10000.0

    start_price = df['Close'].iloc[0]
    end_price = df['Close'].iloc[-1]
    bh_shares = initial_cash / start_price
    bh_final = bh_shares * end_price
    bh_profit = bh_final - initial_cash

    print(f"🏆 BENCHMARK -> Buy & Hold Final Value: ${bh_final:,.2f} ({bh_profit:+,.2f} Profit)")
    print("-" * 85)
    print(f"{'ID':<3} | {'Strategy Setup Name':<32} | {'Final Value':<14} | {'Net P/L':<13}")
    print("-" * 85)

    strategy_pool = [
        {"class": EmaCross, "kwargs": {"fast": 9, "slow": 21}, "name": "Fast EMA Cross (9/21)"},
        {"class": EmaCross, "kwargs": {"fast": 20, "slow": 50}, "name": "Medium EMA Cross (20/50)"},
        {"class": DipBuyer, "kwargs": {"sma_period": 50, "rsi_period": 14, "rsi_low": 30, "rsi_high": 70}, "name": "Bull Market Dip Buyer (50SMA)"},
        {"class": DipBuyer, "kwargs": {"sma_period": 20, "rsi_period": 10, "rsi_low": 25, "rsi_high": 75}, "name": "Aggressive Dip Buyer (20SMA)"},
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
        cerebro.broker.setcommission(commission=0.001) 
        
        cerebro.run()
        
        final_cash = cerebro.broker.getvalue()
        profit = final_cash - initial_cash
        profit_str = f"+${profit:,.2f}" if profit >= 0 else f"-${abs(profit):,.2f}"
        
        beat_marker = "🔥 BEATS B&H!" if final_cash > bh_final else ""
        
        print(f"#{idx:<2} | {strat['name']:<32} | ${final_cash:<13,.2f} | {profit_str:<13} {beat_marker}")

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
