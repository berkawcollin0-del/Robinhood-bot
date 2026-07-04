import requests
import numpy as np
import pandas as pd
from scipy.stats import norm

# Station coordinate mapping for primary Kalshi settlement locations
KALSHI_STATIONS = {
    "NYC": {"lat": 40.7829, "lon": -73.9654, "desc": "Central Park (KNYC)"},
    "Chicago": {"lat": 41.9742, "lon": -87.9073, "desc": "O'Hare Airport (KORD)"},
    "Miami": {"lat": 25.7959, "lon": -80.2870, "desc": "Miami Int'l Airport (KMIA)"},
    "Austin": {"lat": 30.1945, "lon": -97.6664, "desc": "Austin-Bergstrom (KAUS)"},
    "LA": {"lat": 33.9416, "lon": -118.4085, "desc": "LAX Airport (KLAX)"},
    "Philly": {"lat": 39.8729, "lon": -75.2437, "desc": "Philadelphia Int'l (KPHL)"}
}

def analyze_threshold_market(city_code, target_date, threshold_f, model="gfs_seamless"):
    """
    Pulls live ensemble member tracks, isolates the daily max for each member,
    fits a normal distribution, and returns the threshold-crossing probability.
    
    city_code: str ('NYC', 'Chicago', etc.)
    target_date: str ('YYYY-MM-DD')
    threshold_f: float (e.g., 90.0)
    """
    if city_code not in KALSHI_STATIONS:
        raise ValueError(f"City code {city_code} not configured.")
        
    loc = KALSHI_STATIONS[city_code]
    
    # 1. Fetch raw ensemble members from Open-Meteo
    url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    params = {
        "latitude": loc["lat"],
        "longitude": loc["lon"],
        "hourly": "temperature_2m",
        "models": model,
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": 14
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        raise Exception(f"API Error: {response.text}")
        
    data = response.json()
    hourly = data.get("hourly", {})
    times = pd.to_datetime(hourly.get("time", []))
    
    # Identify all individual ensemble member keys
    member_keys = [k for k in hourly.keys() if k.startswith("temperature_2m_member_")]
    
    # 2. Extract the daily maximum temperature *per member* for the target date
    daily_maxes = []
    for member in member_keys:
        series = pd.Series(hourly[member], index=times)
        day_series = series[series.index.date == pd.to_datetime(target_date).date()]
        if not day_series.empty:
            daily_maxes.append(day_series.max())
            
    if not daily_maxes:
        raise ValueError(f"No forecast data returned for {target_date}. Check lead time.")

    # 3. Fit distribution to the spread of maximums
    mu = np.mean(daily_maxes)
    sigma = np.std(daily_maxes, ddof=1) if len(daily_maxes) > 1 else 0.1
    sigma = max(sigma, 0.1) # Prevent division by zero if variance is absolute zero
    
    # Compute the survival function (1 - CDF) for P(Max >= Threshold)
    prob_crossing = norm.sf(threshold_f, loc=mu, scale=sigma)
    
    print(f"=== MARKET ANALYSIS: {city_code} ({loc['desc']}) ===")
    print(f"Target Date: {target_date} | Threshold: ≥ {threshold_f}°F")
    print(f"Ensemble Model: {model} ({len(daily_maxes)} members parsed)")
    print(f"---")
    print(f"Ensemble Expected Max Mean: {mu:.2f}°F")
    print(f"Ensemble Spread (Std Dev):  {sigma:.2f}°F")
    print(f"Raw Range across Members:   {min(daily_maxes)}°F to {max(daily_maxes)}°F")
    print(f"---")
    print(f"MODEL PROBABILITY:          {prob_crossing * 100:.2f}%")
    print(f"Implied Fair Value Price:   {int(round(prob_crossing * 100))}¢")
    
    return {
        "mean": mu,
        "std": sigma,
        "probability": prob_crossing,
        "raw_maxes": daily_maxes
    }

# Example Usage:
# result = analyze_threshold_market("NYC", "2026-07-10", 90.0)
