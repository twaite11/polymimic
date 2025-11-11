import pandas as pd
import os
import sys
from sklearn.feature_extraction.text import CountVectorizer

# --- config ---
MARKETS_FILE =  "markets_v2.csv"
TOP_N_RESULTS = 1000 # how many top phrases to show

# --- setup ---
if not os.path.exists(MARKETS_FILE):
    print(f"Error: '{MARKETS_FILE}' not found.")
    sys.exit(1)

print(f"Loading '{MARKETS_FILE}' to discover keywords...")
try:
    markets_df = pd.read_csv(MARKETS_FILE)
except Exception as e:
    print(f"Error reading {MARKETS_FILE}: {e}")
    sys.exit(1)

if 'question' not in markets_df.columns:
    print("Error: 'question' column not found in CSV.")
    sys.exit(1)

# --- analysis ---
print("Analyzing questions to find common phrases...")

# get a clean list of all questions
questions = markets_df['question'].dropna().astype(str)

# define "stop words" - common words to ignore
# we add 'yes' and 'no' as they are part of many market questions
stop_words_list = [
    'will', 'be', 'a', 'to', 'the', 'by', 'on', 'in', 'at', 'of', 'for', 'is', 'at',
    'or', 'and', 'from', 'what', 'when', 'which', 'who', 'how', 'over', 'under',
    'yes', 'no', 'market', 'end', 'before', 'after', 'between', 'than', 'et','up','down','up down','vs','september','price','win','bitcoin','october',
    'ethereum','2025','down october','up down october','bitcoin up','bitcoin up down','above','ethereum up','ethereum up down','solana',
    'xrp','win 2025','10','november','down september','up down september','august','spread','11','12','say','solana up','solana up down',
    'down november','up down november','july','xrp up','xrp up down','during','highest','000',
    '00am','more','00pm','beat','temperature','highest temperature','30pm','15pm','30am','15am','45pm','45am','june','30','draw',
    'down july','up down july','down august','up down august','4pm','4pm et','25','15','20','times','fc','bitcoin above','18','24',
    'nba','21','4am','4am et','new','8am','8am et','26','14','29','open','27','19','13','12am','12am et','points','22','500','ethereum above',
    '23','state','12pm','12pm et','8pm','8pm et','31','28','17','solana above','16','xrp above'
    ,'city','2023','00am et','london','temperature london','highest temperature london','00pm et',
    'may','pm','down june','up down june','30pm et','york','election','45pm et','15pm et','new york','45am et','15am et','30am et','2025 10',
    'win 2025 10','pm et','09','000 september','2024','their','march','more points','april','less','next','championship',
    '500 september','matchup','first','15pm 30pm','15pm 30pm et','30pm 45pm','30pm 45pm et','00pm 15pm','00pm 15pm et','york city',
    '30am 45am','00am 15am','30am 45am et','00am 15am et','new york city','bo3','15am 30am','15am 30am et','counter','grand','counter strike',
    '45am 00am','45am 00am et','team','score','45pm 00pm','45pm 00pm et','1h','tournament','temperature new','temperature new york',
    'highest temperature new','game','mlb','times during','2025 09','win 2025 09','5pm','5pm et','cup','february','04',
    'world','greater','round','his','03','points their','week','us','most','reach','red','rally','total','05','higher','league','00','100','january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'                                                                                                                                                                                                                                                    '08', 'have', 'club','50','200','dip', 'winner', 'below', 'weekend', 'opening', 'with', 'opening weekend', 'san', 'post', 'best', 'finish', '60', '11pm',
    'top', '10pm', 'day', '1pm', '5pm', '5am', '9pm', '2am', '10am', '9am', '1am', '2pm', '6pm', '3am', '6am', '400', '3pm', 'friday', 'saturday', 'sunday', 'monday', 'tuesday', 'wednesday',
    'get', 'de', '70', '116', 'scheduled', 'million', 'lead', 'match', 'st', '11am', '112', '40', '7pm', 'south', 'as', '02', 'an', 'am', 'lol'
]
def get_top_ngrams(corpus, ngram_range, n=20):
    """
    Finds the most frequent n-grams (phrases) in a list of text.
    """
    # create a vectorizer to count words/phrases,
    # ignoring our custom list of stop words
    vec = CountVectorizer(
        ngram_range=ngram_range,
        stop_words=stop_words_list
    ).fit(corpus)

    bag_of_words = vec.transform(corpus)
    sum_words = bag_of_words.sum(axis=0)
    words_freq = [(word, sum_words[0, idx]) for word, idx in vec.vocabulary_.items()]
    words_freq = sorted(words_freq, key = lambda x: x[1], reverse=True)
    return words_freq[:n]

# get the top 1-word, 2-word, and 3-word phrases
top_1_words = get_top_ngrams(questions, ngram_range=(1, 1), n=TOP_N_RESULTS)
top_2_words = get_top_ngrams(questions, ngram_range=(2, 2), n=TOP_N_RESULTS)
top_3_words = get_top_ngrams(questions, ngram_range=(3, 3), n=TOP_N_RESULTS)

# combine them into one big list
all_top_phrases = top_1_words + top_2_words + top_3_words

# sort the combined list by frequency
all_top_phrases_sorted = sorted(all_top_phrases, key=lambda x: x[1], reverse=True)

# --- NEW FILTER TO EXCLUDE NUMBERS ---
all_top_phrases_filtered = [
    (phrase, count) for phrase, count in all_top_phrases_sorted
    if not any(char.isdigit() for char in phrase)
]
# --- END OF NEW FILTER ---


# --- print report ---
print(f"\n--- Top {TOP_N_RESULTS} Recurring Keywords & Phrases (No Numbers, CSV Format) ---")
print("(Copy this list to build your 'KEYWORD_GROUPS' dictionary)\n")

# filter list generate
phrases_only = [phrase for phrase, count in all_top_phrases_filtered[:TOP_N_RESULTS]]
quoted_phrases = [f"'{phrase}'" for phrase in phrases_only]
csv_output = ",".join(quoted_phrases)
print(csv_output)


print("\n\n--- End of Report ---")