import pandas as pd
import numpy as np
import os
import sys

# --- config ---

ANALYSIS_FILE = "wallet_master_analysis.csv"
FINAL_REPORT_FILE = "whale_report.csv"

# 1. minimum P&L to even be considered.
MIN_TOTAL_PNL = 1000  # at least $1,000 in profit

# 2. minimum trades in a single group.
MIN_TRADE_COUNT = 10  # at least 10 trades

# 3. minimum average profit per trade.
MIN_PNL_PER_TRADE = 5  # at least $5 profit per trade

# 4. spec score
MIN_SPECIALIZATION_SCORE = 0.75

# --- setup ---
if not os.path.exists(ANALYSIS_FILE):
    print(f"Error: '{ANALYSIS_FILE}' not found.")
    print("Please run the analysis script first (the one you just posted).")
    sys.exit(1)

print(f"Loading '{ANALYSIS_FILE}' to find specialist whales...")
try:
    df = pd.read_csv(ANALYSIS_FILE)
except Exception as e:
    print(f"Error reading {ANALYSIS_FILE}: {e}")
    sys.exit(1)

# --- analysis ---
print("Analyzing wallet performance...")

# 1. apply basic filters
df_filtered = df[
    (df['total_pnl'] > MIN_TOTAL_PNL) &
    (df['trade_count'] >= MIN_TRADE_COUNT)
    ]

# 2. calculate edge
df_filtered['pnl_per_trade'] = 0.0
df_filtered.loc[df_filtered['trade_count'] > 0, 'pnl_per_trade'] = \
    df_filtered['total_pnl'] / df_filtered['trade_count']

# 3. filtef for traders with "edge"
df_filtered = df_filtered[df_filtered['pnl_per_trade'] >= MIN_PNL_PER_TRADE]

# 4. calc spec score
print("Calculating specialization scores for remaining wallets...")

# total P&L for each user across all groups
total_pnl_by_user = df_filtered.groupby('user')['total_pnl'].sum().reset_index()
total_pnl_by_user.rename(columns={'total_pnl': 'total_profit_all_groups'}, inplace=True)

# total back onto filtered list
df_specialists = pd.merge(df_filtered, total_pnl_by_user, on='user')

# calculate score
df_specialists['specialization_score'] = 1.0 # Default to 1.0
df_specialists.loc[df_specialists['total_profit_all_groups'] > 0, 'specialization_score'] = \
    df_specialists['total_pnl'] / df_specialists['total_profit_all_groups']

# 5. final spec filter
df_final_whales = df_specialists[
    df_specialists['specialization_score'] >= MIN_SPECIALIZATION_SCORE
    ]

# --- final report ---
print("\n--- Whale Report Complete! ---")
print(f"Found {len(df_final_whales)} high-signal 'Specialist Whales' matching your criteria.")

if df_final_whales.empty:
    print("No wallets matched all criteria. Try lowering your thresholds.")
    sys.exit(0)

# sort most profitable to least
df_final_whales = df_final_whales.sort_values(by='total_pnl', ascending=False)

# columns for a clean report
final_columns = [
    'user',
    'market_group',
    'total_pnl',
    'trade_count',
    'pnl_per_trade',
    'specialization_score'
]

df_final_whales = df_final_whales[final_columns]


df_final_whales.to_csv(FINAL_REPORT_FILE, index=False)
print(f"Final report saved to '{FINAL_REPORT_FILE}'")

print("\n--- Top 20 Specialist Whales ---")
print(df_final_whales.head(40).to_string())