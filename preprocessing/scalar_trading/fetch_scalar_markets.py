import requests
import pandas as pd
import time
import sys
import json

MARKETS_URL = "https://gamma-api.polymarket.com/markets"
session = requests.Session()

def parse_market_data(market_row):
    """
    Parses the outcome and price data from the API.
    This new version handles data that is *already* a list
    or data that is a JSON string.
    """
    try:
        prices_data = market_row.get('outcomePrices')
        outcomes_data = market_row.get('outcomes')

        if not prices_data or not outcomes_data:
            return None, None

        if isinstance(prices_data, list):
            prices_list = prices_data
        elif isinstance(prices_data, str):
            try:
                prices_list = json.loads(prices_data)
            except json.JSONDecodeError:
                return None, None # bad json string
        else:
            return None, None # unknown data type

        if isinstance(outcomes_data, list):
            outcomes_list = outcomes_data
        elif isinstance(outcomes_data, str):
            try:
                outcomes_list = json.loads(outcomes_data)
            except json.JSONDecodeError:
                return None, None # bad json string
        else:
            return None, None # unknown data type

        if not isinstance(prices_list, list) or not prices_list:
            return None, None
        if not isinstance(outcomes_list, list) or not outcomes_list:
            return None, None
        if len(prices_list) != len(outcomes_list):
            return None, None

        prices_as_float = []
        for p in prices_list:
            try:
                if p is None:
                    prices_as_float.append(0.0)
                else:
                    prices_as_float.append(float(p))
            except (ValueError, TypeError):
                return None, None

        if sum(prices_as_float) < 0.01:
            return None, None

        return json.dumps(outcomes_list), json.dumps(prices_as_float)

    except Exception:
        return None, None

print("Starting to fetch ALL resolved markets (normal + scalar)...")

all_resolved_markets = []
limit = 100
offset = 0

while True:
    params = {
        'closed': True,
        'limit': limit,
        'offset': offset,
        'order': 'endDate',
        'ascending': False
    }

    try:
        response = session.get(MARKETS_URL, params=params)
        response.raise_for_status()
        markets_data = response.json()

        if not isinstance(markets_data, list) or not markets_data:
            print("Reached the end of the market list.")
            break

        print(f"Fetched {len(markets_data)} markets in this batch (total: {offset + len(markets_data)})...")

        for market in markets_data:

            outcomes_list, final_prices_list = parse_market_data(market)

            if outcomes_list and final_prices_list:
                all_resolved_markets.append({
                    'conditionId': market.get('conditionId'),
                    'question': market.get('question'),
                    'category': market.get('category'),
                    'outcomes': outcomes_list,
                    'final_prices': final_prices_list
                })

        offset += limit

        time.sleep(0.1)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data at offset {offset}: {e}")
        break

print(f"\nSuccessfully processed {offset} markets. Found {len(all_resolved_markets)} total resolved markets.")

if not all_resolved_markets:
    print("No resolved markets were found. Exiting.")
    sys.exit(1)

final_df = pd.DataFrame(all_resolved_markets)
final_df.drop_duplicates(subset=['conditionId'], inplace=True)

output_file = "../markets_v2.csv"
final_df.to_csv(output_file, index=False)

print(f"\nDone! Saved {len(final_df)} unique resolved markets to '{output_file}'.")