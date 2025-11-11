import requests
import pandas as pd
import sys

MARKETS_URL = "https://gamma-api.polymarket.com/markets"
session = requests.Session()

print("Starting to fetch resolved markets (FINAL DIAGNOSTIC RUN)...")

params = {
    'closed': 'true',
    'limit': 100  # just get a small sample
}

try:
    response = session.get(MARKETS_URL, params=params)
    response.raise_for_status()
    all_markets_data = response.json()
except requests.exceptions.RequestException as e:
    print(f"Error fetching sample data: {e}")
    sys.exit(1)

if not all_markets_data:
    print("No market data was fetched. Exiting.")
    sys.exit(1)

df = pd.DataFrame(all_markets_data)

print(f"Fetched {len(df)} sample markets.")

# filter for 'normal' markets
normal_markets_df = df[df['marketType'] == 'normal'].copy()

if normal_markets_df.empty:
    print("Could not find any 'normal' markets in the sample. Exiting.")
    sys.exit(0)

print(f"Found {len(normal_markets_df)} 'normal' markets in sample.")

# --- NEW DIAGNOSTIC SECTION ---
print("\n--- DATA PEEK (first 5 'normal' markets) ---")

# set pandas to show full column contents
pd.set_option('display.max_colwidth', None)

print(normal_markets_df[['question', 'outcomes', 'outcomePrices']].head(5).to_string())

print("\n--- End of Diagnostics ---")
