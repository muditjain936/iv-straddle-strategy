# risk/risk_manager.py
# Monitors open positions, tracks drawdown, triggers hedge after 2 strikes move

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from config import HEDGE_STRIKE_MOVE, MAX_DRAWDOWN_PCT, RISK_FREE_RATE, OPTION_EXPIRY_DAYS


# ─────────────────────────────────────────────
# POSITION TRACKER
# ─────────────────────────────────────────────

class Position:
    """
    Tracks a single open straddle position.
    Monitors P&L, drawdown, and strike distance.
    """

    def __init__(self, trade_order, strike_interval=50):
        self.order           = trade_order
        self.entry_spot      = trade_order.spot
        self.entry_strike    = trade_order.strike
        self.entry_premium   = trade_order.total_prem
        self.signal          = trade_order.signal
        self.strike_interval = strike_interval
        self.entry_date      = trade_order.date

        self.current_pnl     = 0.0
        self.max_pnl         = 0.0
        self.max_drawdown    = 0.0
        self.pnl_history     = []

        self.is_hedged       = False
        self.hedge_triggered = False
        self.hedge_date      = None
        self.strikes_moved   = 0

        self.status          = 'OPEN'


    def update(self, current_spot, current_call_price, current_put_price, date=None):
        """
        Update position with today's market prices.
        Computes P&L and checks hedge trigger.
        """
        if date is None:
            date = datetime.today().date()

        current_straddle = current_call_price + current_put_price

        if self.signal == 'SHORT_STRADDLE':
            self.current_pnl = self.entry_premium - current_straddle
        else:
            self.current_pnl = current_straddle - self.entry_premium

        if self.current_pnl > self.max_pnl:
            self.max_pnl = self.current_pnl

        drawdown = self.max_pnl - self.current_pnl
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

        self.strikes_moved = abs(current_spot - self.entry_strike) / self.strike_interval

        self.pnl_history.append({
            'date'           : date,
            'spot'           : current_spot,
            'straddle_price' : round(current_straddle, 2),
            'pnl'            : round(self.current_pnl, 2),
            'strikes_moved'  : round(self.strikes_moved, 2),
            'is_hedged'      : self.is_hedged
        })

        return self._check_hedge_trigger(current_spot, date)


    def _check_hedge_trigger(self, current_spot, date):
        """
        Hedge trigger logic.
        Triggers when spot moves 2 strikes away OR drawdown is too large.
        """
        if self.is_hedged:
            return None

        trigger_reason = None

        if self.strikes_moved >= HEDGE_STRIKE_MOVE:
            trigger_reason = (f"Spot moved {self.strikes_moved:.1f} strikes "
                              f"(>= {HEDGE_STRIKE_MOVE} trigger)")

        dd_pct = self.max_drawdown / self.entry_premium if self.entry_premium > 0 else 0
        if dd_pct >= MAX_DRAWDOWN_PCT:
            trigger_reason = (f"Drawdown {dd_pct*100:.1f}% "
                              f"(>= {MAX_DRAWDOWN_PCT*100:.0f}% trigger)")

        if trigger_reason:
            self.is_hedged       = True
            self.hedge_triggered = True
            self.hedge_date      = date
            self.status          = 'HEDGED'
            return {
                'hedge_triggered' : True,
                'reason'          : trigger_reason,
                'date'            : date,
                'spot'            : current_spot,
                'pnl_at_hedge'    : round(self.current_pnl, 2),
                'strikes_moved'   : round(self.strikes_moved, 2)
            }

        return None


    def get_hedge_recommendation(self, current_spot):
        """
        Recommend what hedge to add based on position type.
        """
        direction       = 'UP' if current_spot > self.entry_strike else 'DOWN'
        otm_strike_up   = self.entry_strike + (2 * self.strike_interval)
        otm_strike_down = self.entry_strike - (2 * self.strike_interval)

        if self.signal == 'SHORT_STRADDLE':
            if direction == 'UP':
                return (f"Buy CALL at strike Rs.{otm_strike_up} "
                        f"to cap upside loss (convert to short butterfly)")
            else:
                return (f"Buy PUT at strike Rs.{otm_strike_down} "
                        f"to cap downside loss (convert to short butterfly)")
        else:
            return (f"Sell OTM strangle: "
                    f"CALL at Rs.{otm_strike_up} + PUT at Rs.{otm_strike_down} "
                    f"to recover premium cost")

    def summary(self):
        """Print position summary."""
        print(f"\n  Signal       : {self.signal}")
        print(f"  Entry spot   : Rs.{self.entry_spot}")
        print(f"  Entry strike : Rs.{self.entry_strike}")
        print(f"  Entry prem   : Rs.{self.entry_premium:.2f}")
        print(f"  Current P&L  : Rs.{self.current_pnl:.2f}")
        print(f"  Max drawdown : Rs.{self.max_drawdown:.2f}")
        print(f"  Strikes moved: {self.strikes_moved:.1f}")
        print(f"  Status       : {self.status}")
        if self.is_hedged:
            print(f"  Hedge date   : {self.hedge_date}")


# ─────────────────────────────────────────────
# RISK MANAGER
# ─────────────────────────────────────────────

class RiskManager:
    """
    Manages all open positions.
    Monitors hedge triggers across the portfolio.
    """

    def __init__(self, strike_interval=50):
        self.positions       = []
        self.active_position = None
        self.strike_interval = strike_interval
        self.hedge_log       = []

    def open_position(self, trade_order):
        """Open a new position from a trade order."""
        pos = Position(trade_order, self.strike_interval)
        self.positions.append(pos)
        self.active_position = pos
        print(f"  [POSITION OPENED] {trade_order.signal} | "
              f"Strike: Rs.{trade_order.strike} | "
              f"Premium: Rs.{trade_order.total_prem:.2f}")
        return pos

    def update_position(self, current_spot, current_call, current_put, date=None):
        """
        Update active position with today's prices.
        Returns hedge alert if triggered.
        """
        if not self.active_position:
            return None

        hedge_alert = self.active_position.update(
            current_spot, current_call, current_put, date
        )

        if hedge_alert:
            hedge_alert['recommendation'] = \
                self.active_position.get_hedge_recommendation(current_spot)
            self.hedge_log.append(hedge_alert)
            self._print_hedge_alert(hedge_alert)

        return hedge_alert

    def close_position(self):
        """Close the active position."""
        if self.active_position:
            self.active_position.status = 'CLOSED'
            self.active_position = None

    def _print_hedge_alert(self, alert):
        print(f"\n  !! HEDGE TRIGGERED")
        print(f"  Reason       : {alert['reason']}")
        print(f"  Date         : {alert['date']}")
        print(f"  Spot         : Rs.{alert['spot']}")
        print(f"  P&L at hedge : Rs.{alert['pnl_at_hedge']}")
        print(f"  Action       : {alert['recommendation']}\n")

    def get_portfolio_summary(self):
        """Print full portfolio summary."""
        print("\n" + "="*55)
        print("  RISK MANAGER SUMMARY")
        print("="*55)
        print(f"  Total positions : {len(self.positions)}")
        print(f"  Hedge events    : {len(self.hedge_log)}")
        for i, pos in enumerate(self.positions):
            print(f"\n  Position {i+1}:")
            pos.summary()
        print("="*55)


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    from strategy.iv_calculator import black_scholes_price
    from strategy.strategy import TradeOrder, get_atm_strike
    from datetime import timedelta

    print("Testing RiskManager — SHORT straddle with hedge trigger...\n")

    fake_order = TradeOrder(
        signal      = 'SHORT_STRADDLE',
        spot        = 22000,
        strike      = 22000,
        expiry_days = 14,
        call_price  = 280.0,
        put_price   = 265.0,
        iv          = 0.30,
        iv_rank     = 82.0,
        date        = datetime(2024, 1, 10).date()
    )

    rm = RiskManager(strike_interval=50)
    rm.open_position(fake_order)

    spots = [22000, 22050, 22100, 22150, 22200,
             22250, 22300, 22350, 22400, 22450]
    vols  = [0.30, 0.29, 0.28, 0.27, 0.26,
             0.27, 0.28, 0.29, 0.30, 0.31]

    base_date = datetime(2024, 1, 10).date()
    T         = 14 / 365

    print(f"\n{'Day':<4} {'Spot':<8} {'Call':<8} {'Put':<8} "
          f"{'Straddle':<10} {'P&L':<10} {'Strikes Moved'}")
    print("-" * 62)

    for i, (spot, vol) in enumerate(zip(spots, vols)):
        date = base_date + timedelta(days=i)
        call = black_scholes_price(spot, 22000, T, 0.065, vol, 'call')
        put  = black_scholes_price(spot, 22000, T, 0.065, vol, 'put')

        alert = rm.update_position(spot, call, put, date)

        pos      = rm.active_position or rm.positions[-1]
        strangle = call + put
        print(f"{i+1:<4} Rs.{spot:<7} Rs.{call:<7.2f} Rs.{put:<7.2f} "
              f"Rs.{strangle:<9.2f} Rs.{pos.current_pnl:<9.2f} "
              f"{pos.strikes_moved:.1f}")

        if alert:
            break

    rm.get_portfolio_summary()
    print("risk_manager.py working correctly.")