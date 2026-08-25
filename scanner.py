import json
import requests
from thefuzz import fuzz

# ==========================================
# CONFIGURATION & THRESHOLDS
# ==========================================
# Volume Filters (Reduce noise from dead markets)
MIN_KALSHI_VOLUME = 5000     # Minimum contract volume to scan on Kalshi
MIN_POLY_VOLUME = 5000       # Minimum volume (in USD) to scan on Polymarket

# Arbitrage / Discrepancy Settings
MIN_DISCREPANCY_PCT = 5.0    # Only show cross-market differences >= 5%
FUZZY_MATCH_THRESHOLD = 80   # Title match similarity (0-100)

# Lopsided Market Settings (Kalshi)
MAX_SPREAD_CENTS = 5.0       # Ignore markets with bid/ask spreads wider than this
EXTREME_FAVORITE = 90.0      # Flag favorites priced >= 90¢
EXTREME_LONGSHOT = 10.0      # Flag longshots priced <= 10¢

# API Endpoints
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_API = "https://gamma-api.polymarket.com"

# Standard headers to bypass bot filters on cloud runners
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


# ==========================================
# DATA FETCHING
# ==========================================
def fetch_kalshi_markets():
    """Fetches active, liquid open markets from Kalshi."""
    try:
        res = requests.get(
            f"{KALSHI_API}/markets",
            headers=HEADERS,
            params={"status": "open", "limit": 1000},
            timeout=15,
        )

        if res.status_code != 200:
            print(f"Kalshi API error ({res.status_code}): {res.text[:200]}")
            return []

        data = res.json().get("markets", [])
        clean = []

        for m in data:
            # Kalshi V2 uses decimals (e.g., "0.55" for 55 cents)
            yes_bid_dollars = float(m.get("yes_bid_dollars", 0) or 0)
            yes_ask_dollars = float(m.get("yes_ask_dollars", 0) or 0)
            volume = float(m.get("volume", 0) or 0)

            # Convert to cents (0-100)
            yes_bid = yes_bid_dollars * 100
            yes_ask = yes_ask_dollars * 100

            # Filter for liquidity
            if yes_ask > 0 and volume >= MIN_KALSHI_VOLUME:
                clean.append({
                    "ticker": m.get("ticker"),
                    "title": m.get("title", ""),
                    "yes_bid": yes_bid,
                    "yes_ask": yes_ask,
                    "implied_prob": yes_ask_dollars,
                    "volume": volume,
                })
        return clean
    except Exception as e:
        print(f"Error fetching Kalshi: {e}")
        return []


def fetch_polymarket_events():
    """Fetches active, liquid events from Polymarket."""
    try:
        res = requests.get(
            f"{POLYMARKET_API}/events",
            headers=HEADERS,
            params={"closed": "false", "limit": 200},
            timeout=15,
        )

        if res.status_code != 200:
            print(f"Polymarket API error ({res.status_code}): {res.text[:200]}")
            return []

        events = res.json()
        clean = []
        for e in events:
            title = e.get("title", "")
            for m in e.get("markets", []):
                outcome_prices = m.get("outcomePrices")
                volume = float(m.get("volume", 0) or 0)
                
                # Filter for liquidity and valid prices
                if outcome_prices and volume >= MIN_POLY_VOLUME:
                    try:
                        prices = (
                            json.loads(outcome_prices)
                            if isinstance(outcome_prices, str)
                            else outcome_prices
                        )
                        yes_price = float(prices[0]) * 100
                        clean.append({
                            "title": f"{title} - {m.get('groupItemTitle', '')}".strip(" - "),
                            "poly_yes_price": yes_price,
                            "volume": volume,
                        })
                    except Exception:
                        continue
        return clean
    except Exception as e:
        print(f"Error fetching Polymarket: {e}")
        return []


# ==========================================
# SCANNER LOGIC
# ==========================================
def scan_for_opportunities():
    print(f"Fetching live market data (Kalshi Min Vol: {MIN_KALSHI_VOLUME}, Poly Min Vol: {MIN_POLY_VOLUME})...")
    kalshi = fetch_kalshi_markets()
    poly = fetch_polymarket_events()

    print(f"Loaded {len(kalshi)} Kalshi markets and {len(poly)} Polymarket contracts.\n")

    # --- 1. DETECT LOPSIDED / EXTREME ODDS ON KALSHI ---
    print("=" * 65)
    print("🔎 HIGH-CONVICTION / LOPSIDED MARKETS (Kalshi)")
    print("=" * 65)
    lopsided_count = 0
    for k in kalshi:
        spread = k["yes_ask"] - k["yes_bid"]
        
        # Look for extreme favorites or longshots with tight spreads
        if (k["yes_ask"] >= EXTREME_FAVORITE or k["yes_ask"] <= EXTREME_LONGSHOT) and spread <= MAX_SPREAD_CENTS:
            lopsided_count += 1
            print(f"[{k['ticker']}] {k['title']}")
            print(f"  Price: {k['yes_ask']:.0f}¢ (Bid: {k['yes_bid']:.0f}¢) | Spread: {spread:.0f}¢ | Vol: {k['volume']:.0f}")

    if lopsided_count == 0:
        print("No extreme lopsided contracts met the liquidity and spread requirements.")


    # --- 2. CROSS-MARKET SPREAD SCANNER ---
    print("\n" + "=" * 65)
    print(f"⚡ CROSS-MARKET DISCREPANCIES (>= {MIN_DISCREPANCY_PCT}%)")
    print("=" * 65)
    found_matches = 0

    for k in kalshi:
        for p in poly:
            similarity = fuzz.token_set_ratio(k["title"].lower(), p["title"].lower())
            
            if similarity >= FUZZY_MATCH_THRESHOLD:
                diff = abs(k["yes_ask"] - p["poly_yes_price"])
                
                if diff >= MIN_DISCREPANCY_PCT:
                    found_matches += 1
                    print(f"Match: {k['title']}")
                    print(f"  Kalshi:     {k['yes_ask']:.1f}¢")
                    print(f"  Polymarket: {p['poly_yes_price']:.1f}¢")
                    print(f"  --> Discrepancy: {diff:.1f}%\n")

    if found_matches == 0:
        print(f"No cross-market discrepancies >= {MIN_DISCREPANCY_PCT}% found in current sample.")

if __name__ == "__main__":
    scan_for_opportunities()
