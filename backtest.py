import collections
import collections.abc
# Hotfix for Backtrader in modern Python versions (used by GitHub Actions)
collections.Iterable = collections.abc.Iterable

import backtrader as bt
import yfinance as yf

class SmaCross(bt.Strategy):
    # Strategy parameters: 10-day vs 30-day moving average
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

def run_backtest(ticker):
    print(f"\n{'='*40}")
    print(f"🚀 BACKTESTING: {ticker}")
    print(f"{'='*40}")
    
    cerebro = bt.Cerebro()
    cerebro.addstrategy(SmaCross)

    # Use Ticker().history() to fetch clean data
    stock = yf.Ticker(ticker)
    df = stock.history(start='2022-01-01', end='2024-01-01')
    
    if df.empty:
        print(f"⚠️ Failed to fetch data for {ticker}. Skipping.")
        return

    # Remove timezone data to prevent Backtrader errors
    df.index = df.index.tz_localize(None)

    # Pass the pandas dataframe into Backtrader
    data = bt.feeds.PandasData(dataname=df)
    cerebro.adddata(data)

    # Start with a $10,000 hypothetical portfolio
    initial_cash = 10000.0
    cerebro.broker.setcash(initial_cash)
    
    # 0.1% fee per trade to make the simulation realistic
    cerebro.broker.setcommission(commission=0.001) 

    print(f'Starting Portfolio Value: ${initial_cash:,.2f}')
    
    # Run the simulation
    cerebro.run()
    
    final_cash = cerebro.broker.getvalue()
    profit = final_cash - initial_cash
    
    print(f'Final Portfolio Value:  ${final_cash:,.2f}')
    print(f'Total Profit / Loss:    ${profit:,.2f}\n')

if __name__ == '__main__':
    # Backtest NVDA and GOOG sequentially
    tickers = ['NVDA', 'GOOG']
    for t in tickers:
        run_backtest(t)
