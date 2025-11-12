import websocket
import json
import sqlite3
import pandas as pd
import os
import sys
import time
from threading import Thread
from dotenv import load_dotenv
from pathlib import Path

# --- config ---
DEBUG_MODE = False


load_dotenv()

# --- FILE PATHS ---
WHALE_REPORT_FILE = Path("~/IdeaProjects/PolyCopy/modules/scalar_analysis/whale_report.csv").expanduser()
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()

# --- AUTH KEYS ---
API_KEY = os.getenv("POLYMARKET_API_KEY")
API_SECRET = os.getenv("POLYMARKET_SECRET_KEY")
API_PASSPHRASE = os.getenv("POLYMARKET_PASSPHRASE")

# --- SIMULATION ---
WEBSOCKET_URL = "wss://ws-live-data.polymarket.com"
TOP_N_WHALES = 400
SIMULATED_BET_AMOUNT = 1.0 # $1 per trade

# --- global state ---
db_conn = None
whale_wallets = set()

def load_whales():
    """
    Loads the Top N whale wallets from the whale_report.csv file.
    """
    global whale_wallets
    if not os.path.exists(WHALE_REPORT_FILE):
        print(f"Error: '{WHALE_REPORT_FILE}' not found.")
        print("Please run 'find_whales.py' first to generate your whale list.")
        sys.exit(1)

    print(f"Loading top {TOP_N_WHALES} whales from '{WHALE_REPORT_FILE}'...")
    df = pd.read_csv(WHALE_REPORT_FILE)
    top_wallets = df.nlargest(TOP_N_WHALES, 'total_pnl')['user'].unique()
    whale_wallets = set(top_wallets)
    print(f"Successfully loaded {len(whale_wallets)} unique whale wallets to monitor.")

def setup_database():
    """
    Creates the SQLite database and the 'trades' table if it doesn't exist.
    """
    global db_conn
    try:
        os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
        db_conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        cursor = db_conn.cursor()

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

        db_conn.commit()
        print(f"Database '{DATABASE_FILE}' is ready.")

    except sqlite3.Error as e:
        print(f"Error setting up database: {e}")
        sys.exit(1)

def log_trade(trade_data):
    """
    Called when a whale trade is detected. Inserts it into the database.
    """
    global db_conn
    try:
        whale_wallet = trade_data.get('proxyWallet') # <-- This is our ASSUMPTION
        market_id = trade_data.get('conditionId')
        outcome = trade_data.get('outcome')
        side = trade_data.get('side')
        price_str = trade_data.get('price')

        if price_str is None: return
        price = float(price_str)

        if not all([whale_wallet, market_id, outcome, side, price is not None]):
            if DEBUG_MODE:
                print(f"[Debug] Skipping incomplete trade data: {trade_data}")
            return

        print(f"🚨 WHALE TRADE DETECTED! [Wallet: {whale_wallet[:8]}... | Market: {market_id[:8]}... | {side} {outcome} @ {price:.2f}]")

        cursor = db_conn.cursor()
        cursor.execute('''
                       INSERT INTO trades (whale_wallet, market_id, outcome, side, price, simulated_bet)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ''', (whale_wallet, market_id, outcome, side, price, SIMULATED_BET_AMOUNT))
        db_conn.commit()

        print(f"   -> Simulated $1.00 trade logged to database.")

    except sqlite3.Error as e:
        print(f"Error logging trade to database: {e}")
    except Exception as e:
        print(f"Error parsing trade data: {e} | Data: {trade_data}")

def on_message(ws, message):
    """
    Main websocket callback function for the RTDS.
    """
    global whale_wallets

    if DEBUG_MODE:
        print(message) # --- THIS IS THE FIX ---

    try:
        data = json.loads(message)

        if data.get("topic") == "activity" and data.get("type") == "orders_matched":
            trade = data.get("payload")
            if not trade:
                return

            trader_wallet = trade.get('proxyWallet') # <-- This is our ASSUMPTION

            if trader_wallet in whale_wallets:
                log_trade(trade)

    except json.JSONDecodeError:
        pass
    except Exception as e:
        print(f"Error in on_message: {e}")
        if not DEBUG_MODE: # Don't print message twice
            print(f"Problematic message: {message}")

def on_error(ws, error):
    print(f"--- WebSocket Error: {error} ---")

def on_close(ws, close_status_code, close_msg):
    print(f"--- WebSocket Closed: {close_msg} (Code: {close_status_code}) ---")

def on_open(ws):
    """
    Called when the websocket connection is first established.
    """
    print("--- WebSocket Connection Opened ---")

    subscribe_message = {
        "action": "subscribe",
        "subscriptions": [
            {
                "topic": "activity",
                "type": "orders_matched",
                "clob_auth": {
                    "key": API_KEY,
                    "secret": API_SECRET,
                    "passphrase": API_PASSPHRASE
                }
            }
        ]
    }

    ws.send(json.dumps(subscribe_message))
    print("Sent authenticated subscription request for 'activity' feed.")

def start_websocket():
    """
    Initializes and runs the websocket client.
    """
    while True:
        try:
            print(f"Connecting to {WEBSOCKET_URL}...")
            ws = websocket.WebSocketApp(
                WEBSOCKET_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            wst = Thread(target=ws.run_forever, kwargs={"ping_interval": 5, "ping_timeout": 3})
            wst.daemon = True
            wst.start()

            while wst.is_alive():
                wst.join(1)

        except Exception as e:
            print(f"Websocket run_forever() crashed: {e}")

        print("Connection lost. Reconnecting in 10 seconds...")
        time.sleep(10)

# --- Main execution ---
if __name__ == "__main__":
    if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
        print("Error: POLYMARKET_API_KEY, SECRET, or PASSPHRASE not found in .env file.")
        print("Please create a .env file with your API credentials.")
        sys.exit(1)

    load_whales()
    setup_database()

    print("Starting live trade simulator bot. This will run 24/7.")
    if DEBUG_MODE:
        print("--- DEBUG MODE IS ON: ALL LIVE DATA WILL BE PRINTED ---")
    print("Press CTRL+C to stop.")
    start_websocket()