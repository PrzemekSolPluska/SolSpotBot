"""
Main trading bot loop for SolSpotBot
"""
import time
import json
import logging
import traceback
import sys
import re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from config import (
    BINANCE_API_KEY,
    BINANCE_API_SECRET,
    SYMBOL,
    TIMEFRAME,
    LOOP_INTERVAL,
    STATE_FILE,
    LOG_FILE,
    WATCHDOG_MINUTES
)
from exchange import Exchange
from strategy import should_buy, should_sell, calculate_candle_changes
from telegram_bot import send_telegram_message


class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that safely handles Unicode/emoji on Windows"""
    def emit(self, record):
        try:
            msg = self.format(record)
            # Remove emojis for console output on Windows
            # Keep them in file logs
            if sys.platform == 'win32':
                # Remove emoji and other problematic Unicode characters
                msg = re.sub(r'[^\x00-\x7F]+', '', msg)
            stream = self.stream
            stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)


# Setup logging with UTF-8 encoding for file and safe console handler
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        SafeConsoleHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_state() -> Dict:
    """Load state from state.json file"""
    state_path = Path(STATE_FILE)
    if state_path.exists():
        try:
            with open(state_path, 'r') as f:
                state = json.load(f)
                logger.info(f"Loaded state: {state}")
                return state
        except Exception as e:
            logger.error(f"Error loading state: {e}")
            return {}
    return {}


def save_state(state: Dict):
    """Save state to state.json file"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)
        logger.debug(f"State saved: {state}")
    except Exception as e:
        logger.error(f"Error saving state: {e}")


def startup_sell_if_needed(exchange: Exchange, state: Dict) -> Dict:
    """
    Handle startup behavior: sell all SOL if FIRST_RUN_SELL_DONE is not set
    
    Returns:
        Updated state dictionary
    """
    if state.get("FIRST_RUN_SELL_DONE", False):
        logger.info("FIRST_RUN_SELL_DONE already set, skipping startup sell")
        return state
    
    try:
        sol_balance = exchange.get_balance("SOL")
        logger.info(f"Startup check: SOL balance = {sol_balance:.6f}")
        
        if sol_balance > 0:
            logger.info(f"Startup: Found {sol_balance:.6f} SOL - selling all to USDC...")
            order = exchange.market_sell_all_sol(SYMBOL)
            
            if order:
                logger.info(f"Startup sell completed: {order}")
                state["FIRST_RUN_SELL_DONE"] = True
                save_state(state)
                
                # Telegram notification for startup sell
                try:
                    symbol_base = SYMBOL.replace("USDC", "").replace("USD", "")
                    symbol_quote = "USDC"
                    price = float(order.get('fills', [{}])[0].get('price', 0)) if order.get('fills') else 0
                    qty = float(order.get('executedQty', 0))
                    commission = float(order.get('fills', [{}])[0].get('commission', 0)) if order.get('fills') else 0
                    
                    msg = (
                        f"🔁 Startup SELL executed\n"
                        f"Sold all {symbol_base} to {symbol_quote}\n"
                        f"Price={price:.4f}, qty={qty:.6f}, commission={commission:.6f}"
                    )
                    send_telegram_message(msg)
                except Exception as e:
                    logger.warning(f"Failed to send Telegram notification for startup sell: {e}")
            else:
                logger.warning("Startup sell returned None (may be insufficient balance)")
        else:
            logger.info("Startup: No SOL balance to sell")
            state["FIRST_RUN_SELL_DONE"] = True
            save_state(state)
            
    except Exception as e:
        logger.error(f"Error during startup sell: {e}")
        traceback.print_exc()
        # Don't set FIRST_RUN_SELL_DONE if there was an error
        # This allows retry on next startup
    
    return state


def main_loop():
    """Main trading bot loop"""
    logger.info("=" * 60)
    logger.info("SolSpotBot Starting...")
    logger.info("=" * 60)
    
    # Initialize exchange
    try:
        exchange = Exchange(BINANCE_API_KEY, BINANCE_API_SECRET)
    except Exception as e:
        logger.error(f"Failed to initialize exchange: {e}")
        return
    
    # Load state
    state = load_state()
    
    # Send startup Telegram notification
    try:
        first_run_done = state.get("FIRST_RUN_SELL_DONE", False)
        msg = (
            f"🚀 SolSpotBot started\n"
            f"FIRST_RUN_SELL_DONE={first_run_done}\n"
            f"Symbol={SYMBOL}"
        )
        send_telegram_message(msg)
    except Exception as e:
        logger.warning(f"Failed to send startup Telegram notification: {e}")
    
    # Startup behavior: sell SOL if needed
    state = startup_sell_if_needed(exchange, state)
    
    # Initialize trading state
    holding = state.get("holding", False)
    buy_price = state.get("buy_price", 0.0)
    peak_price = state.get("peak_price", 0.0)
    last_candle_time = None
    
    # Watchdog variables
    last_activity_ts = time.time()
    watchdog_alert_sent = False
    
    logger.info(f"Initial state: holding={holding}, buy_price={buy_price}, peak_price={peak_price}")
    
    # Main loop
    logger.info("Entering main trading loop...")
    
    while True:
        try:
            if not holding:
                # Not holding: check for buy signals
                logger.debug("Not holding - checking for buy signals...")
                
                # Get klines
                klines = exchange.get_klines(SYMBOL, TIMEFRAME, limit=20)
                
                # Activity: successfully fetched candles
                last_activity_ts = time.time()
                watchdog_alert_sent = False
                
                if len(klines) < 3:
                    logger.warning("Not enough candles, waiting...")
                    time.sleep(LOOP_INTERVAL)
                    continue
                
                # Check if we have a new candle (compare last candle's open time)
                current_candle_time = klines[-1][0]
                if last_candle_time is None or current_candle_time != last_candle_time:
                    last_candle_time = current_candle_time
                    
                    # Evaluate buy conditions
                    if should_buy(klines):
                        # Execute buy
                        usdc_balance = exchange.get_balance("USDC")
                        logger.info(f"USDC balance: {usdc_balance:.2f}")
                        
                        if usdc_balance > 0:
                            current_price = exchange.get_current_price(SYMBOL)
                            order = exchange.market_buy_all_usdc(SYMBOL)
                            
                            if order:
                                # Get actual execution price from order fills
                                try:
                                    fills = order.get('fills', [])
                                    if fills:
                                        total_qty = sum(float(f.get('qty', 0)) for f in fills)
                                        total_cost = sum(float(f.get('price', 0)) * float(f.get('qty', 0)) for f in fills)
                                        actual_buy_price = total_cost / total_qty if total_qty > 0 else current_price
                                    else:
                                        actual_buy_price = current_price
                                except Exception:
                                    actual_buy_price = current_price
                                
                                # Calculate r1, r2 for Telegram message
                                try:
                                    r1, r2 = calculate_candle_changes(klines)
                                except Exception:
                                    r1, r2 = 0.0, 0.0
                                
                                # Update state with actual execution price
                                holding = True
                                buy_price = actual_buy_price
                                peak_price = actual_buy_price
                                
                                state["holding"] = holding
                                state["buy_price"] = buy_price
                                state["peak_price"] = peak_price
                                save_state(state)
                                
                                logger.info(
                                    f"BUY EXECUTED: "
                                    f"price={buy_price:.4f}, "
                                    f"order={order.get('orderId', 'N/A')}"
                                )
                                
                                # Telegram notification for BUY
                                try:
                                    qty = float(order.get('executedQty', 0))
                                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    msg = (
                                        f"BUY executed {SYMBOL}\n"
                                        f"Price={buy_price:.4f}\n"
                                        f"Qty={qty:.3f}\n"
                                        f"Reason: 2 green candles r1={r1:.3f}%, r2={r2:.3f}%\n"
                                        f"Time={timestamp}"
                                    )
                                    send_telegram_message(msg)
                                except Exception as e:
                                    logger.warning(f"Failed to send Telegram notification for BUY: {e}")
                            else:
                                logger.warning("Buy signal but order execution returned None")
                        else:
                            logger.warning("Buy signal but insufficient USDC balance")
                else:
                    logger.debug("No new candle yet, waiting...")
            
            else:
                # Holding: check for sell signals
                logger.debug("Holding - checking for sell signals...")
                
                current_price = exchange.get_current_price(SYMBOL)
                
                # Activity: successfully updated price and logic for open position
                last_activity_ts = time.time()
                watchdog_alert_sent = False
                
                # Update peak price
                if current_price > peak_price:
                    peak_price = current_price
                    state["peak_price"] = peak_price
                    save_state(state)
                    logger.debug(f"New peak: {peak_price:.4f}")
                
                # Check sell conditions
                should_sell_flag, reason = should_sell(current_price, buy_price, peak_price)
                
                if should_sell_flag:
                    # Execute sell
                    sol_balance = exchange.get_balance("SOL")
                    logger.info(f"SOL balance: {sol_balance:.6f}")
                    
                    if sol_balance > 0:
                        order = exchange.market_sell_all_sol(SYMBOL)
                        
                        if order:
                            # Capture values before resetting state
                            entry_price = buy_price
                            peak_price_during_trade = peak_price
                            
                            # Get actual exit price from order execution
                            try:
                                # Try to get average execution price from fills
                                fills = order.get('fills', [])
                                if fills:
                                    total_qty = sum(float(f.get('qty', 0)) for f in fills)
                                    total_cost = sum(float(f.get('price', 0)) * float(f.get('qty', 0)) for f in fills)
                                    exit_price = total_cost / total_qty if total_qty > 0 else current_price
                                else:
                                    # Fallback to current_price if fills not available
                                    exit_price = current_price
                            except Exception:
                                exit_price = current_price
                            
                            # Get executed quantity for logging
                            qty = float(order.get('executedQty', 0))
                            
                            # Calculate REAL realized PnL
                            if entry_price > 0:
                                profit_fraction = (exit_price - entry_price) / entry_price
                                realized_pnl_percent = profit_fraction * 100.0
                            else:
                                realized_pnl_percent = 0.0
                            
                            # Calculate max profit during trade
                            max_profit_percent = None
                            if peak_price_during_trade > 0 and entry_price > 0:
                                max_profit_fraction = (peak_price_during_trade - entry_price) / entry_price
                                max_profit_percent = max_profit_fraction * 100.0
                            
                            # Map exit_reason to human-readable label
                            if reason == "STOP_LOSS":
                                exit_label = "stop-loss"
                            elif reason == "TRAILING_TP":
                                exit_label = "trailing TP"
                            else:
                                exit_label = reason or "exit"
                            
                            # Update state
                            holding = False
                            buy_price = 0.0
                            peak_price = 0.0
                            
                            state["holding"] = holding
                            state["buy_price"] = buy_price
                            state["peak_price"] = peak_price
                            save_state(state)
                            
                            # Log exit details
                            max_profit_str = f"{max_profit_percent:.2f}%" if max_profit_percent is not None else "N/A"
                            logger.info(
                                f"EXIT {SYMBOL}: reason={reason}, "
                                f"entry={entry_price:.4f}, exit={exit_price:.4f}, "
                                f"pnl={realized_pnl_percent:+.2f}%, "
                                f"max_profit={max_profit_str}"
                            )
                            
                            # Build improved SELL Telegram message
                            try:
                                lines = []
                                lines.append(f"SELL ({exit_label}) {SYMBOL}")
                                lines.append(f"Entry={entry_price:.4f}")
                                lines.append(f"Exit={exit_price:.4f}")
                                lines.append(f"Qty={qty:.3f}")
                                lines.append(f"PnL={realized_pnl_percent:+.2f}%")
                                
                                if max_profit_percent is not None and max_profit_percent != 0:
                                    lines.append(f"Max profit during trade={max_profit_percent:.2f}%")
                                
                                lines.append(f"Reason={reason}")
                                
                                message = "\n".join(lines)
                                send_telegram_message(message)
                            except Exception as e:
                                logger.warning(f"Failed to send Telegram notification for SELL: {e}")
                        else:
                            logger.warning("Sell signal but order execution returned None")
                    else:
                        logger.error(
                            "Sell signal but SOL balance is 0 - "
                            "possible desync of holding flag"
                        )
                        # Reset state
                        holding = False
                        buy_price = 0.0
                        peak_price = 0.0
                        state["holding"] = holding
                        state["buy_price"] = buy_price
                        state["peak_price"] = peak_price
                        save_state(state)
            
            # Watchdog check
            current_time = time.time()
            minutes_inactive = (current_time - last_activity_ts) / 60.0
            
            if minutes_inactive >= WATCHDOG_MINUTES and not watchdog_alert_sent:
                try:
                    msg = (
                        f"⏰ WATCHDOG: no activity for {int(minutes_inactive)} minutes. "
                        f"Please check the bot / connection."
                    )
                    send_telegram_message(msg)
                    watchdog_alert_sent = True
                    logger.warning(f"Watchdog alert sent: {int(minutes_inactive)} minutes of inactivity")
                except Exception as e:
                    logger.warning(f"Failed to send watchdog Telegram notification: {e}")
            
            # Sleep before next iteration
            time.sleep(LOOP_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            traceback.print_exc()
            
            # Telegram notification for critical errors
            try:
                exception_message = str(e)
                msg = f"⚠️ ERROR in SolSpotBot\n{exception_message}"
                send_telegram_message(msg)
            except Exception as telegram_error:
                logger.warning(f"Failed to send error Telegram notification: {telegram_error}")
            
            logger.info(f"Waiting {LOOP_INTERVAL}s before retry...")
            time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    try:
        main_loop()
    except Exception as e:
        logger.critical(f"Fatal error in main: {e}")
        traceback.print_exc()
        
        # Telegram notification for fatal errors
        try:
            exception_message = str(e)
            msg = f"⚠️ ERROR in SolSpotBot\n{exception_message}"
            send_telegram_message(msg)
        except Exception as telegram_error:
            logger.warning(f"Failed to send fatal error Telegram notification: {telegram_error}")
        
        raise
