import pandas as pd
import numpy as np
import os
import sys
import requests
import time
from datetime import datetime, timedelta


# --- config ---

ANALYSIS_FILE = "wallet_master_analysis.csv"
FINAL_REPORT_FILE = "whale_report.csv"


# --- API Endpoints for Live Activity Check ---
POSITIONS_API_URL = "https://data-api.polymarket.com/positions"
TRADES_API_URL = "https://data-api.polymarket.com/trades"
RATE_LIMIT_DELAY = 0.2 # 200ms delay between API calls

# --- SET YOUR THRESHOLDS ---

# 1. The minimum P&L to even be considered.
MIN_TOTAL_PNL = 1000  # at least $1,000 in profit

# 2. The minimum trades in a single group.
MIN_TRADE_COUNT = 10  # at least 10 trades

# 3. The minimum average profit per trade.
MIN_PNL_PER_TRADE = 5  # at least $5 profit per trade

# 4. The "Specialization Score"
MIN_SPECIALIZATION_SCORE = 0.75

# --- setup ---
session = requests.Session() # Use a session for API calls
if not os.path.exists(ANALYSIS_FILE):
    print(f"Error: '{ANALYSIS_FILE}' not found.")
    print("Please run 'analyze_wallets_v2.py' first.")
    sys.exit(1)

print(f"Loading '{ANALYSIS_FILE}' to find historical specialists...")
try:
    df = pd.read_csv(ANALYSIS_FILE)
except Exception as e:
    print(f"Error reading {ANALYSIS_FILE}: {e}")
    sys.exit(1)

# --- 1. HISTORICAL ANALYSIS ---
print("Analyzing historical performance...")

# Apply basic filters
df_filtered = df[
    (df['total_pnl'] > MIN_TOTAL_PNL) &
    (df['trade_count'] >= MIN_TRADE_COUNT)
    ].copy() # Use .copy() to avoid SettingWithCopyWarning

# Calculate P&L per Trade
df_filtered['pnl_per_trade'] = 0.0
df_filtered.loc[df_filtered['trade_count'] > 0, 'pnl_per_trade'] = \
    df_filtered['total_pnl'] / df_filtered['trade_count']
df_filtered = df_filtered[df_filtered['pnl_per_trade'] >= MIN_PNL_PER_TRADE]

# --- (REMOVED) ROI logic is gone ---

# Calculate Specialization Score
print("Calculating specialization scores...")
total_pnl_by_user = df_filtered.groupby('user')['total_pnl'].sum().reset_index()
total_pnl_by_user.rename(columns={'total_pnl': 'total_profit_all_groups'}, inplace=True)
df_specialists = pd.merge(df_filtered, total_pnl_by_user, on='user')
df_specialists['specialization_score'] = 1.0
df_specialists.loc[df_specialists['total_profit_all_groups'] > 0, 'specialization_score'] = \
    df_specialists['total_pnl'] / df_specialists['total_profit_all_groups']

# Apply Specialization filter
df_historically_good = df_specialists[
    df_specialists['specialization_score'] >= MIN_SPECIALIZATION_SCORE
    ]

print(f"Found {len(df_historically_good)} historically profitable specialists.")

# --- 2. LIVE ACTIVITY ANALYSIS ---
print("Checking live activity for these wallets (this may take a moment)...")

# Get a list of unique potential whales to check
wallets_to_check = df_historically_good['user'].unique()
active_wallets = set() # We will add "active" wallets to this set
one_week_ago = datetime.now() - timedelta(days=7)

for i, wallet in enumerate(wallets_to_check):
    is_active = False
    print(f"Checking wallet {i+1}/{len(wallets_to_check)} ({wallet[:10]}...)...", end="")

    try:
        # --- Check 1: Do they have any open positions? ---
        time.sleep(RATE_LIMIT_DELAY)
        params_pos = {'user': wallet, 'limit': 1}
        response_pos = session.get(POSITIONS_API_URL, params=params_pos)
        response_pos.raise_for_status()
        positions = response_pos.json()

        if isinstance(positions, list) and len(positions) > 0:
            is_active = True
            print(" ACTIVE (has open positions)")

        # --- Check 2: Have they traded in the last 7 days? ---
        if not is_active:
            time.sleep(RATE_LIMIT_DELAY)
            params_trade = {'user': wallet, 'limit': 1} # API sorts by newest first
            response_trade = session.get(TRADES_API_URL, params=params_trade)
            response_trade.raise_for_status()
            trades = response_trade.json()

            if isinstance(trades, list) and len(trades) > 0:
                last_trade = trades[0]
                # API gives timestamp as an integer (seconds)
                last_trade_time = datetime.fromtimestamp(last_trade['timestamp'])

                if last_trade_time > one_week_ago:
                    is_active = True
                    print(" ACTIVE (traded recently)")
                else:
                    print(" INACTIVE (last trade > 7 days ago)")
            else:
                print(" INACTIVE (no trade history)")

        if is_active:
            active_wallets.add(wallet)

    except requests.exceptions.RequestException as e:
        print(f" FAILED (API Error: {e})")
    except Exception as e:
        print(f" FAILED (Parsing Error: {e})")

# --- 3. FINAL REPORT ---
print("\n--- Whale Report Complete! ---")

# Filter our historical list to *only* include the active whales
df_final_whales = df_historically_good[
    df_historically_good['user'].isin(active_wallets)
]

print(f"Found {len(df_final_whales)} high-signal 'Specialist Whales' that are ALSO active.")

if df_final_whales.empty:
    print("No wallets matched all historical AND activity criteria.")
    sys.exit(0)

# Sort by the most profitable specialists first
df_final_whales = df_final_whales.sort_values(by='total_pnl', ascending=False)

# Re-order columns for a clean report
final_columns = [
    'user',
    'market_group',
    'total_pnl',
    'trade_count',
    'pnl_per_trade',
    'specialization_score'
]
df_final_whales = df_final_whales[final_columns]

# Save the final report
df_final_whales.to_csv(FINAL_REPORT_FILE, index=False)
print(f"Final report saved to '{FINAL_REPORT_FILE}'")

print("\n--- Top 20 Active Specialist Whales ---")
# Updated formatting to remove the deleted columns
print(df_final_whales.head(20).to_string(formatters={
    'total_pnl': '${:,.2f}'.format,
    'pnl_per_trade': '${:,.2f}'.format,
    'specialization_score': '{:,.1%}'.format
}))