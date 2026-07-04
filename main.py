import requests
import datetime
import numpy as np
import pandas as pd
from scipy.stats import norm

# 1. Map major airport hubs (primary settlement locations for prediction markets)
AIRPORTS = {
    "JFK": {"lat": 40.6397, "lon": -73.7789, "name": "New York John F. Kennedy Int'l"},
    "ORD": {"lat": 41.9742, "lon": -87.9073, "name": "Chicago O'Hare Int'l"},
    "LAX": {"lat": 33.9416, "lon": -118.4085, "name": "Los Angeles Int'l"},
    "MIA": {"lat": 25.7959, "lon": -80.2870, "name": "Miami Int'l"},
    "DFW": {"lat": 32.8998, "lon": -97.0403, "name": "Dallas/Fort Worth Int'l"},
    "DEN": {"lat": 39.8561, "lon": -104.6737, "name": "Denver Int'l"},
    "ATL": {"lat": 33.6407, "lon": -84.4277, "name": "Atlanta Hartsfield-Jackson"}
}

def backtest_airport_accuracy(start_date, end_date):
    """
    Compares historical operational forecasts against ground-truth reanalysis 
    to calculate Mean Absolute Error (MAE) and systemic Bias for each airport.
    """
    metrics = {}
    print(f"⚙️ Running 30-Day Historical Backtest ({start_date} to {end_date})...")
    
    for code, coords in AIRPORTS.items():
        try:
            # Fetch historical forecast data (what the model predicted)
            f_url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
            f_params = {
                "latitude": coords["lat"], "longitude": coords["lon"],
                "start_date": start_date, "end_date": end_date,
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit", "timezone": "auto"
            }
            f_res = requests.get(f_url, params=f_params).json()
            
            # Fetch ground truth archive data (what actually happened)
            a_url = "https://archive-api.open-meteo.com/v1/archive"
            a_params = f_params.copy()
            a_res = requests.get(a_url, params=a_params).json()
            
            # Extract lists
            pred_max = np.array(f_res["daily"]["temperature_2m_max"])
            true_max = np.array(a_res["daily"]["temperature_2m_max"])
            pred_min = np.array(f_res["daily"]["temperature_2m_min"])
            true_min = np.array(a_res["daily"]["temperature_2m_min"])
            
            # Remove any potential null values safely
            mask_max = ~np.isnan(pred_max) & ~np.isnan(true_max)
            mask_min = ~np.isnan(pred_min) & ~np.isnan(true_min)
            
            # Calculations
            mae_max = np.mean(np.abs(pred_max[mask_max] - true_max[mask_max]))
            bias_max = np.mean(pred_max[mask_max] - true_max[mask_max]) # positive = model runs hot
            
            mae_min = np.mean(np.abs(pred_min[mask_min] - true_min[mask_min]))
            bias_min = np.mean(pred_min[mask_min] - true_min[mask_min]) # positive = model runs warm at night
            
            metrics[code] = {
                "mae_max": mae_max, "bias_max": bias_max,
                "mae_min": mae_min, "bias_min": bias_min,
                "overall_score": (mae_max + mae_min) / 2
            }
        except Exception as e:
            print(f"⚠️ Error processing backtest for {code}: {e}")
            
    return pd.DataFrame.from_dict(metrics, orient='index')

def get_live_ensemble_odds(city_code, target_date, threshold, is_high_market=True, bias_adjustment=0.0):
    """
    Pulls live ensemble data, applies backtested structural bias corrections,
    and returns fair value probabilistic odds for the market threshold.
    """
    loc = AIRPORTS[city_code]
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"],
        "hourly": "temperature_2m", "models": "gfs_seamless",
        "temperature_unit": "fahrenheit", "timezone": "auto", "forecast_days": 10
    }
    
    res = requests.get(url, params=params).json()
    hourly = res.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []))
    member_keys = [k for k in hourly.keys() if k.startswith("temperature_2m_member_")]
    
    daily_extremes = []
    for member in member_keys:
        series = pd.Series(hourly[member], index=times)
        day_series = series[series.index.date == pd.to_datetime(target_date).date()]
        if not day_series.empty:
            # Apply historical bias correction directly to raw member tracks
            corrected_series = day_series - bias_adjustment
            extreme_val = corrected_series.max() if is_high_market else corrected_series.min()
            daily_extremes.append(extreme_val)
            
    if not daily_extremes:
        return None
        
    mu, sigma = np.mean(daily_extremes), max(np.std(daily_extremes, ddof=1), 0.1)
    
    # Survival function (1-CDF) for High markets; Standard CDF for Low markets
    odds = norm.sf(threshold, loc=mu, scale=sigma) if is_high_market else norm.cdf(threshold, loc=mu, scale=sigma)
    return {"odds": odds, "model_mean": mu, "model_std": sigma}

# --- EXECUTION PIPELINE ---
if __name__ == "__main__":
    # 1. Define Backtest Window (Safe 30-day window avoiding real-time reporting lags)
    today = datetime.date(2026, 7, 4)
    backtest_start = (today - datetime.timedelta(days=40)).strftime("%Y-%m-%d")
    backtest_end = (today - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    # Run Backtest
    accuracy_df = backtest_airport_accuracy(backtest_start, backtest_end)
    ranked_cities = accuracy_df.sort_values(by="overall_score")
    
    print("\n" + "="*65)
    print("🏆 AIRPORT FORECAST ACCURACY RANKINGS (LEAST ERROR TO MOST ERROR)")
    print("="*65)
    print(ranked_cities[["mae_max", "bias_max", "mae_min", "bias_min", "overall_score"]].to_string())
    print("\n💡 Alpha Tip: Cities with HIGH MAE offer the biggest mispricing opportunities vs the public.")
    print("💡 Bias Correction: Negative bias means model runs cold (add degrees to correct). Positive means it runs hot.")
    
    # 2. Evaluate Live Target Markets
    target_tomorrow = (today + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    high_threshold = 90.0
    low_threshold = 65.0
    
    print("\n" + "="*65)
    print(f"📊 LIVE PROBABILITY ODDS FOR TARGET DATE: {target_tomorrow}")
    print("="*65)
    
    for code in ranked_cities.index:
        # Pull backtest values for dynamic bias-correction
        bias_h = accuracy_df.loc[code, "bias_max"]
        bias_l = accuracy_df.loc[code, "bias_min"]
        
        # Calculate Odds
        high_market = get_live_ensemble_odds(code, target_tomorrow, high_threshold, is_high_market=True, bias_adjustment=bias_h)
        low_market = get_live_ensemble_odds(code, target_tomorrow, low_threshold, is_high_market=False, bias_adjustment=bias_l)
        
        print(f"\n✈️ {code} ({AIRPORTS[code]['name']}):")
        if high_market:
            print(f"  ▪️ High Market (≥ {high_threshold}°F): {high_market['odds']*100:6.1f}% Odds | Fair Price: {int(round(high_market['odds']*100))}¢ (Exp Max: {high_market['model_mean']:.1f}°F)")
        if low_market:
            print(f"  ▪️ Low Market  (≤ {low_threshold}°F): {low_market['odds']*100:6.1f}% Odds | Fair Price: {int(round(low_market['odds']*100))}¢ (Exp Min: {low_market['model_mean']:.1f}°F)")
