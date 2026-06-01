# main.py
import sys
import os

# Force project root into path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest.backtester import Backtester, fetch_nifty_data
from config import BACKTEST_START, BACKTEST_END, INITIAL_CAPITAL

if __name__ == "__main__":
    print("=" * 45)
    print("  IV STRADDLE STRATEGY")
    print("=" * 45)

    df = fetch_nifty_data(BACKTEST_START, BACKTEST_END)
    bt = Backtester(initial_capital=INITIAL_CAPITAL)
    bt.run(df)
    bt.print_metrics()
    bt.plot_results(df)