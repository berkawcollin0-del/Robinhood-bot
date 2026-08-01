# main.py
"""
Daily opportunity scanner & ranked list
"""

from signals import analyze_ticker
from options import score_options_attractiveness
from risk import calculate_position_size
from tabulate import tabulate
import config

# Starter universe – you can expand this later
WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AMD",
    "JPM", "V", "MA", "UNH", "XOM", "CVX", "LLY", "AVGO",
    "COST", "NFLX", "CRM", "ADBE", "PEP", "KO", "WMT", "DIS"
]

def run_scan():
    print("Scanning for swing options opportunities...\n")
    all_opportunities = []

    for ticker in WATCHLIST:
        print(f"Analyzing {ticker}...")
        results = analyze_ticker(ticker)
        if not results:
            continue

        for res in results:
            # Add options attractiveness
            opt_score, opt_details = score_options_attractiveness(
                ticker, res["direction"], res["price"]
            )
            res["options_score"] = round(opt_score, 1)
            res["options_details"] = opt_details

            # Recalculate final score with real options score
            res["score"] = round(
                res["fund_score"] * config.WEIGHT_FUNDAMENTAL / 0.30 * 0.30 +
                res["trend_score"] * config.WEIGHT_TREND / 0.20 * 0.20 +
                res["setup_score"] * config.WEIGHT_SETUP / 0.25 * 0.25 +
                opt_score * config.WEIGHT_OPTIONS +
                7 * config.WEIGHT_RR,   # temporary RR
                1
            )

            # Position sizing (rough estimate using last price of option)
            est_option_price = opt_details.get("last") or opt_details.get("ask") or 2.50
            sizing = calculate_position_size(est_option_price)
            res["sizing"] = sizing

            all_opportunities.append(res)

    # Sort by score descending
    all_opportunities.sort(key=lambda x: x["score"], reverse=True)

    # Filter and display
    print("\n" + "="*80)
    print("RANKED OPPORTUNITIES")
    print("="*80)

    table_data = []
    for i, opp in enumerate(all_opportunities, 1):
        if opp["score"] < config.MIN_SCORE_TO_TRADE:
            continue

        table_data.append([
            i,
            opp["ticker"],
            opp["direction"],
            opp["score"],
            opp["price"],
            opp["sizing"]["contracts"],
            opp["sizing"]["total_risk"],
            opp.get("options_details", {}).get("expiration", "N/A")
        ])

    headers = ["Rank", "Ticker", "Dir", "Score", "Price", "Contracts", "Risk $", "Exp"]
    print(tabulate(table_data, headers=headers, tablefmt="github"))

    print("\nDetailed top ideas:")
    for opp in all_opportunities[:8]:
        if opp["score"] < config.MIN_SCORE_TO_TRADE:
            continue
        print(f"\n{opp['ticker']} {opp['direction']} | Score: {opp['score']}")
        print(f"  Price: ${opp['price']}")
        print(f"  Fundamental: {opp['reasons']['fundamental']}")
        print(f"  Trend: {opp['reasons']['trend']}")
        print(f"  Setup: {opp['reasons']['setup']}")
        print(f"  Options: {opp.get('options_details', {})}")
        print(f"  Sizing: {opp['sizing']}")

if __name__ == "__main__":
    run_scan()