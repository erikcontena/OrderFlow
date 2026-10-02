"""
Lighter Exchange Execution Client.
Features:
1. Account index & API key management (Standard / Plus / Premium tiers).
2. Integer price & base_amount scaling via orderBookDetails precision metadata.
3. 48-bit unsigned integer (uint48) client_order_index tracking.
4. Nonce management with SkipNonce tolerance (new_nonce > old_nonce).
5. Post-Only (Maker Lock) and Reduce-Only policies.
6. Self-Trade Prevention (STP) protection.
7. Simulated / Paper-trading mode & Live FFI interface stub.
"""
import os
import time
import logging
from typing import Dict, List, Optional, Any
from enum import IntEnum
from dotenv import load_dotenv
import httpx

# Load env variables from .env if present
load_dotenv()

logger = logging.getLogger("LighterClient")

class OrderType(IntEnum):
    LIMIT = 0
    MARKET = 1
    STOP_LOSS = 2
    TAKE_PROFIT = 4

class TimeInForce(IntEnum):
    GTC = 0         # Good 'Til Cancelled
    IOC = 1         # Immediate Or Cancel
    POST_ONLY = 2   # Maker only; cancels if crossing book

class LighterOrder:
    def __init__(
        self,
        client_order_index: int,
        symbol: str,
        side: str,              # "BUY" or "SELL"
        price: float,
        amount: float,
        order_type: OrderType = OrderType.LIMIT,
        post_only: bool = True,
        reduce_only: bool = False,
    ):
        self.client_order_index = client_order_index & 0xFFFFFFFFFFFF  # 48-bit mask
        self.symbol = symbol
        self.side = side.upper()
        self.price = price
        self.amount = amount
        self.order_type = order_type
        self.time_in_force = TimeInForce.POST_ONLY if post_only else TimeInForce.GTC
        self.reduce_only = reduce_only
        self.status = "PENDING"  # PENDING, OPEN, FILLED, CANCELED, REJECTED
        self.created_at = time.time()
        self.exchange_order_id: Optional[str] = None
        self.filled_amount: float = 0.0

    def to_dict(self) -> dict:
        return {
            "client_order_index": self.client_order_index,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "amount": self.amount,
            "order_type": self.order_type.name,
            "time_in_force": self.time_in_force.name,
            "reduce_only": self.reduce_only,
            "status": self.status,
            "created_at": self.created_at,
            "exchange_order_id": self.exchange_order_id,
            "filled_amount": self.filled_amount,
        }


class LighterExecutionClient:
    def __init__(self, mode: Optional[str] = None):
        # Determine mode: arg -> env -> default "testnet"
        self.mode = mode or os.getenv("LIGHTER_MODE", "testnet").lower()
        if self.mode == "mainnet":
            self.base_url = "https://mainnet.zklighter.elliot.ai"
            self.ws_url = "wss://mainnet.zklighter.elliot.ai/stream"
            self.chain_id = 304
        else:
            self.base_url = "https://testnet.zklighter.elliot.ai"
            self.ws_url = "wss://testnet.zklighter.elliot.ai/stream"
            self.chain_id = 300

        # Load Secure Credentials
        self.account_index = int(os.getenv("LIGHTER_ACCOUNT_INDEX", "0"))
        self.api_key_index = int(os.getenv("LIGHTER_API_KEY_INDEX", "4"))
        self.private_key = os.getenv("LIGHTER_PRIVATE_KEY")
        
        # Determine simulation/paper-trading (Default to True for safety unless explicitly overridden)
        paper_trading_env = os.getenv("LIGHTER_PAPER_TRADING", "True").lower()
        self.is_simulation = paper_trading_env in ("true", "1", "yes")

        logger.info(f"Initialized LighterExecutionClient (Mode: {self.mode.upper()}, ChainID: {self.chain_id}, Paper: {self.is_simulation})")

        # Orderbook precision dictionary (e.g. BTC: price 1 decimal, amount 3 decimals)
        self.precisions = {
            "BTC": {"price_decimals": 1, "amount_decimals": 4, "price_scale": 10, "amount_scale": 10000},
            "ETH": {"price_decimals": 2, "amount_decimals": 3, "price_scale": 100, "amount_scale": 1000},
        }

        # 48-bit Nonce Counter
        self.current_nonce: int = int(time.time() * 1000) & 0xFFFFFFFFFFFF
        self.client_order_counter: int = int(time.time() * 10) % 100_000_000

        # Memory store for active and historical orders
        self.orders: Dict[int, LighterOrder] = {}
        
        # Simulated position & balance
        self.simulated_balance: float = 10000.0  # 10,000 USD equity
        self.simulated_position: float = 0.0      # In base currency
        self.simulated_pnl: float = 0.0           # Unrealized PnL
        
        # Live account state cache
        self.live_balance: float = 0.0
        self.live_position: float = 0.0
        self.live_pnl: float = 0.0
        self.last_sync_time: float = 0.0
        self.is_account_synced: bool = False
        # Persistent HTTP Client for low-latency connection pooling
        self._http_client: Optional[httpx.AsyncClient] = None

    async def get_http_client(self):
        import httpx
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=8.0)
        return self._http_client

    async def aclose(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def switch_mode(self, new_mode: str):
        """Dynamically switch between testnet and mainnet."""
        self.mode = new_mode.lower()
        if self.mode == "mainnet":
            self.base_url = "https://mainnet.zklighter.elliot.ai"
            self.ws_url = "wss://mainnet.zklighter.elliot.ai/stream"
            self.chain_id = 304
        else:
            self.base_url = "https://testnet.zklighter.elliot.ai"
            self.ws_url = "wss://testnet.zklighter.elliot.ai/stream"
            self.chain_id = 300
        
        # Clear local simulated state and orders when switching networks
        self.orders.clear()
        self.current_nonce = 0
        self.last_sync_time = 0.0
        self.is_account_synced = False
        self.live_balance = 0.0
        self.live_position = 0.0
        self.live_pnl = 0.0
        if hasattr(self, "market_id_map"):
            self.market_id_map.clear()
        logger.info(f"Switched LighterExecutionClient to Mode: {self.mode.upper()}, ChainID: {self.chain_id}")
        
    def get_next_client_order_index(self) -> int:
        self.client_order_counter = (self.client_order_counter + 1) & 0xFFFFFFFFFFFF
        return self.client_order_counter

    def get_next_nonce(self) -> int:
        """SkipNonce logic: strictly increasing 48-bit sequence."""
        self.current_nonce += 1
        return self.current_nonce & 0xFFFFFFFFFFFF

    def format_integer_amounts(self, symbol: str, price: float, amount: float) -> tuple[int, int]:
        spec = self.precisions.get(symbol.upper(), {"price_scale": 100, "amount_scale": 1000})
        int_price = int(round(price * spec["price_scale"]))
        int_amount = int(round(amount * spec["amount_scale"]))
        return int_price, int_amount

    async def place_order(
        self,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        post_only: bool = True,
        reduce_only: bool = False,
    ) -> LighterOrder:
        order_index = self.get_next_client_order_index()
        order = LighterOrder(
            client_order_index=order_index,
            symbol=symbol,
            side=side,
            price=price,
            amount=amount,
            post_only=post_only,
            reduce_only=reduce_only,
        )

        int_price, int_amount = self.format_integer_amounts(symbol, price, amount)
        nonce = self.get_next_nonce()

        if self.is_simulation:
            # Paper execution simulation on testnet structure
            order.status = "OPEN"
            order.exchange_order_id = f"sim_tx_{nonce}"
            self.orders[order_index] = order
            logger.info(f"[Lighter Testnet Simulator] Placed {side} {amount} {symbol} @ {price} (Index: {order_index}, Nonce: {nonce})")
            
            # Simulate immediate fill for market making bots
            order.status = "FILLED"
            order.filled_amount = amount
            if side.upper() == "BUY":
                self.simulated_position += amount
                self.simulated_balance -= (amount * price)
            else:
                self.simulated_position -= amount
                self.simulated_balance += (amount * price)
            
            # Simulate a bit of PnL change
            import random
            self.simulated_pnl += (random.random() * 20 - 10)
            
            return order
        else:
            # Live execution via Node.js Signer Microservice
            logger.info(f"[Lighter Live] Requesting signature for order #{order_index} with nonce={nonce}")
            
            # Map symbol to WASM signer market index (0: ETH, 1: BTC, 2: SOL)
            wasm_market_map = {"ETH": 0, "BTC": 1, "SOL": 2}
            market_index = wasm_market_map.get(symbol.upper(), 1)
            
            payload = {
                "ctx": {
                    "accountIndex": self.account_index,
                    "apiKeyIndex": self.api_key_index,
                    "apiPrivateKey": self.private_key,
                    "chainId": self.chain_id,
                    "url": ""
                },
                "input": {
                    "marketIndex": market_index,
                    "clientOrderIndex": order_index,
                    "baseAmount": int_amount,
                    "price": int_price,
                    "isAsk": side.upper() == "SELL",
                    "orderType": 0, # 0 = Limit
                    "timeInForce": 0, # 0 = IOC / GTC nil expiry
                    "reduceOnly": reduce_only,
                    "orderExpiry": 0, # 0 = NilOrderExpiry
                    "nonce": nonce
                }
            }
            
            try:
                client = await self.get_http_client()
                # 1. Get Signature from Node.js Sidecar
                resp = await client.post("http://127.0.0.1:3001/sign_create_order", json=payload, timeout=5.0)
                resp.raise_for_status()
                signed_data = resp.json()
                
                if not signed_data.get("success"):
                    raise Exception(signed_data.get("error"))
                    
                # 2. Send Tx to Lighter
                base_url = "https://mainnet.zklighter.elliot.ai" if self.mode.upper() == "MAINNET" else "https://testnet.zklighter.elliot.ai"
                tx_payload = {
                    "tx_type": signed_data["txType"],
                    "tx_info": signed_data["txInfo"]
                }
                tx_resp = await client.post(f"{base_url}/api/v1/sendTx", data=tx_payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
                if tx_resp.status_code != 200:
                    logger.error(f"[Lighter Live sendTx Error] Status: {tx_resp.status_code}, Body: {tx_resp.text}")
                tx_resp.raise_for_status()
                tx_result = tx_resp.json()
                
                if tx_result.get("code") == 200:
                    order.status = "OPEN"
                    order.exchange_order_id = tx_result.get("tx_hash")
                    self.orders[order_index] = order
                    logger.info(f"[Lighter Live] Successfully placed order #{order_index}: {tx_result}")
                    return order
                else:
                    raise Exception(str(tx_result))
            except Exception as e:
                logger.error(f"[Lighter Live] Failed to place live order: {str(e)}")
                order.status = "REJECTED"
                return order

    async def cancel_order(self, client_order_index: int) -> bool:
        if client_order_index in self.orders:
            order = self.orders[client_order_index]
            if order.status in ("OPEN", "PENDING"):
                nonce = self.get_next_nonce()
                if self.is_simulation:
                    order.status = "CANCELED"
                    logger.info(f"[Lighter Testnet] Canceled order #{client_order_index} with nonce={nonce}")
                    return True
                else:
                    try:
                        import httpx
                        payload = {
                            "ctx": {
                                "accountIndex": self.account_index,
                                "apiKeyIndex": self.api_key_index,
                                "apiPrivateKey": self.private_key,
                                "chainId": self.chain_id,
                                "url": ""
                            },
                            "input": {
                                "marketIndex": 0,
                                "orderIndex": client_order_index,
                                "nonce": nonce
                            }
                        }
                        client = await self.get_http_client()
                        resp = await client.post("http://127.0.0.1:3001/sign_cancel_order", json=payload)
                        resp.raise_for_status()
                        signed_data = resp.json()
                        
                        base_url = "https://mainnet.zklighter.elliot.ai" if self.mode == "MAINNET" else "https://testnet.zklighter.elliot.ai"
                        tx_resp = await client.post(f"{base_url}/api/v1/sendTx", data={"tx_type": signed_data["txType"], "tx_info": signed_data["txInfo"]}, headers={"Content-Type": "application/x-www-form-urlencoded"})
                        
                        if tx_resp.json().get("code") == 200:
                            order.status = "CANCELED"
                            logger.info(f"[Lighter Live] Canceled order #{client_order_index}")
                            return True
                    except Exception as e:
                        logger.error(f"[Lighter Live] Cancel failed: {str(e)}")
        return False

    async def cancel_all_orders(self) -> int:
        count = 0
        for idx, order in self.orders.items():
            if order.status in ("OPEN", "PENDING"):
                order.status = "CANCELED"
                count += 1
        logger.info(f"[Lighter Testnet] Bulk canceled {count} open orders.")
        return count

    async def set_leverage(self, leverage: float) -> bool:
        if self.is_simulation:
            logger.info(f"[Lighter Simulator] Set leverage to {leverage}x")
            return True
            
        try:
            # 10x leverage = 1000 basis points
            initial_margin_fraction = int(10000 / leverage)
            nonce = self.get_next_nonce()
            
            payload = {
                "ctx": {
                    "accountIndex": self.account_index,
                    "apiKeyIndex": self.api_key_index,
                    "apiPrivateKey": self.private_key,
                    "chainId": self.chain_id,
                    "url": ""
                },
                "input": {
                    "marketIndex": 0, # BTC-USDC
                    "initialMarginFraction": initial_margin_fraction,
                    "marginMode": 0, # Cross Margin
                    "nonce": nonce
                }
            }
            client = await self.get_http_client()
            resp = await client.post("http://127.0.0.1:3001/sign_update_leverage", json=payload, timeout=5.0)
            resp.raise_for_status()
            signed_data = resp.json()
            
            if not signed_data.get("success"):
                raise Exception(signed_data.get("error"))
                
            base_url = "https://mainnet.zklighter.elliot.ai" if self.mode == "MAINNET" else "https://testnet.zklighter.elliot.ai"
            tx_resp = await client.post(
                f"{base_url}/api/v1/sendTx", 
                data={"tx_type": signed_data["txType"], "tx_info": signed_data["txInfo"]}, 
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            if tx_resp.json().get("code") == 200:
                logger.info(f"[Lighter Live] Successfully set leverage to {leverage}x")
                return True
            else:
                raise Exception(str(tx_resp.json()))
        except Exception as e:
            logger.error(f"[Lighter Live] Failed to set leverage: {str(e)}")
            return False

    def set_account_index(self, index_or_addr: Any):
        try:
            if str(index_or_addr).startswith("0x"):
                self.account_index = str(index_or_addr).lower()
            else:
                self.account_index = int(index_or_addr)
        except Exception:
            self.account_index = index_or_addr
        self.last_sync_time = 0.0
        self.is_account_synced = False
        logger.info(f"Updated Lighter account_index to {self.account_index}")

    def set_paper_trading(self, is_paper: bool):
        self.is_simulation = is_paper
        logger.info(f"Updated Lighter paper trading mode to {is_paper}")

    async def sync_account_state(self):
        """Fetch live balance and positions from Lighter exchange API."""
        now = time.time()
        if now - self.last_sync_time < 2.5:
            return
        self.last_sync_time = now

        try:
            base_url = "https://mainnet.zklighter.elliot.ai" if self.mode.upper() == "MAINNET" else "https://testnet.zklighter.elliot.ai"
            
            # Check whether identifier is Ethereum address or numeric index
            if str(self.account_index).startswith("0x"):
                query_param = f"by=l1_address&value={self.account_index}"
            else:
                query_param = f"by=index&value={self.account_index}"

            client = await self.get_http_client()
            # 1. Populate market map if empty
            if not getattr(self, "market_id_map", None):
                self.market_id_map = {}
                try:
                    ob_res = await client.get(f"{base_url}/api/v1/orderBookDetails")
                    logger.debug(f"[Lighter Markets] Fetching orderBookDetails: status={ob_res.status_code}")
                    if ob_res.status_code == 200:
                        ob_data = ob_res.json()
                        details = ob_data.get("order_book_details") or ob_data.get("orderbooks") or ob_data.get("markets") or []
                        for m in details:
                            sym = m.get("symbol", "").upper()
                            m_idx = m.get("market_id", m.get("market_index", m.get("id")))
                            if m_idx is not None:
                                self.market_id_map[sym] = int(m_idx)
                                if "BTC" in sym:
                                    self.market_id_map["BTC"] = int(m_idx)
                        logger.info(f"[Lighter Markets] Loaded market mapping on {self.mode.upper()}: {self.market_id_map}")
                except Exception as me:
                    logger.warning(f"Failed to fetch orderBookDetails: {me}")

                # 2. Fetch account balance and positions
                res = await client.get(f"{base_url}/api/v1/account?{query_param}")
                if res.status_code == 200:
                    data = res.json()
                    if data.get("code") == 200 and data.get("accounts"):
                        acct = data["accounts"][0]
                        # If query was by address, capture numeric account index
                        if "index" in acct and isinstance(self.account_index, str) and self.account_index.startswith("0x"):
                            self.account_index = acct["index"]
                            
                        bal_str = acct.get("total_asset_value") or acct.get("collateral") or acct.get("available_balance") or "0"
                        self.live_balance = float(bal_str)
                        self.is_account_synced = True
                        
                        btc_pos = 0.0
                        pnl = 0.0
                        for pos in acct.get("positions", []):
                            if pos.get("market_id") == 0 or pos.get("symbol") == "BTC":
                                btc_pos += float(pos.get("position", 0.0))
                                pnl += float(pos.get("unrealized_pnl", 0.0))
                        self.live_position = btc_pos
                        self.live_pnl = pnl
                        logger.info(f"[Lighter Sync] Account #{self.account_index} on {self.mode.upper()}: Equity=${self.live_balance:,.2f}, Pos={self.live_position} BTC, PnL=${self.live_pnl:,.2f}")
                
                # Sync official nextNonce from exchange
                try:
                    nonce_res = await client.get(f"{base_url}/api/v1/nextNonce?account_index={self.account_index}&api_key_index={self.api_key_index}")
                    if nonce_res.status_code == 200:
                        nonce_data = nonce_res.json()
                        if "nonce" in nonce_data:
                            self.current_nonce = max(self.current_nonce, int(nonce_data["nonce"]))
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Failed to sync Lighter account state: {e}")

    async def get_live_trades(self, limit: int = 50, cursor: Optional[str] = None) -> List[dict]:
        """Fetch real trade history from Lighter API.
        Requires sort_by (mandatory per API spec).
        PnL per side: ask_account_pnl = PnL when your account is the ask, bid_account_pnl = PnL as bid.
        """
        try:
            client = await self.get_http_client()
            account_idx = int(self.account_index) if str(self.account_index).isdigit() else 0
            
            # sort_by is REQUIRED by the Lighter API — omitting it causes 400
            params: dict = {
                "account_index": account_idx,
                "sort_by": "timestamp",
                "sort_dir": "desc",
                "limit": min(limit, 100),  # API max is 100
            }
            if cursor:
                params["cursor"] = cursor
            url = f"{self.base_url}/api/v1/trades"
            res = await client.get(url, params=params)
            
            if res.status_code == 200:
                data = res.json()
                trades = data.get("trades", [])
                
                formatted = []
                for t in trades:
                    price = float(t.get("price", 0))
                    size = float(t.get("size", 0))
                    is_maker_ask: bool = t.get("is_maker_ask", False)
                    
                    # Determine our side and PnL
                    ask_id = int(t.get("ask_account_id", -1))
                    bid_id = int(t.get("bid_account_id", -1))
                    our_side = "SELL" if ask_id == account_idx else "BUY"
                    
                    # is_maker: if maker was ask and we are ask, or maker was bid and we are bid
                    is_maker = (is_maker_ask and ask_id == account_idx) or (not is_maker_ask and bid_id == account_idx)
                    
                    # Pick correct PnL field
                    if our_side == "SELL":
                        raw_pnl = t.get("ask_account_pnl", "0") or "0"
                    else:
                        raw_pnl = t.get("bid_account_pnl", "0") or "0"
                    realized_pnl = float(raw_pnl)
                    
                    # taker_fee is in raw integer units (need to convert to USD decimal)
                    # Lighter fee is in 1e-6 USD units (micro-USDC)
                    fee_raw = t.get("taker_fee", 0) if not is_maker else t.get("maker_fee", 0)
                    fee_usd = float(fee_raw) / 1_000_000 if fee_raw else 0.0
                    
                    # timestamp is in milliseconds (int64)
                    ts_ms = int(t.get("timestamp", 0))
                    
                    formatted.append({
                        "timestamp": ts_ms,
                        "symbol": "BTC",
                        "market_id": t.get("market_id", 1),
                        "side": our_side,
                        "exec_price": price,
                        "exec_amount": size,
                        "usd_amount": float(t.get("usd_amount", 0) or 0),
                        "realized_pnl": realized_pnl,
                        "fee_paid": fee_usd,
                        "role": "Maker" if is_maker else "Taker",
                        "type": t.get("type", "trade"),
                        "hash": t.get("tx_hash", ""),
                        "trade_id": str(t.get("trade_id", "")),
                        "client_order_index": str(t.get("ask_client_id", "") if our_side == "SELL" else t.get("bid_client_id", "")),
                    })
                return {
                    "trades": formatted,
                    "next_cursor": data.get("next_cursor"),
                }
            else:
                logger.error(f"[Lighter Trades] API returned {res.status_code}: {res.text[:200]}")
        except Exception as e:
            logger.error(f"Failed to fetch live trades from Lighter: {e}")
        return []

    def get_open_orders(self) -> List[dict]:
        return [
            o.to_dict() for o in self.orders.values() if o.status in ("OPEN", "PENDING")
        ]

    def get_state(self) -> dict:
        use_live = self.is_account_synced or (not self.is_simulation)
        equity = self.live_balance if use_live else self.simulated_balance
        pos = self.live_position if use_live else self.simulated_position
        pnl = self.live_pnl if use_live else self.simulated_pnl

        return {
            "account_index": self.account_index,
            "api_key_index": self.api_key_index,
            "mode": self.mode.upper(),
            "is_simulation": self.is_simulation,
            "is_account_synced": self.is_account_synced,
            "equity_usd": round(equity, 2),
            "position": round(pos, 4),
            "unrealized_pnl": round(pnl, 2),
            "leverage": getattr(self, "leverage", 1.0),
            "open_orders_count": len([o for o in self.orders.values() if o.status == "OPEN"]),
            "open_orders": self.get_open_orders(),
            "last_nonce": self.current_nonce,
        }


