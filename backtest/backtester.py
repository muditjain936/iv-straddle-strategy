# backtest/backtester.py
# Runs the full strategy on historical data and reports P&L

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

from config import (BACKTEST_START, BACKTEST_END, INITIAL_CAPITAL,
                    RISK_FREE_RATE, OPTION_EXPIRY_DAYS, DEFAULT_TICKER)
from strategy.iv_calculator import black_scholes_price, get_implied_volatility
from strategy.iv_ranker     import IVRanker, get_trade_signal
from strategy.strategy      import StraddleStrategy, get_atm_strike, price_straddle
from risk.risk_manager      import RiskManager, Position


# ─────────────────────────────────────────────
# DATA FETCHER
# ─────────────────────────────────────────────

def fetch_nifty_data(start=BACKTEST_START, end=BACKTEST_END):
    """
    Fetch NIFTY 50 historical data from Yahoo Finance.
    Uses ^NSEI ticker (NIFTY 50 index).
    """
    print(f"  Fetching NIFTY data from {start} to {end}...")
    df = yf.download(DEFAULT_TICKER, start=start, end=end, progress=False)

    if df.empty:
        raise ValueError("No data fetched. Check internet connection.")

    df = df[['Close', 'High', 'Low', 'Volume']].copy()
    df.columns = ['close', 'high', 'low', 'volume']
    df.index   = pd.to_datetime(df.index)
    df         = df.dropna()

    print(f"  Fetched {len(df)} trading days of data.")
    return df


# ─────────────────────────────────────────────
# HISTORICAL VOLATILITY
# ─────────────────────────────────────────────

def compute_historical_vol(prices, window=10):
    """
    Compute rolling historical volatility annualised.
    Used to simulate option prices when IV not directly available.
    """
    log_returns = np.log(prices / prices.shift(1))
    hv          = log_returns.rolling(window).std() * np.sqrt(252)
    return hv


# ─────────────────────────────────────────────
# BACKTESTER
# ─────────────────────────────────────────────

class Backtester:
    """
    Full backtest engine.
    Simulates the strategy day by day on historical NIFTY data.
    """

    def __init__(self, initial_capital=INITIAL_CAPITAL,
                 strike_interval=50, expiry_days=OPTION_EXPIRY_DAYS):
        self.capital         = initial_capital
        self.initial_capital = initial_capital
        self.strike_interval = strike_interval
        self.expiry_days     = expiry_days
        self.r               = RISK_FREE_RATE

        self.strategy        = StraddleStrategy(strike_interval, expiry_days)
        self.risk_manager    = RiskManager(strike_interval)

        self.results         = []
        self.equity_curve    = [initial_capital]
        self.trade_returns   = []
        self.all_trades      = []


    def run(self, df):
        """
        Run backtest on DataFrame with columns: close, high, low, volume.
        """
        print("\n  Running backtest...\n")

        df       = df.copy()
        df['hv'] = compute_historical_vol(df['close'], window=10)
        df       = df.dropna()

        active_pos    = None
        entry_day_idx = None
        T             = self.expiry_days / 365

        for i, (date, row) in enumerate(df.iterrows()):
            spot = float(row['close'])
            hv   = float(row['hv'])
            hv   = max(0.05, min(hv, 2.0))

            strike     = get_atm_strike(spot, self.strike_interval)
            call_price = black_scholes_price(spot, strike, T, self.r, hv, 'call')
            put_price  = black_scholes_price(spot, strike, T, self.r, hv, 'put')

            pnl_today = 0
            signal    = 'NO_TRADE'
            hedge     = False

            # ── Update existing position ──────────────────────
            if active_pos:
                alert = self.risk_manager.update_position(
                    spot, call_price, put_price, date.date()
                )
                if alert:
                    hedge = True

                days_held = (i - entry_day_idx)
                pnl_today = active_pos.current_pnl

                # Close position after expiry
                if days_held >= self.expiry_days:
                    trade_pnl = active_pos.current_pnl
                    self.capital += trade_pnl
                    self.trade_returns.append(trade_pnl)
                    self.all_trades.append({
                        'entry_date' : active_pos.entry_date,
                        'exit_date'  : date.date(),
                        'signal'     : active_pos.signal,
                        'pnl'        : round(trade_pnl, 2),
                        'hedged'     : active_pos.is_hedged
                    })
                    self.risk_manager.close_position()
                    self.strategy.close_active_trade()
                    active_pos    = None
                    entry_day_idx = None

            # ── Check for new signal ──────────────────────────
            if not active_pos:
                state  = self.strategy.process_day(spot, call_price, date.date())
                signal = state['signal']

                if state['order']:
                    trade_order   = state['order']
                    active_pos    = self.risk_manager.open_position(trade_order)
                    entry_day_idx = i

            # ── Log equity ────────────────────────────────────
            self.equity_curve.append(
                self.capital + (pnl_today if active_pos else 0)
            )

            self.results.append({
                'date'    : date.date(),
                'spot'    : round(spot, 2),
                'hv'      : round(hv * 100, 2),
                'signal'  : signal,
                'pnl'     : round(pnl_today, 2),
                'capital' : round(self.capital, 2),
                'hedged'  : hedge
            })

        print(f"  Backtest complete. {len(self.trade_returns)} trades executed.\n")
        return self.results


    # ─────────────────────────────────────────
    # PERFORMANCE METRICS
    # ─────────────────────────────────────────

    def get_metrics(self):
        """Compute key performance metrics."""
        if not self.trade_returns:
            print("No trades to analyse.")
            return {}

        returns     = np.array(self.trade_returns)
        total_pnl   = np.sum(returns)
        win_trades  = np.sum(returns > 0)
        loss_trades = np.sum(returns < 0)
        win_rate    = win_trades / len(returns) * 100
        avg_win     = np.mean(returns[returns > 0]) if win_trades > 0 else 0
        avg_loss    = np.mean(returns[returns < 0]) if loss_trades > 0 else 0
        best_trade  = np.max(returns)
        worst_trade = np.min(returns)

        equity    = np.array(self.equity_curve)
        peak      = np.maximum.accumulate(equity)
        drawdown  = (equity - peak) / peak * 100
        max_dd    = np.min(drawdown)
        total_ret = (self.capital - self.initial_capital) / self.initial_capital * 100

        # Sharpe ratio
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 / self.expiry_days)
        else:
            sharpe = 0

        metrics = {
    'Total trades'    : len(returns),
    'Winning trades'  : int(win_trades),
    'Losing trades'   : int(loss_trades),
    'Win rate'        : f"{round(win_rate, 2)}%",
    'Total P&L'       : f"Rs.{round(total_pnl, 2)}",
    'Avg P&L / trade' : f"Rs.{round(np.mean(returns), 2)}",
    'Best trade'      : f"Rs.{round(best_trade, 2)}",
    'Worst trade'     : f"Rs.{round(worst_trade, 2)}",
    'Hedged trades'   : int(np.sum([t['hedged'] for t in self.all_trades])),
    'Final capital'   : f"Rs.{round(self.capital, 2)}",
    'Total return'    : f"{round(total_ret, 2)}%",
    'Sharpe ratio'    : round(sharpe, 2),
    'Max drawdown'    : f"{round(max_dd, 2)}%",
}
        return metrics

    def print_metrics(self):
        """Print performance report."""
        metrics = self.get_metrics()
        print("\n" + "="*45)
        print("  BACKTEST RESULTS")
        print("="*45)
        for k, v in metrics.items():
            print(f"  {k:<22}: {v}")
        print("="*45)

    # ─────────────────────────────────────────
    # PLOT
    # ─────────────────────────────────────────

    def plot_results(self, df):
        """Plot equity curve and IV rank."""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
        fig.suptitle('IV Rank Straddle Strategy — Backtest Results', fontsize=14)

        # Equity curve
        ax1.plot(self.equity_curve, color='#2196F3', linewidth=1.5)
        ax1.axhline(self.initial_capital, color='gray',
                    linestyle='--', linewidth=0.8, label='Initial capital')
        ax1.set_title('Equity Curve')
        ax1.set_ylabel('Portfolio Value (₹)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # IV rank over time
        iv_ranks = [r['hv'] for r in self.results]
        ax2.plot(iv_ranks, color='#FF9800', linewidth=1.0)
        ax2.axhline(70, color='red',   linestyle='--',
                    linewidth=0.8, label='Short threshold (70)')
        ax2.axhline(40, color='green', linestyle='--',
                    linewidth=0.8, label='Long threshold (40)')
        ax2.set_title('Bi-Weekly IV Rank')
        ax2.set_ylabel('IV Rank (Percentile)')
        ax2.set_xlabel('Date')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        os.makedirs('data', exist_ok=True)
        plt.savefig('data/backtest_results.png', dpi=150, bbox_inches='tight')
        print("\n  Chart saved to data/backtest_results.png")
        plt.show()


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("="*45)
    print("  IV STRADDLE STRATEGY — BACKTESTER")
    print("="*45)

    df = fetch_nifty_data(BACKTEST_START, BACKTEST_END)
    bt = Backtester(initial_capital=INITIAL_CAPITAL)
    bt.run(df)
    bt.print_metrics()
    bt.plot_results(df)
    print("\nbacktester.py complete.")