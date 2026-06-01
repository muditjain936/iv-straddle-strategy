# strategy/iv_calculator.py
# Reverse Black-Scholes: extract Implied Volatility from market option prices

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq
import warnings
warnings.filterwarnings('ignore')


# ─────────────────────────────────────────────
# CORE BLACK-SCHOLES PRICE FORMULA
# ─────────────────────────────────────────────

def black_scholes_price(S, K, T, r, sigma, option_type='call'):
    """
    Calculate theoretical option price using Black-Scholes.

    S     = Current stock/index price
    K     = Strike price
    T     = Time to expiry in years (e.g. 14 days = 14/365)
    r     = Risk-free rate (e.g. 0.065 for 6.5%)
    sigma = Volatility (e.g. 0.20 for 20%)
    option_type = 'call' or 'put'
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    return price


# ─────────────────────────────────────────────
# VEGA (needed for Newton-Raphson method)
# ─────────────────────────────────────────────

def vega(S, K, T, r, sigma):
    """
    Vega = sensitivity of option price to volatility.
    Used in Newton-Raphson to find IV faster.
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return S * norm.pdf(d1) * np.sqrt(T)


# ─────────────────────────────────────────────
# REVERSE BLACK-SCHOLES — NEWTON-RAPHSON METHOD
# ─────────────────────────────────────────────

def implied_volatility_newton(market_price, S, K, T, r, option_type='call',
                               max_iterations=100, tolerance=1e-6):
    """
    Extract IV using Newton-Raphson iteration.
    Fast and accurate when vega is not near zero.
    """
    sigma = 0.3  # initial guess: 30% volatility

    for i in range(max_iterations):
        price  = black_scholes_price(S, K, T, r, sigma, option_type)
        v      = vega(S, K, T, r, sigma)
        diff   = market_price - price

        if abs(diff) < tolerance:
            return sigma

        if abs(v) < 1e-10:
            break  # vega too small, switch to Brent method

        sigma = sigma + diff / v
        sigma = max(0.001, min(sigma, 10.0))  # keep sigma in [0.1%, 1000%]

    return None  # fallback to Brent


# ─────────────────────────────────────────────
# REVERSE BLACK-SCHOLES — BRENT METHOD (FALLBACK)
# ─────────────────────────────────────────────

def implied_volatility_brent(market_price, S, K, T, r, option_type='call'):
    """
    Extract IV using Brent's method (bracketed root finding).
    More robust fallback when Newton-Raphson fails.
    """
    try:
        iv = brentq(
            lambda sigma: black_scholes_price(S, K, T, r, sigma, option_type) - market_price,
            a=0.001,   # lower bound: 0.1% vol
            b=10.0,    # upper bound: 1000% vol
            xtol=1e-6,
            maxiter=500
        )
        return iv
    except (ValueError, RuntimeError):
        return None


# ─────────────────────────────────────────────
# MAIN IV FUNCTION — TRIES NEWTON FIRST, THEN BRENT
# ─────────────────────────────────────────────

def get_implied_volatility(market_price, S, K, T, r, option_type='call'):
    """
    Master function to get IV from a market option price.
    Tries Newton-Raphson first (fast), falls back to Brent (robust).

    Returns IV as a decimal (e.g. 0.25 means 25% volatility)
    Returns None if calculation fails.
    """
    # Basic sanity checks
    if market_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None

    intrinsic = max(0, S - K) if option_type == 'call' else max(0, K - S)
    if market_price < intrinsic:
        return None  # price below intrinsic value — bad data

    # Try Newton-Raphson first
    iv = implied_volatility_newton(market_price, S, K, T, r, option_type)

    # Fall back to Brent if Newton failed
    if iv is None:
        iv = implied_volatility_brent(market_price, S, K, T, r, option_type)

    return iv


# ─────────────────────────────────────────────
# TEST — run this file directly to verify
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Example: NIFTY at 22000, strike 22000, 14 days to expiry
    S = 22000   # spot price
    K = 22000   # strike (ATM straddle)
    T = 14/365  # 14 days in years
    r = 0.065   # risk-free rate
    option_type = 'call'

    # Step 1: generate a fake market price using known vol (25%)
    known_vol    = 0.25
    market_price = black_scholes_price(S, K, T, r, known_vol, option_type)
    print(f"Theoretical price at 25% vol : ₹{market_price:.2f}")

    # Step 2: reverse it — recover the IV from that price
    recovered_iv = get_implied_volatility(market_price, S, K, T, r, option_type)
    print(f"Recovered IV (should be 25%) : {recovered_iv*100:.4f}%")

    # Step 3: test with a put
    put_price    = black_scholes_price(S, K, T, r, known_vol, 'put')
    put_iv       = get_implied_volatility(put_price, S, K, T, r, 'put')
    print(f"Put IV (should be 25%)       : {put_iv*100:.4f}%")

    # Step 4: test edge cases
    print(f"\nEdge case tests:")
    print(f"IV with zero price    : {get_implied_volatility(0, S, K, T, r)}")
    print(f"IV with negative time : {get_implied_volatility(100, S, K, 0, r)}")
    print(f"\niv_calculator.py working correctly.")