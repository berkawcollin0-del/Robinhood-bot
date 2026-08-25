import json
import requests
from datetime import datetime, timedelta, timezone
from thefuzz import fuzz

# ==========================================
# OPTIMIZED CONFIGURATION FOR MORE SIGNALS
# ==========================================
MAX_DAYS_OUT = 60            # Look out 60 days to catch monthly macro/Fed/CPI prints

MIN_KALSHI_VOLUME = 50       # Lowered to capture fast-moving short-term markets
MIN_POLY_VOLUME = 1000       # Lowered to match more Polymarket contracts

MIN_DISCREPANCY_PCT = 4.0    # Show spreads of 4% or higher
FUZZY_MATCH_THRESHOLD = 70   # Slightly looser title matching for questions vs statements

MAX_SPREAD_CENTS = 10.0      # Allow slightly wider spreads
EXTREME_FAVORITE = 85.0      # Flag favorites priced >= 85¢
EXTREME_LONGSHOT = 15.0      # Flag underdogs priced <= 15¢

REPORT_FILE = "scan_results.md" # The markdown file saved to your GitHub repo

# API Endpoints
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_API = "https://gamma-api.polymarket.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Calculate the cutoff timestamp
CUTOFF_DATE = datetime.now(timezone.utc) + timedelta(days=MAX_DAYS_OUT)
CUTOFF_STR = CUTOFF_DATE.strftime("%Y-%m-%dT%H:%M:%SZ")

# Simple logger to print and save to markdown
report_lines = []
def log(msg=""):
    print(msg)
    report_lines.append(msg)

# ==========================================
# DATA FETCHING
# ==========================================
def fetch_kalshi_markets():
    """Fetches active open markets from Kalshi resolving within the next 60 days."""
    clean = []
    try:
        res = requests.get(
            f"{KALSHI_API}/events",
            headers=HEADERS,
            params={"status": "open", "limit": 200, "with_nested_markets": "true"},
            timeout=15,
        )

        if res.status_code != 200:
            log(f"Kalshi API error ({res.status_code}): {res.text[:200]}")
            return []

        events = res.json().get("events", [])
        
        for e in events:
            if e.get("event_ticker", "").startswith("KXMV"):
                continue
                
            markets = e.get("markets", [])
            for m in markets:
                expiration_time = m.get("expiration_time", "")
                if expiration_time and expiration_time > CUTOFF_STR:
                    continue

                yes_ask_dollars = float(m.get("yes_ask_dollars", 0) or 0)
                yes_bid_dollars = float(m.get("yes_bid_dollars", 0) or 0)
                yes_ask = yes_ask_dollars * 100
                yes_bid = yes_bid_dollars * 100
                
                volume = float(m.get("volume_fp", m.get("volume", 0)) or 0)

                if yes_ask > 0 and volume >= MIN_KALSHI_VOLUME:
                    clean.append({
                        "ticker": m.get("ticker", ""),
                        "title": m.get("title", ""),
                        "yes_bid": yes_bid,
                        "yes_ask": yes_ask,
                        "volume": volume,
                        "expiration": expiration_time
                    })
        return clean
    except Exception as e:
        log(f"Error fetching Kalshi: {e}")
        return []

def fetch_polymarket_events():
    """Fetches active, liquid events from Polymarket resolving within the next 60 days."""
    try:
        res = requests.get(
            f"{POLYMARKET_API}/events",
            headers=HEADERS,
            params={"closed": "false", "limit": 200},
            timeout=15,
        )

        if res.status_code != 200:
            log(f"Polymarket API error ({res.status_code}): {res.text[:200]}")
            return []

        events = res.json()
        clean = []
        for e in events:
            end_date = e.get("endDate", "")
            if end_date and end_date > CUTOFF_STR:
                continue

            title = e.get("title", "")
            for m in e.get("markets", []):
                outcome_prices = m.get("outcomePrices")
                volume = float(m.get("volume", 0) or 0)
                
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
        log(f"Error fetching Polymarket: {e}")
        return []

# ==========================================
# SCANNER LOGIC
# ==========================================
def scan_for_opportunities():
    log(f"# Market Arbitrage & Opportunity Scan\n*Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*\n")
    log(f"Filtering for events resolving on or before: `{CUTOFF_STR}`")
    log(f"Volume Thresholds: Kalshi $\ge$ {MIN_KALSHI_VOLUME}, Poly $\ge$ {MIN_POLY_VOLUME}\n")
    
    kalshi = fetch_kalshi_markets()
    poly = fetch_polymarket_events()

    log(f"✅ Loaded **{len(kalshi)}** liquid Kalshi markets and **{len(poly)}** Polymarket contracts.\n")

    # --- 1. DETECT LOPSIDED / EXTREME ODDS ON KALSHI ---
    log("## 🔎 HIGH-CONVICTION / LOPSIDED MARKETS (Kalshi)")
    lopsided_count = 0
    kalshi_sorted = sorted(kalshi, key=lambda x: x["expiration"])
    
    for k in kalshi_sorted:
        spread = k["yes_ask"] - k["yes_bid"]
        if (k["yes_ask"] >= EXTREME_FAVORITE or k["yes_ask"] <= EXTREME_LONGSHOT) and spread <= MAX_SPREAD_CENTS:
            lopsided_count += 1
            clean_date = k['expiration'].split('T')[0] if k['expiration'] else "Unknown"
            log(f"**[{clean_date}]** {k['title']}")
            log(f"> Price: **{k['yes_ask']:.1f}¢** (Bid: {k['yes_bid']:.1f}¢) | Spread: {spread:.1f}¢ | Vol: {k['volume']:.0f}\n")

    if lopsided_count == 0:
        log("*No extreme lopsided contracts met the liquidity and spread requirements.*\n")

    # --- 2. CROSS-MARKET SPREAD SCANNER ---
    log(f"## ⚡ CROSS-MARKET DISCREPANCIES ($\ge$ {MIN_DISCREPANCY_PCT}%)")
    found_matches = 0

    for k in kalshi_sorted:
        for p in poly:
            similarity = fuzz.token_set_ratio(k["title"].lower(), p["title"].lower())
            
            if similarity >= FUZZY_MATCH_THRESHOLD:
                diff = abs(k["yes_ask"] - p["poly_yes_price"])
                
                if diff >= MIN_DISCREPANCY_PCT:
                    found_matches += 1
                    clean_date = k['expiration'].split('T')[0] if k['expiration'] else "Unknown"
                    log(f"**Match [{clean_date}]:** {k['title']}")
                    log(f"> Kalshi: **{k['yes_ask']:.1f}¢**  |  Polymarket: **{p['poly_yes_price']:.1f}¢**")
                    log(f"> Discrepancy: **{diff:.1f}%**\n")

    if found_matches == 0:
        log(f"*No cross-market discrepancies $\ge$ {MIN_DISCREPANCY_PCT}% found in current sample.*\n")

    # Write the logged output to a markdown file
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"\nReport successfully saved to {REPORT_FILE}")

if __name__ == "__main__":
    scan_for_opportunities()
