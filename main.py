import pandas as pd
import numpy as np

class OptionsAlphaBot:
    def __init__(self, target_tickers):
        self.tickers = target_tickers
        
    def calculate_technical_cross(self, historical_df):
        """
        Calculates moving averages and checks for Golden or Death crosses.
        historical_df requires columns: 'date', 'close'
        """
        historical_df['SMA50'] = historical_df['close'].rolling(window=50).mean()
        historical_df['SMA200'] = historical_df['close'].rolling(window=200).mean()
        
        latest = historical_df.iloc[-1]
        previous = historical_df.iloc[-2]
        
        # Check Cross Conditions
        is_golden_cross = (previous['SMA50'] <= previous['SMA200']) and (latest['SMA50'] > latest['SMA200'])
        is_death_cross = (previous['SMA50'] >= previous['SMA200']) and (latest['SMA50'] < latest['SMA200'])
        
        # Trend continuation state
        current_trend = "BULLISH" if latest['SMA50'] > latest['SMA200'] else "BEARISH"
        
        return {
            "is_golden": is_golden_cross,
            "is_death": is_death_cross,
            "current_trend": current_trend,
            "sma50": latest['SMA50'],
            "sma200": latest['SMA200']
        }

    def filter_and_aggregate_uoa(self, flow_df):
        """
        Filters raw options flow to isolate direction and strip out hedges.
        Filters used:
        1. Multi-exchange sweep orders only (Aggressive institutional positioning)
        2. Trade size must exceed current Open Interest (OI)
        3. Transaction must hit Ask (Bullish Call / Bearish Put) or Bid (Bearish Call / Bullish Put)
        4. Size must be institutional-grade (> $100k premium)
        """
        # 1. Isolate Sweeps with significant premium
        filtered = flow_df[
            (flow_df['trade_type'] == 'SWEEP') & 
            (flow_df['premium'] >= 100000) & 
            (flow_df['volume'] > flow_df['open_interest'])
        ].copy()
        
        # 2. Determine net bias based on execution side (Ask vs Bid)
        # Standard Hedging Filter: Exclude neutral mid-market or block crosses which are likely complex spreads.
        filtered['net_bias'] = np.where(
            ((filtered['option_type'] == 'CALL') & (filtered['side'] == 'ASK')) |
            ((filtered['option_type'] == 'PUT') & (filtered['side'] == 'BID')), 
            'BULLISH', 'BEARISH'
        )
        
        # Strip trades occurring exactly at the MID price (often multi-leg hedges or spreads)
        filtered = filtered[filtered['side'].isin(['ASK', 'BID'])]
        
        return filtered

    def score_trade(self, tech_setup, filtered_flow, current_price):
        """
        Evaluates the strength of alignment between UOA and Technical setups.
        Scores from 0 to 100.
        """
        if filtered_flow.empty:
            return None
            
        # Group to find the most dominant option contract being targeted
        dominant_contract = filtered_flow.groupby(['strike', 'expiration', 'option_type', 'net_bias']).agg({
            'premium': 'sum',
            'volume': 'sum',
            'open_interest': 'first'
        }).reset_index().sort_values(by='premium', ascending=False).iloc[0]
        
        score = 50 # Base score if UOA exists
        
        # Factor 1: Multiplier for volume over open interest
        oi_multiplier = dominant_contract['volume'] / max(dominant_contract['open_interest'], 1)
        if oi_multiplier > 3: score += 15
        elif oi_multiplier > 1.5: score += 10
        
        # Factor 2: Technical Cross Alignment
        if tech_setup['is_golden'] and dominant_contract['net_bias'] == 'BULLISH':
            score += 35 # High-conviction Golden Cross breakout
        elif tech_setup['is_death'] and dominant_contract['net_bias'] == 'BEARISH':
            score += 35 # High-conviction Death Cross breakdown
        elif tech_setup['current_trend'] == dominant_contract['net_bias']:
            score += 15 # Aligned with long term macro-trend
        else:
            score -= 30 # Disconnected from macro trend (Likely counter-trend trade or a hedge)

        # Caps score at 100, floor at 0
        score = max(0, min(100, score))
        
        # Only surface trades with a score threshold >= 70
        if score < 70:
            return None
            
        return {
            "score": score,
            "contract": dominant_contract,
            "bias": dominant_contract['net_bias']
        }

    def generate_signal(self, ticker, historical_data, raw_flow_data, current_price):
        """
        Main runner function analyzing a ticker for actionable setups.
        """
        # Run pipelines
        tech = self.calculate_technical_cross(historical_data)
        clean_flow = self.filter_and_aggregate_uoa(raw_flow_data)
        
        trade_evaluation = self.score_trade(tech, clean_flow, current_price)
        
        if not trade_evaluation:
            return f"[{ticker}] No high-conviction trade set up found. Flow and Technicals lack alignment."
            
        contract = trade_evaluation['contract']
        score = trade_evaluation['score']
        
        # Formulate Trade Execution Logic
        # For long options, we build exit strategies relative to the underlying security's key technical levels
        entry_trigger = current_price
        
        if trade_evaluation['bias'] == 'BULLISH':
            # Take Profit: Target the next resistance or a 50% contract premium expansion
            target_price = round(current_price * 1.06, 2) 
            # Hard stop under the 50 SMA or a max 3% drop in underlying price
            stop_loss = round(min(tech['sma50'], current_price * 0.97), 2)
        else:
            target_price = round(current_price * 0.94, 2)
            stop_loss = round(max(tech['sma50'], current_price * 1.03), 2)

        # Output Structured Order Ticket
        output = f"""
==================================================
🚨 SIGNAL GENERATED: {ticker} (Score: {score}/100)
==================================================
• Setup Type: {'GOLDEN CROSS + CALL SWEEPS' if tech['is_golden'] else 'DEATH CROSS + PUT SWEEPS' if tech['is_death'] else 'TREND CONTINUATION + FLOW'}
• Underlying Spot Price: ${current_price}

• EXACT OPTION TO TAKE: 
  {ticker} ${contract['strike']} {contract['option_type']} (Exp: {contract['expiration']})
  [Context: Vol/OI Ratio: {round(contract['volume']/max(contract['open_interest'],1), 2)}x | Aggregate Contract Premium: ${contract['premium']:,}]

• TRADE EXECUTION MATRIX (Based on Underlying Asset Price):
  -> ENTRY POINT: Market Order at current spot (${entry_trigger})
  -> EXIT (PROFIT TARGET): ${target_price} 
  -> EXIT (STOP LOSS): ${stop_loss}
==================================================
"""
        return output

# ==========================================
# SIMULATION / EXAMPLE USAGE
# ==========================================
if __name__ == "__main__":
    # 1. Instantiate Bot
    bot = OptionsAlphaBot(target_tickers=["NVDA"])
    
    # 2. Mocking Technical Data (Simulating a Golden Cross event)
    # 50 SMA crosses above 200 SMA on the last day
    hist_data = pd.DataFrame({
        'date': pd.date_range(start='2026-01-01', periods=5),
        'close': [120, 122, 121, 125, 131]
    })
    # Forcing indicators to trigger a cross pattern internally
    bot_tech_mock = {
        'is_golden': True, 'is_death': False, 'current_trend': 'BULLISH', 'sma50': 124.5, 'sma200': 124.0
    }
    
    # 3. Mocking Raw Institutional Options Flow
    # Includes standard trades, mixed bids, and a massive sweep that exceeds Open Interest on the Ask side
    raw_flow = pd.DataFrame([
        {'trade_type': 'BLOCK', 'premium': 50000, 'volume': 100, 'open_interest': 5000, 'option_type': 'CALL', 'side': 'MID', 'strike': 135, 'expiration': '2026-07-17'},
        {'trade_type': 'SWEEP', 'premium': 450000, 'volume': 8500, 'open_interest': 2000, 'option_type': 'CALL', 'side': 'ASK', 'strike': 135, 'expiration': '2026-07-17'},
        {'trade_type': 'SWEEP', 'premium': 120000, 'volume': 300, 'open_interest': 4000, 'option_type': 'PUT', 'side': 'BID', 'strike': 120, 'expiration': '2026-06-26'}
    ])
    
    # Override technical method to ingest our simulation parameters directly
    bot.calculate_technical_cross = lambda x: bot_tech_mock
    
    # 4. Generate Signal
    trade_ticket = bot.generate_signal(
        ticker="NVDA", 
        historical_data=hist_data, 
        raw_flow_data=raw_flow, 
        current_price=131.00
    )
    
    print(trade_ticket)
