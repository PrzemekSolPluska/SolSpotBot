import time
from typing import Tuple, List

from config import SYMBOL, TIMEFRAME


def log(msg: str) -> None:
now = time.strftime("%Y-%m-%d %H:%M:%S")
print(f"[{now}] {msg}", flush=True)


def get_free_balance(exchange, asset: str) -> float:
balance = exchange.fetch_balance()
return float(balance.get(asset, {}).get("free", 0.0))


def fetch_last_3_candles(exchange) -> List[list]:
"""
Pobiera 3 ostatnie ZAMKNIĘTE świece dla SYMBOL/TIMEFRAME.
Zwraca listę [ [ts, o, h, l, c, v], ... ]
"""
ohlcv = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=3)
if len(ohlcv) < 3:
raise RuntimeError("Za mało świec z giełdy (mniej niż 3).")
return ohlcv


def calc_moves(candles: List[list]) -> Tuple[float, float]:
"""
candles: 3 świece: [prev, c1, c2]
Zwraca (move1, move2) w procentach:
move1 = zmiana z prev.close -> c1.close
move2 = zmiana z c1.close -> c2.close
"""
prev_c = candles[0][4]
c1 = candles[1][4]
c2 = candles[2][4]

move1 = (c1 - prev_c) / prev_c * 100.0
move2 = (c2 - c1) / c1 * 100.0
return move1, move2