import streamlit as st
import pandas as pd
import sqlite3
import os
import sys
import subprocess
import plotly.express as px
from pathlib import Path
import json
import time # <--- 1. add this line back

# --- config ---
# file paths. gotta use expanduser() to handle the '~'
WHALE_REPORT_FILE = Path("~/IdeaProjects/PolyCopy/modules/scalar_analysis/whale_report.csv").expanduser()
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
MARKETS_FILE = Path("~/IdeaProjects/PolyCopy/preprocessing/scalar_trading/markets_with_groups_v2.csv").expanduser()
ANALYZER_SCRIPT_PATH = "daily_analyzer.py" # assumes it's in the same folder
SIMULATOR_LOG_FILE = Path("~/IdeaProjects/PolyCopy/logs/simulator.log").expanduser()

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
    """fetches all p&l history for the main graph."""
    conn = get_db_connection()
    if conn:
        try:
            df = pd.read_sql_query("SELECT timestamp, cumulative_pnl FROM pnl_history ORDER BY timestamp ASC", conn)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        except Exception as e:
            # this can happen if the table doesn't exist yet
            st.info("P&L history not found. Run analyzer.")
            return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])
    return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])

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

    if markets_df.empty or not conn:
        base_text = "Market data file not found. Run historical analysis."
    else:
        try:
            query = "SELECT * FROM trades WHERE is_resolved = 0 ORDER BY timestamp DESC LIMIT 500"
            positions_df = pd.read_sql_query(query, conn)

            if positions_df.empty:
                base_text = "No open simulated positions found. Waiting for whale activity..."
            else:
                # get the timestamp of the *newest* trade for the toast
                latest_timestamp = pd.to_datetime(positions_df['timestamp']).max()

                merged_df = pd.merge(
                    positions_df,
                    markets_df,
                    left_on='market_id',
                    right_on='conditionId',
                    how='left'
                )
                merged_df['question'] = merged_df['question'].fillna(merged_df['market_id'])

                ticker_items = []
                for _, row in merged_df.iterrows():
                    side_class = "ticker-buy" if row['side'].upper() == 'BUY' else "ticker-sell"
                    question_short = (row["question"][:70] + '...') if len(row["question"]) > 70 else row["question"]

                    item = (
                        f'<span class="{side_class}">{row["side"].upper()}</span> '
                        f'{question_short} @ ${row["price"]:.2f} | Whale: {row["whale_wallet"][:8]}...'
                    )
                    ticker_items.append(item)

                base_text = "  |  ".join(ticker_items)

        except Exception as e:
            st.error(f"Error loading open positions for ticker: {e}")
            base_text = "Error loading positions."

    # duplicate the text to make the ticker loop seamless
    if "..." not in base_text:
        ticker_content = "  |  ".join([base_text] * 10) # static message, repeat a lot
    else:
        ticker_content = f"{base_text}  |  {base_text}" # trade list, just duplicate once

    return ticker_content, latest_timestamp

@st.cache_data
def load_positions_as_html(is_resolved=0, limit=500):
    """
    fetches open (0) or closed (1) positions and joins
    with market names, returning a styled html table.
    """
    conn = get_db_connection()
    markets_df = load_market_names()

    if markets_df.empty or not conn:
        return "<p>No data found. Market file may be missing.</p>"

    query = f"""
        SELECT timestamp, whale_wallet, side, outcome, price, market_id, pnl
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

    df_merged = pd.merge(
        df,
        markets_df,
        left_on='market_id',
        right_on='conditionId',
        how='left'
    )
    df_merged['question'] = df_merged['question'].fillna(df_merged['market_id'])

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

    df_merged['side'] = df_merged['side'].apply(style_side)
    df_merged['pnl'] = df_merged['pnl'].apply(style_pnl)
    df_merged['price'] = df_merged['price'].map('${:,.2f}'.format)
    df_merged['whale_wallet'] = df_merged['whale_wallet'].str[:10] + '...'
    df_merged['question'] = df_merged['question'].str[:50] + '...'
    df_merged['timestamp'] = pd.to_datetime(df_merged['timestamp']).dt.strftime('%Y-%m-%d %H:%M')

    # reorder cols for display
    if is_resolved == 0:
        final_cols = ['timestamp', 'whale_wallet', 'side', 'outcome', 'price', 'question']
    else:
        final_cols = ['timestamp', 'whale_wallet', 'side', 'outcome', 'price', 'question', 'pnl']

    df_final = df_merged[final_cols]

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
    col1, col2 = st.columns(2)
    layout_font = dict(family="VT323, monospace", color="#dcd0ff", size=16)

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
            fig_line.update_traces(line=dict(color='#a991d4', width=3))
            fig_line.update_layout(
                paper_bgcolor="#0E1117",
                plot_bgcolor="#1f2333",
                font=layout_font
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
                template="plotly_dark",
                color_discrete_sequence=['#a991d4']
            )
            fig_bar.update_layout(
                paper_bgcolor="#0E1117",
                plot_bgcolor="#1f2333",
                font=layout_font
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # --- win/loss chart (new!) ---
    # putting this in a new row to give it space
    st.subheader("Simulation Win/Loss Ratio")
    win_loss = load_win_loss_ratio()

    if win_loss['wins'] == 0 and win_loss['losses'] == 0:
        st.info("No resolved trades to calculate ratio.")
    else:
        pie_df = pd.DataFrame({
            'outcome': ['Wins', 'Losses'],
            'count': [win_loss['wins'], win_loss['losses']]
        })
        fig_pie = px.pie(
            pie_df,
            values='count',
            names='outcome',
            title="Resolved Trades",
            template="plotly_dark",
            color_discrete_map={'Wins':'#3dd56d', 'Losses':'#f94c4c'},
            hole=0.4 # donut chart!
        )
        fig_pie.update_layout(
            paper_bgcolor="#0E1117",
            plot_bgcolor="#1f2333",
            font=layout_font,
            legend=dict(font=dict(size=14))
        )
        fig_pie.update_traces(textfont_size=16)
        st.plotly_chart(fig_pie, use_container_width=True)


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
            # green for profit!
            fig_whale.update_traces(line=dict(color='#3dd56d', width=3))
            fig_whale.update_layout(
                paper_bgcolor="#0E1117",
                plot_bgcolor="#1f2333",
                font=layout_font
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