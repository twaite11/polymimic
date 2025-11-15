import requests
import pandas as pd
import time
import os
import sys
import random
import concurrent.futures
from threading import Lock

# --- config ---

MARKETS_FILE = "markets_v2.csv"
TRADES_FILE = "all_trades.csv"
TRADES_URL = "https://data-api.polymarket.com/trades"
LIMIT = 10000
RATE_LIMIT_DELAY = 0.2
MAX_WORKERS = 10

#  target columns to ensure consistency when saving
FINAL_COLUMNS = [
    'transactionHash',
    'conditionId',
    'proxyWallet',
    'outcome',
    'size',
    'price',
    'side'
]

# Thread-safe lock for file operations
file_lock = Lock()

# --- helper function for batch saving ---

def save_trades_batch(trades_list, filename, columns):
    """
    Converts a list of trade dictionaries into a DataFrame and appends it to
    the target CSV file, handling the header only once. Uses a lock for thread safety.
    """
    if not trades_list:
        return 0

    batch_df = pd.DataFrame(trades_list)

    # select columns that exist
    existing_columns = [col for col in columns if col in batch_df.columns]

    # lock before file operation
    with file_lock:
        file_exists = os.path.exists(filename)

        # append to the CSV file. if file exists, don't write header
        batch_df[existing_columns].to_csv(
            filename,
            mode='a',
            index=False,
            header=not file_exists
        )

    return len(batch_df)

# --- worker function for concurrent processing ---

def fetch_and_save_market_trades(market_id, total_markets):
    """
    Fetches all trades for a single market and saves them immediately to disk.
    Returns the count of trades saved.
    """
    # new session for this thread to ensure thread safety
    session = requests.Session()
    market_trades = []
    offset = 0
    trades_found_in_market = 0

    try:
        while True:
            params = {
                'market': market_id,
                'limit': LIMIT,
                'offset': offset,
                'takerOnly': False
            }

            # dont hammer the api too hard on all threads
            time.sleep(RATE_LIMIT_DELAY)

            response = session.get(TRADES_URL, params=params)
            response.raise_for_status()
            trades = response.json()

            if not trades:
                break

            market_trades.extend(trades)
            trades_found_in_market += len(trades)

            if len(trades) < LIMIT:
                break

            offset += LIMIT

        # --- save batch results immediately ---
        saved_count = save_trades_batch(market_trades, TRADES_FILE, FINAL_COLUMNS)

        return saved_count, market_id, trades_found_in_market

    except requests.exceptions.RequestException as e:
        print(f"\n[ERROR] Market {market_id}: Request failed: {e}")
        return 0, market_id, 0
    except Exception as e:
        print(f"\n[ERROR] Market {market_id}: Unexpected error: {e}")
        return 0, market_id, 0


# --- setup ---
if not os.path.exists(MARKETS_FILE):
    print(f"Error: '{MARKETS_FILE}' not found.")
    print("Please run Script 1 (fetch_markets_v2.py) first.")
    sys.exit(1)

markets_df = pd.read_csv(MARKETS_FILE)
market_ids = markets_df['conditionId'].unique()

random.shuffle(market_ids)

total_markets = len(market_ids)
print(f"Loaded and *shuffled* {total_markets} markets to process.")
print(f"Using endpoint: {TRADES_URL} with {MAX_WORKERS} workers for concurrent fetching.")

# correct headers
if os.path.exists(TRADES_FILE):
    os.remove(TRADES_FILE)
    print(f"Removed previous '{TRADES_FILE}' to start fresh.")

total_trades_saved = 0
processed_count = 0

# --- main execution using ThreadPoolExecutor ---
print("\n--- Starting Concurrent Fetching ---")

# ThreadPoolExecutor to run tasks in parallel
with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

    # submit all market IDs to the executor
    future_to_market = {
        executor.submit(fetch_and_save_market_trades, market_id, total_markets): market_id
        for market_id in market_ids
    }

    # iterate as tasks complete
    for future in concurrent.futures.as_completed(future_to_market):
        market_id = future_to_market[future]
        processed_count += 1

        try:
            # get result from the thread
            saved_count, _, trades_found_in_market = future.result()
            total_trades_saved += saved_count

            print(f"[{processed_count}/{total_markets}] Market {market_id[:8]}... completed. Trades: {trades_found_in_market} | Total saved: {total_trades_saved}")

        except Exception as exc:
            print(f"Market {market_id} generated an exception: {exc}")


# --- final report ---
print("\n--- Done fetching all markets! ---")
print(f"All {total_trades_saved} trades have been incrementally saved to '{TRADES_FILE}'.")
print(f"Concurrency utilized with {MAX_WORKERS} workers.")