"""
Configuration file for SolSpotBot
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Keys
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    raise RuntimeError("Missing BINANCE_API_KEY or BINANCE_API_SECRET in .env file")

# Telegram Configuration
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trading Parameters
SYMBOL = "SOLUSDC"  # Trading pair
TIMEFRAME = "3m"    # Candle interval

# Buy Logic Parameters
ENTRY_TOTAL_MOVE = 0.7   # Combined strength: r1 + r2 >= 0.7%
ENTRY_MIN_SECOND = 0.35  # Second candle must be >= 0.35%

# Sell Logic Parameters
TRAILING_SHARE = 0.2      # 20% trailing stop
MAX_LOSS_PERCENT = 0.005  # 0.5% hard stop-loss

# Loop Parameters
LOOP_INTERVAL = 7  # Seconds between loop iterations (5-10 seconds)

# Watchdog Parameters
WATCHDOG_MINUTES = 15  # Minutes of inactivity before alert

# State File
STATE_FILE = "state.json"

# Log File
LOG_FILE = "bot.log"
