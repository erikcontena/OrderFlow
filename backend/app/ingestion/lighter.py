"""
Lighter Ingestion Engine.
Connects to Lighter WebSocket and receives orderbook and trade data.
Implements snapshot and delta tracking with nonce verification.
"""
import json
import logging
from typing import Optional, Callable
from .base import BaseWebSocketClient
from ..analytics.orderbook import LimitOrderBook

logger = logging.getLogger("LighterIngestion")

class LighterIngestor(BaseWebSocketClient):
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        orderbook: Optional[LimitOrderBook] = None,
        on_trade: Optional[Callable[[float, float, bool], None]] = None,
        mode: str = "testnet",
    ):
        ws_url = "wss://testnet.zklighter.elliot.ai/stream" if mode == "testnet" else "wss://mainnet.zklighter.elliot.ai/stream"
        super().__init__(
            name=f"Lighter_{mode.capitalize()}",
            url=ws_url,
            heartbeat_interval=60.0, # ping at least every 2 mins
            read_timeout=120.0
        )
        self.symbol = symbol
        self.orderbook = orderbook or LimitOrderBook("Lighter", self.symbol)
        self.on_trade = on_trade
        self.last_nonce = -1

    async def switch_mode(self, mode: str):
        self.url = "wss://testnet.zklighter.elliot.ai/stream" if mode == "testnet" else "wss://mainnet.zklighter.elliot.ai/stream"
        self.name = f"Lighter_{mode.capitalize()}"
        logger.info(f"[{self.name}] Switching WS URL to {self.url}")
        if self.ws:
            await self.ws.close() # Connection loop in BaseWebSocketClient will auto-reconnect to the new URL

    async def on_connect(self):
        logger.info(f"[Lighter] Subscribing to orderbook and trades for {self.symbol}...")
        
        # Subscribe to orderbook
        sub_ob = {
            "type": "subscribe",
            "channel": "orderbook",
            "market": self.symbol
        }
        await self.ws.send(json.dumps(sub_ob))

        # Subscribe to trades
        sub_trades = {
            "type": "subscribe",
            "channel": "trades",
            "market": self.symbol
        }
        await self.ws.send(json.dumps(sub_trades))
        
        self.last_nonce = -1

    async def send_ping(self):
        """Application level ping for Lighter (requires type: ping at least every 2 min)."""
        if self.ws:
            await self.ws.send(json.dumps({"type": "ping"}))
            await super().send_ping()

    async def on_message(self, raw_msg: str):
        try:
            msg = json.loads(raw_msg)
            msg_type = msg.get("type")
            
            if msg_type == "pong":
                return
                
            channel = msg.get("channel")
            data = msg.get("data", {})
            
            if channel == "orderbook":
                if msg_type == "snapshot":
                    # Full snapshot
                    bids = [(float(p), float(s)) for p, s in data.get("bids", [])]
                    asks = [(float(p), float(s)) for p, s in data.get("asks", [])]
                    self.last_nonce = int(data.get("end_nonce", 0))
                    self.orderbook.set_snapshot(bids, asks, update_id=self.last_nonce)
                    
                elif msg_type == "delta":
                    begin_nonce = int(data.get("begin_nonce", 0))
                    end_nonce = int(data.get("end_nonce", 0))
                    
                    # Verify begin_nonce == previous nonce (or if first delta, we might be flexible, but strict rule says match)
                    if self.last_nonce != -1 and begin_nonce != self.last_nonce:
                        logger.warning(f"[Lighter] Nonce gap detected: expected {self.last_nonce}, got {begin_nonce}. Resubscribing...")
                        await self.ws.close() # Will trigger auto-reconnect
                        return
                        
                    bids = [(float(p), float(s)) for p, s in data.get("bids", [])]
                    asks = [(float(p), float(s)) for p, s in data.get("asks", [])]
                    self.orderbook.apply_delta(bids, asks, update_id=end_nonce)
                    self.last_nonce = end_nonce

            elif channel == "trades":
                if msg_type == "trade":
                    px = float(data.get("price", 0.0))
                    sz = float(data.get("amount", 0.0))
                    side = data.get("side", "") # BUY / SELL
                    
                    is_buyer_maker = (side == "SELL") # if taker side is SELL, maker was buyer
                    if self.on_trade and px > 0:
                        self.on_trade(px, sz, is_buyer_maker)

        except Exception as e:
            logger.error(f"[Lighter] Error processing message: {e}")

    async def on_disconnect(self):
        self.orderbook.clear()
        self.last_nonce = -1
