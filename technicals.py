# technicals.py
"""
Technical indicators and setup scoring
Uses the stable `ta` library
"""

import pandas as pd
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import config

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all required technical indicators"""
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
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=config.ATR_PERIOD
    ).average_true_range()

    # Volume Moving Average
    df["volume_ma"] = df["volume"].rolling(window=config.VOLUME_MA_PERIOD).mean()

    # ADX (trend strength)
    adx_ind = ADXIndicator(
        high=df["high"],
        low=df["low"],
        close=df["close"],
        window=14
    )
    df["ADX_14"] = adx_ind.adx()

    return df

def score_trend(df: pd.DataFrame) -> tuple[float, str]:
    """
    Trend strength score (0–20 points)
    """
    if df.empty or "ema_50" not in df.columns:
        return 0.0, "Insufficient data"

    last = df.iloc[-1]
    score = 0.0
    reasons = []

    price = last["close"]
    ema50 = last.get("ema_50")
    ema200 = last.get("ema_200")
    adx = last.get("ADX_14", 0)

    # Price vs EMAs
    if pd.notna(ema50) and pd.notna(ema200):
        if price > ema50 > ema200:
            score += 10
            reasons.append("Strong uptrend (Price > 50EMA > 200EMA)")
        elif price > ema50:
            score += 6
            reasons.append("Above 50EMA")
        elif price < ema50 < ema200:
            score += 10
            reasons.append("Strong downtrend (Price < 50EMA < 200EMA)")
        elif price < ema50:
            score += 6
            reasons.append("Below 50EMA")

    # ADX strength
    if pd.notna(adx):
        if adx > 30:
            score += 7
            reasons.append(f"Strong trend (ADX {adx:.1f})")
        elif adx > 20:
            score += 4
            reasons.append(f"Moderate trend (ADX {adx:.1f})")
        else:
            reasons.append(f"Weak trend (ADX {adx:.1f})")

    score = min(score, 20.0)
    return score, " | ".join(reasons) if reasons else "No clear trend"

def score_setup(df: pd.DataFrame, direction: str = "long") -> tuple[float, str]:
    """
    Technical setup quality (0–25 points)
    direction: "long" or "short"
    """
    if df.empty or len(df) < 30:
        return 0.0, "Insufficient data"

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    score = 0.0
    reasons = []

    rsi = last.get("rsi")
    volume = last.get("volume")
    vol_ma = last.get("volume_ma")
    macd_hist = last.get("MACDh_12_26_9")
    prev_macd_hist = prev.get("MACDh_12_26_9", 0)

    # RSI
    if pd.notna(rsi):
        if direction == "long":
            if config.RSI_BULL_LOW <= rsi <= config.RSI_BULL_HIGH:
                score += 8
                reasons.append(f"RSI in bull zone ({rsi:.1f})")
            elif rsi < config.RSI_BULL_LOW:
                score += 4
                reasons.append(f"RSI oversold ({rsi:.1f})")
        else:  # short
            if config.RSI_BEAR_LOW <= rsi <= config.RSI_BEAR_HIGH:
                score += 8
                reasons.append(f"RSI in bear zone ({rsi:.1f})")
            elif rsi > 65:
                score += 4
                reasons.append(f"RSI elevated ({rsi:.1f})")

    # MACD momentum
    if pd.notna(macd_hist):
        if direction == "long" and macd_hist > 0:
            score += 6
            reasons.append("MACD histogram positive")
        elif direction == "short" and macd_hist < 0:
            score += 6
            reasons.append("MACD histogram negative")
        elif direction == "long" and macd_hist > prev_macd_hist:
            score += 3
            reasons.append("MACD improving")
        elif direction == "short" and macd_hist < prev_macd_hist:
            score += 3
            reasons.append("MACD weakening")

    # Volume confirmation
    if pd.notna(volume) and pd.notna(vol_ma) and vol_ma > 0:
        if volume > vol_ma * 1.2:
            score += 6
            reasons.append("Strong volume")
        elif volume > vol_ma:
            score += 3
            reasons.append("Above average volume")

    # Price location relative to EMA
    if direction == "long" and pd.notna(last.get("ema_50")) and last["close"] > last["ema_50"]:
        score += 5
        reasons.append("Price above 50EMA")
    elif direction == "short" and pd.notna(last.get("ema_50")) and last["close"] < last["ema_50"]:
        score += 5
        reasons.append("Price below 50EMA")

    score = min(score, 25.0)
    return score, " | ".join(reasons) if reasons else "No clear setup"