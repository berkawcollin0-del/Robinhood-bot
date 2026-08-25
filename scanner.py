import json
import requests
from thefuzz import fuzz

KALSHI_API = "https://external-api.kalshi.com/trade-api/v2"
POLYMARKET_API = "https://gamma-api.polymarket.com"


def fetch_kalshi_markets():
  """Fetches active, open markets from Kalshi with liquid volume."""
  try:
    res = requests.get(
        f"{KALSHI_API}/markets",
        params={"status": "open", "limit": 200},
        timeout=10,
    )
    data = res.json().get("markets", [])
    clean = []
    for m in data:
      # Filter for active markets with bid/ask prices
      yes_bid = m.get("yes_bid", 0)
      yes_ask = m.get("yes_ask", 0)
      volume = m.get("volume", 0)

      if yes_ask > 0 and volume > 100:
        clean.append({
            "ticker": m.get("ticker"),
            "title": m.get("title", ""),
            "yes_bid": yes_bid,  # Price in cents (0-100)
            "yes_ask": yes_ask,  # Price in cents (0-100)
            "implied_prob": yes_ask / 100.0,
            "volume": volume,
        })
    return clean
  except Exception as e:
    print(f"Error fetching Kalshi: {e}")
    return []


def fetch_polymarket_events():
  """Fetches active events from Polymarket Gamma API."""
  try:
    res = requests.get(
        f"{POLYMARKET_API}/events",
        params={"closed": "false", "limit": 100},
        timeout=10,
    )
    events = res.json()
    clean = []
    for e in events:
      title = e.get("title", "")
      for m in e.get("markets", []):
        outcome_prices = m.get("outcomePrices")
        if outcome_prices:
          try:
            # outcomePrices is typically a JSON string array: ["0.65", "0.35"]
            prices = (
                json.loads(outcome_prices)
                if isinstance(outcome_prices, str)
                else outcome_prices
            )
            yes_price = float(prices[0]) * 100  # Convert to cents
            clean.append({
                "title": f"{title} - {m.get('groupItemTitle', '')}".strip(
                    " - "
                ),
                "poly_yes_price": yes_price,
                "volume": float(m.get("volume", 0)),
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
  for k in kalshi:
    # Flag extreme favorites (>= 90%) or cheap underdogs (<= 10%) with tight spreads
    spread = k["yes_ask"] - k["yes_bid"]
    if (k["yes_ask"] >= 90 or k["yes_ask"] <= 10) and spread <= 3:
      print(f"[{k['ticker']}] {k['title']}")
      print(
          f"  Price: {k['yes_ask']}¢ | Spread: {spread}¢ | Volume: {k['volume']}"
      )

  # --- 2. CROSS-MARKET SPREAD SCANNER (Kalshi vs Polymarket) ---
  print("\n" + "=" * 60)
  print("⚡ CROSS-MARKET DISCREPANCIES (Kalshi vs Polymarket)")
  print("=" * 60)
  found_matches = 0

  for k in kalshi:
    for p in poly:
      # Fuzzy string match on question titles
      similarity = fuzz.token_set_ratio(
          k["title"].lower(), p["title"].lower()
      )

      if similarity > 80:  # Strong title match
        diff = abs(k["yes_ask"] - p["poly_yes_price"])
        if diff >= 6.0:  # 6%+ discrepancy threshold
          found_matches += 1
          print(f"Match: {k['title']}")
          print(
              f"  Kalshi:     {k['yes_ask']:.1f}¢ (Implied: {k['implied_prob']*100:.1f}%)"
          )
          print(f"  Polymarket: {p['poly_yes_price']:.1f}¢")
          print(f"  --> Discrepancy: {diff:.1f}%\n")

  if found_matches == 0:
    print("No cross-market discrepancies >= 6% found in current sample.")


if __name__ == "__main__":
  scan_for_opportunities()
