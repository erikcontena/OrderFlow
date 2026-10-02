"""
In-Memory Limit Order Book (LOB) Manager.
Maintains high-performance bid and ask books with price level sorting,
fast depth queries, mid-price calculation, and weighted spread analysis.
"""
from typing import Dict, List, Tuple
import time
import heapq

class LimitOrderBook:
    def __init__(self, venue: str, symbol: str):
        self.venue = venue
        self.symbol = symbol
        # Prices stored as floats, quantities as floats
        self.bids: Dict[float, float] = {}  # price -> qty
        self.asks: Dict[float, float] = {}  # price -> qty
        self.last_update_id: int = 0
        self.last_timestamp: float = time.time()
        self.is_synced: bool = False

    def clear(self):
        self.bids.clear()
        self.asks.clear()
        self.last_update_id = 0
        self.is_synced = False

    def set_snapshot(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]], update_id: int = 0):
        self.bids = {float(p): float(q) for p, q in bids if float(q) > 0}
        self.asks = {float(p): float(q) for p, q in asks if float(q) > 0}
        self.last_update_id = update_id
        self.last_timestamp = time.time()
        self.is_synced = True

    def apply_delta(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]], update_id: int = 0):
        """Apply incremental order book update. qty=0 means remove price level."""
        for price, qty in bids:
            p = float(price)
            q = float(qty)
            if q <= 0:
                self.bids.pop(p, None)
            else:
                self.bids[p] = q
        for price, qty in asks:
            p = float(price)
            q = float(qty)
            if q <= 0:
                self.asks.pop(p, None)
            else:
                self.asks[p] = q
        self.last_update_id = update_id
        self.last_timestamp = time.time()

    def update_bid(self, price: float, qty: float):
        if qty <= 0:
            self.bids.pop(price, None)
        else:
            self.bids[price] = qty
        self.last_timestamp = time.time()

    def update_ask(self, price: float, qty: float):
        if qty <= 0:
            self.asks.pop(price, None)
        else:
            self.asks[price] = qty
        self.last_timestamp = time.time()

    def get_top_bids(self, depth: int = 15) -> List[Tuple[float, float]]:
        # O(N log k) top bid extraction using heapq.nlargest
        top_prices = heapq.nlargest(depth, self.bids.keys())
        return [(p, self.bids[p]) for p in top_prices]

    def get_top_asks(self, depth: int = 15) -> List[Tuple[float, float]]:
        # O(N log k) top ask extraction using heapq.nsmallest
        top_prices = heapq.nsmallest(depth, self.asks.keys())
        return [(p, self.asks[p]) for p in top_prices]

    def get_best_bid(self) -> Tuple[float, float]:
        if not self.bids:
            return 0.0, 0.0
        best_p = max(self.bids.keys())
        return best_p, self.bids[best_p]

    def get_best_ask(self) -> Tuple[float, float]:
        if not self.asks:
            return 0.0, 0.0
        best_p = min(self.asks.keys())
        return best_p, self.asks[best_p]

    def get_mid_price(self) -> float:
        best_b, _ = self.get_best_bid()
        best_a, _ = self.get_best_ask()
        if best_b > 0 and best_a > 0:
            return (best_b + best_a) / 2.0
        return best_b or best_a or 0.0

    def get_microprice(self) -> float:
        """Volume-weighted mid price at top of book."""
        best_b, q_b = self.get_best_bid()
        best_a, q_a = self.get_best_ask()
        total_q = q_b + q_a
        if total_q > 0:
            return (best_b * q_a + best_a * q_b) / total_q
        return self.get_mid_price()

    def to_dict(self, depth: int = 10) -> dict:
        bids = self.get_top_bids(depth)
        asks = self.get_top_asks(depth)
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 0.0
        spread = best_ask - best_bid if best_ask > best_bid else 0.0
        return {
            "venue": self.venue,
            "symbol": self.symbol,
            "is_synced": self.is_synced,
            "last_update_id": self.last_update_id,
            "timestamp": self.last_timestamp,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": self.get_mid_price(),
            "spread": spread,
            "spread_bps": (spread / best_bid * 10000) if best_bid > 0 else 0.0,
            "bids": bids,
            "asks": asks,
        }
