"""
Trading strategy logic: buy and sell conditions
"""
import logging
from typing import List, Tuple, Optional
from config import (
    ENTRY_TOTAL_MOVE,
    ENTRY_MIN_SECOND,
    TRAILING_SHARE,
    MAX_LOSS_PERCENT
)

logger = logging.getLogger(__name__)


def calculate_candle_changes(candles: List[List]) -> Tuple[float, float]:
    """
    Calculate percentage changes for two most recent closed candles
    
    Args:
        candles: List of klines, where each kline is [open_time, open, high, low, close, volume, ...]
                 Must have at least 3 candles: [prev, r1, r2]
    
    Returns:
        Tuple (r1, r2) where:
        - r1 = % change of previous closed candle
        - r2 = % change of most recent closed candle
    """
    if len(candles) < 3:
        raise ValueError("Need at least 3 candles to calculate changes")
    
    # Get closes: prev_close, r1_close, r2_close
    prev_close = float(candles[0][4])  # Previous candle close
    r1_close = float(candles[1][4])     # First candle close
    r2_close = float(candles[2][4])     # Second (most recent) candle close
    
    # Calculate percentage changes
    # r1 = change from prev_close to r1_close
    r1 = (r1_close - prev_close) / prev_close * 100.0
    
    # r2 = change from r1_close to r2_close
    r2 = (r2_close - r1_close) / r1_close * 100.0
    
    return r1, r2


def should_buy(candles: List[List]) -> bool:
    """
    Determine if buy conditions are met
    
    Conditions (all must be true):
    1. Both candles must be green: r1 > 0 and r2 > 0
    2. Combined strength >= 0.7%: r1 + r2 >= 0.7
    3. Momentum increases: r2 >= r1
    4. Second candle strong enough: r2 >= 0.35
    
    Args:
        candles: List of klines (need at least 3)
    
    Returns:
        True if all buy conditions are met
    """
    try:
        r1, r2 = calculate_candle_changes(candles)
        
        logger.debug(f"Candle analysis: r1={r1:.4f}%, r2={r2:.4f}%")
        
        # Condition 1: Both candles must be green
        if r1 <= 0 or r2 <= 0:
            logger.debug("Buy condition failed: Not both candles green")
            return False
        
        # Condition 2: Combined strength >= 0.7%
        if (r1 + r2) < ENTRY_TOTAL_MOVE:
            logger.debug(f"Buy condition failed: Combined strength {r1 + r2:.4f}% < {ENTRY_TOTAL_MOVE}%")
            return False
        
        # Condition 3: Momentum must increase (r2 >= r1)
        if r2 < r1:
            logger.debug(f"Buy condition failed: Momentum not increasing (r2={r2:.4f}% < r1={r1:.4f}%)")
            return False
        
        # Condition 4: Second candle must be strong enough
        if r2 < ENTRY_MIN_SECOND:
            logger.debug(f"Buy condition failed: Second candle {r2:.4f}% < {ENTRY_MIN_SECOND}%")
            return False
        
        logger.info(f"BUY SIGNAL: r1={r1:.4f}%, r2={r2:.4f}%, combined={r1+r2:.4f}%")
        return True
        
    except Exception as e:
        logger.error(f"Error in should_buy: {e}")
        return False


def should_sell(
    current_price: float,
    buy_price: float,
    peak_price: float
) -> Tuple[bool, str]:
    """
    Determine if sell conditions are met (trailing stop or hard stop-loss)
    
    Args:
        current_price: Current market price
        buy_price: Price at which we bought
        peak_price: Highest price reached since buy
    
    Returns:
        Tuple (should_sell, reason) where:
        - should_sell: True if we should sell
        - reason: "TRAILING_STOP" or "STOP_LOSS"
    """
    if buy_price <= 0:
        return False, ""
    
    # Calculate profits
    profit_peak = (peak_price - buy_price) / buy_price
    profit_now = (current_price - buy_price) / buy_price
    
    logger.debug(
        f"Price check: current={current_price:.4f}, buy={buy_price:.4f}, "
        f"peak={peak_price:.4f}, profit_now={profit_now*100:.2f}%, "
        f"profit_peak={profit_peak*100:.2f}%"
    )
    
    # Hard stop-loss: -1% loss
    if profit_now <= -MAX_LOSS_PERCENT:
        logger.warning(
            f"STOP LOSS triggered: profit_now={profit_now*100:.2f}% <= -{MAX_LOSS_PERCENT*100}%"
        )
        return True, "STOP_LOSS"
    
    # Trailing stop: if we've had profit, check if we've given back 20% of it
    if profit_peak > 0:
        min_allowed_profit = profit_peak * (1 - TRAILING_SHARE)
        
        if profit_now <= min_allowed_profit:
            logger.warning(
                f"TRAILING STOP triggered: profit_now={profit_now*100:.2f}% <= "
                f"min_allowed={min_allowed_profit*100:.2f}% "
                f"(peak_profit={profit_peak*100:.2f}%, trailing={TRAILING_SHARE*100}%)"
            )
            return True, "TRAILING_STOP"
    
    return False, ""

