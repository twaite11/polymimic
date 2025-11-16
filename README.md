# polymimic: a polymarket copy-trading simulator

**polymimic** is a sophisticated copy-trading simulation system for polymarket that identifies profitable traders ("whales") and simulates copying their trades in real-time.

## core concept

the system works in three main phases:

1. **find profitable traders**: analyze historical market data to identify traders who consistently profit in specific market categories
2. **monitor live trades**: connect to polymarket's websocket feed to detect when these "whales" make trades
3. **simulate copy trading**: automatically simulate copying their trades with $1 per trade and track p&l as markets resolve

## project structure

### 1. preprocessing pipeline (`preprocessing/`)

data collection and preparation scripts:

#### binary trading (`binary_trading/`)
- **`fetch_markets.py`**: fetches resolved binary markets from polymarket api
- **`fetch_trades.py`**: fetches all historical trades for resolved markets
- **`fetch_wallets.py`**: extracts unique wallet addresses from market holders

#### scalar trading (`scalar_trading/`)
- **`fetch_scalar_markets.py`**: fetches resolved scalar markets (with outcomes/prices)
- **`fetch_scalar_trades.py`**: concurrent fetching of trades for scalar markets (multi-threaded for performance)
- **`discover_groups.py`**: uses nlp to discover recurring keywords/phrases in market questions
- **`create_market_groups.py`**: groups markets by keywords (politics, sports, crypto, etc.)

### 2. analysis modules (`modules/`)

identifies profitable traders from historical data:

#### binary analysis (`binary_analysis/`)
- **`analyze_wallets.py`**: analyzes binary market trades, calculates p&l per wallet/category

#### scalar analysis (`scalar_analysis/`)
- **`analyze_wallets_scalar.py`**: analyzes scalar markets, handles multiple outcomes and settlement prices
- **`find_whales.py`**: filters traders by:
  - minimum total p&l ($1,000+)
  - minimum trade count (10+)
  - minimum p&l per trade ($5+)
  - specialization score (75%+ of profit from one market group)
  - live activity check (open positions or trades in last 7 days)

### 3. live trading system (`live_trading/`)

real-time simulation components:

#### **`live_trade_simulator.py`**
- websocket connection to polymarket's live data feed
- monitors top 400 whale wallets from analysis
- detects trades (both taker and maker side)
- logs simulated $1 trades to sqlite database
- runs 24/7 with auto-reconnect functionality

#### **`daily_analyzer.py`**
- checks for newly resolved markets via api
- calculates p&l for resolved trades
- updates database with results
- generates p&l graphs (matplotlib)
- posts daily reports to discord (with graphs and top whales)

#### **`dashboard.py`**
- streamlit dashboard with retro/80s theme
- **live ticker** showing open positions scrolling across screen
- **p&l charts**: total over time, by market group, win/loss ratio
- **position tables**: open and closed positions
- **top profitable whales** leaderboard
- **individual whale deep-dive** analysis
- **live log feed** from simulator

## data flow

### historical analysis pipeline
```
fetch resolved markets → fetch all trades → analyze wallet performance 
→ identify specialists → filter for active whales → generate whale report
```

### live simulation pipeline
```
load whale list → connect to websocket → detect trades → log to database 
→ wait for resolution → calculate p&l → update reports
```

### daily resolution process
```
check for resolved markets → calculate p&l → update database 
→ generate reports → post to discord
```

## key features

- **dual market support**: handles both binary (yes/no) and scalar (multiple outcomes) markets
- **market grouping**: automatically categorizes markets by topic (politics, sports, crypto, etc.)
- **specialization scoring**: finds traders who focus on specific market types
- **live activity verification**: ensures tracked whales are still actively trading
- **real-time monitoring**: websocket connection for instant trade detection
- **sqlite database**: persistent storage for all simulated trades
- **interactive dashboard**: beautiful streamlit interface with real-time updates
- **discord integration**: automated daily reports with graphs
- **concurrent processing**: multi-threaded data fetching for performance

## technology stack

- **python** (pandas, requests, websocket, sqlite3)
- **streamlit** (interactive dashboard)
- **plotly** (interactive charts)
- **matplotlib** (p&l graphs)
- **discord webhooks** (notifications)
- **polymarket api** (markets, trades, positions)
- **polymarket websocket** (live trade feed)

## how it works

1. **historical analysis phase**:
   - fetch all resolved markets and their final outcomes/prices
   - download all historical trades for these markets
   - calculate p&l for each wallet by market category
   - identify "specialist whales" who profit consistently in specific areas
   - verify they're still active (have open positions or recent trades)

2. **live monitoring phase**:
   - load the top 400 profitable whale wallets
   - connect to polymarket's websocket feed
   - when a whale makes a trade, simulate copying it with $1
   - store the trade in database (marked as unresolved)

3. **daily resolution phase**:
   - check which markets have resolved since last run
   - calculate actual p&l for each simulated trade
   - update cumulative p&l tracking
   - generate visualizations and reports
   - post summary to discord

## getting started

### prerequisites

install dependencies:
```bash
pip install -r requirements.txt
```

### configuration

create a `.env` file with:
```
POLYMARKET_API_KEY=your_api_key
POLYMARKET_SECRET_KEY=your_secret_key
POLYMARKET_PASSPHRASE=your_passphrase
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

### running the system

1. **historical analysis** (one-time setup):
   ```bash
   # fetch markets and trades
   cd preprocessing/scalar_trading
   python fetch_scalar_markets.py
   python fetch_scalar_trades.py
   
   # analyze and find whales
   cd ../../modules/scalar_analysis
   python analyze_wallets_scalar.py
   python find_whales.py
   ```

2. **start live simulator**:
   ```bash
   cd live_trading
   python live_trade_simulator.py
   ```

3. **run daily analyzer** (schedule daily):
   ```bash
   cd live_trading
   python daily_analyzer.py
   ```

4. **launch dashboard**:
   ```bash
   cd live_trading
   streamlit run dashboard.py
   ```

## dashboard features

- **live ticker**: real-time scrolling display of open positions
- **p&l visualization**: track cumulative profit/loss over time
- **market group analysis**: see which categories are most profitable
- **win/loss metrics**: track success rate of copied trades
- **whale leaderboard**: top performers by total p&l
- **individual analysis**: deep dive into specific whale performance
- **live logs**: real-time feed from the simulator

## dashboard theme

the dashboard features a retro 80s aesthetic with:
- crt scanline effects
- purple gradient text
- dark theme with neon accents
- vt323 monospace font
- smooth animations

## notes

- the system simulates $1 per trade (configurable in `live_trade_simulator.py`)
- tracks top 400 whales by default (configurable)
- database stores all trades in `db/simulation.db`
- daily analyzer should be run once per day (can be scheduled via cron)

## market groups

markets are automatically categorized into groups such as:
- us politics & government
- sports (nfl, nba, mlb, nhl, soccer, golf, tennis, ufc, esports, f1)
- tech, ai & crypto
- finance & economics
- geopolitics
- entertainment & media

## database schema

### `trades` table
- `id`: primary key
- `timestamp`: when trade was detected
- `whale_wallet`: address of the whale
- `market_id`: polymarket condition id
- `outcome`: which outcome was traded
- `side`: buy or sell
- `price`: entry price
- `simulated_bet`: amount simulated ($1)
- `is_resolved`: 0 = open, 1 = resolved
- `pnl`: profit/loss (calculated on resolution)

### `pnl_history` table
- `id`: primary key
- `timestamp`: date
- `cumulative_pnl`: running total p&l

---

**polymimic** - because sometimes the best trading strategy is to follow the smart money.

