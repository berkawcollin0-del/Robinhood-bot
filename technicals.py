# technicals.py
"""
Technical indicators and setup scoring
"""

import pandas as pd
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice
import config

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all required technical indicators using the `ta` library"""
    if df.empty or len(df) < 50:
        return df

    df = df.copy()

    # EMAs
    df["ema_50"] = EMAIndicator(close=df["close"], window=config.EMA_FAST).ema_indicator()
    df["ema_200"] = EMAIndicator(close=df["close"], window=config.EMA_SLOW).ema_indicator()

    # RSI
    df["rsi"] = RSIIndicator(close=df["close"], window=config.RSI_PERIOD).rsi()

    # MACD
    macd = MACD(close=df["close"])
    df["MACD_12_26_9"] = macd.macd()
    df["MACDh_12_26_9"] = macd.macd_diff()
    df["MACDs_12_26_9"] = macd.macd_signal()

    # ATR
    df["atr"] = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=config.ATR_PERIOD
    ).average_true_range()

    # Volume MA
    df["volume_ma"] = df["volume"].rolling(window=config.VOLUME_MA_PERIOD).mean()

    # ADX
    adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close"], window=14)
    df["ADX_14"] = adx.adx()

    return df