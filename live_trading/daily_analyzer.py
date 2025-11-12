import requests
import pandas as pd
import sqlite3
import os
import sys
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# --- config ---
load_dotenv()

# --- FILE PATH FIX ---
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
GRAPH_FILE = "pnl_over_time.png"
# --- END FILE PATH FIX ---

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
MARKETS_URL = "https://gamma-api.polymarket.com/markets"
BATCH_SIZE = 50 # How many markets to query the API for at once

# --- 1. Database & API Functions ---

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_unresolved_trades(conn):
    """
    Fetches all trades from the database that have not been
    resolved yet (is_resolved = 0).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE is_resolved = 0")
    return cursor.fetchall()

# --- THIS IS THE CRITICAL FIX ---
def fetch_market_results(market_ids):
    """
    Fetches the resolution data for a *specific list*
    of market IDs from the Polymarket API.
    """
    print(f"Fetching results for {len(market_ids)} specific markets from API...")
    results = {}

    # We must query in batches, as the API may have a URL length limit
    for i in range(0, len(market_ids), BATCH_SIZE):
        batch_ids = market_ids[i : i + BATCH_SIZE]
        id_string = ",".join(batch_ids)

        try:
            # Use the 'condition_ids' parameter to get *only* the markets we need
            params = {
                'condition_ids': id_string
            }
            response = requests.get(MARKETS_URL, params=params)
            response.raise_for_status()
            markets_data = response.json()

            if not isinstance(markets_data, list):
                print(f"Error: API did not return a list for batch {i}.")
                continue

            for market in markets_data:
                condition_id = market.get('conditionId')
                if condition_id in batch_ids:
                    # Parse the data *only* if it is also closed
                    if market.get('closed') == True:
                        outcomes, final_prices = parse_market_data(market)
                        if outcomes and final_prices:
                            results[condition_id] = {
                                "outcomes": json.loads(outcomes),
                                "final_prices": json.loads(final_prices)
                            }

            time.sleep(0.2) # Rate limit

        except Exception as e:
            print(f"Error fetching market results for batch {i}: {e}")

    print(f"Found results for {len(results)} newly resolved markets.")
    return results
# --- END OF FIX ---

def parse_market_data(market_row):
    """
    Parses the outcome and price data from the API.
    Handles both list and string formats.
    """
    try:
        prices_data = market_row.get('outcomePrices')
        outcomes_data = market_row.get('outcomes')

        if not prices_data or not outcomes_data: return None, None

        if isinstance(prices_data, list): prices_list = prices_data
        elif isinstance(prices_data, str): prices_list = json.loads(prices_data)
        else: return None, None

        if isinstance(outcomes_data, list): outcomes_list = outcomes_data
        elif isinstance(outcomes_data, str): outcomes_list = json.loads(outcomes_data)
        else: return None, None

        if not all([isinstance(l, list) for l in [prices_list, outcomes_list]]): return None, None
        if len(prices_list) != len(outcomes_list): return None, None

        prices_as_float = []
        for p in prices_list:
            if p is None:
                prices_as_float.append(0.0)
            else:
                prices_as_float.append(float(p))

        if not prices_as_float or sum(prices_as_float) < 0.01:
            return None, None

        return json.dumps(outcomes_list), json.dumps(prices_as_float)

    except Exception:
        return None, None

def calculate_pnl(trade, market_result):
    """
    Calculates the P&L for a single simulated trade.
    """
    try:
        trade_outcome = trade['outcome'].upper()

        if trade_outcome not in [o.upper() for o in market_result['outcomes']]:
            return 0

        trade_index = [o.upper() for o in market_result['outcomes']].index(trade_outcome)
        settlement_price = market_result['final_prices'][trade_index]

        purchase_price = trade['price']
        bet_amount = trade['simulated_bet']

        if trade['side'].upper() == 'BUY':
            if purchase_price == 0: return 0
            shares_bought = bet_amount / purchase_price
            value_at_settlement = shares_bought * settlement_price
            pnl = value_at_settlement - bet_amount
        else: # SELL
            if (1 - purchase_price) == 0: return 0
            shares_shorted = bet_amount / (1 - purchase_price)
            payout_at_settlement = shares_shorted * (1 - settlement_price)
            pnl = payout_at_settlement - bet_amount

        return pnl

    except Exception as e:
        print(f"Error calculating PNL: {e}")
        return 0

def update_database(conn, trades_to_update, today_pnl):
    """
    Updates trades to 'is_resolved=1' and logs daily P&L.
    """
    cursor = conn.cursor()

    for trade_id, pnl in trades_to_update:
        cursor.execute('''
                       UPDATE trades
                       SET is_resolved = 1, pnl = ?
                       WHERE id = ?
                       ''', (pnl, trade_id))

    print(f"Updated {len(trades_to_update)} trades as 'resolved' in database.")

    today_str = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("SELECT cumulative_pnl FROM pnl_history ORDER BY timestamp DESC LIMIT 1")
    last_pnl_row = cursor.fetchone()
    last_cumulative_pnl = last_pnl_row['cumulative_pnl'] if last_pnl_row else 0

    new_cumulative_pnl = last_cumulative_pnl + today_pnl

    cursor.execute('''
                   INSERT INTO pnl_history (timestamp, cumulative_pnl)
                   VALUES (?, ?)
                       ON CONFLICT(timestamp) DO UPDATE SET cumulative_pnl = excluded.cumulative_pnl
                   ''', (today_str, new_cumulative_pnl))

    conn.commit()
    print(f"Updated P&L history for {today_str}. New total P&L: ${new_cumulative_pnl:.2f}")

# --- 2. Reporting & Graphing Functions ---

def get_pnl_history(conn):
    """Fetches all P&L history for the graph."""
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, cumulative_pnl FROM pnl_history ORDER BY timestamp ASC")
    rows = cursor.fetchall()

    if not rows:
        return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])

    df = pd.DataFrame(rows, columns=['timestamp', 'cumulative_pnl'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def generate_pnl_graph(pnl_df):
    """
    Creates and saves a .png graph of the cumulative P&L over time.
    """
    if pnl_df.empty:
        print("No P&L history to graph.")
        return False

    print("Generating P&L graph...")
    plt.figure(figsize=(10, 6))

    plt.plot(pnl_df['timestamp'], pnl_df['cumulative_pnl'], marker='o', linestyle='-', color='b')

    plt.title(f"Total Simulation P&L Over Time (Current: ${pnl_df['cumulative_pnl'].iloc[-1]:.2f})", fontsize=16)
    plt.ylabel("Cumulative P&L ($)")
    plt.xlabel("Date")
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    plt.gcf().autofmt_xdate()

    plt.savefig(GRAPH_FILE, dpi=100, bbox_inches='tight')
    plt.close()
    print(f"Graph saved to '{GRAPH_FILE}'.")
    return True

def get_report_stats(conn, today_pnl):
    """
    Generates text stats for the Discord message.
    """
    cursor = conn.cursor()

    cursor.execute("SELECT cumulative_pnl FROM pnl_history ORDER BY timestamp DESC LIMIT 1")
    total_pnl_row = cursor.fetchone()
    total_pnl = total_pnl_row['cumulative_pnl'] if total_pnl_row else 0

    cursor.execute('''
                   SELECT whale_wallet, SUM(pnl) as total_pnl
                   FROM trades
                   WHERE is_resolved = 1
                   GROUP BY whale_wallet
                   ORDER BY total_pnl DESC
                       LIMIT 5
                   ''')
    top_whales_rows = cursor.fetchall()

    top_whales_str = "```"
    if not top_whales_rows:
        top_whales_str += "No whales have resolved trades yet."
    else:
        for i, row in enumerate(top_whales_rows):
            top_whales_str += f"{i+1}. {row['whale_wallet']}  |  ${row['total_pnl']:.2f}\n"
    top_whales_str += "```"

    return total_pnl, top_whales_str

def post_to_discord(today_pnl, total_pnl, top_whales_report, graph_generated):
    """
    Posts the complete summary message to Discord with the graph.
    """
    if not DISCORD_WEBHOOK_URL:
        print("Error: DISCORD_WEBHOOK_URL not set in .env file. Skipping Discord post.")
        return

    print("Posting daily report to Discord...")

    if today_pnl > 0: color = 3066993 # Green
    elif today_pnl < 0: color = 15158332 # Red
    else: color = 10070709 # Grey

    data = {
        "content": "📈 **Daily Whale Simulation Report**",
        "embeds": [
            {
                "title": "Simulation P&L Summary",
                "color": color,
                "fields": [
                    {
                        "name": "Today's P&L",
                        "value": f"**${today_pnl:+.2f}**",
                        "inline": True
                    },
                    {
                        "name": "Total P&L (All-Time)",
                        "value": f"**${total_pnl:+.2f}**",
                        "inline": True
                    },
                    {
                        "name": "Top 5 Profitable Whales (All-Time)",
                        "value": top_whales_report,
                        "inline": False
                    }
                ],
                "footer": {
                    "text": f"Report generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            }
        ]
    }

    files = {}
    if graph_generated:
        try:
            files['file'] = (GRAPH_FILE, open(GRAPH_FILE, 'rb'))
            data["embeds"][0]["image"] = {"url": f"attachment://{GRAPH_FILE}"}
        except FileNotFoundError:
            print(f"Warning: Could not find graph file '{GRAPH_FILE}' to attach.")
            graph_generated = False

    try:
        if graph_generated and files:
            response = requests.post(DISCORD_WEBHOOK_URL, files=files, data={'payload_json': json.dumps(data)})
        else:
            response = requests.post(DISCORD_WEBHOOK_URL, json=data)

        response.raise_for_status()
        print("Successfully posted to Discord.")
    except Exception as e:
        print(f"Error posting to Discord: {e}")
        if hasattr(response, 'text'):
            print(f"Discord API response: {response.text}")

# --- 3. Main Execution ---

def main():
    print(f"--- Running Daily Analyzer ({datetime.now().isoformat()}) ---")
    conn = get_db_connection()

    unresolved_trades = get_unresolved_trades(conn)

    if not unresolved_trades:
        print("No unresolved trades found in database. Nothing to do.")
        today_pnl = 0
    else:
        print(f"Found {len(unresolved_trades)} unresolved trades.")
        market_ids = list(set([t['market_id'] for t in unresolved_trades]))

        market_results = fetch_market_results(market_ids)

        if not market_results:
            print("No new markets were resolved. Nothing to update.")
            today_pnl = 0
        else:
            trades_to_update = [] # (trade_id, pnl)
            today_pnl = 0

            for trade in unresolved_trades:
                if trade['market_id'] in market_results:
                    market_result = market_results[trade['market_id']]
                    pnl = calculate_pnl(trade, market_result)

                    trades_to_update.append((trade['id'], pnl))
                    today_pnl += pnl

            print(f"Calculated P&L for {len(trades_to_update)} newly resolved trades.")
            print(f"Today's total P&L: ${today_pnl:+.2f}")

            update_database(conn, trades_to_update, today_pnl)

    pnl_df = get_pnl_history(conn)
    graph_generated = generate_pnl_graph(pnl_df)

    total_pnl, top_whales_report = get_report_stats(conn, today_pnl)

    post_to_discord(today_pnl, total_pnl, top_whales_report, graph_generated)

    conn.close()
    print("--- Daily analysis complete. ---")

if __name__ == "__main__":
    main()