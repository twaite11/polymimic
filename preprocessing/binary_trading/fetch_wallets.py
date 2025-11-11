import requests
import pandas as pd
import time
import os
import sys

# --- config ---
MARKETS_FILE = "../resolved_markets.csv"
WALLETS_FILE = "../unique_wallets.csv"
HOLDERS_URL = "https://data-api.polymarket.com/holders"
RATE_LIMIT_DELAY = 0.2
BATCH_SIZE = 20

# --- setup ---
session = requests.Session()

if not os.path.exists(MARKETS_FILE):
    print(f"Error: '{MARKETS_FILE}' not found.")
    print("Please run Script 1 (fetch_markets.py) first.")
    sys.exit(1)

markets_df = pd.read_csv(MARKETS_FILE)
market_ids = markets_df['conditionId'].unique()
total_markets = len(market_ids)
print(f"Loaded {total_markets} resolved markets from '{MARKETS_FILE}'.")

# a set automatically handles duplicates
all_wallets = set()
processed_count = 0

# --- main loop (batched) ---
print(f"Fetching wallets in batches of {BATCH_SIZE}...")
for i in range(0, total_markets, BATCH_SIZE):
    batch_ids = market_ids[i : i + BATCH_SIZE]

    # create comma-separated string: "0x123...,0x456...,0x789..."
    market_id_string = ",".join(batch_ids)

    params = {
        'market': market_id_string,
        'limit': 500
    }

    try:
        time.sleep(RATE_LIMIT_DELAY)
        response = session.get(HOLDERS_URL, params=params)
        response.raise_for_status()
        data = response.json() # this is a list of market objects

        if not isinstance(data, list):
            print(f"Warning: API response was not a list for batch starting at {i}. Skipping.")
            continue

        # parse the response:
        # data is a list: [ {market1_data}, {market2_data}, ... ]
        for market_data in data:
            holders_list = market_data.get('holders')
            if isinstance(holders_list, list):
                # now loop through the wallets in this market
                for holder in holders_list:
                    wallet = holder.get('proxyWallet')
                    if wallet:
                        all_wallets.add(wallet)

    except requests.exceptions.RequestException as e:
        print(f"\nError on batch starting at index {i}: {e}")

    processed_count += len(batch_ids)
    print(f"Processed {min(processed_count, total_markets)}/{total_markets} markets... Found {len(all_wallets)} unique wallets so far.")

# --- save results ---
print("\nDone fetching wallets.")
if not all_wallets:
    print("No wallets were found.")
    sys.exit(0)

# convert the set to a dataframe
wallets_df = pd.DataFrame(list(all_wallets), columns=['proxyWallet'])

wallets_df.to_csv(WALLETS_FILE, index=False)

print(f"\n--- Success! ---")
print(f"Saved {len(wallets_df)} unique wallets to '{WALLETS_FILE}'.")