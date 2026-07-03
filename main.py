"""
Command-line entry point.

    python -m weather_bot.cli                       # live consensus, all airports
    python -m weather_bot.cli --airport JFK          # single airport
    python -m weather_bot.cli --backtest --days 90   # add calibrated std from history
    python -m weather_bot.cli --check JFK high above 85 78
        -> compares this tool's probability that JFK's high is above 85F
           against a market trading that YES contract at 78 cents

This tool does not place trades. It has no Robinhood integration, because
Robinhood does not expose a public API for retail bots to trade event
contracts. Use its output as one input to a manual trading decision.
"""

import argparse
import logging
import sys

from . import backtest, probability, sources
from .config import AIRPORTS, AIRPORTS_BY_CODE

log = logging.getLogger("weather_bot.cli")


def gather_readings(airport):
    return [
        sources.fetch_nws(airport.lat, airport.lon),
        sources.fetch_open_meteo(airport.lat, airport.lon),
        sources.fetch_owm(airport.lat, airport.lon),
    ]


def print_airport_report(airport, run_backtest: bool, backtest_days: int):
    print(f"\n{airport.code} — {airport.name}")
    readings = gather_readings(airport)
    consensus = probability.build_consensus(readings)

    bt = backtest.backtest_station(airport.lat, airport.lon, days=backtest_days) if run_backtest else None

    for label in ("high", "low"):
        c = consensus[label]
        if c is None:
            print(f"  {label.upper():4}: no data available from any source")
            continue

        line = (
            f"  {label.upper():4}: {c['mean']}°F consensus "
            f"(n={c['n_sources']} sources, spread={c['spread']}°F, confidence={c['confidence']})"
        )
        if bt and bt.get(label):
            b = bt[label]
            line += f" | backtest: bias={b['bias']:+.1f}F, std={b['std']}F over {b['n']} days"
        print(line)

    if airport.market_city is None:
        print(f"  -> No matching Robinhood city market found for {airport.name}.")
    else:
        print(f"  -> Robinhood market to check: '{airport.market_city} Daily Temperature High/Low'")

    return consensus, bt


def run_check(code, label, direction, threshold, market_price):
    airport = AIRPORTS_BY_CODE.get(code.upper())
    if not airport:
        print(f"Unknown airport code '{code}'. Options: {', '.join(AIRPORTS_BY_CODE)}")
        return

    readings = gather_readings(airport)
    consensus = probability.build_consensus(readings)
    c = consensus.get(label)
    if not c:
        print(f"No consensus data available for {code} {label}.")
        return

    bt = backtest.backtest_station(airport.lat, airport.lon)
    std = backtest.calibrated_std(bt, label)

    p = probability.estimate_probability(
        c["mean"], threshold, direction, std=std, spread_fallback=c["spread"]
    )
    e = probability.edge(p, market_price)

    print(f"\n{airport.code} {label} {direction} {threshold}F")
    print(f"  Consensus mean: {c['mean']}F (confidence {c['confidence']})")
    print(f"  Calibrated std: {std}F")
    print(f"  Tool probability estimate: {p}")
    print(f"  Market implied probability: {market_price/100}")
    print(f"  Edge (tool - market): {e:+.4f}")
    if c["confidence"] < 0.5:
        print("  NOTE: source agreement is weak here — treat this edge with extra skepticism.")


def main(argv=None):
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    parser = argparse.ArgumentParser(description="Weather consensus tool for prediction-market research.")
    parser.add_argument("--airport", help="Limit to one airport code, e.g. JFK")
    parser.add_argument("--backtest", action="store_true", help="Include historical accuracy calibration")
    parser.add_argument("--days", type=int, default=60, help="Backtest lookback window in days (default 60)")
    parser.add_argument(
        "--check", nargs=5, metavar=("CODE", "high|low", "above|below", "THRESHOLD", "MARKET_PRICE_CENTS"),
        help="Compare tool probability vs a specific market price, e.g. --check JFK high above 85 78",
    )
    args = parser.parse_args(argv)

    print("=" * 78)
    print("WEATHER CONSENSUS — research tool, not a trading bot")
    print("Does not place trades. No public Robinhood trading API exists for this.")
    print("=" * 78)

    if args.check:
        code, label, direction, threshold, market_price = args.check
        if label not in ("high", "low") or direction not in ("above", "below"):
            print("label must be 'high' or 'low'; direction must be 'above' or 'below'")
            sys.exit(1)
        run_check(code, label, direction, float(threshold), float(market_price))
        return

    airports = [AIRPORTS_BY_CODE[args.airport.upper()]] if args.airport else AIRPORTS
    if args.airport and args.airport.upper() not in AIRPORTS_BY_CODE:
        print(f"Unknown airport code '{args.airport}'. Options: {', '.join(AIRPORTS_BY_CODE)}")
        sys.exit(1)

    for a in airports:
        print_airport_report(a, run_backtest=args.backtest, backtest_days=args.days)


if __name__ == "__main__":
    main()
