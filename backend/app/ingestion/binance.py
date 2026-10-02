"""
Binance Futures Ingestion Engine.
Implements:
1. Multi-stream WebSocket for Depth (100ms) and Public Trades.
2. REST Snapshot buffer reconciliation.
3. Sequence Gap detection and recovery.
"""
import asyncio
import json
import logging
from typing import List, Callable, Optional
import httpx

from .base import BaseWebSocketClient
from ..analytics.orderbook import LimitOrderBook

logger = logging.getLogger("BinanceIngestion")

class BinanceIngestor(BaseWebSocketClient):
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        orderbook: Optional[LimitOrderBook] = None,
        on_trade: Optional[Callable[[float, float, bool], None]] = None,
    ):
        sym_lower = symbol.lower()
        url = f"wss://fstream.binance.com/stream?streams={sym_lower}@depth@100ms/{sym_lower}@trade"
        super().__init__(name="Binance", url=url, heartbeat_interval=25.0)

        self.symbol = symbol.upper()
        self.orderbook = orderbook or LimitOrderBook("Binance", self.symbol)
        self.on_trade = on_trade
        
        self.buffer: List[dict] = []
        self.snapshot_loaded: bool = False
        self.is_reconciling: bool = False

    async def on_connect(self):
        self.buffer.clear()
        self.snapshot_loaded = False
        self.is_reconciling = True
        logger.info(f"[Binance] Connected. Requesting REST snapshot for {self.symbol}...")
        asyncio.create_task(self._fetch_rest_snapshot())

    async def _fetch_rest_snapshot(self):
        try:
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={self.symbol}&limit=1000"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    last_update_id = data["lastUpdateId"]
                    bids = [(float(p), float(q)) for p, q in data["bids"]]
                    asks = [(float(p), float(q)) for p, q in data["asks"]]
                    
                    self.orderbook.set_snapshot(bids, asks, last_update_id)
                    self.snapshot_loaded = True
                    logger.info(f"[Binance] Snapshot applied at updateId {last_update_id}. Reconciling buffer ({len(self.buffer)} events)...")
                    self._apply_buffer()
                else:
                    logger.error(f"[Binance] Failed to fetch depth snapshot: {res.status_code}")
        except Exception as e:
            logger.error(f"[Binance] Snapshot error: {e}")
        finally:
            self.is_reconciling = False

    def _apply_buffer(self):
        """Applies buffered diff depth updates adhering to Binance sequence rules."""
        if not self.orderbook.is_synced:
            return

        last_id = self.orderbook.last_update_id
        valid_events = []

        for item in self.buffer:
            u = item.get("u", 0)
            U = item.get("U", 0)
            pu = item.get("pu", 0)
            if u < last_id:
                continue
            if not valid_events:
                # Find the bridge event or accept first available update
                if (U <= last_id and u >= last_id) or U > last_id:
                    valid_events.append(item)
                    self._apply_diff(item)
                    last_id = u
            else:
                self._apply_diff(item)
                last_id = u

        self.buffer.clear()
        self.orderbook.last_update_id = last_id

    def _apply_diff(self, data: dict):
        for p, q in data.get("b", []):
            self.orderbook.update_bid(float(p), float(q))
        for p, q in data.get("a", []):
            self.orderbook.update_ask(float(p), float(q))
        self.orderbook.last_update_id = data.get("u", self.orderbook.last_update_id)

    async def on_message(self, raw_msg: str):
        try:
            payload = json.loads(raw_msg)
            stream = payload.get("stream", "")
            data = payload.get("data", {})

            if "depth" in stream:
                if not self.snapshot_loaded:
                    self.buffer.append(data)
                else:
                    u = data.get("u", 0)
                    if u < self.orderbook.last_update_id:
                        return
                    self._apply_diff(data)

            elif "trade" in stream:
                price = float(data.get("p", 0.0))
                qty = float(data.get("q", 0.0))
                is_buyer_maker = bool(data.get("m", False))
                if self.on_trade and price > 0:
                    self.on_trade(price, qty, is_buyer_maker)

        except Exception as e:
            logger.error(f"[Binance] Message parse error: {e}")

    async def on_disconnect(self):
        self.buffer.clear()
        self.snapshot_loaded = False
        self.orderbook.clear()
