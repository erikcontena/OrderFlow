"""
Bitget Public V2 Ingestion Engine.
Subscribes to books15 (high-speed depth stream) and trade channels,
with CRC32 checksum integrity verification.
"""
import json
import zlib
import logging
from typing import Optional, Callable
from .base import BaseWebSocketClient
from ..analytics.orderbook import LimitOrderBook

logger = logging.getLogger("BitgetIngestion")

class BitgetIngestor(BaseWebSocketClient):
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        orderbook: Optional[LimitOrderBook] = None,
        on_trade: Optional[Callable[[float, float, bool], None]] = None,
    ):
        super().__init__(
            name="Bitget",
            url="wss://ws.bitget.com/v2/ws/public",
            heartbeat_interval=30.0,
            read_timeout=15.0
        )
        self.symbol = symbol.upper()
        self.orderbook = orderbook or LimitOrderBook("Bitget", self.symbol)
        self.on_trade = on_trade

    async def on_connect(self):
        logger.info(f"[Bitget] Subscribing to books15 and trade for {self.symbol}...")
        sub_msg = {
            "op": "subscribe",
            "args": [
                {
                    "instType": "USDT-FUTURES",
                    "channel": "books15",
                    "instId": self.symbol
                },
                {
                    "instType": "USDT-FUTURES",
                    "channel": "trade",
                    "instId": self.symbol
                }
            ]
        }
        await self.ws.send(json.dumps(sub_msg))

    async def send_ping(self):
        """Bitget plain string ping."""
        if self.ws:
            await self.ws.send("ping")
            await super().send_ping()

    def _verify_crc32(self, bids, asks, remote_checksum: int) -> bool:
        """Constructs CRC32 string: 25 levels of bids and asks formatted."""
        s = ""
        for i in range(min(25, max(len(bids), len(asks)))):
            if i < len(bids):
                s += f"{bids[i][0]}:{bids[i][1]}:"
            if i < len(asks):
                s += f"{asks[i][0]}:{asks[i][1]}:"
        s = s.rstrip(":")
        local_crc = zlib.crc32(s.encode("utf-8")) & 0xffffffff
        return local_crc == (remote_checksum & 0xffffffff)

    async def on_message(self, raw_msg: str):
        if raw_msg == "pong":
            return
        try:
            msg = json.loads(raw_msg)
            action = msg.get("action")
            arg = msg.get("arg", {})
            channel = arg.get("channel")
            data_list = msg.get("data", [])

            if channel == "books15":
                for item in data_list:
                    bids = [(float(b[0]), float(b[1])) for b in item.get("bids", [])]
                    asks = [(float(a[0]), float(a[1])) for a in item.get("asks", [])]
                    
                    # If snapshot or full update
                    if action == "snapshot" or True:
                        self.orderbook.set_snapshot(bids, asks, update_id=item.get("ts", 0))

                    # Optional checksum verification
                    checksum = item.get("checksum")
                    if checksum is not None:
                        if not self._verify_crc32(bids, asks, int(checksum)):
                            logger.warning("[Bitget] CRC32 Checksum mismatch! Potential packet loss.")

            elif channel == "trade":
                for tr in data_list:
                    price = float(tr.get("price", 0.0))
                    size = float(tr.get("size", 0.0))
                    side = tr.get("side", "")  # "buy" or "sell"
                    # "buy" means taker buy (buyer is aggressor)
                    is_buyer_maker = (side != "buy")
                    if self.on_trade and price > 0:
                        self.on_trade(price, size, is_buyer_maker)

        except Exception as e:
            logger.error(f"[Bitget] Message error: {e}")

    async def on_disconnect(self):
        self.orderbook.clear()
