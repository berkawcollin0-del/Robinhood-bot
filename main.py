import requests
import datetime
import time
import numpy as np
import pandas as pd
from scipy.stats import norm

AIRPORTS = {
    "JFK": {"lat": 40.6397, "lon": -73.7789, "name": "New York John F. Kennedy Int'l"},
    "ORD": {"lat": 41.9742, "lon": -87.9073, "name": "Chicago O'Hare Int'l"},
    "LAX": {"lat": 33.9416, "lon": -118.4085, "name": "Los Angeles Int'l"},
    "MIA": {"lat": 25.7959, "lon": -80.2870, "name": "Miami Int'l"},
    "DFW": {"lat": 32.8998, "lon": -97.0403, "name": "Dallas/Fort Worth Int'l"},
    "DEN": {"lat": 39.8561, "lon": -104.6737, "name": "Denver Int'l"},
    "ATL": {"lat": 33.6407, "lon": -84.4277, "name": "Atlanta Hartsfield-Jackson"}
}

def robust_get_request(url, params, retries=3, backoff_factor=2):
    """
    Executes a GET request with an explicit timeout and exponential backoff
    to handle public API rate limits or transient network drops.
    """
    for i in range(retries):
        try:
            # Added explicit timeout=15 seconds
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429: # Rate limited
                time.sleep(backoff_factor ** i)
        except (requests.exceptions.RequestException, Exception):
            if i == retries - 1:
                raise
            time.sleep(backoff_factor ** i)
    raise requests.exceptions.ReadTimeout("Max retries exceeded.")

def backtest_airport_accuracy(start_date, end_date):
    metrics = {}
    print(f"⚙️ Running 30-Day Historical Backtest ({start_date} to {end_date})...")
    
    for code, coords in AIRPORTS.items():
        try:
            f_url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
            f_params = {
                "latitude": coords["lat"], "longitude": coords["lon"],
                "start_date": start_date, "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit", "timezone": "auto"
            }
            f_res = robust_get_request(f_url, f_params)
            
            a_url = "https://archive-api.open-meteo.com/v1/archive"
            a_params = f_params.copy()
            a_res = robust_get_request(a_url, a_params)
            
            pred_max = np.array(f_res["daily"]["temperature_2m_max"])
            true_max = np.array(a_res["daily"]["temperature_2m_max"])
            pred_min = np.array(f_res["daily"]["temperature_2m_min"])
            true_min = np.array(a_res["daily"]["temperature_2m_min"])
            
            mask_max = ~np.isnan(pred_max) & ~np.isnan(true_max)
            mask_min = ~np.isnan(pred_min) & ~np.isnan(true_min)
            
            mae_max = np.mean(np.abs(pred_max[mask_max] - true_max[mask_max]))
            bias_max = np.mean(pred_max[mask_max] - true_max[mask_max])
            
            mae_min = np.mean(np.abs(pred_min[mask_min] - true_min[mask_min]))
            bias_min = np.mean(pred_min[mask_min] - true_min[mask_min])
            
            metrics[code] = {
                "mae_max": mae_max, "bias_max": bias_max,
                "mae_min": mae_min, "bias_min": bias_min,
                "overall_score": (mae_max + mae_min) / 2
            }
            # Tiny cool-down breathing room between airport hits
            time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Error processing backtest for {code}: {e}")
            
    return pd.DataFrame.from_dict(metrics, orient='index')

def get_live_ensemble_odds(city_code, target_date, threshold, is_high_market=True, bias_adjustment=0.0):
    loc = AIRPORTS[city_code]
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"],
        "hourly": "temperature_2m", "models": "gfs_seamless",
        "temperature_unit": "fahrenheit", "timezone": "auto", "forecast_days": 10
    }
    
    res = robust_get_request(url, params)
    hourly = res.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []))
    member_keys = [k for k in hourly.keys() if k.startswith("temperature_2m_member_")]
    
    daily_extremes = []
    for member in member_keys:
        series = pd.Series(hourly[member], index=times)
        day_series = series[series.index.date == pd.to_datetime(target_date).date()]
        if not day_series.empty:
            corrected_series = day_series - bias_adjustment
            extreme_val = corrected_series.max() if is_high_market else corrected_series.min()
            daily_extremes.append(extreme_val)
            
    if not daily_extremes:
        return None
        
    mu, sigma = np.mean(daily_extremes), max(np.std(daily_extremes, ddof=1), 0.1)
    odds = norm.sf(threshold, loc=mu, scale=sigma) if is_high_market else norm.cdf(threshold, loc=mu, scale=sigma)
    return {"odds": odds, "model_mean": mu, "model_std": sigma}

if __name__ == "__main__":
    today = datetime.date(2026, 7, 4)
    backtest_start = (today - datetime.timedelta(days=40)).strftime("%Y-%m-%d")
    backtest_end = (today - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    accuracy_df = backtest_airport_accuracy(backtest_start, backtest_end)
    
    # Check if we got any valid backtest results back before attempting sorting
    if accuracy_df.empty:
        print("❌ Error: No backtest data gathered. Aborting run.")
        exit(1)
        
    ranked_cities = accuracy_df.sort_values(by="overall_score")
    
    print("\n" + "="*65)
    print("🏆 AIRPORT FORECAST ACCURACY RANKINGS (LEAST ERROR TO MOST ERROR)")
    print("="*65)
    print(ranked_cities[["mae_max", "bias_max", "mae_min", "bias_min", "overall_score"]].to_string())
    
    target_tomorrow = (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    high_threshold = 90.0
    low_threshold = 65.0
    
    print("\n" + "="*65)
    print(f"📊 LIVE PROBABILITY ODDS FOR TARGET DATE: {target_tomorrow}")
    print("="*65)
    
    for code in ranked_cities.index:
        # Wrap the live loops inside a try/except so one failing network request won't crash the whole bot
        try:
            bias_h = accuracy_df.loc[code, "bias_max"]
            bias_l = accuracy_df.loc[code, "bias_min"]
            
            high_market = get_live_ensemble_odds(code, target_tomorrow, high_threshold, is_high_market=True, bias_adjustment=bias_h)
            time.sleep(0.5) # Give the API a brief moment to breathe
            low_market = get_live_ensemble_odds(code, target_tomorrow, low_threshold, is_high_market=False, bias_adjustment=bias_l)
            time.sleep(0.5)
            
            print(f"\n✈️ {code} ({AIRPORTS[code]['name']}):")
            if high_market:
                print(f"  ▪️ High Market (≥ {high_threshold}°F): {high_market['odds']*100:6.1f}% Odds | Fair Price: {int(round(high_market['odds']*100))}¢ (Exp Max: {high_market['model_mean']:.1f}°F)")
            if low_market:
                print(f"  ▪️ Low Market  (≤ {low_threshold}°F): {low_market['odds']*100:6.1f}% Odds | Fair Price: {int(round(low_market['odds']*100))}¢ (Exp Min: {low_market['model_mean']:.1f}°F)")
        
        except Exception as e:
            print(f"\n✈️ {code}: ⚠️ Skipped live evaluation due to error: {e}")
