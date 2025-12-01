"""
Trading strategy logic: buy and sell conditions
"""
import logging
from typing import List, Tuple, Optional
from config import MAX_LOSS_PERCENT

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
    Scalp strategy: Entry based on 2-candle OR 4-candle momentum with filters.
    
    Returns True ONLY if:
    - At least one momentum condition is satisfied (two-candle OR four-candle)
    AND
    - All four filters are satisfied (volatility, volume, distance-from-high, synthetic M5 trend)
    
    Args:
        candles: List of klines
    
    Returns:
        True if buy conditions are met
    """
    try:
        # ============================================
        # FILTER A: Volatility Filter (first gate)
        # ============================================
        if len(candles) < 3:
            return False
        
        # Check last 3 candles for volatility
        for i in range(-3, 0):  # Last 3 candles
            candle = candles[i]
            c_open = float(candle[1])
            c_high = float(candle[2])
            c_low = float(candle[3])
            vol = (c_high - c_low) / c_open * 100.0
            
            if vol > 0.6:
                logger.debug(f"Volatility filter failed: candle {i} has vol={vol:.4f}% > 0.6%")
                return False
        
        # ============================================
        # FILTER B: Volume Filter (second gate)
        # ============================================
        if len(candles) >= 20:
            # Calculate average volume of last 20 candles
            volumes = [float(candle[5]) for candle in candles[-20:]]
            average_volume = sum(volumes) / len(volumes)
            
            # Get last candle volume
            last_volume = float(candles[-1][5])
            
            if last_volume < average_volume:
                logger.debug(f"Volume filter failed: last_volume={last_volume:.2f} < average={average_volume:.2f}")
                return False
        
        # ============================================
        # FILTER C: Distance-from-local-high Filter (third gate)
        # ============================================
        if len(candles) >= 20:
            # Get last 20 candles
            last_20_candles = candles[-20:]
            
            # Find highest high
            highest_high = max(float(c[2]) for c in last_20_candles)
            
            # Get last close
            last_close = float(candles[-1][4])
            
            # Calculate distance from high
            distance_from_high = (highest_high - last_close) / last_close * 100.0
            
            if distance_from_high <= 0.25:
                logger.debug(f"Distance-from-high filter failed: distance={distance_from_high:.4f}% <= 0.25%")
                return False
        
        # ============================================
        # FILTER D: Higher Timeframe Trend Filter (synthetic M5, gate 4)
        # ============================================
        if len(candles) >= 5:
            # Take last 5 candles to form synthetic M5
            m5_open = float(candles[-5][1])   # open of first candle in 5-candle block
            m5_close = float(candles[-1][4])  # close of last candle in 5-candle block
            
            if m5_close <= m5_open:
                logger.debug(f"Synthetic M5 trend filter failed: m5_close={m5_close:.4f} <= m5_open={m5_open:.4f}")
                return False
        
        # ============================================
        # MOMENTUM CONDITIONS (after all filters pass)
        # ============================================
        
        # Two-candle momentum condition
        if len(candles) >= 3:
            r1, r2 = calculate_candle_changes(candles)
            
            if r1 >= 0.20 and r2 >= 0.30:
                logger.info(f"BUY SIGNAL (TWO-CANDLE): r1={r1:.4f}%, r2={r2:.4f}%, combined={r1+r2:.4f}%")
                return True
        
        # Four-candle momentum condition
        if len(candles) >= 4:
            changes, is_red = calculate_four_candle_analysis(candles)
            
            total_gain = sum(changes)
            last_not_red = not is_red[3]  # Last candle (index 3) must NOT be red
            
            if total_gain >= 0.8 and last_not_red:
                logger.info(
                    f"BUY SIGNAL (FOUR-CANDLE): changes={[f'{c:.4f}%' for c in changes]}, "
                    f"total_gain={total_gain:.4f}%"
                )
                return True
        
        # Both momentum conditions failed
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

