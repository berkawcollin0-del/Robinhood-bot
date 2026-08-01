# risk.py
"""
Position sizing for options (defined risk)
"""

import config

def calculate_position_size(option_price: float, account_size: float = config.ACCOUNT_SIZE) -> dict:
    """
    Calculate how many contracts to buy based on max risk.
    Assumes long options (defined risk = premium paid).
    """
    max_risk = min(config.MAX_RISK_PER_TRADE_USD, account_size * config.MAX_RISK_PER_TRADE_PCT)

    if option_price <= 0:
        return {"contracts": 0, "total_risk": 0, "reason": "Invalid option price"}

    # Cost per contract (option_price is per share, multiply by 100)
    cost_per_contract = option_price * 100

    contracts = int(max_risk // cost_per_contract)

    # Safety: never risk more than max
    total_risk = contracts * cost_per_contract

    return {
        "contracts": max(contracts, 0),
        "cost_per_contract": round(cost_per_contract, 2),
        "total_risk": round(total_risk, 2),
        "max_allowed_risk": round(max_risk, 2),
        "percent_of_account": round((total_risk / account_size) * 100, 2)
    }