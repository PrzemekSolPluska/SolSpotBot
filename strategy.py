"""
Trading strategy logic: buy and sell conditions
"""
import logging
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


def calculate_candle_changes(candles: List[List]) -> Tuple[float, float]:
    """
    Calculate percentage changes for last 2 closed candles (for display/logging purposes)
    
    Args:
        candles: List of klines, must have at least 2 candles
    
    Returns:
        Tuple (change1, change2) where:
        - change1 = % change of second last candle (open to close)
        - change2 = % change of last candle (open to close)
    """
    if len(candles) < 2:
        return 0.0, 0.0
    
    c1 = candles[-2]
    c2 = candles[-1]
    
    change1 = (float(c1[4]) - float(c1[1])) / float(c1[1]) * 100.0
    change2 = (float(c2[4]) - float(c2[1])) / float(c2[1]) * 100.0
    
    return change1, change2


def check_two_candle_strategy(candles: List[List]) -> bool:
    """
    Strategy A: Check last 2 closed candles for entry signal
    
    Conditions:
    1. Both candles are green (change > 0)
    2. Second candle is at least +0.20%
    3. Sum of both candles is at least +0.35%
    
    Args:
        candles: List of klines (must have at least 2 candles)
    
    Returns:
        True if Strategy A conditions are met
    """
    if len(candles) < 2:
        return False
    
    # Get last 2 closed candles
    c1 = candles[-2]  # Second last closed candle
    c2 = candles[-1]  # Last closed candle
    
    # Calculate % change from open to close for each candle
    c1_open = float(c1[1])
    c1_close = float(c1[4])
    change1 = (c1_close - c1_open) / c1_open * 100.0
    
    c2_open = float(c2[1])
    c2_close = float(c2[4])
    change2 = (c2_close - c2_open) / c2_open * 100.0
    
    # Condition 1: Both candles are green
    if change1 <= 0 or change2 <= 0:
        return False
    
    # Condition 2: Second candle is at least +0.20%
    if change2 < 0.20:
        return False
    
    # Condition 3: Sum of both candles is at least +0.35%
    if (change1 + change2) < 0.35:
        return False
    
    return True


def check_four_candle_strategy(candles: List[List]) -> bool:
    """
    Strategy B: Check last 4 closed candles for entry signal
    
    Conditions:
    1. Total change of 4 candles is at least +0.70%
    2. At most ONE candle is red
    3. Last two candles cannot both be red
    
    Args:
        candles: List of klines (must have at least 4 candles)
    
    Returns:
        True if Strategy B conditions are met
    """
    if len(candles) < 4:
        return False
    
    # Get last 4 closed candles: d0, d1, d2, d3 (d3 is most recent)
    d0 = candles[-4]
    d1 = candles[-3]
    d2 = candles[-2]
    d3 = candles[-1]
    
    # Calculate % change from open to close for each candle
    ch0 = (float(d0[4]) - float(d0[1])) / float(d0[1]) * 100.0
    ch1 = (float(d1[4]) - float(d1[1])) / float(d1[1]) * 100.0
    ch2 = (float(d2[4]) - float(d2[1])) / float(d2[1]) * 100.0
    ch3 = (float(d3[4]) - float(d3[1])) / float(d3[1]) * 100.0
    
    # Check which candles are red (close < open)
    is_red_d0 = float(d0[4]) < float(d0[1])
    is_red_d1 = float(d1[4]) < float(d1[1])
    is_red_d2 = float(d2[4]) < float(d2[1])
    is_red_d3 = float(d3[4]) < float(d3[1])
    
    # Count red candles
    red_count = sum([is_red_d0, is_red_d1, is_red_d2, is_red_d3])
    
    # Calculate total change
    total_change = ch0 + ch1 + ch2 + ch3
    
    # Condition 1: Total change is at least +0.70%
    if total_change < 0.70:
        return False
    
    # Condition 2: At most ONE candle is red
    if red_count > 1:
        return False
    
    # Condition 3: Last two candles cannot both be red
    if is_red_d2 and is_red_d3:
        return False
    
    return True


def should_buy(candles: List[List]) -> bool:
    """
    Entry logic with two independent strategies (A or B).
    
    Strategy A: Last 2 candles - both green, second >= 0.20%, sum >= 0.35%
    Strategy B: Last 4 candles - total >= 0.70%, at most 1 red, last two not both red
    
    Args:
        candles: List of klines (1-minute candles)
    
    Returns:
        True if Strategy A OR Strategy B conditions are met
    """
    # Need at least 4 closed candles to check both strategies
    if len(candles) < 4:
        return False
    
    # Check Strategy A (last 2 candles)
    strategy_a = check_two_candle_strategy(candles)
    
    # Check Strategy B (last 4 candles)
    strategy_b = check_four_candle_strategy(candles)
    
    if strategy_a:
        logger.info("BUY SIGNAL (Strategy A - 2 candles): Both green, second >= 0.20%, sum >= 0.35%")
        return True
    
    if strategy_b:
        logger.info("BUY SIGNAL (Strategy B - 4 candles): Total >= 0.70%, at most 1 red, last two not both red")
        return True
    
    return False


def should_sell(
    current_price: float,
    buy_price: float,
    peak_price: float
) -> Tuple[bool, str]:
    """
    Exit logic with hard stop-loss at -0.5% and 20% trailing take profit.
    
    Args:
        current_price: Current market price
        buy_price: Price at which we bought
        peak_price: Highest price reached since buy
    
    Returns:
        Tuple (should_sell, reason) where:
        - should_sell: True if we should sell
        - reason: "STOP_LOSS" or "TRAILING_TP"
    """
    # Step 1: Check if buy_price is valid
    if buy_price <= 0:
        return False, ""
    
    # Step 2: Compute current and peak profit (fractions, not percents)
    profit_now = (current_price - buy_price) / buy_price
    profit_peak = (peak_price - buy_price) / buy_price
    
    logger.debug(
        f"Price check: current={current_price:.4f}, buy={buy_price:.4f}, "
        f"peak={peak_price:.4f}, profit_now={profit_now*100:.2f}%, "
        f"profit_peak={profit_peak*100:.2f}%"
    )
    
    # Step 3: STOP LOSS at -0.5%
    if profit_now <= -0.005:  # -0.5%
        logger.warning(
            f"STOP LOSS triggered: profit_now={profit_now*100:.2f}% <= -0.5%"
        )
        return True, "STOP_LOSS"
    
    # Step 4: Trailing TAKE PROFIT (20% giveback from max profit)
    if profit_peak > 0:  # Only if we had some profit
        profit_drawdown = profit_peak - profit_now
        relative_drawdown = profit_drawdown / profit_peak
        
        if relative_drawdown >= 0.20:  # 20% giveback
            logger.warning(
                f"TRAILING_TP triggered: relative_drawdown={relative_drawdown*100:.2f}%, "
                f"profit_peak={profit_peak*100:.2f}%, profit_now={profit_now*100:.2f}%, "
                f"peak_price={peak_price:.4f}, current_price={current_price:.4f}"
            )
            return True, "TRAILING_TP"
    
    # Step 5: No exit condition met
    return False, ""

