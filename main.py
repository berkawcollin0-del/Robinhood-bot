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
    for i in range(retries):
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                time.sleep(backoff_factor ** i)
        except (requests.exceptions.RequestException, Exception):
            if i == retries - 1:
                raise
            time.sleep(backoff_factor ** i)
    raise requests.exceptions.ReadTimeout("Max retries exceeded.")

def get_realtime_observations_today(lat, lon, target_date):
    """
    Pulls the actual recorded hourly temperatures for today up to the current hour
    to prevent the bot from guessing on things that have already happened.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "hourly": "temperature_2m", "temperature_unit": "fahrenheit",
        "timezone": "auto", "forecast_days": 1
    }
    try:
        res = robust_get_request(url, params)
        hourly = res.get("hourly", {})
        times = pd.to_datetime(hourly.get("time", []))
        temps = hourly.get("temperature_2m", [])
        
        df = pd.DataFrame({"temp": temps}, index=times)
        # Filter for hours that have already occurred today in the local timezone
        now_local = datetime.datetime.now()
        observed_today = df[(df.index.date == pd.to_datetime(target_date).date()) & (df.index <= now_local)]
        
        if not observed_today.empty:
            return observed_today["temp"].max(), observed_today["temp"].min()
    except Exception:
        pass
    return -999.0, 999.0 # Fallbacks if station data has a brief reporting lag

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
            time.sleep(0.2)
        except Exception as e:
            print(f"⚠️ Error processing backtest for {code}: {e}")
            
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
            # Apply our historical model correction bias to the forecast slice
            corrected_forecast = day_series - bias_adjustment
            
            if is_high_market:
                # Intraday Blend: True daily high is the max of what ALREADY happened vs what is FORECAST to happen
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
    # AUTOMATICALLY TARGET TODAY
    today = datetime.date.today()
    target_today = today.strftime("%Y-%m-%d")
    
    # Slidback window dynamically updates relative to today
    backtest_start = (today - datetime.timedelta(days=35)).strftime("%Y-%m-%d")
    backtest_end = (today - datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    
    accuracy_df = backtest_airport_accuracy(backtest_start, backtest_end)
    if accuracy_df.empty:
        print("❌ Error: No backtest data gathered. Aborting run.")
        exit(1)
        
    ranked_cities = accuracy_df.sort_values(by="overall_score")
    
    print("\n" + "="*75)
    print(f"📊 LIVE INTRADAY TRADING ODDS FOR TODAY ONLY: {target_today}")
    print("="*75)
    print("Pulling live station observations and parsing the newest midday ensemble tracks...")
    
    for code in ranked_cities.index:
        try:
            bias_h = accuracy_df.loc[code, "bias_max"]
            bias_l = accuracy_df.loc[code, "bias_min"]
            
            # Fetch live ground-truth readings recorded so far today
            obs_max, obs_min = get_realtime_observations_today(AIRPORTS[code]["lat"], AIRPORTS[code]["lon"], target_today)
            
            # Baseline pull to construct the active ladder
            base_high = get_live_ensemble_odds(code, target_today, threshold=70.0, is_high_market=True, bias_adjustment=bias_h, obs_max=obs_max, obs_min=obs_min)
            time.sleep(0.2)
            base_low = get_live_ensemble_odds(code, target_today, threshold=70.0, is_high_market=False, bias_adjustment=bias_l, obs_max=obs_max, obs_min=obs_min)
            time.sleep(0.2)
            
            print("\n" + "-"*75)
            print(f"✈️ {code} ({AIRPORTS[code]['name']})")
            if obs_max > -90.0:
                print(f"   Station Recorded Real-Time Bounds So Far Today: High {obs_max:.1f}°F | Low {obs_min:.1f}°F")
            
            # --- HIGH TEMPERATURE LADDER ---
            if base_high:
                expected_max = base_high['model_mean']
                center_t = int(round(expected_max))
                ladder_highs = [center_t - 2, center_t - 1, center_t, center_t + 1, center_t + 2]
                
                print(f"\n   ☀️ TODAY'S ACTIVE HIGH CONTRACTS (Blended Expected Max: {expected_max:.1f}°F):")
                for t in ladder_highs:
                    m_data = get_live_ensemble_odds(code, target_today, threshold=float(t), is_high_market=True, bias_adjustment=bias_h, obs_max=obs_max, obs_min=obs_min)
                    prob = m_data['odds'] * 100
                    print(f"     ▪️ Will High hit ≥ {t}°F? -> {prob:5.1f}% Odds | Fair Value: {int(round(prob))}¢")
            
            # --- LOW TEMPERATURE LADDER ---
            if base_low:
                expected_min = base_low['model_mean']
                center_t = int(round(expected_min))
                ladder_lows = [center_t - 2, center_t - 1, center_t, center_t + 1, center_t + 2]
                
                print(f"\n   🌙 TODAY'S ACTIVE LOW CONTRACTS (Blended Expected Min: {expected_min:.1f}°F):")
                for t in ladder_lows:
                    m_data = get_live_ensemble_odds(code, target_today, threshold=float(t), is_high_market=False, bias_adjustment=bias_l, obs_max=obs_max, obs_min=obs_min)
                    prob = m_data['odds'] * 100
                    print(f"     ▪️ Will Low hit ≤ {t}°F?  -> {prob:5.1f}% Odds | Fair Value: {int(round(prob))}¢")
                    
        except Exception as e:
            print(f"\n✈️ {code}: ⚠️ Skipped live evaluation due to error: {e}")
