# config.py

# ── Strategy Parameters ──────────────────────────────────────────
IV_RANK_SHORT_THRESHOLD = 70    # Above this → Short Straddle
IV_RANK_LONG_THRESHOLD  = 40    # Below this → Long Straddle
BIWEEKLY_DAYS           = 10    # Trading days in 2 weeks

# ── Risk Management ──────────────────────────────────────────────
HEDGE_STRIKE_MOVE       = 2     # Hedge if price moves 2 strikes away
MAX_DRAWDOWN_PCT        = 0.15  # 15% max drawdown before forced hedge

# ── Data Settings ────────────────────────────────────────────────
RISK_FREE_RATE          = 0.065 # 6.5% Indian repo rate
DEFAULT_TICKER          = "^NSEI"
OPTION_EXPIRY_DAYS      = 14    # 2-week expiry

# ── Backtest Settings ────────────────────────────────────────────
BACKTEST_START          = "2024-01-01"
BACKTEST_END            = "2025-01-01"
INITIAL_CAPITAL         = 100000  # ₹1,00,000