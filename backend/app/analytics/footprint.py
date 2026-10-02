"""
Footprint Chart & Cumulative Volume Delta (CVD) Aggregator.
Slices sub-second aggressor trades into footprint bars with price-level bid/ask volume distribution,
delta calculation, and CVD divergence indicators.
"""
from typing import Dict, List, Optional
from collections import deque
import time

class FootprintBar:
    def __init__(self, bar_id: int, start_time: float, timeframe_seconds: float = 5.0):
        self.bar_id = bar_id
        self.start_time = start_time
        self.timeframe_seconds = timeframe_seconds
        
        self.open: float = 0.0
        self.high: float = 0.0
        self.low: float = 0.0
        self.close: float = 0.0
        self.volume: float = 0.0
        
        # Price -> {"buy_vol": float, "sell_vol": float, "delta": float}
        self.levels: Dict[float, Dict[str, float]] = {}
        
        self.total_buy_vol: float = 0.0
        self.total_sell_vol: float = 0.0
        self.delta: float = 0.0
        self.is_closed: bool = False

    def add_trade(self, price: float, qty: float, is_buyer_maker: bool):
        """
        In Binance / crypto semantics:
        is_buyer_maker == True -> The maker was buyer, so the aggressor (taker) was a SELLER.
        is_buyer_maker == False -> Aggressor was a BUYER.
        """
        is_taker_buy = not is_buyer_maker
        
        if self.open == 0.0:
            self.open = price
            self.high = price
            self.low = price
        else:
            if price > self.high:
                self.high = price
            if price < self.low:
                self.low = price
        self.close = price
        self.volume += qty

        # Group by rounded tick price (e.g. 0.5 or 1.0 dollar resolution for BTC)
        price_tick = round(price, 1)
        if price_tick not in self.levels:
            self.levels[price_tick] = {"buy_vol": 0.0, "sell_vol": 0.0, "delta": 0.0}

        if is_taker_buy:
            self.levels[price_tick]["buy_vol"] += qty
            self.total_buy_vol += qty
        else:
            self.levels[price_tick]["sell_vol"] += qty
            self.total_sell_vol += qty

        self.levels[price_tick]["delta"] = (
            self.levels[price_tick]["buy_vol"] - self.levels[price_tick]["sell_vol"]
        )
        self.delta = self.total_buy_vol - self.total_sell_vol

    def to_dict(self) -> dict:
        sorted_keys = sorted(self.levels.keys(), reverse=True)
        # Cap to 40 most relevant levels around bar to minimize serialization overhead
        if len(sorted_keys) > 40:
            sorted_keys = sorted_keys[:40]
            
        sorted_levels = [
            {
                "price": p,
                "buy_vol": round(self.levels[p]["buy_vol"], 4),
                "sell_vol": round(self.levels[p]["sell_vol"], 4),
                "delta": round(self.levels[p]["delta"], 4),
            }
            for p in sorted_keys
        ]
        return {
            "bar_id": self.bar_id,
            "start_time": self.start_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": round(self.volume, 4),
            "total_buy_vol": round(self.total_buy_vol, 4),
            "total_sell_vol": round(self.total_sell_vol, 4),
            "delta": round(self.delta, 4),
            "levels": sorted_levels,
            "is_closed": self.is_closed,
        }


class FootprintAggregator:
    def __init__(self, timeframe_seconds: float = 5.0, max_bars: int = 50):
        self.timeframe_seconds = timeframe_seconds
        self.max_bars = max_bars
        self.bars: Deque[FootprintBar] = deque(maxlen=max_bars)
        
        self.current_bar: Optional[FootprintBar] = None
        self.bar_counter: int = 0
        self.cvd: float = 0.0
        self.cvd_history: Deque[dict] = deque(maxlen=200)

    def process_trade(self, price: float, qty: float, is_buyer_maker: bool):
        now = time.time()
        
        # Check if new bar should be formed
        if not self.current_bar or (now - self.current_bar.start_time >= self.timeframe_seconds):
            if self.current_bar:
                self.current_bar.is_closed = True
                self.bars.append(self.current_bar)
            self.bar_counter += 1
            self.current_bar = FootprintBar(self.bar_counter, now, self.timeframe_seconds)

        self.current_bar.add_trade(price, qty, is_buyer_maker)
        
        # Update CVD
        trade_delta = qty if not is_buyer_maker else -qty
        self.cvd += trade_delta
        self.cvd_history.append({
            "timestamp": now,
            "price": price,
            "cvd": round(self.cvd, 4),
            "delta": round(trade_delta, 4)
        })

    def get_recent_bars(self, count: int = 15) -> List[dict]:
        all_bars = list(self.bars)
        if self.current_bar:
            all_bars.append(self.current_bar)
        return [b.to_dict() for b in all_bars[-count:]]

    def get_cvd_summary(self) -> dict:
        return {
            "cvd": round(self.cvd, 4),
            "points": list(self.cvd_history)[-50:]
        }
