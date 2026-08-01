# options.py
"""
Options selection & attractiveness scoring
"""

import pandas as pd
from data import get_option_chain_summary
import config

def score_options_attractiveness(ticker: str, direction: str, current_price: float) -> tuple[float, dict]:
    """
    Score how attractive the options are (0–15 points)
    Returns (score, details dict)
    """
    chain = get_option_chain_summary(ticker)
    if not chain:
        return 5.0, {"note": "No suitable options data"}

    dte = chain["dte"]
    score = 0.0
    details = {
        "expiration": chain["expiration"],
        "dte": dte
    }

    # DTE preference
    if config.PREFERRED_DTE_MIN <= dte <= config.PREFERRED_DTE_MAX:
        score += 5
        details["dte_score"] = "Good DTE"
    elif 20 <= dte <= 70:
        score += 3
        details["dte_score"] = "Acceptable DTE"
    else:
        details["dte_score"] = "Suboptimal DTE"

    # Simple ATM / near ATM selection
    if direction == "CALL":
        options = chain["calls"]
        target_delta = config.TARGET_DELTA_CALL
    else:
        options = chain["puts"]
        target_delta = abs(config.TARGET_DELTA_PUT)

    # Find roughly ATM options
    options = options.copy()
    options["distance"] = abs(options["strike"] - current_price)
    near_atm = options.nsmallest(5, "distance")

    if near_atm.empty:
        return score, details

    # Pick the one closest to desired delta if available, otherwise closest strike
    best = near_atm.iloc[0]
    details["recommended_strike"] = best["strike"]
    details["bid"] = best.get("bid", 0)
    details["ask"] = best.get("ask", 0)
    details["last"] = best.get("lastPrice", 0)

    # Spread quality
    mid = (details["bid"] + details["ask"]) / 2 if details["ask"] > 0 else details["last"]
    if mid > 0:
        spread_pct = (details["ask"] - details["bid"]) / mid
        if spread_pct < 0.05:
            score += 5
            details["spread"] = "Tight"
        elif spread_pct < config.MAX_BID_ASK_SPREAD_PCT:
            score += 3
            details["spread"] = "Acceptable"
        else:
            details["spread"] = "Wide"
    else:
        details["spread"] = "Unknown"

    # Liquidity proxy (open interest / volume)
    oi = best.get("openInterest", 0)
    vol = best.get("volume", 0)
    if oi > 500 or vol > 100:
        score += 5
        details["liquidity"] = "Good"
    elif oi > 100 or vol > 20:
        score += 2
        details["liquidity"] = "Moderate"
    else:
        details["liquidity"] = "Low"

    score = min(score, 15.0)
    return score, details