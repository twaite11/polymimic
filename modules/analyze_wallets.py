import pandas as pd
import numpy as np
import os
import sys

# --- config ---
MARKETS_FILE = "resolved_markets.csv"
TRADES_FILE = "all_trades.csv"
REPORT_FILE = "wallet_analysis.csv"
CHUNK_SIZE = 100000

# --- setup ---
if not (os.path.exists(MARKETS_FILE) and os.path.exists(TRADES_FILE)):
    print(f"Error: Missing '{MARKETS_FILE}' or '{TRADES_FILE}'.")
    sys.exit(1)

print("Loading resolved markets (answer key)...")
try:
    markets_df = pd.read_csv(MARKETS_FILE)
    markets_df = markets_df[['conditionId', 'category', 'resolution']].copy()
    # standardize 'resolution' to uppercase (e.g., 'Yes' -> 'YES')
    markets_df['resolution'] = markets_df['resolution'].astype(str).str.upper()

except Exception as e:
    print(f"Error loading {MARKETS_FILE}: {e}")
    sys.exit(1)

print(f"Loaded {len(markets_df)} resolved markets.")

# --- main processing loop ---
print(f"Starting analysis of '{TRADES_FILE}'...")
all_chunk_results = []
chunk_num = 1

try:
    for chunk in pd.read_csv(TRADES_FILE, chunksize=CHUNK_SIZE):

        # merge the chunk of trades with our answer key
        chunk_with_answers = pd.merge(chunk, markets_df, on='conditionId')

        if chunk_with_answers.empty:
            print(f"Chunk {chunk_num}: No trades matched resolved markets. Skipping.")
            chunk_num += 1
            continue

        # standardize 'outcome' (e.g., 'Yes', 'no')
        chunk_with_answers['outcome_upper'] = chunk_with_answers['outcome'].astype(str).str.upper()
        # standardize 'side' (e.g., 'BUY', 'sell')
        chunk_with_answers['side_upper'] = chunk_with_answers['side'].astype(str).str.upper()

        # convert 'size' (shares) to numeric
        chunk_with_answers['size_num'] = pd.to_numeric(chunk_with_answers['size'], errors='coerce')
        # drop rows where 'size' or 'price' was not a number
        chunk_with_answers.dropna(subset=['size_num', 'price'], inplace=True)

        is_winner = np.where(chunk_with_answers['outcome_upper'] == chunk_with_answers['resolution'], 1, 0)

        pnl_buy = (is_winner - chunk_with_answers['price']) * chunk_with_answers['size_num']
        pnl_sell = (chunk_with_answers['price'] - is_winner) * chunk_with_answers['size_num']

        chunk_with_answers['pnl'] = np.where(chunk_with_answers['side_upper'] == 'BUY', pnl_buy, pnl_sell)

        # group by 'proxyWallet' (user) and category
        chunk_agg = chunk_with_answers.groupby(['proxyWallet', 'category']).agg(
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

final_report = final_df.groupby(['proxyWallet', 'category']).agg(
    total_pnl=('total_pnl', 'sum'),
    trade_count=('trade_count', 'sum')
).reset_index()

# rename 'proxyWallet' to 'user' for a cleaner report
final_report.rename(columns={'proxyWallet': 'user'}, inplace=True)

final_report = final_report[final_report['trade_count'] > 5]
final_report = final_report.sort_values(by='total_pnl', ascending=False)

final_report.to_csv(REPORT_FILE, index=False)

print(f"\n--- Analysis Complete! ---")
print(f"Report saved to '{REPORT_FILE}'.")
print("\nTop 20 Anomalous Wallet/Category Pairs (by Total Profit):")
print(final_report.head(20).to_string())