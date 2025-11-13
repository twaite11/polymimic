import streamlit as st
import pandas as pd
import sqlite3
import os
import sys
import subprocess
import plotly.express as px
from pathlib import Path
import json

# --- config ---
WHALE_REPORT_FILE = Path("~/IdeaProjects/PolyCopy/modules/scalar_analysis/whale_report.csv").expanduser()
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
MARKETS_FILE = Path("~/IdeaProjects/PolyCopy/preprocessing/scalar_trading/markets_with_groups_v2.csv").expanduser()
ANALYZER_SCRIPT_PATH ="daily_analyzer.py"

# --- styling ---
st.set_page_config(layout="wide", page_title="Whale Watcher Dashboard")

# CSS 80's theme retro retro retro
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');

    /* --- (GLOBAL FONT & THEME) --- */
    /* Apply font to all text elements */
    body, .stApp, div, p, span, h1, h2, h3, h4, h5, h6, th, td, button, summary {
        font-family: 'VT323', monospace !important;
        color: #dcd0ff !important; /* Set default text color */
    }
    
    body, .stApp {
        background-color: #0E1117 !important;
    }

    /* Titles - Purple Gradient */
    h1, h2, h3 {
        background: -webkit-linear-gradient(45deg, #a991d4, #7348c3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700 !important;
    }

    /* --- (STYLED BUTTON) --- */
    /* This styles *all* buttons, including "What is this?" */
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
    [data-testid="stButton"] button p { /* Text inside button */
        font-family: 'VT323', monospace !important;
        color: #dcd0ff !important;
    }
    [data-testid="stButton"] button:hover p {
        color: #0E1117 !important;
    }


    /* --- (STYLED MARKDOWN for help text) --- */
    /* This targets the text INSIDE the help section */
    .help-text p, .help-text li {
        font-size: 1.1em !important;
        color: #dcd0ff !important;
        font-family: 'VT323', monospace !important;
    }
    /* This targets the headers INSIDE the help section */
    .help-text h3, .help-text h4 {
        font-size: 1.3em !important;
        background: -webkit-linear-gradient(45deg, #a991d4, #7348c3);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'VT323', monospace !important;
    }


    /* --- (STYLED TABLE) --- */
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

    /* --- (TICKER) --- */
    /* *** CHANGED KEYFRAMES *** */
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
        animation: ticker 15000s linear infinite;
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
# --- END OF CSS ---

# --- Database & Data Loading Functions cached ---

@st.cache_resource
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        st.error(f"Error connecting to database: {e}")
        return None

@st.cache_data
def load_market_names():
    """Loads just the market IDs and questions from the v2 file."""
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
    """Fetches all P&L history for the main graph."""
    conn = get_db_connection()
    if conn:
        df = pd.read_sql_query("SELECT timestamp, cumulative_pnl FROM pnl_history ORDER BY timestamp ASC", conn)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        return df
    return pd.DataFrame(columns=['timestamp', 'cumulative_pnl'])

@st.cache_data
def load_market_group_pnl():
    """Calculates P&L grouped by market_group."""
    conn = get_db_connection()

    if not os.path.exists(MARKETS_FILE):
        st.error(f"Market file not found: {MARKETS_FILE}")
        return pd.DataFrame(columns=['market_group', 'total_pnl'])
    if not conn:
        return pd.DataFrame(columns=['market_group', 'total_pnl'])

    try:
        trades_df = pd.read_sql_query("SELECT market_id, pnl FROM trades WHERE is_resolved = 1", conn)

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
    """Fetches ALL live, unresolved trades for the ticker."""
    conn = get_db_connection()
    markets_df = load_market_names()

    base_text = "" # Initialize base_text

    if markets_df.empty or not conn:
        base_text = "Market data file not found. Run historical analysis."
    else:
        try:
            query = "SELECT * FROM trades WHERE is_resolved = 0 ORDER BY timestamp DESC"
            positions_df = pd.read_sql_query(query, conn)


            if positions_df.empty:
                base_text = "No open simulated positions found. Waiting for whale activity..."
            else:
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

    if "..." not in base_text:
        return "  |  ".join([base_text] * 10)

    # If it is a list of trades, just duplicate it once for a seamless loop
    return f"{base_text}  |  {base_text}"

@st.cache_data
def load_positions_as_html(is_resolved=0, limit=500):
    """
    Fetches open (0) or closed (1) positions and joins
    with market names, returning a styled HTML table.
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

    def style_side(side):
        s_upper = str(side).upper()
        return f'<span class="text-{s_upper.lower()}">{s_upper}</span>'

    def style_pnl(pnl):
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

    final_cols = ['timestamp', 'whale_wallet', 'side', 'outcome', 'price', 'question', 'pnl']
    df_final = df_merged[final_cols]

    return df_final.to_html(
        classes='retro-table',
        escape=False,
        index=False
    )
@st.cache_data
def load_top_profitable_whales():
    """Fetches the top 5 whale wallets by total realized P&L."""
    conn = get_db_connection()
    if conn:
        try:
            query = """
                    SELECT whale_wallet, SUM(pnl) as total_pnl
                    FROM trades
                    WHERE is_resolved = 1
                    GROUP BY whale_wallet
                    ORDER BY total_pnl DESC
                        LIMIT 5 \
                    """
            df = pd.read_sql_query(query, conn)
            return df
        finally:
            # Note: This conn.close() assumes you removed the @st.cache_resource
            # decorator from get_db_connection as discussed previously.
            conn.close()
    return pd.DataFrame(columns=['whale_wallet', 'total_pnl'])

# --- Main App Layout ---

st.title("PolyMimic: A PolyMarket Copy-Trading Simulator")

# Initialize session state for the toggle
if 'show_help' not in st.session_state:
    st.session_state.show_help = False

# describe button
if st.button("What is this?"):
    # toggle state
    st.session_state.show_help = not st.session_state.show_help

#  is true show the description
if st.session_state.show_help:
    # We wrap the markdown in a div to ensure our CSS targets it
    st.markdown('<div class="help-text">', unsafe_allow_html=True)
    st.markdown("<h3>🚀 What is this App?</h3>", unsafe_allow_html=True)
    st.markdown("""
    <p>This is your personal mission control for a live, $1-per-trade simulation that copies the top whales on Polymarket.</p>
    
    <p>It is powered by two scripts running in the background:</p>
    <ol>
        <li><strong>`live_trade_simulator.py`</strong>: A 24/7 bot that listens to every Polymarket trade and logs any trade made by your target whales.</li>
        <li><strong>`daily_analyzer.py`</strong>: A script that runs when you click the 'Refresh' button. It finds all resolved markets, calculates your P&L, and updates all the graphs.</li>
    </ol>
    """, unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<h4>Features</h4>", unsafe_allow_html=True)
    st.markdown("""
    <ul>
        <li><strong>Live Ticker:</strong> The scrolling ticker at the top shows all <i>currently open</i> simulated positions from your whale list.</li>
        <li><strong>Run Daily Analysis:</strong> This is your P&L button. Click it once a day. It finds all trades for markets that just resolved, calculates your profit/loss, and updates all the graphs and tables.</li>
        <li><strong>Graphs:</strong> See your total simulation P&L over time and which <i>types</i> of markets (e.g., `nfl_game`) are most profitable.</li>
        <li><strong>Position Tables:</strong> See a full log of all your 'Live Open Positions' (waiting for a result) and your 'Recent Closed Positions' (P&L is realized).</li>
    </ul>
    """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

ticker_text = load_open_positions_ticker()
ticker_html = f"""
<div class="ticker-wrap">
    <div class="ticker-move">
        <div class="ticker-item">{ticker_text}</div>
    </div>
</div>
"""
st.markdown(ticker_html, unsafe_allow_html=True)

st.markdown("---")

if st.button("Analyze & Refresh Data"):
    with st.spinner("Running daily analysis... this may take a few minutes..."):
        try:
            result = subprocess.run(
                [sys.executable, ANALYZER_SCRIPT_PATH],
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8'
            )
            st.success("Analysis complete! Data has been refreshed.")


        except subprocess.CalledProcessError as e:
            st.error(f"Failed to run daily analyzer:")
            st.code(e.stderr)
        except Exception as e:
            st.error(f"An unexpected error occurred: {e}")


    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()
# graphs
st.header("Simulation P&L")
col1, col2 = st.columns(2)
layout_font = dict(family="VT323, monospace", color="#dcd0ff")

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

# open close tables
st.markdown("---")
st.header("Live Simulation Trades")
col3, col4 = st.columns(2)

# *** ALL TABLE LIMITS CHANGED TO 20 ***
with col3:
    st.subheader("Live Open Positions (Last 20)")
    open_positions_html = load_positions_as_html(is_resolved=0, limit=20)
    st.markdown(open_positions_html, unsafe_allow_html=True)

with col4:
    st.subheader("Recent Closed Positions (Last 20)")
    closed_positions_html = load_positions_as_html(is_resolved=1, limit=20)
    st.markdown(closed_positions_html, unsafe_allow_html=True)

st.markdown("---")
st.header("Americas Next Top Whales!!!")
whale_df = load_top_profitable_whales()

if whale_df.empty:
    st.info("No resolved trades yet to rank whale profitability.")
else:
    # --- Custom Styling for Dashboard ---

    # Apply your CSS classes for consistent styling
    def style_whale_table(df):
        styled_df = df.copy()

        # Format P&L
        styled_df['total_pnl'] = styled_df['total_pnl'].apply(
            lambda pnl: f'<span class="text-buy">${pnl:+.2f}</span>' if pnl >= 0 else f'<span class="text-sell">${pnl:+.2f}</span>'
        )

        # Truncate wallet address for display
        styled_df['whale_wallet'] = styled_df['whale_wallet'].str[:10] + '...'

        # Rename columns for display
        styled_df.columns = ['Whale Address', 'Total P&L']

        # Convert to HTML using retro-table class
        return styled_df.to_html(
            classes='retro-table',
            escape=False,
            index=True # Keep index to show rank 1, 2, 3...
        )

    st.markdown(style_whale_table(whale_df), unsafe_allow_html=True)