# strategy/strategy.py
# Core strategy engine — generates straddle trade orders

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from config import (IV_RANK_SHORT_THRESHOLD, IV_RANK_LONG_THRESHOLD,
                    OPTION_EXPIRY_DAYS, RISK_FREE_RATE)
from strategy.iv_ranker import IVRanker, get_trade_signal


# ─────────────────────────────────────────────
# TRADE ORDER OBJECT
# ─────────────────────────────────────────────

class TradeOrder:
    """
    Represents a single straddle trade order.
    Created by the strategy engine, consumed by risk manager.
    """

    def __init__(self, signal, spot, strike, expiry_days,
                 call_price, put_price, iv, iv_rank, date=None):
        self.signal      = signal           # SHORT_STRADDLE / LONG_STRADDLE
        self.spot        = spot             # underlying price at entry
        self.strike      = strike           # ATM strike
        self.expiry_days = expiry_days      # days to expiry
        self.call_price  = call_price       # call leg price
        self.put_price   = put_price        # put leg price
        self.total_prem  = call_price + put_price  # total straddle premium
        self.iv          = iv               # implied volatility at entry
        self.iv_rank     = iv_rank          # IV percentile rank
        self.date        = date or datetime.today().date()
        self.status      = 'OPEN'           # OPEN / CLOSED / HEDGED

    def __repr__(self):
        return (f"TradeOrder({self.signal} | "
                f"Spot: ₹{self.spot} | Strike: ₹{self.strike} | "
                f"Premium: ₹{self.total_prem:.2f} | "
                f"IV: {self.iv*100:.1f}% | Rank: {self.iv_rank})")


# ─────────────────────────────────────────────
# ATM STRIKE FINDER
# ─────────────────────────────────────────────

def get_atm_strike(spot_price, strike_interval=50):
    """
    Find the nearest ATM (At The Money) strike.
    NIFTY strikes are in multiples of 50.
    BANKNIFTY strikes are in multiples of 100.

    Example: spot = 22134 → ATM strike = 22150
    """
    return round(spot_price / strike_interval) * strike_interval


# ─────────────────────────────────────────────
# STRADDLE PRICER
# ─────────────────────────────────────────────

def price_straddle(spot, strike, T, r, iv):
    """
    Price both legs of a straddle using Black-Scholes.
    Returns (call_price, put_price).
    """
    from strategy.iv_calculator import black_scholes_price
    call = black_scholes_price(spot, strike, T, r, iv, 'call')
    put  = black_scholes_price(spot, strike, T, r, iv, 'put')
    return round(call, 2), round(put, 2)


# ─────────────────────────────────────────────
# MAIN STRATEGY ENGINE
# ─────────────────────────────────────────────

class StraddleStrategy:
    """
    Core strategy engine.

    Each day:
      1. Receives market option price
      2. Computes IV via reverse Black-Scholes
      3. Updates IV history
      4. Ranks IV in bi-weekly window
      5. Generates trade signal
      6. Creates TradeOrder if signal is actionable
    """

    def __init__(self, strike_interval=50, expiry_days=OPTION_EXPIRY_DAYS,
                 risk_free_rate=RISK_FREE_RATE):
        self.ranker          = IVRanker()
        self.strike_interval = strike_interval
        self.expiry_days     = expiry_days
        self.r               = risk_free_rate
        self.active_trade    = None     # current open trade
        self.trade_log       = []       # all historical trades
        self.daily_log       = []       # day-by-day state log

    def process_day(self, spot, market_call_price, date=None):
        """
        Process a single trading day.

        spot              = underlying price (e.g. NIFTY level)
        market_call_price = ATM call option market price
        date              = trading date

        Returns a dict with full state for that day.
        """
        if date is None:
            date = datetime.today().date()

        T      = self.expiry_days / 365
        strike = get_atm_strike(spot, self.strike_interval)

        # Step 1: compute IV from market price
        iv = self.ranker.update(market_call_price, spot, strike, T, self.r,
                                'call', date)

        # Step 2: get IV rank and signal
        result = self.ranker.get_rank_and_signal()
        signal   = result['signal']
        iv_rank  = result['iv_rank']

        # Step 3: price the full straddle
        call_px, put_px = price_straddle(spot, strike, T, self.r,
                                          iv if iv else 0.20)

        # Step 4: generate trade order if no active trade
        order = None
        if signal != 'NO_TRADE' and self.active_trade is None:
            order = TradeOrder(
                signal      = signal,
                spot        = spot,
                strike      = strike,
                expiry_days = self.expiry_days,
                call_price  = call_px,
                put_price   = put_px,
                iv          = iv if iv else 0.0,
                iv_rank     = iv_rank,
                date        = date
            )
            self.active_trade = order
            self.trade_log.append(order)

        # Step 5: log the day
        day_state = {
            'date'       : date,
            'spot'       : spot,
            'strike'     : strike,
            'iv'         : round(iv * 100, 2) if iv else None,
            'iv_rank'    : iv_rank,
            'signal'     : signal,
            'call_price' : call_px,
            'put_price'  : put_px,
            'straddle'   : round(call_px + put_px, 2),
            'order'      : order
        }
        self.daily_log.append(day_state)
        return day_state

    def close_active_trade(self):
        """Mark the current active trade as closed."""
        if self.active_trade:
            self.active_trade.status = 'CLOSED'
            self.active_trade = None

    def get_summary(self):
        """Print a summary of all signals generated."""
        print("\n" + "="*55)
        print("  STRATEGY ENGINE SUMMARY")
        print("="*55)
        print(f"  Total days processed : {len(self.daily_log)}")
        print(f"  Total trades placed  : {len(self.trade_log)}")
        print()
        for t in self.trade_log:
            print(f"  [{t.date}] {t.signal}")
            print(f"    Spot: ₹{t.spot} | Strike: ₹{t.strike}")
            print(f"    Premium collected : ₹{t.total_prem:.2f}")
            print(f"    IV: {t.iv*100:.1f}% | IV Rank: {t.iv_rank}")
            print()
        print("="*55)


# ─────────────────────────────────────────────
# TEST — run directly to verify
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from strategy.iv_calculator import black_scholes_price
    from datetime import timedelta

    print("Testing StraddleStrategy with 15 simulated days...\n")

    engine = StraddleStrategy(strike_interval=50, expiry_days=14)

    # Simulated NIFTY spot prices and vols over 15 days
    sim_data = [
        (22000, 0.18), (22100, 0.19), (22050, 0.20),
        (22200, 0.22), (22150, 0.21), (22300, 0.24),
        (22250, 0.26), (22400, 0.28), (22350, 0.30),
        (22500, 0.32), (22450, 0.34), (22600, 0.36),
        (22100, 0.28), (21900, 0.22), (21800, 0.19),
    ]

    base_date = datetime(2024, 1, 1).date()

    print(f"{'Day':<4} {'Date':<12} {'Spot':<8} {'IV%':<7} "
          f"{'Rank':<8} {'Signal':<18} {'Straddle ₹'}")
    print("-" * 70)

    for i, (spot, vol) in enumerate(sim_data):
        date      = base_date + timedelta(days=i)
        T         = 14 / 365
        strike    = get_atm_strike(spot)
        mkt_price = black_scholes_price(spot, strike, T, 0.065, vol, 'call')

        state = engine.process_day(spot, mkt_price, date)

        rank_str   = f"{state['iv_rank']:.1f}" if state['iv_rank'] else "N/A"
        iv_str     = f"{state['iv']:.1f}%" if state['iv'] else "N/A"
        order_flag = " ← TRADE" if state['order'] else ""

        print(f"{i+1:<4} {str(date):<12} ₹{spot:<7} {iv_str:<7} "
              f"{rank_str:<8} {state['signal']:<18} "
              f"₹{state['straddle']:<8.2f}{order_flag}")

    engine.get_summary()
    print("strategy.py working correctly.")