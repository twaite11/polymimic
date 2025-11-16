import websocket
import json
import sqlite3
import pandas as pd
import os
import sys
import time
import logging
import requests
from datetime import datetime, timedelta
from threading import Thread
from dotenv import load_dotenv
from pathlib import Path

# --- config ---
DEBUG_MODE = False
HEARTBEAT_INTERVAL = 60 # print a "." every 60 seconds to show it's alive

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
MARKETS_URL = "https://gamma-api.polymarket.com/markets"
TOP_N_WHALES = 400
SIMULATED_BET_AMOUNT = 1.0  # $1 per trade

# --- global state ---
db_conn = None
whale_wallets = set()
api_session = requests.Session()

# new function to set up logging
def setup_logging():
    """
    configures logging to print to both console and the log file.
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

        logging.info("logging setup complete.")

    except Exception as e:
        print(f"fatal error: could not set up logging. {e}")
        sys.exit(1)


def load_whales():
    """
    loads the top n whale wallets from the whale_report.csv file.
    """
    global whale_wallets
    if not os.path.exists(WHALE_REPORT_FILE):
        logging.error(f"'{WHALE_REPORT_FILE}' not found.")
        logging.error("please run 'find_whales.py' first to generate your whale list.")
        sys.exit(1)

    logging.info(f"loading top {TOP_N_WHALES} whales from '{WHALE_REPORT_FILE}'...")
    df = pd.read_csv(WHALE_REPORT_FILE)
    top_wallets_df = df.groupby('user')['total_pnl'].sum().nlargest(TOP_N_WHALES).reset_index()

    # convert all whale addresses to lowercase for reliable matching
    whale_wallets = set(top_wallets_df['user'].str.lower().unique())

    logging.info(f"successfully loaded {len(whale_wallets)} unique whale wallets to monitor.")

def setup_database():
    """
    creates the sqlite database and the 'trades' table if it doesn't exist.
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
                                                             question TEXT,
                                                             outcome TEXT NOT NULL,
                                                             side TEXT NOT NULL,
                                                             price REAL NOT NULL,
                                                             simulated_bet REAL NOT NULL,
                                                             is_resolved INTEGER DEFAULT 0,
                                                             pnl REAL DEFAULT 0
                       )
                       ''')
        
        # add question column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE trades ADD COLUMN question TEXT")
        except sqlite3.OperationalError:
            # column already exists, ignore
            pass

        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS pnl_history (
                                                                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                                                                  timestamp DATE UNIQUE,
                                                                  cumulative_pnl REAL NOT NULL
                       )
                       ''')

        db_conn.commit()
        logging.info(f"database '{DATABASE_FILE}' is ready.")

    except sqlite3.Error as e:
        logging.error(f"error setting up database: {e}")
        sys.exit(1)

def fetch_market_info(market_id):
    """
    fetches the market info from the polymarket api.
    returns a dict with question, closed status, and endDate, or none if not found.
    """
    try:
        time.sleep(0.1)  # rate limit: small delay to avoid hammering api
        params = {'condition_ids': market_id}
        response = api_session.get(MARKETS_URL, params=params, timeout=5)
        response.raise_for_status()
        markets_data = response.json()
        
        if isinstance(markets_data, list) and len(markets_data) > 0:
            market = markets_data[0]
            if market.get('conditionId') == market_id:
                return {
                    'question': market.get('question'),
                    'closed': market.get('closed', False),
                    'endDate': market.get('endDate'),
                    'umaResolutionStatus': market.get('umaResolutionStatus')
                }
        
        return None
    except Exception as e:
        logging.debug(f"error fetching market info for {market_id[:8]}...: {e}")
        return None

def log_trade(trade_data, whale_wallet):
    """
    called when a whale trade is detected. inserts it into the database.
    """
    global db_conn
    try:
        market_id = trade_data.get('conditionId')
        outcome = trade_data.get('outcome')
        side = trade_data.get('side')
        price_str = trade_data.get('price')

        if price_str is None: 
            return
        price = float(price_str)

        if not all([whale_wallet, market_id, outcome, side, price is not None]):
            logging.debug(f"skipping incomplete trade data: {trade_data}")
            return

        # fetch market info from api (question, closed status, etc.)
        market_info = fetch_market_info(market_id)
        if not market_info:
            logging.debug(f"could not fetch market info for market {market_id[:8]}...")
            question = None
            is_closed = False
        else:
            question = market_info.get('question')
            is_closed = market_info.get('closed', False)
            
            # print market question for verification
            if question:
                logging.info(f"market question: {question}")
            else:
                logging.warning(f"market {market_id[:8]}... has no question field")

        logging.info(f"whale trade detected! [wallet: {whale_wallet[:8]}... | market: {market_id[:8]}... | {side} {outcome} @ {price:.2f}]")

        cursor = db_conn.cursor()
        cursor.execute('''
                       INSERT INTO trades (whale_wallet, market_id, question, outcome, side, price, simulated_bet)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ''', (whale_wallet, market_id, question, outcome, side, price, SIMULATED_BET_AMOUNT))
        db_conn.commit()

        logging.info(f"   -> simulated $1.00 trade logged to database.")

    except sqlite3.Error as e:
        logging.error(f"error logging trade to database: {e}")
    except Exception as e:
        logging.error(f"error parsing trade data: {e} | data: {trade_data}")

def is_market_active(market_id):
    """
    checks if a market is still active (not closed/resolved).
    returns true if market is active, false if it's already resolved.
    """
    try:
        market_info = fetch_market_info(market_id)
        if not market_info:
            # if we can't fetch market info, assume it's active (better to process than skip)
            logging.debug(f"could not fetch market info for {market_id[:8]}..., assuming active")
            return True
        
        # check if market is closed
        is_closed = market_info.get('closed', False)
        resolution_status = market_info.get('umaResolutionStatus')
        
        # market is active if it's not closed and not resolved
        if is_closed:
            logging.debug(f"market {market_id[:8]}... is closed, skipping trade")
            return False
        
        if resolution_status and resolution_status.upper() in ['FINAL', 'RESOLVED', 'RESOLVED_FINAL']:
            logging.debug(f"market {market_id[:8]}... is resolved ({resolution_status}), skipping trade")
            return False
        
        # market is active
        return True
    except Exception as e:
        logging.debug(f"error checking market status for {market_id[:8]}...: {e}")
        # if we can't check, assume it's active (better to process than skip)
        return True

def on_message(ws, message):
    """
    main websocket callback function for the rtds.
    """
    global whale_wallets

    logging.debug(message) # will only print if debug_mode is on

    try:
        data = json.loads(message)

        if data.get("topic") == "activity" and data.get("type") == "orders_matched":
            trade = data.get("payload")
            if not trade:
                return

            market_id = trade.get('conditionId')
            if not market_id:
                return

            # filter out trades for markets that are already closed/resolved
            if not is_market_active(market_id):
                logging.debug(f"skipping trade for resolved/closed market: {market_id[:8]}...")
                return

            # check 1: is the taker one of our whales? (convert to lowercase)
            taker_wallet = trade.get('proxyWallet')
            if taker_wallet and taker_wallet.lower() in whale_wallets:
                log_trade(trade, taker_wallet)
                return

            # check 2: is the maker one of our whales? (convert to lowercase)
            maker_orders = trade.get('maker_orders', [])
            if not maker_orders:
                return

            for maker_order in maker_orders:
                maker_wallet = maker_order.get('maker_address')
                if maker_wallet and maker_wallet.lower() in whale_wallets:
                    log_trade(trade, maker_wallet)
                    break

    except json.JSONDecodeError:
        pass
    except Exception as e:
        logging.error(f"error in on_message: {e}")
        logging.debug(f"problematic message: {message}")

def on_error(ws, error):
    """
    handles websocket errors. connection errors will trigger reconnection.
    """
    error_str = str(error)
    # connection errors are expected and will auto-reconnect
    if "ping/pong" in error_str.lower() or "timeout" in error_str.lower() or "connection" in error_str.lower():
        logging.debug(f"websocket connection issue (will reconnect): {error}")
    else:
        logging.warning(f"--- websocket error: {error} ---")

def on_close(ws, close_status_code, close_msg):
    """
    handles websocket close events. this is normal when reconnecting.
    """
    if close_status_code is None and close_msg is None:
        # this often happens with ping/pong timeouts, it's normal
        logging.info("websocket closed (will reconnect)")
    else:
        logging.warning(f"--- websocket closed: {close_msg} (code: {close_status_code}) ---")

# global variable to track reconnect delay
reconnect_delay = 5

def on_open(ws):
    """
    called when the websocket connection is first established.
    """
    global reconnect_delay
    logging.info("--- websocket connection opened ---")
    
    # reset reconnect delay on successful connection
    reconnect_delay = 5

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
    logging.info("sent authenticated subscription request for 'activity' feed.")
    logging.info(f"bot is now silently listening... (will print '.' every {HEARTBEAT_INTERVAL}s if DEBUG_MODE is on)")
    logging.info("note: connection issues will auto-reconnect silently")

def start_websocket():
    """
    initializes and runs the websocket client.
    """
    global reconnect_delay
    max_reconnect_delay = 60  # max delay of 60 seconds
    
    while True:
        try:
            logging.info(f"connecting to {WEBSOCKET_URL}...")
            ws = websocket.WebSocketApp(
                WEBSOCKET_URL,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )

            # disable automatic ping/pong - the server may handle keepalive differently
            # or we can rely on the server's own keepalive mechanism
            # if ping/pong timeouts occur, we'll reconnect automatically
            wst = Thread(target=ws.run_forever, kwargs={
                "ping_interval": None,  # disable automatic ping
                "ping_timeout": None
            })
            wst.daemon = True
            wst.start()

            # --- heartbeat thread ---
            # this loops in the main thread, printing a dot
            # so you know the script is alive.
            while wst.is_alive():
                time.sleep(HEARTBEAT_INTERVAL)
                logging.debug(".")  # prints a dot to the log in debug mode
            # --- end heartbeat ---

        except Exception as e:
            logging.error(f"websocket run_forever() crashed: {e}")
            import traceback
            traceback.print_exc()

        # reconnect immediately on first attempt, then use exponential backoff
        if reconnect_delay > 5:
            logging.warning(f"connection lost. reconnecting in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
        else:
            logging.info("connection lost. reconnecting immediately...")
            time.sleep(1)  # minimal delay to avoid rapid reconnection loops
        
        # exponential backoff for reconnection delay (cap at max)
        reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)

# --- main execution ---
if __name__ == "__main__":
    # set up logging first
    setup_logging()

    if not all([API_KEY, API_SECRET, API_PASSPHRASE]):
        logging.error("error: POLYMARKET_API_KEY, SECRET, or PASSPHRASE not found in .env file.")
        logging.error("please create a .env file with your API credentials.")
        sys.exit(1)

    load_whales()
    setup_database()

    logging.info(f"starting live trade simulator bot. this will run 24/7.")
    logging.info(f"only processing trades for active markets (not closed/resolved).")
    if DEBUG_MODE:
        logging.info("--- debug mode is on: all live data will be logged ---")
    logging.info("press CTRL+C to stop.")
    start_websocket()