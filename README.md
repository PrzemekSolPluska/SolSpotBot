# SolSpotBot - Binance Spot Trading Bot for SOL/USDC

A fully automated trading bot for Binance Spot that trades SOL/USDC using market orders only.

## Features

- **All-in strategy**: Always holds 100% USDC or 100% SOL, never partial allocations
- **Market orders only**: No limit orders, instant execution
- **Spot trading only**: No margin, futures, leverage, or withdrawals
- **Startup safety**: Automatically sells any SOL balance on first run
- **Smart entry**: Analyzes 3-minute candles for momentum-based buy signals
- **Trailing stop**: 20% trailing take-profit protection
- **Hard stop-loss**: 1% maximum loss protection

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Create `.env` file:**
   Create a `.env` file in the project root with your Binance API credentials:
   ```
   BINANCE_API_KEY=your_api_key_here
   BINANCE_API_SECRET=your_api_secret_here
   ```

   **Important**: Make sure your Binance API key has Spot trading permissions enabled, and **disable** withdrawals for security.

3. **Run the bot:**
   ```bash
   python main.py
   ```

## Trading Logic

### Buy Conditions (all must be true):
1. Both last two candles are green (positive % change)
2. Combined strength >= 0.7% (r1 + r2 >= 0.7)
3. Momentum increases (r2 >= r1)
4. Second candle >= 0.35%

### Sell Conditions:
- **Trailing Stop**: If profit drops 20% from peak profit
- **Hard Stop-Loss**: If loss reaches -1%

## Files

- `main.py` - Main loop and orchestration
- `exchange.py` - Binance API wrapper
- `strategy.py` - Buy/sell logic
- `config.py` - Configuration parameters
- `state.json` - Bot state (auto-created)
- `bot.log` - Log file (auto-created)

## State Management

The bot maintains state in `state.json`:
- `FIRST_RUN_SELL_DONE`: Prevents multiple startup sells
- `holding`: Whether currently holding SOL
- `buy_price`: Price at which SOL was bought
- `peak_price`: Highest price reached since buy

## Logging

All activity is logged to both:
- Console (stdout)
- `bot.log` file

## Important Notes

- The bot runs continuously until stopped (Ctrl+C)
- It checks for signals every 5-10 seconds
- On first run, any existing SOL balance will be sold to USDC
- Always test with small amounts first
- Monitor the bot regularly
- Ensure you have sufficient USDC balance for trading

## Disclaimer

This bot is for educational purposes. Trading cryptocurrencies involves risk. Use at your own risk and never invest more than you can afford to lose.

