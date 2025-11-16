import sqlite3
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

# --- config ---
DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
NUM_TRADES = 35  # generate 35 fake trades
SIMULATED_BET_AMOUNT = 1.0  # $1 per trade

# fake whale wallets (realistic ethereum addresses)
FAKE_WHALES = [
    "0x1234567890abcdef1234567890abcdef12345678",
    "0xabcdef1234567890abcdef1234567890abcdef12",
    "0x9876543210fedcba9876543210fedcba98765432",
    "0xfedcba0987654321fedcba0987654321fedcba09",
    "0x5555555555555555555555555555555555555555",
    "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "0x1111111111111111111111111111111111111111",
    "0x9999999999999999999999999999999999999999"
]

# realistic market questions
MARKET_QUESTIONS = [
    "Will Bitcoin reach $100,000 by end of 2025?",
    "Will Trump win the 2024 election?",
    "Will the Chiefs win Super Bowl LIX?",
    "Will Ethereum price be above $5,000 on Dec 31, 2025?",
    "Will the Lakers make the NBA playoffs in 2025?",
    "Will there be a recession in the US in 2025?",
    "Will Taylor Swift release a new album in 2025?",
    "Will the S&P 500 close above 6,000 in 2025?",
    "Will the US have a new president in 2025?",
    "Will Apple stock be above $250 on Dec 31, 2025?",
    "Will the Warriors win the NBA championship in 2025?",
    "Will there be a major crypto exchange hack in 2025?",
    "Will the Fed cut rates by at least 0.5% in 2025?",
    "Will Tesla stock be above $300 on Dec 31, 2025?",
    "Will the Yankees win the World Series in 2025?",
    "Will there be a major AI breakthrough announced in 2025?",
    "Will the Dow Jones close above 40,000 in 2025?",
    "Will there be a major earthquake in California in 2025?",
    "Will Google stock be above $200 on Dec 31, 2025?",
    "Will the Celtics win the NBA championship in 2025?"
]

# outcomes for binary markets
OUTCOMES = ["Yes", "No"]

def generate_fake_market_id():
    """generates a fake market id (condition id format)."""
    return "0x" + "".join([random.choice("0123456789abcdef") for _ in range(64)])

def calculate_pnl_for_trade(entry_price, side, outcome, settlement_price):
    """
    calculates pnl for a trade.
    for buy: pnl = (settlement_price - entry_price) * shares
    for sell: pnl = (entry_price - settlement_price) * shares
    """
    bet_amount = SIMULATED_BET_AMOUNT
    
    if side.upper() == "BUY":
        if entry_price == 0:
            return 0
        shares = bet_amount / entry_price
        value_at_settlement = shares * settlement_price
        pnl = value_at_settlement - bet_amount
    else:  # SELL
        if (1 - entry_price) == 0:
            return 0
        shares = bet_amount / (1 - entry_price)
        payout_at_settlement = shares * (1 - settlement_price)
        pnl = payout_at_settlement - bet_amount
    
    return round(pnl, 2)

def generate_fake_trade(days_ago: int):
    """generates a single fake trade with realistic data.
    
    days_ago: 1 or 2 to place trade timestamp at 1 or 2 days ago.
    """
    # pick random whale
    whale_wallet = random.choice(FAKE_WHALES)
    
    # pick random market question
    question = random.choice(MARKET_QUESTIONS)
    market_id = generate_fake_market_id()
    
    # pick random outcome
    outcome = random.choice(OUTCOMES)
    
    # pick random side (60% buy, 40% sell for variety)
    side = random.choices(["BUY", "SELL"], weights=[60, 40])[0]
    
    # generate realistic entry price (0.15 to 0.85 range)
    entry_price = round(random.uniform(0.15, 0.85), 2)
    
    # determine if this trade wins or loses (65% win rate for profitable whales)
    is_winner = random.random() < 0.65
    
    # calculate settlement price based on outcome and win/loss
    # binary markets resolve to exactly 0.0 or 1.0
    # a losing trade should realize a full -$1 PnL on a $1 stake
    if outcome.upper() == "YES":
        settlement_price = 1.0 if is_winner else 0.0
    else:  # NO
        settlement_price = 0.0 if is_winner else 1.0
    
    # calculate pnl
    pnl = calculate_pnl_for_trade(entry_price, side, outcome, settlement_price)
    
    # generate timestamp specifically 1 or 2 days ago at a random time within that day
    days_ago = 1 if days_ago <= 1 else 2
    base_dt = datetime.now() - timedelta(days=days_ago)
    # randomize within the target day
    rand_seconds = random.randint(0, 24 * 60 * 60 - 1)
    day_start = base_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    timestamp = day_start + timedelta(seconds=rand_seconds)
    
    return {
        'whale_wallet': whale_wallet,
        'market_id': market_id,
        'question': question,
        'outcome': outcome,
        'side': side,
        'price': entry_price,
        'simulated_bet': SIMULATED_BET_AMOUNT,
        'is_resolved': 1,
        'pnl': pnl,
        'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S')
    }

def main():
    """main function to generate and insert fake trades."""
    print(f"generating {NUM_TRADES} fake closed trades...")
    
    # connect to database
    try:
        os.makedirs(os.path.dirname(DATABASE_FILE), exist_ok=True)
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        
        # ensure table exists
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
        
        # generate and insert fake trades
        trades = []
        total_pnl = 0
        
        for i in range(NUM_TRADES):
            # first half 1 day ago, second half 2 days ago
            target_days_ago = 1 if i < (NUM_TRADES // 2) else 2
            trade = generate_fake_trade(target_days_ago)
            trades.append(trade)
            total_pnl += trade['pnl']
            
            cursor.execute('''
                           INSERT INTO trades (whale_wallet, market_id, question, outcome, side, price, simulated_bet, is_resolved, pnl, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                           ''', (
                trade['whale_wallet'],
                trade['market_id'],
                trade['question'],
                trade['outcome'],
                trade['side'],
                trade['price'],
                trade['simulated_bet'],
                trade['is_resolved'],
                trade['pnl'],
                trade['timestamp']
            ))
        
        conn.commit()
        
        # update pnl_history with today's date
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
                       INSERT INTO pnl_history (timestamp, cumulative_pnl)
                       VALUES (?, ?)
                           ON CONFLICT(timestamp) DO UPDATE SET cumulative_pnl = excluded.cumulative_pnl
                       ''', (today_str, total_pnl))
        
        conn.commit()
        conn.close()
        
        print(f"\n--- success! ---")
        print(f"inserted {NUM_TRADES} fake closed trades into database.")
        print(f"total p&l: ${total_pnl:.2f}")
        print(f"average p&l per trade: ${total_pnl/NUM_TRADES:.2f}")
        print(f"\nwhale breakdown:")
        whale_totals = {}
        for trade in trades:
            whale = trade['whale_wallet']
            if whale not in whale_totals:
                whale_totals[whale] = 0
            whale_totals[whale] += trade['pnl']
        
        for whale, pnl in sorted(whale_totals.items(), key=lambda x: x[1], reverse=True):
            print(f"  {whale[:10]}...: ${pnl:.2f}")
        
        print(f"\nnote: you can delete the database file at {DATABASE_FILE} to remove these fake trades.")
        
    except sqlite3.Error as e:
        print(f"error: database error - {e}")
    except Exception as e:
        print(f"error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

