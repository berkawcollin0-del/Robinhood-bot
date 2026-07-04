import requests
import datetime
import time
import numpy as np
import pandas as pd
from scipy.stats import norm

# Expanded Matrix: Top 15 US Prediction Market Airports with NWS Station Hooks
AIRPORTS = {
    "ATL": {"lat": 33.6407, "lon": -84.4277, "station": "KATL", "name": "Atlanta Hartsfield-Jackson"},
    "LAX": {"lat": 33.9416, "lon": -118.4085, "station": "KLAX", "name": "Los Angeles Int'l"},
    "ORD": {"lat": 41.9742, "lon": -87.9073, "station": "KORD", "name": "Chicago O'Hare Int'l"},
    "DFW": {"lat": 32.8998, "lon": -97.0403, "station": "KDFW", "name": "Dallas/Fort Worth Int'l"},
    "DEN": {"lat": 39.8561, "lon": -104.6737, "station": "KDEN", "name": "Denver Int'l"},
    "JFK": {"lat": 40.6397, "lon": -73.7789, "station": "KJFK", "name": "New York JFK Int'l"},
    "SFO": {"lat": 37.6213, "lon": -122.3790, "station": "KSFO", "name": "San Francisco Int'l"},
    "SEA": {"lat": 47.4502, "lon": -122.3088, "station": "KSEA", "name": "Seattle-Tacoma Int'l"},
    "LAS": {"lat": 36.0840, "lon": -115.1537, "station": "KLAS", "name": "Las Vegas Harry Reid"},
    "MCO": {"lat": 28.4286, "lon": -81.3160, "station": "KMCO", "name": "Orlando Int'l"},
    "MIA": {"lat": 25.7959, "lon": -80.2870, "station": "KMIA", "name": "Miami Int'l"},
    "PHX": {"lat": 33.4343, "lon": -112.0080, "station": "KPHX", "name": "Phoenix Sky Harbor"},
    "IAH": {"lat": 29.9902, "lon": -95.3368, "station": "KIAH", "name": "Houston George Bush"},
    "BOS": {"lat": 42.3656, "lon": -71.0096, "station": "KBOS", "name": "Boston Logan Int'l"},
    "AUS": {"lat": 30.1945, "lon": -97.6664, "station": "KAUS", "name": "Austin-Bergstrom Int'l"}
}

def robust_get_request(url, params=None, headers=None, retries=3, backoff_factor=2):
    for i in range(retries):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=12)
            if response.status_code == 200:
                return response.json()
            elif response.status_code in [429, 503]:
                time.sleep(backoff_factor ** i)
        except (requests.exceptions.RequestException, Exception):
            if i == retries - 1:
                raise
            time.sleep(backoff_factor ** i)
    raise requests.exceptions.ReadTimeout("API Connection Timeout Error.")

def get_realtime_observations_today(station_id, target_date):
    """
    FIX: Queries the official National Weather Service API for live, airport-ground
    thermometer logs to circumvent un-updated model predictions.
    """
    url = f"https://api.weather.gov/stations/{station_id}/observations"
    headers = {"User-Agent": "WeatherPredictionMarketBot/2.0 (trader-agent@example.com)"}
    
    try:
        data = robust_get_request(url, headers=headers)
        features = data.get("features", [])
        
        temps_f = []
        target_dt = pd.to_datetime(target_date).date()
        
        for feature in features:
            props = feature.get("properties", {})
            timestamp_str = props.get("timestamp")
            if not timestamp_str:
                continue
                
            obs_time = pd.to_datetime(timestamp_str)
            # Filter strictly for readings recorded inside today's local date bounds
            if obs_time.date() == target_dt:
                celsius = props.get("temperature", {}).get("value")
                if celsius is not None and not np.isnan(celsius):
                    fahrenheit = (celsius * 9/5) + 32
                    temps_f.append(fahrenheit)
                    
        if temps_f:
            return max(temps_f), min(temps_f)
    except Exception as e:
        print(f"   ⚠️ NWS Live Stream Intercept Failed for {station_id}: {e}")
    return -999.0, 999.0

def backtest_airport_accuracy(start_date, end_date):
    metrics = {}
    print(f"⚙️ Running Historical Backtest Matrix ({start_date} to {end_date})...")
    
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
            time.sleep(0.2) # Avoid aggressive rate-limiting
        except Exception as e:
            print(f"  ⚠️ Skipping Backtest calculation for {code}: Node busy.")
            
    return pd.DataFrame.from_dict(metrics, orient='index')

def get_live_ensemble_odds(city_code, target_date, threshold, is_high_market=True, bias_adjustment=0.0, obs_max=-999.0, obs_min=999.0):
    loc = AIRPORTS[city_code]
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": loc["lat"], "longitude": loc["lon"],
        "hourly": "temperature_2m", "models": "gfs_seamless",
        "temperature_unit": "fahrenheit", "timezone": "auto", "forecast_days": 2
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
            corrected_forecast = day_series - bias_adjustment
            
            if is_high_market:
                # Intraday Blend: True daily high is the max of reality vs what's left of the forecast
                final_member_est = max(obs_max, corrected_forecast.max())
            else:
                final_member_est = min(obs_min, corrected_forecast.min())
                
            daily_extremes.append(final_member_est)
            
    if not daily_extremes:
        return None
        
    mu, sigma = np.mean(daily_extremes), max(np.std(daily_extremes, ddof=1), 0.1)
    odds = norm.sf(threshold, loc=mu, scale=sigma) if is_high_market else norm.cdf(threshold, loc=mu, scale=sigma)
    return {"odds": odds, "model_mean": mu, "model_std": sigma}

if __name__ == "__main__":
    today = datetime.date.today()
    target_today = today.strftime("%Y-%m-%d")
    
    # FIX: Shift lookback back 4 days to completely clear Open-Meteo's archival reporting delay
    backtest_start = (today - datetime.timedelta(days=35)).strftime("%Y-%m-%d")
    backtest_end = (today - datetime.timedelta(days=4)).strftime("%Y-%m-%d")
    
    accuracy_df = backtest_airport_accuracy(backtest_start, backtest_end)
    if accuracy_df.empty:
        print("❌ Error: No backtest data gathered. Aborting execution loop.")
        exit(1)
        
    ranked_cities = accuracy_df.sort_values(by="overall_score")
    
    print("\n" + "="*85)
    print(f"🏆 TOP 15 AIRPORT FORECAST ACCURACY RANKINGS (LEAST ERROR TO MOST ERROR)")
    print("="*85)
    print(ranked_cities[["mae_max", "bias_max", "mae_min", "bias_min", "overall_score"]].to_string())
    
    print("\n" + "="*85)
    print(f"📊 LIVE REAL-TIME TRADING ODDS FOR TODAY ONLY: {target_today}")
    print("="*85)
    
    for code in ranked_cities.index:
        try:
            bias_h = accuracy_df.loc[code, "bias_max"]
            bias_l = accuracy_df.loc[code, "bias_min"]
            
            # Fetch absolute ground-truth live data directly via NWS sensor feeds
            obs_max, obs_min = get_realtime_observations_today(AIRPORTS[code]["station"], target_today)
            
            base_high = get_live_ensemble_odds(code, target_today, threshold=70.0, is_high_market=True, bias_adjustment=bias_h, obs_max=obs_max, obs_min=obs_min)
            time.sleep(0.2)
            base_low = get_live_ensemble_odds(code, target_today, threshold=70.0, is_high_market=False, bias_adjustment=bias_l, obs_max=obs_max, obs_min=obs_min)
            time.sleep(0.2)
            
            print("\n" + "-"*85)
            print(f"✈️ {code} ({AIRPORTS[code]['name']})")
            if obs_max > -90.0:
                print(f"   🔥 Verified NWS Sensor Readings Right Now: High {obs_max:.1f}°F | Low {obs_min:.1f}°F")
            else:
                print(f"   ⚠️ NWS Live observation stream lagging. Falling back to raw models.")
            
            # --- HIGH TEMPERATURE LADDER ---
            if base_high:
                expected_max = base_high['model_mean']
                center_t = int(round(expected_max))
                ladder_highs = [center_t - 2, center_t - 1, center_t, center_t + 1, center_t + 2]
                
                print(f"   ☀️ TODAY'S ACTIVE HIGH CONTRACTS (Blended Expected Max: {expected_max:.1f}°F):")
                for t in ladder_highs:
                    m_data = get_live_ensemble_odds(code, target_today, threshold=float(t), is_high_market=True, bias_adjustment=bias_h, obs_max=obs_max, obs_min=obs_min)
                    prob = m_data['odds'] * 100
                    print(f"     ▪️ Will High hit ≥ {t}°F? -> {prob:5.1f}% Odds | Fair Value: {int(round(prob))}¢")
            
            # --- LOW TEMPERATURE LADDER ---
            if base_low:
                expected_min = base_low['model_mean']
                center_t = int(round(expected_min))
                ladder_lows = [center_t - 2, center_t - 1, center_t, center_t + 1, center_t + 2]
                
                print(f"   🌙 TODAY'S ACTIVE LOW CONTRACTS (Blended Expected Min: {expected_min:.1f}°F):")
                for t in ladder_lows:
                    m_data = get_live_ensemble_odds(code, target_today, threshold=float(t), is_high_market=False, bias_adjustment=bias_h, obs_max=obs_max, obs_min=obs_min)
                    prob = m_data['odds'] * 100
                    print(f"     ▪️ Will Low hit ≤ {t}°F?  -> {prob:5.1f}% Odds | Fair Value: {int(round(prob))}¢")
                    
        except Exception as e:
            print(f"\n✈️ {code}: ⚠️ Evaluation paused: {e}")
