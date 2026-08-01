# signals.py
"""
Signal generation + full opportunity scoring & ranking
"""

import pandas as pd
from data import get_stock_data, get_fundamentals
from fundamentals import score_fundamentals
from technicals import add_indicators, score_trend, score_setup
import config

def analyze_ticker(ticker: str) -> dict | None:
    """
    Full analysis of one ticker.
    Returns a dict with scores and recommendation, or None if not tradable.
    """
    df = get_stock_data(ticker)
    if df.empty or len(df) < 100:
        return None

    df = add_indicators(df)
    fund = get_fundamentals(ticker)

    # Basic liquidity / price filters
    last_price = df["close"].iloc[-1]
    avg_vol = fund.get("average_volume") or df["volume"].tail(20).mean()

    if last_price < config.MIN_PRICE or avg_vol < config.MIN_AVG_VOLUME:
        return None
    if fund.get("market_cap", 0) < config.MIN_MARKET_CAP:
        return None

    # Scores
    fund_score, fund_reason = score_fundamentals(fund)
    trend_score, trend_reason = score_trend(df)

    # Determine bias
    last = df.iloc[-1]
    bullish_bias = last["close"] > last.get("ema_50", 0) and last.get("ema_50", 0) > last.get("ema_200", 0)
    bearish_bias = last["close"] < last.get("ema_50", float("inf")) and last.get("ema_50", float("inf")) < last.get("ema_200", float("inf"))

    results = []

    # Long / Call candidate
    if bullish_bias or trend_score >= 10:
        setup_score, setup_reason = score_setup(df, direction="long")
        total = (
            fund_score * (config.WEIGHT_FUNDAMENTAL / 0.30) * 0.30 +
            trend_score * (config.WEIGHT_TREND / 0.20) * 0.20 +
            setup_score * (config.WEIGHT_SETUP / 0.25) * 0.25
        )
        # Temporary options & RR placeholders (will be refined later)
        options_score = 10  # placeholder
        rr_score = 7

        final_score = (
            fund_score * config.WEIGHT_FUNDAMENTAL / 0.30 * 0.30 +
            trend_score * config.WEIGHT_TREND / 0.20 * 0.20 +
            setup_score * config.WEIGHT_SETUP / 0.25 * 0.25 +
            options_score * config.WEIGHT_OPTIONS +
            rr_score * config.WEIGHT_RR
        )

        results.append({
            "ticker": ticker,
            "direction": "CALL",
            "score": round(final_score, 1),
            "fund_score": round(fund_score, 1),
            "trend_score": round(trend_score, 1),
            "setup_score": round(setup_score, 1),
            "price": round(last_price, 2),
            "reasons": {
                "fundamental": fund_reason,
                "trend": trend_reason,
                "setup": setup_reason
            }
        })

    # Short / Put candidate
    if bearish_bias or trend_score >= 10:
        setup_score, setup_reason = score_setup(df, direction="short")
        final_score = (
            fund_score * config.WEIGHT_FUNDAMENTAL / 0.30 * 0.30 +
            trend_score * config.WEIGHT_TREND / 0.20 * 0.20 +
            setup_score * config.WEIGHT_SETUP / 0.25 * 0.25 +
            10 * config.WEIGHT_OPTIONS +
            7 * config.WEIGHT_RR
        )

        results.append({
            "ticker": ticker,
            "direction": "PUT",
            "score": round(final_score, 1),
            "fund_score": round(fund_score, 1),
            "trend_score": round(trend_score, 1),
            "setup_score": round(setup_score, 1),
            "price": round(last_price, 2),
            "reasons": {
                "fundamental": fund_reason,
                "trend": trend_reason,
                "setup": setup_reason
            }
        })

    return results if results else None