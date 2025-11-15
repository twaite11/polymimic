import websocket
import json
import sqlite3
import pandas as pd
import os
import sys
import time
import logging # <-- 1. added this
from threading import Thread
from dotenv import load_dotenv
from pathlib import Path

# --- config ---
DEBUG_MODE = False
HEARTBEAT_INTERVAL = 60 # Print a "." every 60 seconds to show it's alive

load_dotenv()

# --- FILE PATHS ---
WHALE_REPORT_FILE = Path("~/IdeaProjects/PolyCopy/modules/scalar_analysis/whale_report.csv").expanduser()
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
SIMULATOR_LOG_FILE = Path("~/IdeaProjects/PolyCopy/logs/simulator.log").expanduser()

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

# 3. new function to set up logging
def setup_logging():
    """
    Configures logging to print to both console and the log file.
    """
    try:
        # ensure the 'logs' directory exists
        SIMULATOR_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

        # set logging level
        level = logging.DEBUG if DEBUG_MODE else logging.INFO

        # basic config sets up the root logger
        # using 'w' filemode to clear the log on each new run
        logging.basicConfig(
            level=level,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[
                logging.FileHandler(SIMULATOR_LOG_FILE, mode='w'), # writes to the file
                logging.StreamHandler(sys.stdout) # writes to the console
            ]
        )

        logging.info("Logging setup complete.")

    except Exception as e:
        print(f"Fatal Error: Could not set up logging. {e}")
        sys.exit(1)


def load_whales():
    """
    Loads the Top N whale wallets from the whale_report.csv file.
    """
    global whale_wallets
    if not os.path.exists(WHALE_REPORT_FILE):
        logging.error(f"'{WHALE_REPORT_FILE}' not found.")
        logging.error("Please run 'find_whales.py' first to generate your whale list.")
        sys.exit(1)

    logging.info(f"Loading top {TOP_N_WHALES} whales from '{WHALE_REPORT_FILE}'...")
    df = pd.read_csv(WHALE_REPORT_FILE)
    top_wallets_df = df.groupby('user')['total_pnl'].sum().nlargest(TOP_N_WHALES).reset_index()

    # --- THIS IS THE FIX ---
    # Convert all whale addresses to lowercase for reliable matching
    whale_wallets = set(top_wallets_df['user'].str.lower().unique())
    # --- END OF FIX ---

    logging.info(f"Successfully loaded {len(whale_wallets)} unique whale wallets to monitor.")

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
        logging.info(f"Database '{DATABASE_FILE}' is ready.")

    except sqlite3.Error as e:
        logging.error(f"Error setting up database: {e}")
        sys.exit(1)

def log_trade(trade_data, whale_wallet):
    """
    Called when a whale trade is detected. Inserts it into the database.
    """
    global db_conn
    try:
        market_id = trade_data.get('conditionId')
        outcome = trade_data.get('outcome')
        side = trade_data.get('side')
        price_str = trade_data.get('price')

        if price_str is None: return
        price = float(price_str)

        if not all([whale_wallet, market_id, outcome, side, price is not None]):
            logging.debug(f"Skipping incomplete trade data: {trade_data}")
            return

        logging.info(f"🚨 WHALE TRADE DETECTED! [Wallet: {whale_wallet[:8]}... | Market: {market_id[:8]}... | {side} {outcome} @ {price:.2f}]")

        cursor = db_conn.cursor()
        cursor.execute('''
                       INSERT INTO trades (whale_wallet, market_id, outcome, side, price, simulated_bet)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ''', (whale_wallet, market_id, outcome, side, price, SIMULATED_BET_AMOUNT))
        db_conn.commit()

        logging.info(f"   -> Simulated $1.00 trade logged to database.")

    except sqlite3.Error as e:
        logging.error(f"Error logging trade to database: {e}")
    except Exception as e:
        logging.error(f"Error parsing trade data: {e} | Data: {trade_data}")

def on_message(ws, message):
    """
    Main websocket callback function for the RTDS.
    """
    global whale_wallets

    logging.debug(message) # will only print if debug_mode is on

    try:
        data = json.loads(message)

        if data.get("topic") == "activity" and data.get("type") == "orders_matched":
            trade = data.get("payload")
            if not trade:
                return

            # --- THIS IS THE FIX (Part 1) ---
            # Check 1: Is the TAKER one of our whales? (Convert to lowercase)
            taker_wallet = trade.get('proxyWallet')
            if taker_wallet and taker_wallet.lower() in whale_wallets:
                log_trade(trade, taker_wallet)
                return

                # --- THIS IS THE FIX (Part 2) ---
            # Check 2: Is the MAKER one of our whales? (Convert to lowercase)
            maker_orders = trade.get('maker_orders', [])
            if not maker_orders:
                return

            for maker_order in maker_orders:
                maker_wallet = maker_order.get('maker_address')
                if maker_wallet and maker_wallet.lower() in whale_wallets:
                    log_trade(trade, maker_wallet)
                    break
                    # --- END OF FIX ---

    except json.JSONDecodeError:
        pass
    except Exception as e:
        logging.error(f"Error in on_message: {e}")
        logging.debug(f"Problematic message: {message}")

def on_error(ws, error):
    logging.warning(f"--- WebSocket Error: {error} ---")

def on_close(ws, close_status_code, close_msg):
    logging.warning(f"--- WebSocket Closed: {close_msg} (Code: {close_status_code}) ---")

def on_open(ws):
    """
    Called when the websocket connection is first established.
    """
    logging.info("--- WebSocket Connection Opened ---")

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
    logging.info("Sent authenticated subscription request for 'activity' feed.")
    logging.info(f"Bot is now silently listening... (will print '.' every {HEARTBEAT_INTERVAL}s if DEBUG_MODE is on)")

def start_websocket():
    """
    Initializes and runs the websocket client.
    """
    while True:
        try:
            logging.info(f"Connecting to {WEBSOCKET_URL}...")
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

            # --- HEARTBEAT THREAD ---
            # this loops in the main thread, printing a dot
            # so you know the script is alive.
            while wst.is_alive():
                time.sleep(HEARTBEAT_INTERVAL)
                # 4. changed this to logging.debug
                logging.debug(".") # prints a dot to the log in debug mode
            # --- END HEARTBEAT ---

        except Exception as e:
            logging.error(f"Websocket run_forever() crashed: {e}")

        logging.warning("Connection lost. Reconnecting in 10 seconds...")
        time.sleep(10)

# --- Main execution ---
if __name__ == "__main__":
    # 5. set up logging first!
    setup_logging()

    if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
        logging.error("Error: POLYMARKET_API_KEY, SECRET, or PASSPHRASE not found in .env file.")
        logging.error("Please create a .env file with your API credentials.")
        sys.exit(1)

    load_whales()
    setup_database()

    logging.info("Starting live trade simulator bot. This will run 24/7.")
    if DEBUG_MODE:
        logging.info("--- DEBUG MODE IS ON: ALL LIVE DATA WILL BE LOGGED ---")
    logging.info("Press CTRL+C to stop.")
    start_websocket()