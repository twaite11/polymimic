import requests
import pandas as pd
import sys

MARKETS_URL = "https://gamma-api.polymarket.com/markets"
session = requests.Session()

print("Starting diagnostic check (v2)...")
print("Fetching 100 newest closed markets to inspect their columns...")

params = {
    'closed': True,
    'limit': 100,
    'offset': 0,
    'order': 'endDate',
    'ascending': False
}

try:
    response = session.get(MARKETS_URL, params=params)
    response.raise_for_status()
    markets_data = response.json()

    if not isinstance(markets_data, list) or not markets_data:
        print("Error: Did not get a list of markets from the API.")
        sys.exit(1)

    df = pd.DataFrame(markets_data)

    print(f"Successfully fetched {len(df)} newest markets.")

    # --- NEW DIAGNOSTIC SECTION ---

    print("\n--- All Available Columns: ---")
    print(df.columns.tolist())

    # We'll select a few key columns that are likely to exist
    # to see what the new data looks like.
    print("\n--- First 5 Rows (Sample Data): ---")

    # We look for the most likely columns based on your docs
    sample_cols = [
        'id',
        'question',
        'category',
        'closed',
        'outcomes',
        'outcomePrices'
    ]

    # Get just the columns that actually exist in the dataframe
    existing_sample_cols = [col for col in sample_cols if col in df.columns]

    if existing_sample_cols:
        pd.set_option('display.max_colwidth', 100) # prevent crazy text wrapping
        print(df[existing_sample_cols].head(5).to_string())
    else:
        print("Could not find any of the expected sample columns.")

    print("\n--- End of Diagnostic ---")


except requests.exceptions.RequestException as e:
    print(f"Error fetching data: {e}")
    sys.exit(1)