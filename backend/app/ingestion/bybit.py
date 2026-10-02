"""
Bybit V5 Linear Public Ingestion Engine.
Consumes orderbook snapshot followed by incremental delta streams and public trades.
"""
import json
import logging
from typing import Optional, Callable
from .base import BaseWebSocketClient
from ..analytics.orderbook import LimitOrderBook

logger = logging.getLogger("BybitIngestion")

class BybitIngestor(BaseWebSocketClient):
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        orderbook: Optional[LimitOrderBook] = None,
        on_trade: Optional[Callable[[float, float, bool], None]] = None,
    ):
        super().__init__(
            name="Bybit",
            url="wss://stream.bybit.com/v5/public/linear",
            heartbeat_interval=20.0,
            read_timeout=10.0
        )
        self.symbol = symbol.upper()
        self.orderbook = orderbook or LimitOrderBook("Bybit", self.symbol)
        self.on_trade = on_trade

    async def on_connect(self):
        logger.info(f"[Bybit] Subscribing to orderbook.50 and publicTrade for {self.symbol}...")
        sub_msg = {
            "op": "subscribe",
            "args": [
                f"orderbook.50.{self.symbol}",
                f"publicTrade.{self.symbol}"
            ]
        }
        await self.ws.send(json.dumps(sub_msg))

    async def send_ping(self):
        """Bybit application ping."""
        if self.ws:
            await self.ws.send(json.dumps({"op": "ping"}))
            await super().send_ping()

    async def on_message(self, raw_msg: str):
        try:
            msg = json.loads(raw_msg)
            topic = msg.get("topic", "")
            msg_type = msg.get("type", "")  # snapshot or delta
            data = msg.get("data", {})

            if "orderbook" in topic:
                bids_raw = data.get("b", [])
                asks_raw = data.get("a", [])
                u_seq = data.get("u", 0)

                if msg_type == "snapshot":
                    bids = [(float(b[0]), float(b[1])) for b in bids_raw]
                    asks = [(float(a[0]), float(a[1])) for a in asks_raw]
                    self.orderbook.set_snapshot(bids, asks, update_id=u_seq)
                elif msg_type == "delta":
                    for b in bids_raw:
                        self.orderbook.update_bid(float(b[0]), float(b[1]))
                    for a in asks_raw:
                        self.orderbook.update_ask(float(a[0]), float(a[1]))
                    self.orderbook.last_update_id = u_seq

            elif "publicTrade" in topic:
                trades_list = data if isinstance(data, list) else []
                for tr in trades_list:
                    price = float(tr.get("p", 0.0))
                    size = float(tr.get("v", 0.0))
                    side = tr.get("S", "")  # "Buy" or "Sell"
                    # "Buy" side means aggressive buyer (taker buy)
                    is_buyer_maker = (side != "Buy")
                    if self.on_trade and price > 0:
                        self.on_trade(price, size, is_buyer_maker)

        except Exception as e:
            logger.error(f"[Bybit] Message error: {e}")

    async def on_disconnect(self):
        self.orderbook.clear()
