import requests
import pandas as pd
import time
import os
import sys
import random

# --- config ---

MARKETS_FILE = "markets_v2.csv" # Read from our new "v2" file
TRADES_FILE = "all_trades.csv"
TRADES_URL = "https://data-api.polymarket.com/trades"
LIMIT = 1000
RATE_LIMIT_DELAY = 0.2

# --- setup ---
session = requests.Session()

if not os.path.exists(MARKETS_FILE):
    print(f"Error: '{MARKETS_FILE}' not found.")
    print("Please run Script 1 (fetch_markets_v2.py) first.")
    sys.exit(1)

markets_df = pd.read_csv(MARKETS_FILE)
market_ids = markets_df['conditionId'].unique()

random.shuffle(market_ids)


total_markets = len(market_ids)
print(f"Loaded and *shuffled* {total_markets} resolved markets to process.")
print(f"Using endpoint: {TRADES_URL}")
print("This will be the long-running script that fetches all trades for all markets.")

all_trades_data = []
processed_count = 0

# --- main loop ---
for market_id in market_ids:
    offset = 0

    while True:
        params = {
            'market': market_id,
            'limit': LIMIT,
            'offset': offset,
            'takerOnly': False # Get ALL trades (maker + taker)
        }

        try:
            time.sleep(RATE_LIMIT_DELAY)
            response = session.get(TRADES_URL, params=params)
            response.raise_for_status()
            trades = response.json()

            if not trades:
                break

            all_trades_data.extend(trades)

            if len(trades) < LIMIT:
                break

            offset += LIMIT

        except requests.exceptions.RequestException as e:
            print(f"\nError on market {market_id} offset {offset}: {e}")
            break

    processed_count += 1
    print(f"Processed {processed_count}/{total_markets} markets... Found {len(all_trades_data)} total trades so far.")

# --- save results ---
print("\nDone fetching all trades. Converting to DataFrame...")
if not all_trades_data:
    print("No trades were found.")
    sys.exit(0)

trades_df = pd.DataFrame(all_trades_data)

final_columns = [
    'transactionHash',
    'conditionId',
    'proxyWallet',
    'outcome',
    'size',
    'price',
    'side'
]

existing_columns = [col for col in final_columns if col in trades_df.columns]
final_trades_df = trades_df[existing_columns]

print(f"Saving {len(final_trades_df)} trades to '{TRADES_FILE}'...")
final_trades_df.to_csv(TRADES_FILE, index=False)

print("--- All trades saved! ---")