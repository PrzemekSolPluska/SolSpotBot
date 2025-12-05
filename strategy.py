"""
Trading strategy logic: buy and sell conditions
"""
import logging
from typing import List, Tuple, Optional
from config import MAX_LOSS_PERCENT

logger = logging.getLogger(__name__)

# Exit strategy constants
TRAILING_GIVEBACK_FRACTION = 0.20      # 20% giveback


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
    2. Sum of both candles is at least +0.25%
    
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
    
    # Condition 2: Sum of both candles is at least +0.25%
    if (change1 + change2) < 0.25:
        return False
    
    return True


def check_four_candle_strategy(candles: List[List]) -> bool:
    """
    Strategy B: Check last 4 closed candles for entry signal
    
    Conditions:
    1. Total change of 4 candles is at least +0.45%
    2. Last candle must NOT be red (close >= open)
    
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
    
    # Calculate total change
    total_change = ch0 + ch1 + ch2 + ch3
    
    # Condition 1: Total change is at least +0.45%
    if total_change < 0.45:
        return False
    
    # Condition 2: Last candle must NOT be red (close >= open)
    d3_open = float(d3[1])
    d3_close = float(d3[4])
    if d3_close < d3_open:
        return False
    
    return True


def should_buy(candles: List[List]) -> bool:
    """
    Entry logic with two independent strategies (A or B).
    
    Strategy A: Last 2 candles - both green, sum >= 0.25%
    Strategy B: Last 4 candles - total >= 0.45%, last candle not red
    
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
        logger.info("BUY SIGNAL (Strategy A - 2 candles): Both green, total move >= +0.25%")
        return True
    
    if strategy_b:
        logger.info("BUY SIGNAL (Strategy B - 4 candles): Sum >= +0.45%, last candle not red")
        return True
    
    return False


def should_sell(
    current_price: float,
    buy_price: float,
    peak_price: float
) -> Tuple[bool, str]:
    """
    Exit strategy:
    - Hard stop-loss at -MAX_LOSS_PERCENT (e.g. -0.10%).
    - Trailing take profit, always active once the trade is in profit:
      we track the maximum profit reached, and exit when the current profit
      has given back TRAILING_GIVEBACK_FRACTION (e.g. 20%) of that max profit,
      as long as we are still above 0% profit.
    """
    # If we don't have a valid buy price, we can't decide anything
    if buy_price <= 0:
        return False, ""

    # Profit as fractions of entry price
    profit_now = (current_price - buy_price) / buy_price
    profit_peak = (peak_price - buy_price) / buy_price

    logger.debug(
        f"Profit check: current_price={current_price:.4f}, buy_price={buy_price:.4f}, "
        f"peak_price={peak_price:.4f}, profit_now={profit_now*100:.4f}%, "
        f"profit_peak={profit_peak*100:.4f}%"
    )

    # 1) Hard stop-loss: e.g. -0.10% from entry
    if profit_now <= -MAX_LOSS_PERCENT:
        logger.warning(
            f"STOP LOSS triggered: profit_now={profit_now*100:.4f}% <= -{MAX_LOSS_PERCENT*100:.3f}%"
        )
        return True, "STOP_LOSS"

    # 2) Trailing take profit: always active once the trade is in profit
    #    We only apply trailing if:
    #    - we have seen some positive peak profit (profit_peak > 0)
    #    - we are still in profit now (profit_now > 0)
    if profit_peak > 0 and profit_now > 0:
        profit_drawdown = profit_peak - profit_now
        relative_drawdown = profit_drawdown / profit_peak

        logger.debug(
            f"Trailing check: profit_now={profit_now*100:.4f}%, "
            f"profit_peak={profit_peak*100:.4f}%, "
            f"profit_drawdown={profit_drawdown*100:.4f}%, "
            f"relative_drawdown={relative_drawdown*100:.4f}%"
        )

        # If we have given back 20% or more of the maximum profit, exit with TRAILING_TP
        if relative_drawdown >= TRAILING_GIVEBACK_FRACTION:
            logger.warning(
                f"TRAILING_TP triggered: relative_drawdown={relative_drawdown*100:.4f}% "
                f"(>= {TRAILING_GIVEBACK_FRACTION*100:.1f}%), "
                f"profit_now={profit_now*100:.4f}%, profit_peak={profit_peak*100:.4f}%"
            )
            return True, "TRAILING_TP"

    # 3) Otherwise, hold the position
    return False, ""

