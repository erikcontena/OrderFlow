"""
Hyperliquid Ingestion Engine.
Connects to Hyperliquid L1 WebSocket and receives per-block full aggregated L2 Book snapshots
and raw trade executions.
"""
import json
import logging
from typing import Optional, Callable
from .base import BaseWebSocketClient
from ..analytics.orderbook import LimitOrderBook

logger = logging.getLogger("HyperliquidIngestion")

class HyperliquidIngestor(BaseWebSocketClient):
    def __init__(
        self,
        coin: str = "BTC",
        orderbook: Optional[LimitOrderBook] = None,
        on_trade: Optional[Callable[[float, float, bool], None]] = None,
    ):
        super().__init__(
            name="Hyperliquid",
            url="wss://api.hyperliquid.xyz/ws",
            heartbeat_interval=30.0,
            read_timeout=15.0
        )
        self.coin = coin.upper()
        self.orderbook = orderbook or LimitOrderBook("Hyperliquid", self.coin)
        self.on_trade = on_trade

    async def on_connect(self):
        logger.info(f"[Hyperliquid] Subscribing to l2Book and trades for {self.coin}...")
        
        # Subscribe to L2 Book (per-block full snapshot)
        sub_l2 = {
            "method": "subscribe",
            "subscription": {"type": "l2Book", "coin": self.coin}
        }
        await self.ws.send(json.dumps(sub_l2))

        # Subscribe to trades
        sub_trades = {
            "method": "subscribe",
            "subscription": {"type": "trades", "coin": self.coin}
        }
        await self.ws.send(json.dumps(sub_trades))

    async def send_ping(self):
        """Application level ping for Hyperliquid."""
        if self.ws:
            await self.ws.send(json.dumps({"method": "ping"}))
            # Also invoke protocol ping
            await super().send_ping()

    async def on_message(self, raw_msg: str):
        try:
            msg = json.loads(raw_msg)
            channel = msg.get("channel")
            data = msg.get("data", {})

            if channel == "l2Book" and data.get("coin") == self.coin:
                # Hyperliquid sends full snapshot per block
                levels = data.get("levels", [[], []])
                bids_raw = levels[0] if len(levels) > 0 else []
                asks_raw = levels[1] if len(levels) > 1 else []

                bids = [(float(b["px"]), float(b["sz"])) for b in bids_raw]
                asks = [(float(a["px"]), float(a["sz"])) for a in asks_raw]
                
                update_time = int(data.get("time", 0))
                self.orderbook.set_snapshot(bids, asks, update_id=update_time)

            elif channel == "trades":
                trades_list = data if isinstance(data, list) else []
                for tr in trades_list:
                    if tr.get("coin") == self.coin:
                        px = float(tr.get("px", 0.0))
                        sz = float(tr.get("sz", 0.0))
                        side = tr.get("side", "")  # "B" or "A"
                        # side "B" means buyer is aggressor (taker buy)
                        is_buyer_maker = (side != "B")
                        if self.on_trade and px > 0:
                            self.on_trade(px, sz, is_buyer_maker)

        except Exception as e:
            logger.error(f"[Hyperliquid] Error processing message: {e}")

    async def on_disconnect(self):
        self.orderbook.clear()
