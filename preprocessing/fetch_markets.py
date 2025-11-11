import requests
import pandas as pd
import time
import sys
import json

MARKETS_URL = "https://gamma-api.polymarket.com/markets"
session = requests.Session()


def get_resolution(row):
    """
    Parses JSON strings from the API, then safely
    finds the winner.
    """

    # 1. get the data as strings
    prices_str = row.get('outcomePrices')
    outcomes_str = row.get('outcomes')

    # 2. check for None or empty strings
    if not prices_str or not outcomes_str:
        return None

    try:
        # 3. parse the JSON strings into python lists
        prices_list = json.loads(prices_str)
        outcomes_list = json.loads(outcomes_str)
    except json.JSONDecodeError:
        return None # bad json data

    # 4. run all the same safety checks as before
    if not isinstance(prices_list, list) or not prices_list:
        return None
    if not isinstance(outcomes_list, list) or not outcomes_list:
        return None
    if len(prices_list) != len(outcomes_list):
        return None

    prices_as_float = []

    # 5. loop and safely convert each price
    for p_str in prices_list:
        try:
            if p_str is None:
                prices_as_float.append(0.0)
            else:
                prices_as_float.append(float(p_str))
        except (ValueError, TypeError):
            return None # corrupted price data

    # 6. now we can safely do the math
    try:
        max_price = max(prices_as_float)
        if max_price > 0.99:
            winner_index = prices_as_float.index(max_price)
            if winner_index < len(outcomes_list):
                return outcomes_list[winner_index]
        return None # not resolved

    except Exception:
        return None

print("Starting to fetch resolved markets. This will take time...")

all_markets_data = []
limit = 100
offset = 0

while True:
    params = {
        'closed': 'true',
        'limit': limit,
        'offset': offset,
        'order_by': 'endDate',
        'ascending': 'false'
    }

    try:
        response = session.get(MARKETS_URL, params=params)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list):
            print(f"Error: API response was not a list. Got: {data}")
            break

        if not data:
            print("Reached the end of the market list.")
            break

        all_markets_data.extend(data)
        print(f"Fetched {len(all_markets_data)} closed markets so far...")

        offset += limit
        time.sleep(0.1)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data at offset {offset}: {e}")
        break

print(f"\nSuccessfully fetched {len(all_markets_data)} total closed markets.")

if not all_markets_data:
    print("No market data was fetched. Exiting.")
    sys.exit(1)

df = pd.DataFrame(all_markets_data)
print("Filtering for resolved 'normal' (YES/NO) markets...")

required_cols = ['marketType', 'outcomePrices', 'outcomes']
if not all(col in df.columns for col in required_cols):
    print(f"Error: DataFrame is missing required columns. Found: {df.columns.tolist()}")
    sys.exit("Cannot filter for resolved markets.")

df['marketType'] = df['marketType'].astype(str).str.strip()
filtered_df = df[df['marketType'] == 'normal'].copy()

if filtered_df.empty:
    print("Found 0 closed, 'normal' markets after cleaning. Exiting.")
    sys.exit(0)

print(f"Found {len(filtered_df)} closed, 'normal' markets. Determining resolutions...")

filtered_df['resolution'] = filtered_df.apply(get_resolution, axis=1)
resolved_df = filtered_df.dropna(subset=['resolution'])

print(f"Found {len(resolved_df)} fully resolved markets.")

# use 'conditionId' from the gamma-api docs
final_columns = [
    'conditionId', # <-- use the correct field name
    'question',
    'category',
    'resolution'
]

existing_columns = [col for col in final_columns if col in resolved_df.columns]
final_df = resolved_df[existing_columns]

output_file = "resolved_markets.csv"
final_df.to_csv(output_file, index=False)

print(f"\nDone! Saved {len(final_df)} resolved markets to '{output_file}'.")

if not final_df.empty:
    print("\n--- Example Data ---")
    print(final_df.head())