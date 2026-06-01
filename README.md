# IV Straddle Strategy

A quantitative options trading strategy in Python that uses Implied Volatility 
percentile ranking to generate straddle trade signals on NIFTY 50.

Built as a learning project based on a senior's suggestion to combine 
reverse Black-Scholes, IV ranking, and systematic risk management.

---

## What This Strategy Does

It looks at how expensive or cheap options are right now compared to 
the last 2 weeks. If options are too expensive, it sells a straddle. 
If options are too cheap, it buys a straddle. If price moves too far, 
it adds a hedge automatically.

---

## Strategy Rules

If IV Rank is above 70 then Short Straddle — sell ATM call and put, 
collect premium, profit if market stays flat.

If IV Rank is below 40 then Long Straddle — buy ATM call and put, 
profit if market makes a big move in either direction.

If IV Rank is between 40 and 70 then No Trade — IV is neutral, 
stay out of the market.

If spot price moves 2 strikes away from entry or drawdown exceeds 15 percent 
then add a hedge to protect the position.

---

## How It Works Step by Step

Step 1 — Fetch the market option price for NIFTY ATM strike.

Step 2 — Run reverse Black-Scholes to extract the Implied Volatility 
that the market is pricing in. This uses Newton-Raphson iteration 
with Brent's method as a fallback.

Step 3 — Store today's IV and compute its percentile rank 
against the last 10 trading days (2 weeks).

Step 4 — Generate a trade signal based on where the rank falls.

Step 5 — Monitor the open position every day. If spot moves 
2 strikes away from entry strike, trigger a hedge automatically.

Step 6 — Close the position after 14 days (option expiry).

---

## Project Structure

```
iv_straddle_strategy/
├── strategy/
│   ├── iv_calculator.py   
│   ├── iv_ranker.py       
│   └── strategy.py        
├── risk/
│   └── risk_manager.py    
├── backtest/
│   └── backtester.py      
├── config.py              
├── main.py                
└── requirements.txt
```

iv_calculator.py extracts implied volatility from market prices using 
reverse Black-Scholes.

iv_ranker.py tracks IV history and computes the bi-weekly percentile rank.

strategy.py generates SHORT STRADDLE or LONG STRADDLE signals.

risk_manager.py monitors positions and triggers hedges when needed.

backtester.py runs the full strategy on historical NIFTY data.

---

## Setup

```bash
git clone https://github.com/muditjain936/iv-straddle-strategy.git
cd iv-straddle-strategy
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## Run the Backtest

```bash
python -m backtest.backtester
```

This fetches NIFTY 50 data from Yahoo Finance, runs the strategy, 
prints a performance report, and saves an equity curve chart.

---

## Configuration

All parameters are in config.py. Change them to adjust the strategy.

```python
IV_RANK_SHORT_THRESHOLD = 70    
IV_RANK_LONG_THRESHOLD  = 40    
HEDGE_STRIKE_MOVE       = 2     
MAX_DRAWDOWN_PCT        = 0.15  
BACKTEST_START          = "2023-01-01"
BACKTEST_END            = "2024-01-01"
INITIAL_CAPITAL         = 100000
```

---

## Tech Stack

Python 3.9 or above.
numpy and scipy for Black-Scholes math and root finding.
pandas for IV history and data handling.
yfinance for NIFTY historical price data.
matplotlib for equity curve chart.

---

## Key Terms

Implied Volatility is the market's expectation of future volatility, 
reverse-engineered from the option's market price.

IV Rank is today's IV expressed as a percentile compared to 
the last 2 weeks. High rank means IV is expensive. Low rank means cheap.

Short Straddle means selling both a call and put at the same strike. 
You profit when the market does not move much and premium decays.

Long Straddle means buying both a call and put at the same strike. 
You profit when the market makes a large move in either direction.

Hedge means adding an option position to limit your loss when 
the market moves too far against your straddle.

---

## Disclaimer

This project is for educational purposes only and is not financial advice. 
Options trading involves significant risk of loss.