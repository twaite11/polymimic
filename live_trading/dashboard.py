import streamlit as st
import pandas as pd
import sqlite3
import os
import sys
import subprocess
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import json
import time # 

# --- config ---
# repo-relative paths for streamlit cloud
REPO_ROOT = Path(__file__).resolve().parent.parent
WHALE_REPORT_FILE = REPO_ROOT / "modules" / "scalar_analysis" / "whale_report.csv"
DATABASE_FILE = REPO_ROOT / "db" / "simulation.db"
MARKETS_FILE = REPO_ROOT / "preprocessing" / "scalar_trading" / "markets_with_groups_v2.csv"
ANALYZER_SCRIPT_PATH = (Path(__file__).resolve().parent / "daily_analyzer.py").as_posix()
SIMULATOR_LOG_FILE = REPO_ROOT / "logs" / "simulator.log"

# --- styling ---
st.set_page_config(layout="wide", page_title="Whale Watcher Dashboard")

# css 80's theme retro retro retro
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');

    /* --- (global font & theme) --- */
    /* apply font to all text elements */
    body, .stApp, div, p, span, h1, h2, h3, h4, h5, h6, th, td, button, summary, [data-testid="stTabs"] button {
        font-family: 'VT323', monospace !important;
        color: #dcd0ff !important; /* set default text color */
    }
    
    body, .stApp {
        background-color: #0E1117 !important;
    }

    /* --- (crt scanline & vignette effect) --- */
    .stApp::before {
        content: " ";
        display: block;
        position: fixed; 
        top: 0;
        left: 0;
        bottom: 0;
        right: 0;
        width: 100%;
        height: 100%;
        
        /* 1st background: the vignette (clear center, dark edges) */
        background: radial-gradient(
            ellipse at center, 
            rgba(0,0,0,0) 0%, /* clear center */
            rgba(0,0,0,0) 50%, /* clear out to 50% */
            rgba(0,0,0,0.4) 100% /* fade to 40% black at the edge */
        ),
        
        /* 2nd background: the fainter, wider scanlines */
        repeating-linear-gradient(
            to bottom,
            rgba(0, 0, 0, 0) 0px,
            rgba(0, 0, 0, 0) 2px,  /* 2px transparent */
            rgba(0, 0, 0, 0.1) 3px,  /* 1px very faint line (10% opacity) */
            rgba(0, 0, 0, 0.1) 4px
        );
        
        z-index: 2; /* above background, below modals */
        pointer-events: none; /* lets you click through it */
    }
    
    /* titles - purple gradient + glow */
    h1, h2, h3 {
        background: -webkit-linear-gradient(95deg, #E23A79, #7348c3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 600 !important;
    }

    /* --- (styled button) --- */
    /* this styles *all* buttons, including "what is this?" */
    [data-testid="stButton"] button {
        background-color: #312a45 !important;
        color: #dcd0ff !important;
        border: 1px solid #a991d4 !important;
        font-size: 1.2em !important; 
        padding: 10px 15px !important;
        border-radius: 8px !important;
    }
    [data-testid="stButton"] button:hover {
        background-color: #a991d4 !important;
        color: #0E1117 !important;
        border-color: #7348c3 !important;
    }
    [data-testid="stButton"] button p { /* text inside button */
        font-family: 'VT323', monospace !important;
        color: #dcd0ff !important;
    }
    [data-testid="stButton"] button:hover p {
        color: #0E1117 !important;
    }


    /* --- (styled markdown for help text) --- */
    /* this targets the text inside the help section */
    .help-text p, .help-text li {
        font-size: 1.1em !important;
        color: #dcd0ff !important;
        font-family: 'VT323', monospace !important;
    }
    /* this targets the headers inside the help section */
    .help-text h3, .help-text h4 {
        font-size: 1.3em !important;
        background: -webkit-linear-gradient(45deg, #a991d4, #7348c3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'VT323', monospace !important;
    }


    /* --- (styled table) --- */
    .retro-table {
        width: 100%;
        border-collapse: collapse;
    }
    .retro-table th {
        background: -webkit-linear-gradient(45deg, #a991d4, #7348c3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: left;
        padding: 8px;
        font-size: 1.2em !important; 
    }
    .retro-table td {
        padding: 6px 8px;
        border-bottom: 1px solid #312a45;
        font-size: 1.1em !important; 
    }
    .retro-table tr:hover td {
        background-color: #1f2333 !important;
        color: #ffffff !important;
        transition: background-color 0.2s ease-in-out;
    }
    
    .text-buy { color: #3dd56d !important; font-weight: 700; }
    .text-sell { color: #f94c4c !important; font-weight: 700; }
    
    
    /* --- (styled tabs) --- */
    /* this styles the tab buttons */
    [data-testid="stTabs"] button {
        background-color: transparent !important;
        color: #a991d4 !important; /* text color */
        border: 1px solid #312a45 !important;
        font-size: 1.2em !important;
        border-radius: 8px 8px 0 0 !important;
    }

    /* this is the "selected" tab button */
    [data-testid="stTabs"] button[aria-selected="true"] {
        background-color: #1f2333 !important;
        color: #dcd0ff !important;
        border: 1px solid #a991d4 !important;
        border-bottom: 1px solid #1f2333 !important; 
    }

    /* this is the content area below the tabs */
    [data-testid="stTabContent"] {
        background-color: #1f2333 !important;
        border: 1px solid #a991d4 !important;
        border-top: none !important;
        border-radius: 0 0 8px 8px !important;
        padding: 20px !important;
    }
    [data-testid="stTabs"] [role="tab"]:hover {
        background-color: #1f2333 !important;
        color: #dcd0ff !important;
        border: 1px solid #a991d4 !important;
        border-bottom: 1px solid #1f2333 !important; 
    }
    
    /* --- (ticker) --- */
    /* *** changed keyframes *** */
    @keyframes ticker {
        0% { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    .ticker-wrap {
        width: 100%;
        overflow: hidden;
        background-color: #1f2333;
        padding: 15px 0;
        border-radius: 8px;
    }
    .ticker-move {
        display: inline-block;
        white-space: nowrap;
        animation: ticker 500s linear infinite;
        color: #FFFFFF;
        font-size: 1.2em; 
    }
    .ticker-item {
        margin-right: 50px;
    }
    .ticker-buy { color: #3dd56d; }
    .ticker-sell { color: #f94c4c; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
# --- end of css ---

# --- database & data loading functions cached ---

@st.cache_resource
def get_db_connection():
    """establishes a connection to the sqlite database."""
    try:
        # ensure directories exist on first run
        DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        (REPO_ROOT / "logs").mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Error connecting to database: {e}")
        return None

@st.cache_data
def load_market_names():
    """loads just the market ids and questions from the v2 file."""
    if not os.path.exists(MARKETS_FILE):
        st.error(f"Market file not found: {MARKETS_FILE}")
        return pd.DataFrame(columns=['conditionId', 'question'])
    try:
        markets_df = pd.read_csv(MARKETS_FILE)[['conditionId', 'question']]
        return markets_df
    except Exception as e:
        st.error(f"Error loading market names: {e}")
        return pd.DataFrame(columns=['conditionId', 'question'])

@st.cache_data
def load_pnl_history():
    """builds daily cumulative p&l time series from resolved trades."""
    conn = get_db_connection()
    if conn:
        try:
            # build per-day realized pnl from resolved trades
            trades_df = pd.read_sql_query("""
                SELECT timestamp, pnl
                FROM trades
                WHERE is_resolved = 1
            """, conn)
            if trades_df.empty:
                return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])

            trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
            trades_df['pnl'] = pd.to_numeric(trades_df['pnl'], errors='coerce').fillna(0.0)
            trades_df['date'] = trades_df['timestamp'].dt.date

            daily_pnl = trades_df.groupby('date', as_index=False)['pnl'].sum().sort_values('date')
            daily_pnl['cumulative_pnl'] = daily_pnl['pnl'].cumsum()
            daily_pnl['timestamp'] = pd.to_datetime(daily_pnl['date'])
            return daily_pnl[['timestamp', 'cumulative_pnl']]
        except Exception:
            return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])
    return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])

@st.cache_data
def load_roi_history():
    """calculates cumulative roi (%) over time using daily aggregates.
    
    roi(t) = cumulative_pnl_to_date / cumulative_invested_to_date * 100
    """
    conn = get_db_connection()
    if not conn:
        return pd.DataFrame(columns=['timestamp', 'roi_percentage'])
    
    try:
        # cumulative pnl by day (already cumulative in load_pnl_history)
        pnl_df = load_pnl_history()
        if pnl_df.empty:
            return pd.DataFrame(columns=['timestamp', 'roi_percentage'])
        pnl_df = pnl_df.copy()
        pnl_df['date'] = pd.to_datetime(pnl_df['timestamp']).dt.date

        # cumulative invested by day (all trades, regardless of resolution)
        trades_df = pd.read_sql_query("""
            SELECT timestamp, simulated_bet 
            FROM trades
        """, conn)
        if trades_df.empty:
            return pd.DataFrame(columns=['timestamp', 'roi_percentage'])
        trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
        trades_df['date'] = trades_df['timestamp'].dt.date

        daily_invested = (
            trades_df.groupby('date', as_index=False)['simulated_bet']
            .sum()
            .sort_values('date')
            .rename(columns={'simulated_bet': 'invested'})
        )
        daily_invested['cumulative_invested'] = daily_invested['invested'].cumsum()

        # align by date and compute cumulative roi
        merged = pd.merge(pnl_df[['date', 'timestamp', 'cumulative_pnl']],
                          daily_invested[['date', 'cumulative_invested']],
                          on='date', how='left')
        merged['cumulative_invested'] = merged['cumulative_invested'].ffill().fillna(0)

        merged['roi_percentage'] = merged.apply(
            lambda r: (r['cumulative_pnl'] / r['cumulative_invested'] * 100) if r['cumulative_invested'] > 0 else 0,
            axis=1
        )

        return merged[['timestamp', 'roi_percentage']]
    except Exception as e:
        st.error(f"error loading roi history: {e}")
        return pd.DataFrame(columns=['timestamp', 'roi_percentage'])

@st.cache_data
def load_market_group_pnl():
    """calculates p&l grouped by market_group."""
    conn = get_db_connection()

    if not os.path.exists(MARKETS_FILE):
        st.error(f"Market file not found: {MARKETS_FILE}")
        return pd.DataFrame(columns=['market_group', 'total_pnl'])
    if not conn:
        return pd.DataFrame(columns=['market_group', 'total_pnl'])

    try:
        trades_df = pd.read_sql_query("SELECT market_id, pnl FROM trades WHERE is_resolved = 1", conn)

        if trades_df.empty:
            return pd.DataFrame(columns=['market_group', 'total_pnl'])

        full_markets_df = pd.read_csv(MARKETS_FILE)

        trades_with_groups = pd.merge(
            trades_df,
            full_markets_df,
            left_on='market_id',
            right_on='conditionId'
        )

        group_pnl = trades_with_groups.groupby('market_group')['pnl'].sum().reset_index()
        group_pnl = group_pnl.sort_values(by='pnl', ascending=False)
        return group_pnl

    except Exception as e:
        st.error(f"Error loading market group P&L: {e}")
        return pd.DataFrame(columns=['market_group', 'total_pnl'])

@st.cache_data
def load_open_positions_ticker():
    """
    fetches all live, unresolved trades for the ticker.
    now returns the ticker html string AND the latest timestamp for toasts.
    """
    conn = get_db_connection()
    markets_df = load_market_names()

    base_text = ""
    latest_timestamp = None

    if not conn:
        base_text = "database connection error."
    else:
        try:
            # query includes question from database (now stored directly in trades table)
            query = "SELECT * FROM trades WHERE is_resolved = 0 ORDER BY timestamp DESC LIMIT 500"
            positions_df = pd.read_sql_query(query, conn)

            if positions_df.empty:
                base_text = "no open simulated positions found. waiting for whale activity..."
            else:
                # get the timestamp of the *newest* trade for the toast
                latest_timestamp = pd.to_datetime(positions_df['timestamp']).max()

                # if question is null in database, try to get it from the csv file as fallback
                if not markets_df.empty:
                    merged_df = pd.merge(
                        positions_df,
                        markets_df,
                        left_on='market_id',
                        right_on='conditionId',
                        how='left',
                        suffixes=('', '_csv')
                    )
                    # use question from database, fallback to csv question, then to market_id
                    if 'question_csv' in merged_df.columns:
                        merged_df['question'] = merged_df['question'].fillna(merged_df['question_csv'])
                    merged_df['question'] = merged_df['question'].fillna(merged_df['market_id'])
                    # drop the csv question column if it exists
                    merged_df = merged_df.drop(columns=['question_csv'], errors='ignore')
                    positions_df = merged_df
                else:
                    # if no csv file, use question from db or fallback to market_id
                    positions_df['question'] = positions_df['question'].fillna(positions_df['market_id'])

                ticker_items = []
                for _, row in positions_df.iterrows():
                    side_class = "ticker-buy" if row['side'].upper() == 'BUY' else "ticker-sell"
                    question_short = (row["question"][:70] + '...') if row["question"] and len(str(row["question"])) > 70 else (row["question"] if row["question"] else "N/A")

                    item = (
                        f'<span class="{side_class}">{row["side"].upper()}</span> '
                        f'{question_short} @ ${row["price"]:.2f} | Whale: {row["whale_wallet"][:8]}...'
                    )
                    ticker_items.append(item)

                base_text = "  |  ".join(ticker_items)

        except Exception as e:
            st.error(f"error loading open positions for ticker: {e}")
            base_text = "error loading positions."

    # duplicate the text to make the ticker loop seamless
    if "..." not in base_text:
        ticker_content = "  |  ".join([base_text] * 10)  # static message, repeat a lot
    else:
        ticker_content = f"{base_text}  |  {base_text}"  # trade list, just duplicate once

    return ticker_content, latest_timestamp

@st.cache_data
def load_positions_as_html(is_resolved=0, limit=500):
    """
    fetches open (0) or closed (1) positions and returns
    a styled html table with market questions.
    """
    conn = get_db_connection()
    markets_df = load_market_names()

    if not conn:
        return "<p>No data found. Database connection error.</p>"

    # query includes question from database (now stored directly in trades table)
    query = f"""
        SELECT timestamp, whale_wallet, side, outcome, price, market_id, question, pnl
        FROM trades 
        WHERE is_resolved = {is_resolved}
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)

    if df.empty:
        if is_resolved == 0:
            return "<p>No open positions are currently being tracked.</p>"
        else:
            return "<p>No positions have been resolved yet.</p>"

    # if question is null in database, try to get it from the csv file as fallback
    if not markets_df.empty:
        df_merged = pd.merge(
            df,
            markets_df,
            left_on='market_id',
            right_on='conditionId',
            how='left',
            suffixes=('', '_csv')
        )
        # use question from database, fallback to csv question, then to market_id
        if 'question_csv' in df_merged.columns:
            df_merged['question'] = df_merged['question'].fillna(df_merged['question_csv'])
        df_merged['question'] = df_merged['question'].fillna(df_merged['market_id'])
        # drop the csv question column if it exists
        df_merged = df_merged.drop(columns=['question_csv'], errors='ignore')
        df = df_merged
    else:
        # if no csv file, use question from db or fallback to market_id
        df['question'] = df['question'].fillna(df['market_id'])

    # helper funcs to style the table cells
    def style_side(side):
        s_upper = str(side).upper()
        return f'<span class="text-{s_upper.lower()}">{s_upper}</span>'

    def style_pnl(pnl):
        if pnl is None:
            return "$0.00" # for open positions
        pnl_num = float(pnl)
        if pnl_num > 0:
            return f'<span class="text-buy">${pnl_num:+.2f}</span>'
        elif pnl_num < 0:
            return f'<span class="text-sell">${pnl_num:+.2f}</span>'
        else:
            return f'${pnl_num:.2f}'

    df['side'] = df['side'].apply(style_side)
    df['pnl'] = df['pnl'].apply(style_pnl)
    df['price'] = df['price'].map('${:,.2f}'.format)
    df['whale_wallet'] = df['whale_wallet'].str[:10] + '...'
    # truncate question if too long, but show more than before (80 chars instead of 50)
    df['question'] = df['question'].apply(lambda x: (x[:80] + '...') if x and len(str(x)) > 80 else (x if x else 'N/A'))
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%Y-%m-%d %H:%M')

    # reorder cols for display (question replaces market_id)
    if is_resolved == 0:
        final_cols = ['timestamp', 'whale_wallet', 'side', 'outcome', 'price', 'question']
    else:
        final_cols = ['timestamp', 'whale_wallet', 'side', 'outcome', 'price', 'question', 'pnl']

    df_final = df[final_cols]

    return df_final.to_html(
        classes='retro-table',
        escape=False,
        index=False,
        header=True
    )

@st.cache_data
def load_top_profitable_whales():
    """fetches the top 5 whale wallets by total realized p&l."""
    conn = get_db_connection()
    if conn:
        try:
            query = """
                    SELECT whale_wallet, SUM(pnl) as total_pnl
                    FROM trades
                    WHERE is_resolved = 1
                    GROUP BY whale_wallet
                    HAVING total_pnl > 0
                    ORDER BY total_pnl DESC
                        LIMIT 5 \
                    """
            df = pd.read_sql_query(query, conn)
            return df
        except Exception as e:
            st.error(f"Error loading top whales: {e}")
            return pd.DataFrame(columns=['whale_wallet', 'total_pnl'])

    return pd.DataFrame(columns=['whale_wallet', 'total_pnl'])

@st.cache_data
def load_pnl_history_for_whale(whale_wallet):
    """fetches p&l history for one specific whale."""
    conn = get_db_connection()
    if conn and whale_wallet:
        try:
            query = """
                    SELECT timestamp, SUM(pnl) OVER (ORDER BY timestamp) as cumulative_pnl
                    FROM trades
                    WHERE is_resolved = 1 AND whale_wallet = ?
                    ORDER BY timestamp ASC \
                    """
            df = pd.read_sql_query(query, conn, params=(whale_wallet,))
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            st.error(f"Error loading P&L for whale {whale_wallet}: {e}")
            return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])
    return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])

@st.cache_data
def load_win_loss_ratio():
    """calculates simulation-wide wins vs losses."""
    conn = get_db_connection()
    if conn:
        try:
            query = """
                    SELECT
                        SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                        SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses
                    FROM trades
                    WHERE is_resolved = 1 \
                    """
            # using .iloc[0] because sql query always returns one row
            df = pd.read_sql_query(query, conn).iloc[0]
            return df.fillna(0) # handle case where there are no wins or no losses
        except Exception as e:
            st.error(f"Error loading win/loss: {e}")
            return pd.Series({'wins': 0, 'losses': 0})
    return pd.Series({'wins': 0, 'losses': 0})

@st.cache_data(ttl=10) # cache for 10 seconds
def get_latest_logs(num_lines=50):
    """grabs the tail end of the log file."""
    if not SIMULATOR_LOG_FILE.exists():
        return f"[LOG FILE NOT FOUND at {SIMULATOR_LOG_FILE}]"
    try:
        with open(SIMULATOR_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return "".join(lines[-num_lines:])
    except Exception as e:
        return f"[ERROR READING LOG: {e}]"

# --- main app layout ---

st.title(" 〽️ PolyMimic: A PolyMarket Copy-Trading Simulator")

# create the main tabs for dashboard vs log
main_tab1, main_tab2 = st.tabs([" DASHBOARD ", " LIVE LOG FEED "])

# --- dashboard tab ---
with main_tab1:
    # retro neon color scheme (defined at top for use throughout)
    neon_purple = "#a991d4"
    neon_blue = "#4a9eff"
    neon_cyan = "#00ffff"
    dark_purple = "#7348c3"
    dark_blue = "#1e3a8a"
    win_color = "#7c3aed"  # purple for wins
    loss_color = "#a855f7"  # lighter purple for losses
    
    # initialize session state for the help toggle
    if 'show_help' not in st.session_state:
        st.session_state.show_help = False

    # describe button
    if st.button("CLICK FOR INFORMATION"):
        # toggle state
        st.session_state.show_help = not st.session_state.show_help

    #  is true show the description
    if st.session_state.show_help:
        # we wrap the markdown in a div to ensure our css targets it
        st.markdown('<div class="help-text">', unsafe_allow_html=True)
        st.markdown("<h3><strong>INFORMATION ON POLYMIMIC</strong></h3>", unsafe_allow_html=True)
        st.markdown("""
        <p>This is your personal degenerate's cockpit for a live $1-per-trade sim that shamelessly leeches off the fattest whales on Polymarket.</p>
        
        <p>This mess is held together by two scripts running in the background:</p>
        <ol>
            <li><strong>`live_trade_simulator.py`</strong>: A sleepless, crack-addled bot that eavesdrops 24/7 on Polymarket, snitching on every move your target whales make.</li>
            <li><strong>`daily_analyzer.py`</strong>: This is the 'magic bean counter'. It digs through the graveyard of dead markets, figures out your P&L (profit or, more likely, loss), and pushes it into the charts.</li>
        </ol>
        """, unsafe_allow_html=True)
        st.markdown("---")
        st.markdown("<h4>Features</h4>", unsafe_allow_html=True)
        st.markdown("""
        <ul>
            <li><strong>Live Ticker:</strong> That seizure-inducing scrollbar up top? That's all the dumb bets you've currently aped into. Stare at it and pray.</li>
            <li><strong>Run Daily Analysis:</strong> This is your P&L button. Click it once a day. It finds all trades for markets that just resolved, calculates your profit/loss, and updates all the graphs and tables.</li>
            <li><strong>Graphs:</strong> See your total fake money going up over time and which <i>types</i> of markets are most profitable.</li>
            <li><strong>Position Tables:</strong> See a full log of all your 'Live Open Positions' (waiting for a result) and your 'Recent Closed Positions' (P&L is realized).</li>
        </ul>
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # --- ticker & toast logic ---

    # initialize session state for toast
    if 'last_trade_timestamp' not in st.session_state:
        st.session_state.last_trade_timestamp = None

    ticker_text, new_latest_timestamp = load_open_positions_ticker()

    # check if there's a new trade to show a toast for
    if new_latest_timestamp and st.session_state.last_trade_timestamp:
        if new_latest_timestamp > st.session_state.last_trade_timestamp:
            st.toast(f"🐋 New Whale Trade Detected!", icon="🚨")

    # update the session state *after* the check
    st.session_state.last_trade_timestamp = new_latest_timestamp

    ticker_html = f"""
    <div class="ticker-wrap">
        <div class="ticker-move">
            <div class="ticker-item">{ticker_text}</div>
        </div>
    </div>
    """
    st.markdown(ticker_html, unsafe_allow_html=True)

    st.markdown("---")

    if st.button("CLICK TO REFRESH DATA"):
        with st.spinner("Running daily analysis... this may take a few minutes..."):
            try:
                # make sure we're using the right python executable
                result = subprocess.run(
                    [sys.executable, ANALYZER_SCRIPT_PATH],
                    capture_output=True,
                    text=True,
                    check=True,
                    encoding='utf-8'
                )
                st.success("Analysis complete! Data has been refreshed.")
                st.code(result.stdout) # show the script's print statements

            except subprocess.CalledProcessError as e:
                st.error(f"Failed to run daily analyzer:")
                st.code(e.stderr)
            except Exception as e:
                st.error(f"An unexpected error occurred: {e}")

        # clear all caches and rerun the app
        st.cache_data.clear()
        st.cache_resource.clear()
        st.rerun()

    # --- graphs ---
    st.header("Simulation P&L")

    # first-run bootstrap: if db file doesn't exist or has no resolved trades, seed with fakes
    try:
        if not DATABASE_FILE.exists():
            from live_trading import generate_fake_trades as gft
            gft.main()
        else:
            conn_chk = sqlite3.connect(DATABASE_FILE)
            cursor_chk = conn_chk.cursor()
            cursor_chk.execute("SELECT COUNT(1) FROM sqlite_master WHERE type='table' AND name='trades'")
            has_trades_table = cursor_chk.fetchone()[0] == 1
            seed_needed = True
            if has_trades_table:
                cursor_chk.execute("SELECT COUNT(1) FROM trades WHERE is_resolved = 1")
                seed_needed = (cursor_chk.fetchone()[0] == 0)
            conn_chk.close()
            if seed_needed:
                from live_trading import generate_fake_trades as gft
                gft.main()
    except Exception as e:
        st.info("first-run bootstrap skipped.")

    col1, col2, col3 = st.columns([2, 2, 1])  # pie chart takes 1/5 of space
    layout_font = dict(family="'VT323', monospace", color="#dcd0ff", size=18)

    with col1:
        st.subheader("Total P&L Over Time")
        pnl_history_df = load_pnl_history()

        if pnl_history_df.empty:
            st.info("No P&L history yet. Run the daily analyzer after some trades have resolved.")
        else:
            fig_line = px.line(
                pnl_history_df,
                x='timestamp',
                y='cumulative_pnl',
                title="Total Simulation P&L",
                template="plotly_dark"
            )
            # neon purple line with glow effect
            fig_line.update_traces(
                line=dict(color=neon_purple, width=4),
                marker=dict(size=8, color=neon_cyan, line=dict(width=2, color=neon_purple)),
                fill='tonexty',
                fillcolor=f'rgba(169, 145, 212, 0.1)'
            )
            fig_line.update_layout(
                paper_bgcolor="#0a0a0f",
                plot_bgcolor="#0a0a0f",
                font=layout_font,
                title_font=dict(size=22, color=neon_cyan, family="'VT323', monospace"),
                xaxis=dict(
                    gridcolor='rgba(169, 145, 212, 0.2)',
                    gridwidth=1,
                    showgrid=True,
                    zeroline=False,
                    linecolor=neon_purple,
                    linewidth=2,
                    tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff"),
                ),
                yaxis=dict(
                    gridcolor='rgba(169, 145, 212, 0.2)',
                    gridwidth=1,
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor=neon_purple,
                    zerolinewidth=2,
                    linecolor=neon_purple,
                    linewidth=2,
                    tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff")
                ),
                hovermode='x unified',
                hoverlabel=dict(
                    bgcolor='rgba(10, 10, 15, 0.9)',
                    bordercolor=neon_purple,
                    font=dict(color=neon_cyan, family="'VT323', monospace", size=16)
                )
            )
            st.plotly_chart(fig_line, use_container_width=True)

    with col2:
        st.subheader("P&L by Market Group")
        group_pnl_df = load_market_group_pnl()

        if group_pnl_df.empty:
            st.info("No resolved trades with market groups found.")
        else:
            fig_bar = px.bar(
                group_pnl_df,
                x='market_group',
                y='pnl',
                title="Total P&L by Market Group",
                template="plotly_dark"
            )
            # neon gradient bars with purple/blue theme
            # create color array based on pnl values
            pnl_values = group_pnl_df['pnl'].values
            min_pnl = pnl_values.min()
            max_pnl = pnl_values.max()
            
            # normalize for colorscale (0 to 1)
            if max_pnl != min_pnl:
                normalized = (pnl_values - min_pnl) / (max_pnl - min_pnl)
            else:
                normalized = [0.5] * len(pnl_values)
            
            fig_bar.update_traces(
                marker=dict(
                    color=normalized,
                    colorscale=[[0, dark_purple], [0.5, neon_purple], [1, neon_cyan]],
                    showscale=True,
                    colorbar=dict(
                        title="P&L",
                        titlefont=dict(color=neon_cyan, family="'VT323', monospace", size=16),
                        tickfont=dict(color=neon_cyan, family="'VT323', monospace", size=14),
                        bordercolor=neon_purple,
                        borderwidth=2,
                        len=0.5
                    ),
                    line=dict(width=2, color=neon_cyan)
                )
            )
            fig_bar.update_layout(
                paper_bgcolor="#0a0a0f",
                plot_bgcolor="#0a0a0f",
                font=layout_font,
                title_font=dict(size=22, color=neon_cyan, family="'VT323', monospace"),
                xaxis=dict(
                    gridcolor='rgba(169, 145, 212, 0.2)',
                    gridwidth=1,
                    showgrid=True,
                    linecolor=neon_purple,
                    linewidth=2,
                    tickfont=dict(family="'VT323', monospace", size=14, color="#dcd0ff"),
                ),
                yaxis=dict(
                    gridcolor='rgba(169, 145, 212, 0.2)',
                    gridwidth=1,
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor=neon_purple,
                    zerolinewidth=2,
                    linecolor=neon_purple,
                    linewidth=2,
                    tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff")
                ),
                hoverlabel=dict(
                    bgcolor='rgba(10, 10, 15, 0.9)',
                    bordercolor=neon_purple,
                    font=dict(color=neon_cyan, family="'VT323', monospace", size=16)
                )
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # --- win/loss chart (smaller, in column 3) ---
    with col3:
        st.subheader("Win/Loss")
        win_loss = load_win_loss_ratio()

        if win_loss['wins'] == 0 and win_loss['losses'] == 0:
            st.info("No resolved trades.")
        else:
            total_trades = int(win_loss['wins'] + win_loss['losses'])
            win_rate = (float(win_loss['wins']) / total_trades) * 100 if total_trades > 0 else 0.0

            # neon gauge: cumulative win rate
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=round(win_rate, 1),
                number={
                    "suffix": "%",
                    "font": {"family": "VT323, monospace", "size": 42, "color": neon_cyan}
                },
                title={"text": "win rate", "font": {"family": "VT323, monospace", "size": 18, "color": neon_cyan}},
                gauge={
                    "axis": {"range": [0, 100], "tickwidth": 2, "tickcolor": neon_purple},
                    "bar": {"color": win_color, "thickness": 0.3},
                    # retro neon gradient steps for the remaining arc
                    "steps": [
                        {"range": [0, 50], "color": "rgba(115, 72, 195, 0.25)"},
                        {"range": [50, 80], "color": "rgba(169, 145, 212, 0.25)"},
                        {"range": [80, 100], "color": "rgba(0, 255, 255, 0.2)"}
                    ],
                    "threshold": {
                        "line": {"color": neon_cyan, "width": 4},
                        "thickness": 0.6,
                        "value": win_rate
                    }
                },
                domain={"x": [0, 1], "y": [0.12, 1]}
            ))

            fig_gauge.update_layout(
                paper_bgcolor="#0a0a0f",
                plot_bgcolor="#0a0a0f",
                margin=dict(l=10, r=10, t=30, b=30),
                height=360,
                font=layout_font,
            )

            # add small retro annotations (total trades)
            fig_gauge.add_annotation(
                text=f"{total_trades} trades",
                x=0.5, y=0.02, xref="paper", yref="paper",
                showarrow=False,
                font=dict(family="VT323, monospace", size=14, color="#a991d4")
            )

            st.plotly_chart(fig_gauge, use_container_width=True)

    # --- roi percentage chart (new row) ---
    st.markdown("---")
    st.subheader("ROI Percentage Over Time")
    roi_df = load_roi_history()
    
    if roi_df.empty:
        st.info("No ROI data available. Run daily analyzer after some trades have resolved.")
    else:
        fig_roi = px.line(
            roi_df,
            x='timestamp',
            y='roi_percentage',
            title="Return on Investment (%)",
            template="plotly_dark"
        )
        # neon blue line for roi
        fig_roi.update_traces(
            line=dict(color=neon_blue, width=4),
            marker=dict(size=8, color=neon_cyan, line=dict(width=2, color=neon_blue)),
            fill='tonexty',
            fillcolor=f'rgba(74, 158, 255, 0.1)'
        )
        fig_roi.update_layout(
            paper_bgcolor="#0a0a0f",
            plot_bgcolor="#0a0a0f",
            font=layout_font,
            title_font=dict(size=22, color=neon_cyan, family="'VT323', monospace"),
            xaxis=dict(
                gridcolor='rgba(169, 145, 212, 0.2)',
                gridwidth=1,
                showgrid=True,
                zeroline=False,
                linecolor=neon_purple,
                linewidth=2,
                tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff")
            ),
            yaxis=dict(
                gridcolor='rgba(169, 145, 212, 0.2)',
                gridwidth=1,
                showgrid=True,
                zeroline=True,
                zerolinecolor=neon_purple,
                zerolinewidth=2,
                linecolor=neon_purple,
                linewidth=2,
                tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff"),
                ticksuffix="%"
            ),
            hovermode='x unified',
            hoverlabel=dict(
                bgcolor='rgba(10, 10, 15, 0.9)',
                bordercolor=neon_purple,
                font=dict(color=neon_cyan, family="'VT323', monospace", size=16)
            )
        )
        st.plotly_chart(fig_roi, use_container_width=True)


    # --- open/close tables (now in tabs!) ---
    st.markdown("---")
    st.header("Live Simulation Trades")

    tab1, tab2 = st.tabs(["LIVE OPEN POSITIONS", "RECENT CLOSED POSITIONS"])

    with tab1:
        st.subheader("Last 20 Open Positions")
        open_positions_html = load_positions_as_html(is_resolved=0, limit=20)
        st.markdown(open_positions_html, unsafe_allow_html=True)

    with tab2:
        st.subheader("Last 20 Closed Positions")
        closed_positions_html = load_positions_as_html(is_resolved=1, limit=20)
        st.markdown(closed_positions_html, unsafe_allow_html=True)


    # --- top whales table ---
    st.markdown("---")
    st.header("America's Next Top Whales!!!")
    whale_df = load_top_profitable_whales()

    if whale_df.empty:
        st.info("No resolved trades yet to rank whale profitability.")
    else:
        # custom styling for dashboard
        def style_whale_table(df):
            styled_df = df.copy()

            # format p&l
            styled_df['total_pnl'] = styled_df['total_pnl'].apply(
                lambda pnl: f'<span class="text-buy">${pnl:+.2f}</span>' if pnl >= 0 else f'<span class="text-sell">${pnl:+.2f}</span>'
            )

            # truncate wallet address for display
            styled_df['whale_wallet'] = styled_df['whale_wallet'].str[:10] + '...'

            # rename columns for display
            styled_df.columns = ['Whale Address', 'Total P&L']

            # set index to start from 1 (for rank)
            styled_df.index = styled_df.index + 1
            styled_df.index.name = "Rank"

            # convert to html using retro-table class
            return styled_df.to_html(
                classes='retro-table',
                escape=False,
                index=True # keep index to show rank 1, 2, 3...
            )

        st.markdown(style_whale_table(whale_df), unsafe_allow_html=True)

    # --- whale deep dive (new!) ---
    st.markdown("---")
    st.header("Whale Deep Dive")
    # use the same loaded df from the table above
    top_whales_list = whale_df['whale_wallet'].tolist()

    if not top_whales_list:
        st.info("No profitable whales to analyze yet.")
    else:
        # use the full wallet address for the selectbox value
        full_whale_addresses = load_top_profitable_whales()['whale_wallet'].tolist()

        # but display the truncated version
        # fixed a bug here: .set_index('whale_wallet')
        whale_display_map = {w: f"{w[:10]}... (P&L: ${pnl:.2f})" for w, pnl in load_top_profitable_whales().set_index('whale_wallet')['total_pnl'].items()}


        selected_whale_display = st.selectbox(
            "Select a Whale to Analyze:",
            options=full_whale_addresses,
            format_func=lambda w: whale_display_map.get(w, f"{w[:10]}...") # show truncated address
        )

        whale_pnl_df = load_pnl_history_for_whale(selected_whale_display)

        if whale_pnl_df.empty:
            st.info(f"No resolved P&L history for wallet {selected_whale_display[:10]}...")
        else:
            fig_whale = px.line(
                whale_pnl_df,
                x='timestamp',
                y='cumulative_pnl',
                title=f"P&L Over Time for {selected_whale_display[:10]}...",
                template="plotly_dark"
            )
            # neon cyan for whale profit
            fig_whale.update_traces(
                line=dict(color=neon_cyan, width=4),
                marker=dict(size=8, color=neon_cyan, line=dict(width=2, color=neon_purple)),
                fill='tonexty',
                fillcolor=f'rgba(0, 255, 255, 0.1)'
            )
            fig_whale.update_layout(
                paper_bgcolor="#0a0a0f",
                plot_bgcolor="#0a0a0f",
                font=layout_font,
                title_font=dict(size=22, color=neon_cyan, family="'VT323', monospace"),
                xaxis=dict(
                    gridcolor='rgba(169, 145, 212, 0.2)',
                    gridwidth=1,
                    showgrid=True,
                    zeroline=False,
                    linecolor=neon_purple,
                    linewidth=2,
                    tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff")
                ),
                yaxis=dict(
                    gridcolor='rgba(169, 145, 212, 0.2)',
                    gridwidth=1,
                    showgrid=True,
                    zeroline=True,
                    zerolinecolor=neon_purple,
                    zerolinewidth=2,
                    linecolor=neon_purple,
                    linewidth=2,
                    tickfont=dict(family="'VT323', monospace", size=16, color="#dcd0ff")
                ),
                hovermode='x unified',
                hoverlabel=dict(
                    bgcolor='rgba(10, 10, 15, 0.9)',
                    bordercolor=neon_purple,
                    font=dict(color=neon_cyan, family="'VT323', monospace", size=16)
                )
            )
            st.plotly_chart(fig_whale, use_container_width=True)


# --- live log feed tab ---
with main_tab2:
    st.header("Live Simulator Log")
    st.info("Showing the last 50 lines from the simulator log. Auto-refreshes every 10 seconds.")

    log_contents = get_latest_logs()

    # use st.code for a nice terminal-like block
    st.code(log_contents, language='log', line_numbers=False)

    # --- 2. replace the try/except block with this ---
    # this is the old-school way to auto-refresh
    # it works on all streamlit versions
    time.sleep(10)
    st.rerun()