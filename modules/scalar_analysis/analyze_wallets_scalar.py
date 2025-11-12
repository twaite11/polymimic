import pandas as pd
import numpy as np
import os
import sys
import json
from pathlib import Path

# --- config ---
MARKETS_FILE = Path("~/IdeaProjects/PolyCopy/preprocessing/scalar_trading/markets_with_groups_v2.csv").expanduser()
TRADES_FILE = Path("~/IdeaProjects/PolyCopy/preprocessing/scalar_trading/all_trades.csv").expanduser()
REPORT_FILE = "wallet_master_analysis.csv"
CHUNK_SIZE = 100000


def find_settlement_price(row):
    """
    Finds the final settlement price for the *specific outcome*
    that a user traded.
    """
    try:
        trade_outcome = str(row['outcome_upper'])

        outcomes_list = json.loads(row['outcomes'])
        prices_list = json.loads(row['final_prices'])

        # uppercase outcomes
        outcomes_list_upper = [str(o).upper() for o in outcomes_list]

        # index of the outcome the user traded
        trade_index = outcomes_list_upper.index(trade_outcome)

        return prices_list[trade_index]

    except (ValueError, TypeError, json.JSONDecodeError):
        return None

# --- setup ---
if not (os.path.exists(MARKETS_FILE) and os.path.exists(TRADES_FILE)):
    print(f"Error: Missing '{MARKETS_FILE}' or '{TRADES_FILE}'.")
    sys.exit(1)

print("Loading grouped markets (answer key)...")
try:
    markets_df = pd.read_csv(MARKETS_FILE)
    # Load all the new columns we need
    markets_df = markets_df[['conditionId', 'market_group', 'outcomes', 'final_prices']].copy()

except Exception as e:
    print(f"Error loading {MARKETS_FILE}: {e}")
    sys.exit(1)

print(f"Loaded {len(markets_df)} resolved markets with groups.")

# --- main processing loop ---
print(f"Starting analysis of '{TRADES_FILE}'...")
all_chunk_results = []
chunk_num = 1

try:
    for chunk in pd.read_csv(TRADES_FILE, chunksize=CHUNK_SIZE):

        chunk_with_answers = pd.merge(chunk, markets_df, on='conditionId')

        if chunk_with_answers.empty:
            print(f"Chunk {chunk_num}: No trades matched resolved markets. Skipping.")
            chunk_num += 1
            continue

        # --- Data Cleaning ---
        chunk_with_answers['outcome_upper'] = chunk_with_answers['outcome'].astype(str).str.upper()
        chunk_with_answers['side_upper'] = chunk_with_answers['side'].astype(str).str.upper()
        chunk_with_answers['size_num'] = pd.to_numeric(chunk_with_answers['size'], errors='coerce')
        chunk_with_answers.dropna(subset=['size_num', 'price'], inplace=True)


        # 1. Find the settlement price for the outcome a user traded
        chunk_with_answers['settlement_price'] = chunk_with_answers.apply(find_settlement_price, axis=1)

        # 2. Drop rows where we couldn't find a price (bad data)
        chunk_with_answers.dropna(subset=['settlement_price'], inplace=True)

        # 3. Calculate P&L using this price.
        # This logic now works for BOTH normal and scalar markets.
        pnl_buy = (chunk_with_answers['settlement_price'] - chunk_with_answers['price']) * chunk_with_answers['size_num']
        pnl_sell = (chunk_with_answers['price'] - chunk_with_answers['settlement_price']) * chunk_with_answers['size_num']

        chunk_with_answers['pnl'] = np.where(chunk_with_answers['side_upper'] == 'BUY', pnl_buy, pnl_sell)

        # Group by wallet and market_group
        chunk_agg = chunk_with_answers.groupby(['proxyWallet', 'market_group']).agg(
            total_pnl=('pnl', 'sum'),
            trade_count=('transactionHash', 'count')
        ).reset_index()

        all_chunk_results.append(chunk_agg)

        print(f"Processed chunk {chunk_num}...")
        chunk_num += 1

except pd.errors.EmptyDataError:
    print(f"Error: '{TRADES_FILE}' is empty or corrupted.")
    sys.exit(1)
except Exception as e:
    print(f"An error occurred during chunk processing: {e}")
    sys.exit(1)

if not all_chunk_results:
    print("No matching trades were found in the entire file. Exiting.")
    sys.exit(0)

print("\nAll chunks processed. Compiling final report...")

# --- final report ---
final_df = pd.concat(all_chunk_results)

final_report = final_df.groupby(['proxyWallet', 'market_group']).agg(
    total_pnl=('total_pnl', 'sum'),
    trade_count=('trade_count', 'sum')
).reset_index()

final_report.rename(columns={'proxyWallet': 'user'}, inplace=True)

final_report = final_report[final_report['trade_count'] > 5]
final_report = final_report.sort_values(by='total_pnl', ascending=False)

final_report.to_csv(REPORT_FILE, index=False)

print(f"\n--- Analysis Complete! ---")
print(f"Report saved to '{REPORT_FILE}'.")
print("\nTop 20 Specialist Wallets (by Total Profit):")
print(final_report.head(20).to_string())