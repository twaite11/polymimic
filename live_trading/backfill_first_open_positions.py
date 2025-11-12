import requests
import pandas as pd
import sqlite3
import os
import sys
import time
from pathlib import Path

# --- config ---

WHALE_REPORT_FILE = Path("~/IdeaProjects/PolyCopy/modules/scalar_analysis/whale_report.csv").expanduser()
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()

POSITIONS_API_URL = "https://data-api.polymarket.com/positions"
MARKETS_URL = "https://gamma-api.polymarket.com/markets"

# be nice to the api
WHALE_LOOP_DELAY = 1.0  # Wait 1 full second between each whale
BATCH_API_DELAY = 0.5   # Wait 0.5s between each *batch* of market checks


TOP_N_WHALES = 200
SIMULATED_BET_AMOUNT = 1.0 # $1 per trade
MARKET_BATCH_SIZE = 50

# --- global state ---
session = requests.Session()

def load_whales():
    """Loads the Top N whale wallets from the whale_report.csv file."""
    if not os.path.exists(WHALE_REPORT_FILE):
        print(f"Error: '{WHALE_REPORT_FILE}' not found.")
        print("Please run 'find_whales.py' first to generate your whale list.")
        sys.exit(1)

    print(f"Loading top {TOP_N_WHALES} whales from '{WHALE_REPORT_FILE}'...")
    df = pd.read_csv(WHALE_REPORT_FILE)
    top_wallets = df.nlargest(TOP_N_WHALES, 'total_pnl')['user'].unique()
    return set(top_wallets)

def setup_database():
    """Connects to the SQLite database."""
    try:
        os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS trades (
                                                             id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                             timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                                             whale_wallet TEXT NOT NULL,
                                                             market_id TEXT NOT NULL,
                                                             outcome TEXT NOT NULL,
                                                             side TEXT NOT NULL,
                                                             price REAL NOT NULL,
                                                             simulated_bet REAL NOT NULL,
                                                             is_resolved INTEGER DEFAULT 0,
                                                             pnl REAL DEFAULT 0
                       )
                       ''')
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS pnl_history (
                                                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                  timestamp DATE UNIQUE,
                                                                  cumulative_pnl REAL NOT NULL
                       )
                       ''')
        conn.commit()
        print(f"Database '{DATABASE_FILE}' is ready.")
        return conn

    except sqlite3.Error as e:
        print(f"Error setting up database: {e}")
        sys.exit(1)


def get_active_markets(market_ids):
    """
    Cross-references a list of market IDs with the API
    and returns a set of only the ones that are NOT closed.
    """
    active_market_ids = set()
    if not market_ids:
        return active_market_ids

    print(f" (Checking status of {len(market_ids)} markets)...", end="")

    # loop through markets
    for i in range(0, len(market_ids), MARKET_BATCH_SIZE):
        batch_ids = market_ids[i : i + MARKET_BATCH_SIZE]
        id_string = ",".join(batch_ids)

        try:
            params_markets = {'condition_ids': id_string}
            response_markets = session.get(MARKETS_URL, params=params_markets)
            response_markets.raise_for_status()
            markets_data = response_markets.json()

            if isinstance(markets_data, list):
                for market in markets_data:
                    if market.get('closed') == False:
                        active_market_ids.add(market.get('conditionId'))

            # delay between batches
            time.sleep(BATCH_API_DELAY)

        except requests.exceptions.RequestException as e:
            print(f" FAILED (Market Status API Error on batch {i}: {e})")
            continue
        except Exception as e:
            print(f" FAILED (Market Parsing Error on batch {i}: {e})")
            continue

    return active_market_ids

def backfill_positions(conn, whale_wallets):
    """
    Fetches all current open positions for each whale and logs them
    to the database as new simulated trades.
    """
    print(f"Backfilling open positions for {len(whale_wallets)} whales...")
    total_positions_found = 0

    for i, wallet in enumerate(whale_wallets):

        # avoid 403 Forbidden
        print(f"Processing wallet {i+1}/{len(whale_wallets)} ({wallet[:10]}...)...", end="")
        time.sleep(WHALE_LOOP_DELAY)


        try:
            # Fetch all positions for this user
            params = {'user': wallet, 'limit': 500}
            response = session.get(POSITIONS_API_URL, params=params)
            response.raise_for_status()
            positions = response.json()

            if not isinstance(positions, list) or not positions:
                print(" No open positions.")
                continue

            # unique market IDs from this whale's positions
            market_ids_to_check = list(set([
                pos.get('conditionId') for pos in positions
                if pos.get('conditionId') and float(pos.get('size', 0)) > 0
            ]))

            if not market_ids_to_check:
                print(" No valid positions found.")
                continue

            # find which ones are still active
            active_market_ids = get_active_markets(market_ids_to_check)

            if not active_market_ids:
                print(f" No *active* positions found ({len(positions)} total positions).")
                continue

            whale_positions_added = 0
            cursor = conn.cursor()

            for pos in positions:
                market_id = pos.get('conditionId')

                # check for active markets
                if market_id in active_market_ids:
                    price = float(pos.get('curPrice', 0))
                    if price > 0:
                        outcome = pos.get('outcome')

                        cursor.execute('''
                                       INSERT INTO trades (whale_wallet, market_id, outcome, side, price, simulated_bet, is_resolved, pnl)
                                       VALUES (?, ?, ?, 'BUY', ?, ?, 0, 0)
                                       ''', (wallet, market_id, outcome, price, SIMULATED_BET_AMOUNT))

                        whale_positions_added += 1

            conn.commit()
            total_positions_found += whale_positions_added
            if whale_positions_added > 0:
                print(f" Found and logged {whale_positions_added} active positions.")
            else:
                print(" No *active* positions found.")

        except requests.exceptions.RequestException as e:
            print(f" FAILED (API Error: {e})")
        except Exception as e:
            print(f" FAILED (Parsing Error: {e})")

    print(f"\n--- Backfill Complete! ---")
    print(f"Logged a total of {total_positions_found} active positions to 'simulation.db'.")
    print("You can now start 'live_trade_simulator.py'.")

# MAIN
if __name__ == "__main__":
    print("--- Starting One-Time Position Backfill ---")

    whale_wallets = load_whales()
    db_conn = setup_database()
    backfill_positions(db_conn, whale_wallets)
    db_conn.close()