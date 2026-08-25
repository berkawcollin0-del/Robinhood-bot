import json
import requests
from thefuzz import fuzz

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_API = "https://gamma-api.polymarket.com"

# Headers to prevent Cloudflare/bot-filter blocks on cloud runners
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_kalshi_markets():
  """Fetches active, open markets from Kalshi."""
  try:
    # Query up to 1,000 active markets
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
      yes_bid = m.get("yes_bid", 0) or 0
      yes_ask = m.get("yes_ask", 0) or 0
      volume = m.get("volume", 0) or 0

      # Include markets that have an active ask price
      if yes_ask > 0:
        clean.append({
            "ticker": m.get("ticker"),
            "title": m.get("title", ""),
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "implied_prob": yes_ask / 100.0,
            "volume": volume,
        })
    return clean
  except Exception as e:
    print(f"Error fetching Kalshi: {e}")
    return []


def fetch_polymarket_events():
  """Fetches active events from Polymarket."""
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
        if outcome_prices:
          try:
            prices = (
                json.loads(outcome_prices)
                if isinstance(outcome_prices, str)
                else outcome_prices
            )
            yes_price = float(prices[0]) * 100
            clean.append({
                "title": f"{title} - {m.get('groupItemTitle', '')}".strip(
                    " - "
                ),
                "poly_yes_price": yes_price,
                "volume": float(m.get("volume", 0) or 0),
            })
          except Exception:
            continue
    return clean
  except Exception as e:
    print(f"Error fetching Polymarket: {e}")
    return []


def scan_for_opportunities():
  print("Fetching live market data...")
  kalshi = fetch_kalshi_markets()
  poly = fetch_polymarket_events()

  print(
      f"Loaded {len(kalshi)} Kalshi markets and {len(poly)} Polymarket"
      " contracts.\n"
  )

  # --- 1. DETECT LOPSIDED / EXTREME ODDS ON KALSHI ---
  print("=" * 60)
  print("🔎 HIGH-CONVICTION / LOPSIDED MARKETS (Kalshi)")
  print("=" * 60)
  lopsided_count = 0
  for k in kalshi:
    spread = k["yes_ask"] - k["yes_bid"]
    # Flag extreme favorites (>= 90%) or extreme longshots (<= 10%)
    if (k["yes_ask"] >= 90 or k["yes_ask"] <= 10) and spread <= 5:
      lopsided_count += 1
      print(f"[{k['ticker']}] {k['title']}")
      print(
          f"  Price: {k['yes_ask']}¢ (Bid: {k['yes_bid']}¢) | Vol: {k['volume']}"
      )

  if lopsided_count == 0:
    print("No extreme lopsided contracts found.")

  # --- 2. CROSS-MARKET SPREAD SCANNER (Kalshi vs Polymarket) ---
  print("\n" + "=" * 60)
  print("⚡ CROSS-MARKET DISCREPANCIES (Kalshi vs Polymarket)")
  print("=" * 60)
  found_matches = 0

  for k in kalshi:
    for p in poly:
      # Match titles across both platforms
      similarity = fuzz.token_set_ratio(k["title"].lower(), p["title"].lower())
      if similarity >= 80:
        diff = abs(k["yes_ask"] - p["poly_yes_price"])
        if diff >= 5.0:  # 5%+ discrepancy threshold
          found_matches += 1
          print(f"Match: {k['title']}")
          print(f"  Kalshi:     {k['yes_ask']:.1f}¢")
          print(f"  Polymarket: {p['poly_yes_price']:.1f}¢")
          print(f"  --> Discrepancy: {diff:.1f}%\n")

  if found_matches == 0:
    print("No cross-market discrepancies >= 5% found in current sample.")


if __name__ == "__main__":
  scan_for_opportunities()
