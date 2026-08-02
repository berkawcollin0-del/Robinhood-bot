# data.py
"""
Data fetching module – stocks + basic options info using yfinance
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import config

def get_stock_data(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Download OHLCV data for a ticker"""
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()

        # Fix MultiIndex columns (common yfinance issue)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.rename(columns=str.lower)
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return pd.DataFrame()

def get_fundamentals(ticker: str) -> dict:
    """Fetch key fundamental metrics"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "Unknown"),
            "industry": info.get("industry", "Unknown"),
            "market_cap": info.get("marketCap", 0),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "forward_pe": info.get("forwardPE"),
            "peg_ratio": info.get("pegRatio"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth"),
            "profit_margins": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "free_cashflow": info.get("freeCashflow"),
            "average_volume": info.get("averageVolume"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception as e:
        print(f"Error fetching fundamentals for {ticker}: {e}")
        return {}

def get_option_chain_summary(ticker: str, max_dte: int = 60):
    """
    Get a simplified view of available options.
    Returns nearest expirations and approximate ATM prices.
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return None

        today = datetime.now().date()
        valid_exps = []
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte = (exp_date - today).days
            if config.PREFERRED_DTE_MIN <= dte <= max_dte:
                valid_exps.append((exp, dte))

        if not valid_exps:
            return None

        # Take the first good expiration
        best_exp, dte = valid_exps[0]
        chain = stock.option_chain(best_exp)

        return {
            "expiration": best_exp,
            "dte": dte,
            "calls": chain.calls,
            "puts": chain.puts
        }
    except Exception as e:
        print(f"Error fetching options for {ticker}: {e}")
        return None