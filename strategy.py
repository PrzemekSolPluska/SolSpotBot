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


def calculate_four_candle_analysis(candles: List[List]) -> Tuple[List[float], List[bool]]:
    """
    Analyze four consecutive candles to determine which are red and their individual changes
    
    Args:
        candles: List of klines, where each kline is [open_time, open, high, low, close, volume, ...]
                 Must have at least 4 candles: [c0, c1, c2, c3]
    
    Returns:
        Tuple (changes, is_red) where:
        - changes: List of % change for each candle [ch0, ch1, ch2, ch3]
        - is_red: List of bool indicating if each candle is red (close < open)
    """
    if len(candles) < 4:
        raise ValueError("Need at least 4 candles to calculate four-candle analysis")
    
    changes = []
    is_red = []
    
    for i in range(4):
        candle_open = float(candles[i][1])
        candle_close = float(candles[i][4])
        
        # Calculate % change for this candle
        change = (candle_close - candle_open) / candle_open * 100.0
        changes.append(change)
        
        # Check if candle is red (close < open)
        is_red.append(candle_close < candle_open)
    
    return changes, is_red


def should_buy(candles: List[List]) -> bool:
    """
    Determine if buy conditions are met
    
    Original conditions (all must be true):
    1. Both candles must be green: r1 > 0 and r2 > 0
    2. Combined strength >= 0.7%: r1 + r2 >= 0.7
    3. Momentum increases: r2 >= r1
    4. Second candle strong enough: r2 >= 0.35
    
    New condition A:
    - Last two candles combined >= 0.5% AND second candle >= 0.25%
    
    New condition B:
    - Within four consecutive candles, one (not the last) is red, and total gain of others >= 0.7%
    
    Args:
        candles: List of klines (need at least 3 for original, 4 for condition B)
    
    Returns:
        True if any buy condition is met
    """
    try:
        # Original condition: Check if we have at least 3 candles
        if len(candles) >= 3:
            r1, r2 = calculate_candle_changes(candles)
            
            logger.debug(f"Candle analysis: r1={r1:.4f}%, r2={r2:.4f}%")
            
            # Original condition: All 4 original conditions must be true
            original_condition = (
                r1 > 0 and r2 > 0 and  # Both green
                (r1 + r2) >= ENTRY_TOTAL_MOVE and  # Combined >= 0.7%
                r2 >= r1 and  # Momentum increases
                r2 >= ENTRY_MIN_SECOND  # Second candle >= 0.35%
            )
            
            if original_condition:
                logger.info(f"BUY SIGNAL (Original): r1={r1:.4f}%, r2={r2:.4f}%, combined={r1+r2:.4f}%")
                return True
            
            # New condition A: Last two candles combined >= 0.5% AND second candle >= 0.25%
            condition_a = (r1 + r2) >= 0.5 and r2 >= 0.25
            
            if condition_a:
                logger.info(f"BUY SIGNAL (Condition A): r1={r1:.4f}%, r2={r2:.4f}%, combined={r1+r2:.4f}%")
                return True
        
        # New condition B: Within four consecutive candles, one (not the last) is red, 
        # and total gain of others >= 0.7%
        if len(candles) >= 4:
            changes, is_red = calculate_four_candle_analysis(candles)
            
            logger.debug(f"Four-candle analysis: changes={[f'{c:.4f}%' for c in changes]}, is_red={is_red}")
            
            # Check if any of the first 3 candles (not the last one) is red
            for i in range(3):  # Check positions 0, 1, 2 (not 3, which is the last)
                if is_red[i]:
                    # Calculate total gain of the other candles (exclude the red one)
                    total_gain = sum(changes[j] for j in range(4) if j != i)
                    
                    if total_gain >= 0.7:
                        logger.info(
                            f"BUY SIGNAL (Condition B - red at pos {i}): "
                            f"changes={[f'{c:.4f}%' for c in changes]}, "
                            f"total_gain={total_gain:.4f}%"
                        )
                        return True
        
        return False
        
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
    
    # Hard stop-loss: -0.5% loss
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

