"""
Gemini-powered Financial Expert Chat Interface
Provides financial expert context and analyzes whale trading data.
"""

import google.generativeai as genai
import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

load_dotenv()

DATABASE_FILE = Path("~/IdeaProjects/PolyCopy/db/simulation.db").expanduser()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_financial_expert_context():
    """
    Returns the system context for the financial expert.
    Sets up the LLM as a knowledgeable financial analyst.
    """
    return """You are an elite financial markets analyst and prediction market expert with deep expertise in:

1. **Prediction Markets & Information Economics**: Understanding how information asymmetry creates trading opportunities, how insider knowledge manifests in market behavior, and how to identify predictive signals in prediction market data.

2. **Statistical Analysis & Pattern Recognition**: Expert in analyzing trading patterns, win rates, P&L distributions, and identifying anomalies that suggest superior information or predictive ability.

3. **Market Psychology & Behavioral Finance**: Understanding how traders make decisions, what distinguishes successful traders from others, and how to identify systematic advantages.

4. **Polymarket & Prediction Markets**: Deep knowledge of how prediction markets work, how they resolve, what types of information are valuable, and how to identify profitable trading strategies.

5. **Risk Assessment**: Expert at evaluating trading strategies, identifying risks, and determining when a trader's success is due to skill vs. luck vs. insider information.

When analyzing data, you:
- Provide clear, actionable insights backed by data
- Identify patterns that suggest insider information or exceptional skill
- Recommend specific trading strategies based on evidence
- Assess risk levels appropriately
- Explain your reasoning in accessible terms

You speak with authority but remain grounded in the data provided. You're analytical, insightful, and practical.
"""

def get_whale_trading_data(conn, limit=50):
    """
    Fetches comprehensive whale trading data for financial expert analysis.
    Returns formatted data about whale performance, categories, and trades.
    """
    cursor = conn.cursor()
    
    # Get top whales by P&L
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
            insider_score
        FROM whale_stats
        WHERE total_resolved >= 3
        ORDER BY total_pnl DESC
        LIMIT ?
    ''', (limit,))
    whales = cursor.fetchall()
    
    # Get category performance
    cursor.execute('''
        SELECT 
            whale_wallet,
            category,
            total_trades,
            total_wins,
            total_losses,
            total_pnl,
            win_rate
        FROM whale_category_stats
        ORDER BY total_pnl DESC
        LIMIT 100
    ''')
    category_data = cursor.fetchall()
    
    # Get successful trades
    cursor.execute('''
        SELECT 
            whale_wallet,
            question,
            category,
            outcome,
            pnl,
            timestamp
        FROM successful_trades
        ORDER BY pnl DESC
        LIMIT 50
    ''')
    top_trades = cursor.fetchall()
    
    # Get recent trading activity
    cursor.execute('''
        SELECT 
            whale_wallet,
            question,
            category,
            outcome,
            side,
            price,
            pnl,
            timestamp,
            is_resolved
        FROM trades
        ORDER BY timestamp DESC
        LIMIT 100
    ''')
    recent_trades = cursor.fetchall()
    
    # Format data for LLM
    data_summary = {
        'summary': {
            'total_whales_tracked': len(whales),
            'whales_with_positive_pnl': len([w for w in whales if w['total_pnl'] > 0]),
            'total_resolved_trades': sum([w['total_resolved'] for w in whales]),
            'overall_win_rate': sum([w['total_wins'] for w in whales]) / sum([w['total_resolved'] for w in whales]) if sum([w['total_resolved'] for w in whales]) > 0 else 0
        },
        'top_whales': [dict(w) for w in whales[:10]],
        'category_performance': [dict(c) for c in category_data[:20]],
        'top_trades': [dict(t) for t in top_trades[:20]],
        'recent_activity': [dict(t) for t in recent_trades[:30]]
    }
    
    return data_summary

def format_data_for_prompt(data_summary):
    """
    Formats the whale trading data into a readable prompt for the LLM.
    """
    summary = data_summary['summary']
    top_whales = data_summary['top_whales']
    category_perf = data_summary['category_performance']
    top_trades = data_summary['top_trades']
    
    prompt = f"""WHALE TRADING DATA ANALYSIS

OVERVIEW:
- Total Whales Tracked: {summary['total_whales_tracked']}
- Whales with Positive P&L: {summary['whales_with_positive_pnl']}
- Total Resolved Trades: {summary['total_resolved_trades']}
- Overall Win Rate: {summary['overall_win_rate']:.2%}

TOP 10 WHALES BY P&L:
"""
    for i, whale in enumerate(top_whales, 1):
        prompt += f"{i}. {whale['whale_wallet'][:10]}... | "
        prompt += f"Trades: {whale['total_resolved']}/{whale['total_trades']} | "
        prompt += f"Win Rate: {whale.get('win_rate', 0):.1%} | "
        prompt += f"P&L: ${whale['total_pnl']:.2f} | "
        prompt += f"Avg P&L/Trade: ${whale.get('avg_pnl_per_trade', 0):.2f} | "
        prompt += f"Insider Score: {whale.get('insider_score', 0)}\n"
    
    prompt += "\nCATEGORY PERFORMANCE (Top 10):\n"
    for i, cat in enumerate(category_perf[:10], 1):
        prompt += f"{i}. {cat['category']} | Whale: {cat['whale_wallet'][:10]}... | "
        prompt += f"Trades: {cat['total_trades']} | Win Rate: {cat.get('win_rate', 0):.1%} | "
        prompt += f"P&L: ${cat['total_pnl']:.2f}\n"
    
    prompt += "\nTOP PROFITABLE TRADES (Top 10):\n"
    for i, trade in enumerate(top_trades[:10], 1):
        prompt += f"{i}. {trade.get('question', 'N/A')[:60]}...\n"
        prompt += f"   Whale: {trade['whale_wallet'][:10]}... | "
        prompt += f"Category: {trade.get('category', 'N/A')} | "
        prompt += f"P&L: ${trade.get('pnl', 0):.2f}\n"
    
    return prompt

def chat_with_financial_expert(user_message, conversation_history=None, include_data=True):
    """
    Sends a message to the financial expert LLM and returns the response.
    
    Args:
        user_message: The user's question or request
        conversation_history: List of previous messages in format [{"role": "user/assistant", "content": "..."}]
        include_data: Whether to include whale trading data in the context
    
    Returns:
        Assistant's response text
    """
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY not found in environment variables. Please set it in your .env file."
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-pro')
        
        # Build the prompt
        system_context = get_financial_expert_context()
        
        # Get whale data if requested
        data_context = ""
        if include_data:
            try:
                conn = sqlite3.connect(DATABASE_FILE)
                conn.row_factory = sqlite3.Row
                whale_data = get_whale_trading_data(conn)
                data_context = format_data_for_prompt(whale_data)
                conn.close()
            except Exception as e:
                data_context = f"Note: Could not load trading data ({str(e)}). Proceeding with general knowledge only."
        
        # Build full prompt
        full_prompt = f"""{system_context}

CURRENT WHALE TRADING DATA:
{data_context}

USER QUESTION:
{user_message}

Please provide a detailed, expert analysis in response to the user's question. Use the trading data provided to support your insights. Be specific and actionable.
"""
        
        # If there's conversation history, include it
        if conversation_history and len(conversation_history) > 0:
            # Gemini doesn't have a direct chat interface like OpenAI, so we'll format it
            history_text = "\n\nCONVERSATION HISTORY:\n"
            for msg in conversation_history[-5:]:  # Last 5 messages for context
                role = "USER" if msg["role"] == "user" else "ASSISTANT"
                history_text += f"{role}: {msg['content']}\n"
            full_prompt = history_text + "\n\n" + full_prompt
        
        # Generate response
        response = model.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=2000,
                top_p=0.9,
                top_k=40
            )
        )
        
        return response.text.strip()
        
    except Exception as e:
        return f"Error communicating with financial expert: {str(e)}"

def get_db_connection():
    """Establishes connection to the database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        return None

