"""
Trading strategy logic: buy and sell conditions
"""
import logging
from typing import List, Tuple, Optional
from config import MAX_LOSS_PERCENT

logger = logging.getLogger(__name__)

# Breakout → Retest scalping strategy constants
CONSOLIDATION_LEN = 6
MAX_CONS_RANGE_PER_CANDLE = 0.35
MAX_CONS_TOTAL_RANGE = 0.7
MIN_BREAKOUT_BODY = 0.45
MIN_RETRACE_FRACTION = 0.30
MAX_RETRACE_FRACTION = 0.70


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
    Dynamic Breakout → Retest scalping strategy.
    
    1. Detect a consolidation zone (tight range, last 6 candles).
    2. Detect a strong breakout candle piercing the consolidation.
    3. Enter on a retest if the pullback fits retracement criteria.
    
    Args:
        candles: List of klines
    
    Returns:
        True if buy conditions are met
    """
    if len(candles) < CONSOLIDATION_LEN + 2:
        return False
    
    recent = candles[-(CONSOLIDATION_LEN + 2):]
    
    cons = recent[:-2]
    breakout = recent[-2]
    retest = recent[-1]
    
    cons_high = max(float(c[2]) for c in cons)
    cons_low = min(float(c[3]) for c in cons)
    
    total_cons_range = (cons_high - cons_low) / cons_low * 100.0
    if total_cons_range > MAX_CONS_TOTAL_RANGE:
        return False
    
    for c in cons:
        rng = (float(c[2]) - float(c[3])) / float(c[3]) * 100.0
        if rng > MAX_CONS_RANGE_PER_CANDLE:
            return False
    
    breakout_open = float(breakout[1])
    breakout_close = float(breakout[4])
    breakout_body = (breakout_close - breakout_open) / breakout_open * 100.0
    
    if breakout_close <= cons_high:
        return False
    if breakout_body < MIN_BREAKOUT_BODY:
        return False
    
    retest_low = float(retest[3])
    pullback = cons_high - retest_low
    full_break = breakout_close - cons_high
    
    if full_break <= 0:
        return False
    
    retrace_fraction = pullback / full_break
    
    if retrace_fraction < MIN_RETRACE_FRACTION:
        return False
    if retrace_fraction > MAX_RETRACE_FRACTION:
        return False
    
    if float(retest[4]) <= float(retest[1]):
        return False
    
    logger.info(
        f"BUY SIGNAL (BREAKOUT-RETEST): "
        f"cons_range={total_cons_range:.4f}%, "
        f"breakout_body={breakout_body:.4f}%, "
        f"retrace_fraction={retrace_fraction:.4f}"
    )
    return True


def should_sell(
    current_price: float,
    buy_price: float,
    peak_price: float
) -> Tuple[bool, str]:
    """
    Scalp strategy: Exit with hard stop-loss at -0.4% or trailing TP at 0.2% drop from peak.
    
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
    profit_now = (current_price - buy_price) / buy_price
    profit_peak = (peak_price - buy_price) / buy_price
    
    logger.debug(
        f"Price check: current={current_price:.4f}, buy={buy_price:.4f}, "
        f"peak={peak_price:.4f}, profit_now={profit_now*100:.2f}%, "
        f"profit_peak={profit_peak*100:.2f}%"
    )
    
    # Hard stop-loss: -0.4% loss
    if profit_now <= -MAX_LOSS_PERCENT:
        logger.warning(
            f"STOP LOSS triggered: profit_now={profit_now*100:.2f}% <= -{MAX_LOSS_PERCENT*100}%"
        )
        return True, "STOP_LOSS"
    
    # Trailing TP: price drop of 0.20% from peak
    if peak_price > buy_price:
        drawdown_from_peak = (peak_price - current_price) / peak_price
        
        if drawdown_from_peak >= 0.002:  # 0.20%
            logger.warning(
                f"TRAILING STOP triggered: drawdown_from_peak={drawdown_from_peak*100:.2f}%, "
                f"peak_price={peak_price:.4f}, current_price={current_price:.4f}"
            )
            return True, "TRAILING_STOP"
    
    return False, ""

