"""
LLM-powered whale analysis module.
Uses an LLM to analyze whale trading patterns and identify potential insider information indicators.
"""

import sqlite3
import json
import os
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

# Try to import Google Generative AI (Gemini), fallback to a basic implementation if not available
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google Generative AI library not installed. LLM analysis will use basic heuristics.")

DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANALYSIS_INTERVAL_HOURS = 24  # Run analysis once per day

# Market category keywords for analysis
MARKET_KEYWORD_GROUPS = {
    "us_politics": ["trump", "biden", "election", "republican", "democratic", "president"],
    "sports_nfl": ["nfl", "super bowl", "football"],
    "sports_nba": ["nba", "basketball"],
    "tech_ai": ["ai", "openai", "google", "apple", "meta", "tesla"],
    "crypto": ["crypto", "bitcoin", "ethereum"],
    "finance": ["earnings", "stock", "inflation", "fed"],
    "geopolitics": ["ukraine", "russia", "china", "israel"],
    "entertainment": ["movie", "netflix", "taylor swift"]
}

def extract_market_category(question):
    """Extracts market category from question text."""
    if not question or not isinstance(question, str):
        return "other"
    q_lower = question.lower()
    for category, keywords in MARKET_KEYWORD_GROUPS.items():
        if any(keyword in q_lower for keyword in keywords):
            return category
    return "other"

def get_db_connection():
    """Establishes connection to the database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logging.error(f"Error connecting to database: {e}")
        return None

def get_whale_performance_data(conn):
    """
    Fetches comprehensive whale performance data for LLM analysis.
    Returns a dictionary with whale statistics and trade details.
    """
    cursor = conn.cursor()
    
    # Get whale stats
    cursor.execute('''
        SELECT 
            whale_wallet,
            total_trades,
            total_resolved,
            total_wins,
            total_losses,
            total_pnl,
            win_rate,
            avg_pnl_per_trade,
            categories
        FROM whale_stats
        WHERE total_resolved >= 5
        ORDER BY total_pnl DESC
        LIMIT 50
    ''')
    whales = cursor.fetchall()
    
    whale_data = {}
    for whale in whales:
        wallet = whale['whale_wallet']
        
        # Get category-specific performance
        cursor.execute('''
            SELECT category, total_trades, total_wins, total_losses, 
                   total_pnl, win_rate
            FROM whale_category_stats
            WHERE whale_wallet = ?
            ORDER BY total_pnl DESC
        ''', (wallet,))
        categories = cursor.fetchall()
        
        # Get recent successful trades
        cursor.execute('''
            SELECT question, category, outcome, pnl, timestamp
            FROM successful_trades
            WHERE whale_wallet = ?
            ORDER BY pnl DESC
            LIMIT 10
        ''', (wallet,))
        recent_trades = cursor.fetchall()
        
        # Get all trades for pattern analysis
        cursor.execute('''
            SELECT question, category, outcome, side, price, pnl, 
                   timestamp, is_resolved
            FROM trades
            WHERE whale_wallet = ?
            ORDER BY timestamp DESC
            LIMIT 50
        ''', (wallet,))
        all_trades = cursor.fetchall()
        
        whale_data[wallet] = {
            'stats': dict(whale),
            'categories': [dict(c) for c in categories],
            'recent_trades': [dict(t) for t in recent_trades],
            'all_trades': [dict(t) for t in all_trades]
        }
    
    return whale_data

def analyze_with_llm(whale_data):
    """
    Uses Gemini LLM to analyze whale trading patterns and identify potential insider info indicators.
    Returns analysis results with insider scores and insights.
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        # Fallback to heuristic-based analysis
        return analyze_with_heuristics(whale_data)
    
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-pro')
    
    results = {}
    
    for wallet, data in whale_data.items():
        # Prepare summary for LLM
        stats = data['stats']
        categories = data['categories']
        recent_trades = data['recent_trades']
        
        # Build prompt
        prompt = f"""Analyze this whale trader's performance data and determine if they might have insider information or exceptional predictive ability.

Whale Wallet: {wallet[:10]}...
Total Trades: {stats.get('total_trades', 0)}
Resolved Trades: {stats.get('total_resolved', 0)}
Win Rate: {stats.get('win_rate', 0):.2%}
Total P&L: ${stats.get('total_pnl', 0):.2f}
Average P&L per Trade: ${stats.get('avg_pnl_per_trade', 0):.2f}

Category Performance:
"""
        for cat in categories[:5]:  # Top 5 categories
            prompt += f"- {cat['category']}: {cat['total_trades']} trades, {cat.get('win_rate', 0):.2%} win rate, ${cat.get('total_pnl', 0):.2f} P&L\n"
        
        prompt += f"\nRecent Top Trades:\n"
        for trade in recent_trades[:5]:
            prompt += f"- {trade.get('question', 'N/A')[:60]}... | {trade.get('category')} | P&L: ${trade.get('pnl', 0):.2f}\n"
        
        prompt += """
Analyze this trader and provide:
1. Insider Score (0-100): How likely does this trader have insider information? Consider:
   - Exceptional win rates in specific categories
   - Consistent profits in time-sensitive markets
   - Trading patterns that suggest early information
   - Category specialization vs diversification

2. Key Insights: 2-3 bullet points about their trading style and potential advantages

3. Recommended Categories: Which categories should we prioritize when copying this whale?

Respond in JSON format:
{
  "insider_score": <number 0-100>,
  "insights": ["insight1", "insight2", "insight3"],
  "recommended_categories": ["category1", "category2"],
  "risk_level": "low|medium|high"
}
"""
        
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=500
                )
            )
            
            response_text = response.text.strip()
            
            # Parse JSON response
            try:
                # Remove markdown code blocks if present
                if response_text.startswith("```"):
                    response_text = response_text.split("```")[1]
                    if response_text.startswith("json"):
                        response_text = response_text[4:]
                
                analysis = json.loads(response_text)
                results[wallet] = {
                    'insider_score': analysis.get('insider_score', 0),
                    'insights': analysis.get('insights', []),
                    'recommended_categories': analysis.get('recommended_categories', []),
                    'risk_level': analysis.get('risk_level', 'medium'),
                    'analysis_date': datetime.now().isoformat()
                }
            except json.JSONDecodeError as e:
                logging.warning(f"Failed to parse Gemini response for {wallet[:10]}: {e}")
                results[wallet] = analyze_whale_heuristics(wallet, data)
        except Exception as e:
            logging.error(f"Error calling Gemini API for {wallet[:10]}: {e}")
            results[wallet] = analyze_whale_heuristics(wallet, data)
    
    return results

def analyze_whale_heuristics(wallet, data):
    """Fallback heuristic-based analysis when LLM is unavailable."""
    stats = data['stats']
    categories = data['categories']
    
    # Calculate insider score based on heuristics
    insider_score = 0
    
    # High win rate bonus
    win_rate = stats.get('win_rate', 0)
    if win_rate > 0.75:
        insider_score += 30
    elif win_rate > 0.65:
        insider_score += 20
    elif win_rate > 0.55:
        insider_score += 10
    
    # High P&L per trade bonus
    avg_pnl = stats.get('avg_pnl_per_trade', 0)
    if avg_pnl > 0.5:
        insider_score += 25
    elif avg_pnl > 0.3:
        insider_score += 15
    elif avg_pnl > 0.1:
        insider_score += 5
    
    # Category specialization bonus
    if categories:
        top_category = categories[0]
        if top_category.get('total_trades', 0) >= 10 and top_category.get('win_rate', 0) > 0.7:
            insider_score += 20
        
        # Check for multiple high-performing categories
        high_perf_cats = [c for c in categories if c.get('win_rate', 0) > 0.65 and c.get('total_trades', 0) >= 5]
        if len(high_perf_cats) >= 3:
            insider_score += 15
        elif len(high_perf_cats) >= 2:
            insider_score += 10
    
    # Consistent profit bonus
    total_pnl = stats.get('total_pnl', 0)
    if total_pnl > 10:
        insider_score += 10
    elif total_pnl > 5:
        insider_score += 5
    
    insider_score = min(insider_score, 100)  # Cap at 100
    
    insights = []
    if win_rate > 0.7:
        insights.append(f"Exceptional win rate of {win_rate:.1%}")
    if categories and categories[0].get('total_trades', 0) >= 10:
        insights.append(f"Specializes in {categories[0]['category']} with {categories[0].get('win_rate', 0):.1%} win rate")
    if avg_pnl > 0.3:
        insights.append(f"High average P&L of ${avg_pnl:.2f} per trade")
    
    recommended_categories = [c['category'] for c in categories[:3] if c.get('win_rate', 0) > 0.6]
    
    return {
        'insider_score': insider_score,
        'insights': insights,
        'recommended_categories': recommended_categories,
        'risk_level': 'high' if insider_score > 70 else 'medium' if insider_score > 40 else 'low',
        'analysis_date': datetime.now().isoformat()
    }

def analyze_with_heuristics(whale_data):
    """Batch heuristic analysis when LLM is unavailable."""
    results = {}
    for wallet, data in whale_data.items():
        results[wallet] = analyze_whale_heuristics(wallet, data)
    return results

def update_whale_analysis(conn, analysis_results):
    """Updates the database with LLM analysis results."""
    cursor = conn.cursor()
    
    for wallet, analysis in analysis_results.items():
        cursor.execute('''
            UPDATE whale_stats
            SET insider_score = ?,
                last_analyzed = CURRENT_TIMESTAMP
            WHERE whale_wallet = ?
        ''', (analysis['insider_score'], wallet))
        
        # Store detailed analysis in a separate table or JSON field
        # For now, we'll log it
        logging.info(f"Updated analysis for {wallet[:10]}: Insider Score = {analysis['insider_score']}")
    
    conn.commit()

def main():
    """Main function to run LLM whale analysis."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    
    logging.info("Starting LLM whale analysis...")
    
    conn = get_db_connection()
    if not conn:
        logging.error("Failed to connect to database")
        return
    
    # Check if analysis was run recently
    cursor = conn.cursor()
    cursor.execute('''
        SELECT MAX(last_analyzed) as last_analysis
        FROM whale_stats
    ''')
    last_analysis = cursor.fetchone()['last_analysis']
    
    if last_analysis:
        last_analysis_dt = datetime.fromisoformat(last_analysis.replace(' ', 'T'))
        hours_since = (datetime.now() - last_analysis_dt).total_seconds() / 3600
        if hours_since < ANALYSIS_INTERVAL_HOURS:
            logging.info(f"Analysis ran {hours_since:.1f} hours ago. Skipping.")
            conn.close()
            return
    
    # Get whale data
    whale_data = get_whale_performance_data(conn)
    
    if not whale_data:
        logging.info("No whale data found for analysis")
        conn.close()
        return
    
    logging.info(f"Analyzing {len(whale_data)} whales...")
    
    # Run LLM analysis
    analysis_results = analyze_with_llm(whale_data)
    
    # Update database
    update_whale_analysis(conn, analysis_results)
    
    # Print summary
    logging.info("\n=== Analysis Summary ===")
    for wallet, analysis in sorted(analysis_results.items(), key=lambda x: x[1]['insider_score'], reverse=True)[:10]:
        logging.info(f"{wallet[:10]}... | Score: {analysis['insider_score']} | Risk: {analysis['risk_level']}")
        for insight in analysis['insights']:
            logging.info(f"  - {insight}")
    
    conn.close()
    logging.info("LLM whale analysis complete.")

if __name__ == "__main__":
    main()

