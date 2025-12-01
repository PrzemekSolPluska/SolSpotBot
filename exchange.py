"""
Exchange wrapper for Binance Spot API using python-binance
"""
import time
import logging
import math
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


class Exchange:
    """Wrapper around python-binance Client for Spot trading"""
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Binance Spot client
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
        """
        self.client = Client(api_key, api_secret)
        # Test connection
        try:
            self.client.ping()
            logger.info("Connected to Binance Spot API")
        except Exception as e:
            logger.error(f"Failed to connect to Binance: {e}")
            raise
    
    def get_balance(self, asset: str) -> float:
        """
        Get free balance for an asset
        
        Args:
            asset: Asset symbol (e.g., 'USDC', 'SOL')
            
        Returns:
            Free balance as float
        """
        try:
            account = self.client.get_account()
            for balance in account['balances']:
                if balance['asset'] == asset:
                    return float(balance['free'])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"API error getting balance for {asset}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting balance: {e}")
            raise

    def get_free_balance(self, asset: str) -> float:
        """
        Get free balance of an asset (alias for get_balance for clarity)

        Args:
            asset: Asset symbol (e.g., 'USDC', 'SOL')

        Returns:
            Free balance as float
        """
        return self.get_balance(asset)

    def sanitize_quantity(self, symbol: str, qty: float) -> float:
        """
        Round DOWN quantity to Binance stepSize for the given symbol.

        For SOL/USDC the stepSize is 0.001, so we hardcode step = 0.001
        and always round down to 3 decimal places to avoid APIError
        (-1111) "quantity has too much precision".

        Args:
            symbol: Trading pair symbol (e.g., 'SOLUSDC'). Currently only
                    used for clarity; logic is hardcoded for SOLUSDC.
            qty:    Raw quantity to sanitize.

        Returns:
            Quantity rounded down to a Binance-compliant step.
        """
        if qty <= 0:
            return 0.0

        # Hardcode stepSize for SOL/USDC
        step = 0.001

        # Round DOWN to the nearest step
        stepped = math.floor(qty / step) * step

        # Limit to 3 decimals to match step precision
        sanitized = round(stepped, 3)

        if sanitized <= 0:
            logger.debug(f"sanitize_quantity({symbol}): qty={qty} -> sanitized={sanitized} (non-positive after rounding)")

        return sanitized
    
    def get_free_balance(self, asset: str) -> float:
        """
        Get free balance of an asset (alias for get_balance for clarity)
        
        Args:
            asset: Asset symbol (e.g., 'USDC', 'SOL')
            
        Returns:
            Free balance as float
        """
        return self.get_balance(asset)
    
    def get_klines(self, symbol: str, interval: str, limit: int = 3) -> List[List]:
        """
        Get klines (candles) for a symbol
        
        Args:
            symbol: Trading pair (e.g., 'SOLUSDC')
            interval: Timeframe (e.g., '3m')
            limit: Number of candles to retrieve
            
        Returns:
            List of klines: [[open_time, open, high, low, close, volume, ...], ...]
        """
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
                return klines
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', getattr(e, 'status_code', None))
                if error_code == -1003:  # Rate limit exceeded
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                logger.error(f"API error getting klines: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error getting klines: {e}")
                raise
        
        raise Exception("Failed to get klines after retries")
    
    def get_current_price(self, symbol: str) -> float:
        """
        Get current market price for a symbol
        
        Args:
            symbol: Trading pair (e.g., 'SOLUSDC')
            
        Returns:
            Current price as float
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            logger.error(f"API error getting price: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting price: {e}")
            raise
    
    def market_buy(self, symbol: str, quantity: float) -> Dict:
        """
        Execute market buy order
        
        Args:
            symbol: Trading pair (e.g., 'SOLUSDC')
            quantity: Quantity to buy (in base asset, e.g., SOL)
            
        Returns:
            Order result dictionary
        """
        max_retries = 3
        retry_delay = 2

        # Ensure quantity respects Binance step size (e.g., SOL/USDC step=0.001)
        quantity = self.sanitize_quantity(symbol, quantity)
        if quantity <= 0:
            raise ValueError(f"Sanitized BUY quantity is non-positive for {symbol}")
        
        for attempt in range(max_retries):
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity
                )
                logger.info(f"Market BUY executed: {order}")
                return order
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', getattr(e, 'status_code', None))
                if error_code == -1003:  # Rate limit exceeded
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                if error_code == -1013:  # Filter failure: MIN_NOTIONAL
                    logger.error(f"Order too small: {e}")
                    raise
                logger.error(f"API error in market buy: {e}")
                raise
            except BinanceOrderException as e:
                logger.error(f"Order error in market buy: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in market buy: {e}")
                raise
        
        raise Exception("Failed to execute market buy after retries")
    
    def market_sell(self, symbol: str, quantity: float) -> Dict:
        """
        Execute market sell order
        
        Args:
            symbol: Trading pair (e.g., 'SOLUSDC')
            quantity: Quantity to sell (in base asset, e.g., SOL)
            
        Returns:
            Order result dictionary
        """
        max_retries = 3
        retry_delay = 2

        # Ensure quantity respects Binance step size (e.g., SOL/USDC step=0.001)
        quantity = self.sanitize_quantity(symbol, quantity)
        if quantity <= 0:
            raise ValueError(f"Sanitized SELL quantity is non-positive for {symbol}")
        
        for attempt in range(max_retries):
            try:
                order = self.client.create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=quantity
                )
                logger.info(f"Market SELL executed: {order}")
                return order
            except BinanceAPIException as e:
                error_code = getattr(e, 'code', getattr(e, 'status_code', None))
                if error_code == -1003:  # Rate limit exceeded
                    wait_time = retry_delay * (attempt + 1)
                    logger.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
                    time.sleep(wait_time)
                    continue
                if error_code == -1013:  # Filter failure: MIN_NOTIONAL
                    logger.error(f"Order too small: {e}")
                    raise
                logger.error(f"API error in market sell: {e}")
                raise
            except BinanceOrderException as e:
                logger.error(f"Order error in market sell: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in market sell: {e}")
                raise
        
        raise Exception("Failed to execute market sell after retries")
    
    def market_buy_all_usdc(self, symbol: str) -> Optional[Dict]:
        """
        Market buy using 100% of USDC balance
        
        Args:
            symbol: Trading pair (e.g., 'SOLUSDC')
            
        Returns:
            Order result or None if insufficient balance
        """
        usdc_balance = self.get_balance("USDC")
        
        if usdc_balance <= 0:
            logger.warning("No USDC balance available for buy")
            return None
        
        # Use 99.95% to maximize position size while leaving small buffer for fees and rounding
        usdc_to_use = usdc_balance * 0.9995
        
        # Get symbol info for precision
        try:
            exchange_info = self.client.get_exchange_info()
            symbol_info = next(s for s in exchange_info['symbols'] if s['symbol'] == symbol)
            
            # Get quote precision (for USDC amount)
            quote_precision = None
            for filter_item in symbol_info['filters']:
                if filter_item['filterType'] == 'NOTIONAL':
                    min_notional = float(filter_item.get('minNotional', 0))
                    if min_notional > 0:
                        quote_precision = len(str(min_notional).split('.')[-1]) if '.' in str(min_notional) else 0
            
            # Round USDC amount to appropriate precision
            if quote_precision is not None:
                usdc_to_use = round(usdc_to_use, quote_precision)
            else:
                usdc_to_use = round(usdc_to_use, 2)  # Default to 2 decimal places
            
            if usdc_to_use <= 0:
                logger.warning(f"Insufficient balance: {usdc_balance:.2f} USDC")
                return None
            
            current_price = self.get_current_price(symbol)
            logger.info(f"Buying with {usdc_to_use:.2f} USDC ({usdc_to_use/usdc_balance*100:.2f}% of {usdc_balance:.2f} USDC balance) @ {current_price:.4f}")
            
            # Use quoteOrderQty for market buy (buy with USDC amount)
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    order = self.client.create_order(
                        symbol=symbol,
                        side='BUY',
                        type='MARKET',
                        quoteOrderQty=usdc_to_use
                    )
                    logger.info(f"Market BUY executed: {order}")
                    return order
                except BinanceAPIException as e:
                    error_code = getattr(e, 'code', getattr(e, 'status_code', None))
                    if error_code == -1003:  # Rate limit exceeded
                        wait_time = retry_delay * (attempt + 1)
                        logger.warning(f"Rate limit hit, waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        continue
                    if error_code == -1013:  # Filter failure: MIN_NOTIONAL
                        logger.error(f"Order too small: {e}")
                        raise
                    logger.error(f"API error in market buy: {e}")
                    raise
                except BinanceOrderException as e:
                    logger.error(f"Order error in market buy: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Unexpected error in market buy: {e}")
                    raise
            
            raise Exception("Failed to execute market buy after retries")
        except Exception as e:
            logger.error(f"Error in market_buy_all_usdc: {e}")
            raise
    
    def market_sell_all_sol(self, symbol: str) -> Optional[Dict]:
        """
        Market sell 100% of SOL balance
        
        Args:
            symbol: Trading pair (e.g., 'SOLUSDC')
            
        Returns:
            Order result or None if insufficient balance
        """
        sol_balance = self.get_balance("SOL")
        
        if sol_balance <= 0:
            logger.warning("No SOL balance available for sell")
            return None
        
        # Get symbol info for precision
        try:
            exchange_info = self.client.get_exchange_info()
            symbol_info = next(s for s in exchange_info['symbols'] if s['symbol'] == symbol)
            step_size = None
            for filter_item in symbol_info['filters']:
                if filter_item['filterType'] == 'LOT_SIZE':
                    step_size = float(filter_item['stepSize'])
                    break
            
            if step_size:
                # Round down to LOT_SIZE step first
                raw_qty = math.floor(sol_balance / step_size) * step_size
            else:
                raw_qty = sol_balance

            # Apply final sanitization to comply with step size (e.g., 0.001 for SOL/USDC)
            quantity = self.sanitize_quantity(symbol, raw_qty)
            
            if quantity <= 0:
                logger.warning(f"Insufficient balance: {sol_balance:.6f} SOL")
                return None
            
            current_price = self.get_current_price(symbol)
            logger.info(
                f"Selling {quantity:.6f} SOL ({(quantity/sol_balance*100.0):.2f}% of {sol_balance:.6f} SOL balance) "
                f"@ {current_price:.4f}"
            )
            return self.market_sell(symbol, quantity)
        except Exception as e:
            logger.error(f"Error in market_sell_all_sol: {e}")
            raise

