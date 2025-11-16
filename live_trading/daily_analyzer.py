import requests
import pandas as pd
import sqlite3
import os
import sys
import json
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

# --- config ---
load_dotenv()


DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
GRAPH_FILE = "pnl_over_time.png"


DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
MARKETS_URL = "https://gamma-api.polymarket.com/markets"
BATCH_SIZE = 50  # how many markets to query the api for at once

# --- 1. Database & API Functions ---

def get_db_connection():
    """establishes a connection to the sqlite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"error connecting to database: {e}")
        sys.exit(1)

def get_unresolved_trades(conn):
    """
    fetches all trades from the database that have not been
    resolved yet (is_resolved = 0).
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE is_resolved = 0")
    return cursor.fetchall()

def fetch_market_results(market_ids):
    """
    fetches the resolution data for a *specific list*
    of market ids from the polymarket api.
    """
    print(f"fetching results for {len(market_ids)} specific markets from api...")
    results = {}

    # we must query in batches, as the api may have a url length limit
    for i in range(0, len(market_ids), BATCH_SIZE):
        batch_ids = market_ids[i : i + BATCH_SIZE]
        id_string = ",".join(batch_ids)

        try:
            # use the 'condition_ids' parameter to get *only* the markets we need
            params = {
                'condition_ids': id_string
            }
            response = requests.get(MARKETS_URL, params=params, timeout=10)
            response.raise_for_status()
            markets_data = response.json()

            if not isinstance(markets_data, list):
                print(f"error: api did not return a list for batch {i}. response: {markets_data}")
                continue

            print(f"batch {i}: received {len(markets_data)} markets from api")

            for market in markets_data:
                condition_id = market.get('conditionId')
                if not condition_id:
                    continue
                
                # check multiple ways a market can be resolved
                resolution_status = market.get('umaResolutionStatus')
                closed = market.get('closed', False)
                
                # check if market is closed/resolved
                is_resolved = False
                if resolution_status:
                    # check for various resolution statuses
                    if resolution_status.upper() in ['FINAL', 'RESOLVED', 'RESOLVED_FINAL']:
                        is_resolved = True
                elif closed:
                    # if market is closed, check if it has final prices
                    prices_data = market.get('outcomePrices')
                    if prices_data:
                        # try to parse and check if sum is close to 1 (resolved)
                        try:
                            if isinstance(prices_data, list):
                                prices_sum = sum([float(p) if p else 0.0 for p in prices_data])
                            elif isinstance(prices_data, str):
                                prices_list = json.loads(prices_data)
                                prices_sum = sum([float(p) if p else 0.0 for p in prices_list])
                            else:
                                prices_sum = 0
                            
                            if prices_sum > 0.99:  # market is resolved if prices sum to ~1
                                is_resolved = True
                        except:
                            pass

                if condition_id in batch_ids and is_resolved:
                    # parse the data
                    outcomes, final_prices = parse_market_data(market)
                    if outcomes and final_prices:
                        results[condition_id] = {
                            "outcomes": json.loads(outcomes),
                            "final_prices": json.loads(final_prices)
                        }
                        print(f"  -> found resolved market: {condition_id[:8]}... (status: {resolution_status}, closed: {closed})")
                    else:
                        print(f"  -> market {condition_id[:8]}... is resolved but could not parse data")

            time.sleep(0.2)  # rate limit

        except Exception as e:
            print(f"error fetching market results for batch {i}: {e}")
            import traceback
            traceback.print_exc()

    print(f"found results for {len(results)} newly resolved markets.")
    return results

def parse_market_data(market_row):
    """
    parses the outcome and price data from the api.
    handles both list and string formats.
    """
    try:
        prices_data = market_row.get('outcomePrices')
        outcomes_data = market_row.get('outcomes')

        if not prices_data or not outcomes_data:
            return None, None

        if isinstance(prices_data, list):
            prices_list = prices_data
        elif isinstance(prices_data, str):
            prices_list = json.loads(prices_data)
        else:
            return None, None

        if isinstance(outcomes_data, list):
            outcomes_list = outcomes_data
        elif isinstance(outcomes_data, str):
            outcomes_list = json.loads(outcomes_data)
        else:
            return None, None

        if not all([isinstance(l, list) for l in [prices_list, outcomes_list]]):
            return None, None
        if len(prices_list) != len(outcomes_list):
            return None, None

        prices_as_float = []
        for p in prices_list:
            if p is None:
                prices_as_float.append(0.0)
            else:
                try:
                    prices_as_float.append(float(p))
                except (ValueError, TypeError):
                    prices_as_float.append(0.0)

        # check if the market is actually resolved (sum of prices should be close to 1)
        prices_sum = sum(prices_as_float)
        if not prices_as_float or prices_sum < 0.99:
            return None, None

        return json.dumps(outcomes_list), json.dumps(prices_as_float)

    except Exception as e:
        print(f"error parsing market data: {e}")
        return None, None

def calculate_pnl(trade, market_result):
    """
    calculates the p&l for a single simulated trade.
    """
    try:
        trade_outcome = str(trade['outcome']).upper()
        outcomes_upper = [str(o).upper() for o in market_result['outcomes']]

        if trade_outcome not in outcomes_upper:
            print(f"warning: trade outcome '{trade_outcome}' not found in market outcomes: {outcomes_upper}")
            return 0

        trade_index = outcomes_upper.index(trade_outcome)
        settlement_price = market_result['final_prices'][trade_index]

        purchase_price = float(trade['price'])
        bet_amount = float(trade['simulated_bet'])

        if str(trade['side']).upper() == 'BUY':
            if purchase_price == 0:
                return 0
            shares_bought = bet_amount / purchase_price
            value_at_settlement = shares_bought * settlement_price
            pnl = value_at_settlement - bet_amount
        else:  # SELL
            if (1 - purchase_price) == 0:
                return 0
            shares_shorted = bet_amount / (1 - purchase_price)
            payout_at_settlement = shares_shorted * (1 - settlement_price)
            pnl = payout_at_settlement - bet_amount

        return pnl

    except Exception as e:
        print(f"error calculating pnl: {e}")
        import traceback
        traceback.print_exc()
        return 0

def update_database(conn, trades_to_update, today_pnl):
    """
    updates trades to 'is_resolved=1' and logs daily p&l.
    """
    cursor = conn.cursor()

    for trade_id, pnl in trades_to_update:
        cursor.execute('''
                       UPDATE trades
                       SET is_resolved = 1, pnl = ?
                       WHERE id = ?
                       ''', (pnl, trade_id))

    print(f"updated {len(trades_to_update)} trades as 'resolved' in database.")

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
    print(f"updated p&l history for {today_str}. new total p&l: ${new_cumulative_pnl:.2f}")

# --- 2. Reporting & Graphing Functions ---

def get_pnl_history(conn):
    """fetches all p&l history for the graph."""
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
    creates and saves a .png graph of the cumulative p&l over time.
    """
    if pnl_df.empty:
        print("no p&l history to graph.")
        return False

    print("generating p&l graph...")
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
    print(f"graph saved to '{GRAPH_FILE}'.")
    return True

def get_report_stats(conn, today_pnl):
    """
    generates text stats for the discord message.
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
        top_whales_str += "no whales have resolved trades yet."
    else:
        for i, row in enumerate(top_whales_rows):
            top_whales_str += f"{i+1}. {row['whale_wallet']}  |  ${row['total_pnl']:.2f}\n"
    top_whales_str += "```"

    return total_pnl, top_whales_str

def post_to_discord(today_pnl, total_pnl, top_whales_report, graph_generated):
    """
    posts the complete summary message to discord with the graph.
    """
    if not DISCORD_WEBHOOK_URL:
        print("error: DISCORD_WEBHOOK_URL not set in .env file. skipping discord post.")
        return

    print("posting daily report to discord...")

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
            print(f"warning: could not find graph file '{GRAPH_FILE}' to attach.")
            graph_generated = False

    try:
        if graph_generated and files:
            response = requests.post(DISCORD_WEBHOOK_URL, files=files, data={'payload_json': json.dumps(data)})
        else:
            response = requests.post(DISCORD_WEBHOOK_URL, json=data)

        response.raise_for_status()
        print("successfully posted to discord.")
    except Exception as e:
        print(f"error posting to discord: {e}")
        if hasattr(response, 'text'):
            print(f"discord api response: {response.text}")

# --- 3. Main Execution ---

def main():
    print(f"--- running daily analyzer ({datetime.now().isoformat()}) ---")
    conn = get_db_connection()

    unresolved_trades = get_unresolved_trades(conn)

    if not unresolved_trades:
        print("no unresolved trades found in database. nothing to do.")
        today_pnl = 0
    else:
        print(f"found {len(unresolved_trades)} unresolved trades.")
        market_ids = list(set([t['market_id'] for t in unresolved_trades]))
        print(f"checking {len(market_ids)} unique markets for resolution...")

        market_results = fetch_market_results(market_ids)

        if not market_results:
            print("no new markets were resolved. nothing to update.")
            print("note: markets may still be open, or api may not have returned resolution data.")
            today_pnl = 0
        else:
            trades_to_update = []  # (trade_id, pnl)
            today_pnl = 0

            for trade in unresolved_trades:
                if trade['market_id'] in market_results:
                    market_result = market_results[trade['market_id']]
                    pnl = calculate_pnl(trade, market_result)

                    trades_to_update.append((trade['id'], pnl))
                    today_pnl += pnl

            print(f"calculated p&l for {len(trades_to_update)} newly resolved trades.")
            print(f"today's total p&l: ${today_pnl:+.2f}")

            if trades_to_update:
                update_database(conn, trades_to_update, today_pnl)
            else:
                print("warning: market_results found but no trades matched. check market_id matching.")

    pnl_df = get_pnl_history(conn)
    graph_generated = generate_pnl_graph(pnl_df)

    total_pnl, top_whales_report = get_report_stats(conn, today_pnl)

    post_to_discord(today_pnl, total_pnl, top_whales_report, graph_generated)

    conn.close()
    print("--- daily analysis complete. ---")

if __name__ == "__main__":
    main()