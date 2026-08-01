# fundamentals.py
"""
Fundamental quality scoring (0–30 points)
"""

import config

def score_fundamentals(fund: dict) -> tuple[float, str]:
    """
    Returns (score 0-30, explanation string)
    """
    if not fund:
        return 0.0, "No fundamental data"

    score = 0.0
    reasons = []

    # 1. Earnings Growth (max 10 points)
    eg = fund.get("earnings_growth")
    if eg is not None:
        if eg > 0.25:
            score += 10
            reasons.append("Strong earnings growth (>25%)")
        elif eg > 0.10:
            score += 7
            reasons.append("Good earnings growth (>10%)")
        elif eg > 0:
            score += 4
            reasons.append("Positive earnings growth")
        else:
            reasons.append("Negative earnings growth")
    else:
        reasons.append("No earnings growth data")

    # 2. Revenue Growth (max 7 points)
    rg = fund.get("revenue_growth")
    if rg is not None:
        if rg > 0.15:
            score += 7
            reasons.append("Strong revenue growth")
        elif rg > 0.08:
            score += 5
            reasons.append("Solid revenue growth")
        elif rg > 0:
            score += 2
            reasons.append("Positive revenue growth")
    else:
        reasons.append("No revenue growth data")

    # 3. Valuation – PEG or PE (max 7 points)
    peg = fund.get("peg_ratio")
    pe = fund.get("pe_ratio") or fund.get("forward_pe")

    if peg is not None and peg > 0:
        if peg < 1.0:
            score += 7
            reasons.append("Attractive PEG (<1)")
        elif peg < 1.5:
            score += 5
            reasons.append("Reasonable PEG")
        elif peg < 2.0:
            score += 2
            reasons.append("Acceptable PEG")
    elif pe is not None and pe > 0:
        if pe < 15:
            score += 6
            reasons.append("Low PE")
        elif pe < 25:
            score += 3
            reasons.append("Moderate PE")
    else:
        reasons.append("No valuation data")

    # 4. Balance Sheet / Profitability (max 6 points)
    margins = fund.get("profit_margins")
    if margins is not None and margins > 0.10:
        score += 3
        reasons.append("Healthy profit margins")
    elif margins is not None and margins > 0:
        score += 1

    fcf = fund.get("free_cashflow")
    if fcf is not None and fcf > 0:
        score += 3
        reasons.append("Positive free cash flow")

    # Cap at 30
    score = min(score, 30.0)

    explanation = " | ".join(reasons) if reasons else "Limited data"
    return score, explanation