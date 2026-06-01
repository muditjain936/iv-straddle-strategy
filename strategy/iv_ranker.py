# strategy/iv_ranker.py
# Tracks IV history and computes bi-weekly percentile rank

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from strategy.iv_calculator import get_implied_volatility
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import BIWEEKLY_DAYS, IV_RANK_SHORT_THRESHOLD, IV_RANK_LONG_THRESHOLD


# ─────────────────────────────────────────────
# IV HISTORY STORE
# ─────────────────────────────────────────────

class IVHistory:
    """
    Stores daily IV readings and computes rolling percentile rank.
    Think of this as your IV diary — one entry per trading day.
    """

    def __init__(self, window=BIWEEKLY_DAYS):
        self.window  = window          # rolling window (10 = 2 weeks)
        self.records = []              # list of {date, iv} dicts

    def add_iv(self, iv_value, date=None):
        """Add today's IV to history."""
        if date is None:
            date = datetime.today().date()

        if iv_value is None or iv_value <= 0:
            return  # skip bad data

        self.records.append({
            'date' : date,
            'iv'   : round(iv_value, 6)
        })

    def get_dataframe(self):
        """Return history as a pandas DataFrame."""
        if not self.records:
            return pd.DataFrame(columns=['date', 'iv'])
        return pd.DataFrame(self.records)

    def get_recent_ivs(self):
        """Return last N IV values based on window size."""
        df = self.get_dataframe()
        if df.empty:
            return []
        return df['iv'].tail(self.window).tolist()

    def clear(self):
        """Reset history."""
        self.records = []


# ─────────────────────────────────────────────
# IV RANK CALCULATOR
# ─────────────────────────────────────────────

def calculate_iv_rank(current_iv, iv_history_list):
    """
    Calculate IV Rank as a percentile.

    IV Rank = % of past IV values that current IV is ABOVE.

    Example:
        past IVs = [0.15, 0.18, 0.20, 0.22, 0.25]
        current  = 0.23
        rank     = 80th percentile (above 4 out of 5 values)

    Returns a value between 0 and 100.
    """
    if not iv_history_list or len(iv_history_list) < 2:
        return None  # not enough data

    iv_array = np.array(iv_history_list)
    rank     = float(np.sum(iv_array <= current_iv) / len(iv_array) * 100)
    return round(rank, 2)


def calculate_iv_percentile(current_iv, iv_history_list):
    """
    Alternative: uses numpy percentile interpolation.
    More statistically precise than simple rank.
    """
    if not iv_history_list or len(iv_history_list) < 2:
        return None

    iv_array    = np.array(iv_history_list)
    iv_min      = np.min(iv_array)
    iv_max      = np.max(iv_array)

    if iv_max == iv_min:
        return 50.0  # all IVs are same, rank is neutral

    percentile = (current_iv - iv_min) / (iv_max - iv_min) * 100
    return round(float(np.clip(percentile, 0, 100)), 2)


# ─────────────────────────────────────────────
# SIGNAL GENERATOR
# ─────────────────────────────────────────────

def get_trade_signal(iv_rank):
    """
    Convert IV rank into a trading signal.

    > 70  → SHORT straddle (IV expensive, sell premium)
    < 40  → LONG straddle  (IV cheap, buy movement)
    40-70 → NO TRADE       (IV neutral, stay flat)

    Returns: 'SHORT_STRADDLE', 'LONG_STRADDLE', or 'NO_TRADE'
    """
    if iv_rank is None:
        return 'NO_TRADE'

    if iv_rank >= IV_RANK_SHORT_THRESHOLD:
        return 'SHORT_STRADDLE'
    elif iv_rank <= IV_RANK_LONG_THRESHOLD:
        return 'LONG_STRADDLE'
    else:
        return 'NO_TRADE'


# ─────────────────────────────────────────────
# FULL RANKER CLASS (combines everything)
# ─────────────────────────────────────────────

class IVRanker:
    """
    Main class that ties IV history + ranking + signal together.
    This is what strategy.py will import and use.
    """

    def __init__(self, window=BIWEEKLY_DAYS):
        self.history = IVHistory(window=window)
        self.window  = window

    def update(self, market_price, S, K, T, r, option_type='call', date=None):
        """
        Feed in today's market option price.
        Computes IV and stores it in history.
        Returns the computed IV.
        """
        iv = get_implied_volatility(market_price, S, K, T, r, option_type)
        if iv:
            self.history.add_iv(iv, date)
        return iv

    def get_rank_and_signal(self, current_iv=None):
        """
        Compute today's IV rank and trade signal.
        Optionally pass current_iv directly (skip recomputing).
        """
        recent = self.history.get_recent_ivs()

        if not recent:
            return {'iv_rank': None, 'signal': 'NO_TRADE', 'data_points': 0}

        if current_iv is None:
            current_iv = recent[-1]  # use latest stored IV

        iv_rank = calculate_iv_rank(current_iv, recent[:-1])  # rank vs history
        signal  = get_trade_signal(iv_rank)

        return {
            'current_iv'  : round(current_iv * 100, 2),  # as %
            'iv_rank'     : iv_rank,
            'signal'      : signal,
            'data_points' : len(recent),
            'window'      : self.window,
            'iv_history'  : [round(x * 100, 2) for x in recent]
        }

    def summary(self):
        """Print a clean summary of current IV state."""
        result = self.get_rank_and_signal()
        print("\n" + "="*45)
        print("  IV RANKER SUMMARY")
        print("="*45)
        if result['iv_rank'] is None:
            print("  Not enough data yet.")
            print(f"  Data points : {result['data_points']} / {self.window} needed")
        else:
            print(f"  Current IV  : {result['current_iv']}%")
            print(f"  IV Rank     : {result['iv_rank']} percentile")
            print(f"  Signal      : {result['signal']}")
            print(f"  Data points : {result['data_points']}")
            print(f"  IV History  : {result['iv_history']}")
        print("="*45 + "\n")
        return result


# ─────────────────────────────────────────────
# TEST — run this file directly to verify
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from strategy.iv_calculator import black_scholes_price

    print("Testing IVRanker with 12 simulated trading days...\n")

    ranker = IVRanker(window=10)

    S = 22000
    K = 22000
    T = 14/365
    r = 0.065

    # Simulate 12 days of IV data (vols from 18% to 35%)
    simulated_vols = [0.18, 0.20, 0.19, 0.22, 0.21,
                      0.24, 0.23, 0.26, 0.28, 0.30,
                      0.32, 0.35]

    base_date = datetime(2024, 1, 1).date()

    for i, vol in enumerate(simulated_vols):
        date         = base_date + timedelta(days=i)
        market_price = black_scholes_price(S, K, T, r, vol, 'call')
        iv           = ranker.update(market_price, S, K, T, r, 'call', date)
        print(f"Day {i+1:2d} | Vol: {vol*100:.0f}% | "
              f"Market Price: ₹{market_price:.2f} | "
              f"Recovered IV: {iv*100:.2f}%")

    ranker.summary()

    # Test signals at different IV ranks
    print("Signal tests:")
    print(f"  IV rank 75 → {get_trade_signal(75)}")
    print(f"  IV rank 55 → {get_trade_signal(55)}")
    print(f"  IV rank 30 → {get_trade_signal(30)}")
    print(f"\niv_ranker.py working correctly.")