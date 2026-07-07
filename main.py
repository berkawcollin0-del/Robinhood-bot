import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LinearRegression

class StatArbEngine:
    def __init__(self, n_factors=5, window_size=60):
        self.n_factors = n_factors
        self.window_size = window_size
        
    def extract_residuals(self, returns_df):
        """
        Step 1 & 2: Use PCA to find macro factors, then regress them out 
        to isolate the idiosyncratic residuals for each stock.
        """
        # Fit PCA on the returns matrix to find dominant latent factors
        pca = PCA(n_components=self.n_factors)
        factors = pca.fit_transform(returns_df)
        
        residuals = pd.DataFrame(index=returns_df.index, columns=returns_df.columns)
        
        # Regress each stock against the common factors
        for stock in returns_df.columns:
            y = returns_df[stock].values
            reg = LinearRegression().fit(factors, y)
            # Residual = Actual Return - Systematic Return
            residuals[stock] = y - reg.predict(factors)
            
        return residuals

    def fit_ou_process(self, cumulative_residuals):
        """
        Step 3 & 4: Fit an AR(1) process to model the Ornstein-Uhlenbeck parameters
        and calculate the standardized S-Score.
        """
        # Discretized OU: X_t = a + b * X_{t-1} + error
        x_lag = cumulative_residuals.shift(1).dropna().values.reshape(-1, 1)
        x_curr = cumulative_residuals.loc[cumulative_residuals.index[1:]].values
        
        reg = LinearRegression().fit(x_lag, x_curr)
        a = reg.intercept_
        b = reg.coef_[0]
        
        # A valid mean-reverting spring requires 0 < b < 1
        if b <= 0 or b >= 1:
            return {"half_life": np.nan, "s_score": np.nan}
        
        # Calculate OU continuous-time parameters (assuming dt = 1 day)
        kappa = -np.log(b)
        theta = a / (1 - b)
        
        # Calculate residuals of the AR(1) fit to find variance
        fit_residuals = x_curr - reg.predict(x_lag)
        sigma_zeta = np.std(fit_residuals)
        
        # Equilibrium variance of the OU process
        sigma_eq = np.sqrt(sigma_zeta**2 / (1 - b**2))
        
        # Calculate half-life of mean reversion (in days)
        half_life = np.log(2) / kappa
        
        # S-Score = current distance from fair value normalized by equilibrium volatility
        current_x = cumulative_residuals.iloc[-1]
        s_score = (current_x - theta) / sigma_eq
        
        return {"half_life": half_life, "s_score": s_score}

    def generate_signals(self, returns_df):
        """
        Executes the pipeline over the specified lookback window.
        """
        # Keep only the window required for analysis
        window_returns = returns_df.tail(self.window_size)
        residuals = self.extract_residuals(window_returns)
        
        # Convert daily residual returns into a cumulative price-like track
        cumulative_residuals = residuals.cumsum()
        
        results = {}
        for stock in returns_df.columns:
            ou_params = self.fit_ou_process(cumulative_residuals[stock])
            results[stock] = ou_params
            
        # Format into an actionable dashboard
        df_signals = pd.DataFrame(results).T
        df_signals['Signal'] = 'HOLD / NO SIGNAL'
        df_signals.loc[df_signals['s_score'] > 1.25, 'Signal'] = 'SHORT (Overvalued)'
        df_signals.loc[df_signals['s_score'] < -1.25, 'Signal'] = 'LONG (Undervalued)'
        df_signals.loc[(df_signals['s_score'].abs() < 0.2), 'Signal'] = 'CLOSE POSITION'
        
        return df_signals

# =====================================================================
# SIMULATION & VERIFICATION
# =====================================================================
if __name__ == "__main__":
    np.random.seed(42)
    days, n_stocks = 100, 10
    tickers = [f"STK_{i}" for i in range(n_stocks)]
    
    # Generate mock systemic market factors
    market_factor = np.random.normal(0.0005, 0.01, days)
    sector_factor = np.random.normal(0.0002, 0.01, days)
    
    mock_returns = {}
    for ticker in tickers:
        beta_m = np.random.uniform(0.5, 1.5)
        beta_s = np.random.uniform(-0.5, 1.0)
        
        # Inject an artificially mean-reverting idiosyncratic shock into STK_0
        if ticker == "STK_0":
            # Highly stretched negative residual (simulating a severe overreaction)
            idiosyncratic = np.random.normal(0, 0.005, days)
            idiosyncratic[-1] = -0.08  
        else:
            idiosyncratic = np.random.normal(0, 0.01, days)
            
        mock_returns[ticker] = beta_m * market_factor + beta_s * sector_factor + idiosyncratic

    df_market_data = pd.DataFrame(mock_returns, index=pd.date_range(end='2026-07-06', periods=days))
    
    # Run Engine
    engine = StatArbEngine(n_factors=2, window_size=60)
    signal_dashboard = engine.generate_signals(df_market_data)
    
    print("\n=== QUANT STAT-ARB TRADING DASHBOARD ===")
    print(signal_dashboard.to_string())
