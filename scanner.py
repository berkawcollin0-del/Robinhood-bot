import json
import requests
from thefuzz import fuzz

KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"
POLYMARKET_API = "https://gamma-api.polymarket.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

def scan_for_opportunities():
    print("Connecting to Kalshi API...")
    
    try:
        res = requests.get(
            f"{KALSHI_API}/markets",
            headers=HEADERS,
            params={"status": "open", "limit": 10},
            timeout=15,
        )

        if res.status_code != 200:
            print(f"Kalshi API error ({res.status_code}): {res.text[:200]}")
            return
            
        markets = res.json().get("markets", [])
        print(f"✅ Successfully fetched {len(markets)} markets from Kalshi.")
        
        if len(markets) > 0:
            print("\n" + "=" * 60)
            print("🔍 DIAGNOSTIC: RAW KALSHI MARKET SCHEMA")
            print("=" * 60)
            
            # Print the exact raw JSON for the first 3 markets
            for i, m in enumerate(markets[:3]):
                print(f"\n--- Market {i+1} ---")
                print(json.dumps(m, indent=2))
                
            print("\n" + "=" * 60)
            print("Please share the output of the first market so we can map the correct price and volume fields!")
            
    except Exception as e:
        print(f"Error fetching Kalshi: {e}")

if __name__ == "__main__":
    scan_for_opportunities()
