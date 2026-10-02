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
        market_index: Optional[int] = None,  # BTC market index; resolved at connect time if None
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
        self.mode = mode
        self._market_index_override = market_index

    async def switch_mode(self, mode: str):
        self.mode = mode
        self.url = "wss://testnet.zklighter.elliot.ai/stream" if mode == "testnet" else "wss://mainnet.zklighter.elliot.ai/stream"
        self.name = f"Lighter_{mode.capitalize()}"
        self.last_nonce = -1  # Reset nonce on mode switch
        logger.info(f"[{self.name}] Switching WS URL to {self.url}")
        if self.ws:
            await self.ws.close() # Connection loop in BaseWebSocketClient will auto-reconnect to the new URL

    async def _resolve_market_index_async(self) -> int:
        """Get BTC market index. Try state cache first, then fetch from REST."""
        if self._market_index_override is not None:
            return self._market_index_override
        try:
            from app.core import state
            cached = getattr(state.lighter_client, "market_id_map", {}).get("BTC")
            if cached is not None:
                return cached
        except Exception:
            pass

        # Fetch directly from the correct environment
        try:
            import httpx
            base_url = "https://testnet.zklighter.elliot.ai" if self.mode == "testnet" else "https://mainnet.zklighter.elliot.ai"
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{base_url}/api/v1/orderBookDetails")
                if res.status_code == 200:
                    details = res.json()
                    for m in (details.get("order_book_details") or details.get("orderbooks") or details.get("markets") or []):
                        sym = m.get("symbol", "").upper()
                        if sym == "BTC" or sym == "BTCUSD" or sym == "BTC-USD":
                            idx = m.get("market_id", m.get("market_index", m.get("id")))
                            if idx is not None:
                                logger.info(f"[Lighter] Resolved BTC market_index={idx} from REST ({self.mode})")
                                return int(idx)
        except Exception as e:
            logger.warning(f"[Lighter] Could not fetch market index from REST: {e}")

        # Hard fallback: testnet=4096 (observed), mainnet=1 (observed from logs)
        fallback = 4096 if self.mode == "testnet" else 1
        logger.warning(f"[Lighter] Using fallback market_index={fallback} for {self.mode}")
        return fallback

    async def on_connect(self):
        market_index = await self._resolve_market_index_async()
        logger.info(f"[Lighter] Subscribing to orderbook/trade channel {market_index} for {self.symbol} ({self.mode})...")
        
        # Subscribe to orderbook
        sub_ob = {
            "type": "subscribe",
            "channel": f"order_book/{market_index}"
        }
        await self.ws.send(json.dumps(sub_ob))

        # Subscribe to trades
        sub_trades = {
            "type": "subscribe",
            "channel": f"trade/{market_index}"
        }
        await self.ws.send(json.dumps(sub_trades))
        
        self.last_nonce = -1

    async def send_ping(self):
        """Application-level keepalive for Lighter.
        Lighter requires at least one frame every 2 minutes.
        We do NOT call super().send_ping() (WS-level ping) as Lighter
        handles keepalive purely at application level via {type: ping}.
        """
        if self.ws:
            try:
                await self.ws.send(json.dumps({"type": "ping"}))
                logger.debug(f"[Lighter] Sent keepalive ping ({self.mode})")
            except Exception as e:
                logger.warning(f"[Lighter] Ping failed: {e}")

    async def on_message(self, raw_msg: str):
        try:
            msg = json.loads(raw_msg)
            msg_type = msg.get("type", "")
            
            if msg_type == "pong":
                return
                
            channel = msg.get("channel", "")
            
            if msg_type == "update/order_book":
                ob_data = msg.get("order_book", {})
                bids = [(float(b["price"]), float(b["size"])) for b in ob_data.get("bids", [])]
                asks = [(float(a["price"]), float(a["size"])) for a in ob_data.get("asks", [])]
                nonce = int(ob_data.get("nonce", 0))
                begin_nonce = int(ob_data.get("begin_nonce", 0))
                
                if self.last_nonce == -1:
                    # First message after subscribe — treat as full snapshot
                    self.orderbook.set_snapshot(bids, asks, update_id=nonce)
                    self.last_nonce = nonce
                    logger.info(f"[Lighter] LOB snapshot applied, nonce={nonce}, bids={len(bids)}, asks={len(asks)}")
                elif begin_nonce == self.last_nonce:
                    # Continuous delta
                    self.orderbook.apply_delta(bids, asks, update_id=nonce)
                    self.last_nonce = nonce
                else:
                    # Nonce gap: resubscribe to get a fresh snapshot without closing
                    logger.warning(f"[Lighter] Nonce gap: expected begin={self.last_nonce}, got {begin_nonce}. Re-subscribing...")
                    self.last_nonce = -1
                    market_index = await self._resolve_market_index_async()
                    await self.ws.send(json.dumps({"type": "unsubscribe", "channel": f"order_book/{market_index}"}))
                    await self.ws.send(json.dumps({"type": "subscribe", "channel": f"order_book/{market_index}"}))

            elif msg_type == "update/trade":
                trades = msg.get("trades", [])
                for t in trades:
                    px = float(t.get("price", 0.0))
                    sz = float(t.get("size", 0.0))
                    is_maker_ask = t.get("is_maker_ask", False)
                    # If maker was ask, the taker must have been buyer (BUY).
                    is_buyer_maker = not is_maker_ask 
                    
                    if self.on_trade and px > 0:
                        self.on_trade(px, sz, is_buyer_maker)

        except Exception as e:
            logger.error(f"[Lighter] Error processing message: {e}")

    async def on_disconnect(self):
        self.orderbook.clear()
        self.last_nonce = -1
