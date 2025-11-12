import pandas as pd
import os
import sys

# --- config ---
MARKETS_FILE = "markets_v2.csv"
OUTPUT_FILE = "markets_with_groups_v2.csv"

KEYWORD_GROUPS = {

    # --- 1. US Politics & Government ---
    "us_politics_figures": [
        "trump", "biden", "donald", "joe biden", "kamala", "harris",
        "kamala harris", "vance", "jd vance", "leavitt", "karoline"
    ],
    "us_politics_events": [
        "election", "republican", "democratic", "party", "dnc", "rnc",
        "vote", "primary", "democratic primary", "candidate", "debate",
        "speech", "town hall", "address"
    ],
    "us_govt_actions": [
        "white house", "press briefing", "house press", "senate",
        "executive order", "sign executive", "trump sign", "trump issue",
        "trump border", "government", "secretary", "tariff", "bill",
        "nominate", "supreme court", "ruling"
    ],
    "us_polling": ["approval", "rating", "approval rating", "trump approval"],

    # --- 2. Sports: NFL (American Football) ---
    "nfl_game": [
        "nfl", "super bowl", "afc", "chiefs", "eagles", "giants", "jets",
        "cowboys", "bears", "packers", "vikings", "lions", "falcons",
        "panthers", "saints", "buccaneers", "rams", "seahawks", "cardinals",
        "patriots", "bills", "dolphins", "ravens", "steelers", "browns",
        "bengals", "texans", "colts", "jaguars", "titans", "broncos",
        "raiders", "chargers", "commanders", "nfl draft"
    ],

    # --- 3. Sports: NBA (Basketball) ---
    "nba_game": [
        "nba", "celtics", "kings", "timberwolves", "knicks", "warriors",
        "cavaliers", "pacers", "heat", "nuggets", "lakers", "hawks", "bulls",
        "grizzlies", "mavericks", "bucks", "clippers", "magic", "pistons",
        "raptors", "rockets", "suns", "hornets", "nets", "blazers",
        "trail blazers", "spurs", "pelicans", "jazz", "thunder", "wizards", "76ers"
    ],

    # --- 4. Sports: MLB (Baseball) ---
    "mlb_game": [
        "mlb", "series", "sox", "blue jays", "toronto blue", "yankees", "mets",
        "brewers", "milwaukee brewers", "cubs", "chicago cubs", "athletics", "phillies",
        "philadelphia phillies", "royals", "kansas royals", "braves", "atlanta braves",
        "padres", "diego padres", "guardians", "cleveland guardians", "twins",
        "minnesota twins", "astros", "houston astros", "reds", "cincinnati reds",
        "angels", "los angeles angels", "pirates", "pittsburgh pirates", "rays",
        "tampa bay rays", "orioles", "baltimore orioles", "diamondbacks", "arizona diamondbacks",
        "rockies", "colorado rockies", "marlins", "miami marlins", "white sox",
        "chicago white sox", "tigers", "detroit tigers", "dodgers", "los angeles dodgers",
        "rangers", "texas rangers", "mariners", "seattle mariners", "nationals",
        "washington nationals", "cardinals", "louis cardinals", "giants", "francisco giants"
    ],

    # --- 5. Sports: NHL (Hockey) ---
    "nhl_game": [
        "nhl", "oilers", "knights", "golden knights", "hurricanes", "capitals",
        "wild", "senators", "devils", "avalanche", "lightning", "blues",
        "leafs", "maple leafs", "bruins", "flyers", "islanders", "canucks",
        "predators", "penguins", "sharks", "jackets", "blue jackets", "sabres",
        "kraken", "rangers", "stars", "flames"
    ],

    # --- 6. Sports: Soccer (Football) ---
    "soccer_game": [
        "mls", "manchester united", "real madrid", "chelsea", "champions",
        "liverpool", "arsenal", "aston villa", "tottenham", "manchester",
        "barcelona", "bayern", "borussia dortmund", "psg", "paris saint",
        "inter", "milan", "ac milan", "juventus", "roma", "benfica",
        "bayer leverkusen", "lille", "lazio", "porto", "uefa", "fifa", "euro", "epl",
        "newcastle", "everton", "fulham", "bournemouth", "west ham"
    ],

    # --- 7. Sports: Other ---
    "golf_tour": ["pga", "pga tour", "liv", "liv golf", "masters", "wyndham", "fedex", "john deere", "genesis", "bmw", "ryder", "golf"],
    "tennis_tour": ["atp", "wta", "wimbledon", "french", "australian", "us open", "masters", "rolex", "tennis"],
    "ufc_fight": ["ufc", "fight", "fight night", "ko"],
    "esports_match": ["esports", "dota", "valorant", "chess", "blast", "iem", "mouz", "furia", "natus", "vincere", "heroic", "faze", "cs", "counter strike", "lol", "league", "legends"],
    "f1_racing": ["f1", "prix", "gp", "pole", "constructor", "drivers", "sprint", "verstappen", "leclerc", "hamilton", "norris", "piastri", "racing"],
    "ncaa_sports": ["ncaa", "ncaab", "college"],

    # --- 8. Tech, AI, & Crypto ---
    "elon_musk": ["elon", "musk", "tweet", "tweets", "post", "tesla", "spacex", "starship"],
    "tech_ai_launch": [
        "ai", "artificial intelligence", "openai", "google", "meta",
        "apple", "amazon", "tiktok", "app", "launch", "ai model", "app store"
    ],
    "crypto_launch": [
        "crypto", "eth", "btc", "bitcoin", "ethereum", "dogecoin", "token",
        "airdrop", "coinbase", "fdv"
    ],

    # --- 9. Finance & Economics ---
    "company_earnings": ["earnings", "quarterly", "earnings call", "gross"],
    "econ_indicators": ["inflation", "interest", "rates", "fed", "tariff", "unemployment", "cpi", "powell", "bps"],
    "market_terms": ["gold", "trading", "all time high"],

    # --- 10. Geopolitics ---
    "geopolitics_conflict": [
        "israel", "gaza", "hamas", "russia", "ukraine", "iran", "saudi",
        "ceasefire", "strike", "israel strike", "russia capture", "military"
    ],
    "geopolitics_diplomacy": [
        "china", "france", "japan", "england", "uk", "korea", "germany",
        "canada", "australia", "spain", "italy", "india", "mexico", "brazil",
        "poland", "nato", "border", "summit", "global", "prime minister",
        "netanyahu", "putin", "zelensky"
    ],

    # --- 11. Entertainment & Media ---
    "movies_tv_reviews": ["rotten", "tomatoes", "box office", "movie", "actor", "actress", "netflix", "show"],
    "music_awards": [
        "taylor", "swift", "album", "song", "grammy", "kanye", "eurovision",
        "oscars", "academy", "award", "awards", "winner"
    ],
    "online_media": ["mrbeast", "video", "views"]
}

def find_market_group(question):
    """
    Analyzes a question string and returns a market_group
    if it matches any of our keyword sets.
    """
    if not isinstance(question, str):
        return "other"

    q_lower = question.lower()


    matches = []

    for group_name, keywords in KEYWORD_GROUPS.items():
        # --- THIS LOGIC IS NOW 'ANY' ---
        # Find groups where *any* of the keywords match
        if any(keyword in q_lower for keyword in keywords):
            matches.append(group_name)


    if matches:
        return "&".join(sorted(list(set(matches))))


    return "other"

# --- main script ---
print(f"Loading '{MARKETS_FILE}'...")
if not os.path.exists(MARKETS_FILE):
    print(f"Error: '{MARKETS_FILE}' not found. Run script 1 (fetch_markets_v2.py) first.")
    sys.exit(1)

markets_df = pd.read_csv(MARKETS_FILE)

print("Analyzing questions to find repeat-market groups...")

#  new 'market_group' column
markets_df['market_group'] = markets_df['question'].apply(find_market_group)

# unmatched markets by their base category
markets_df['market_group'] = markets_df.apply(
    lambda row: row['category'].lower().strip() if (row['market_group'] == 'other' and isinstance(row['category'], str)) else row['market_group'],
    axis=1
)
# clean up
markets_df['market_group'] = markets_df['market_group'].fillna('other')

# save
markets_df.to_csv(OUTPUT_FILE, index=False)

print(f"\n--- Success! ---")
print(f"Saved new answer key to '{OUTPUT_FILE}'.")
print("\nExample of new groups found (top 25):")
print(markets_df['market_group'].value_counts().head(25).to_string())