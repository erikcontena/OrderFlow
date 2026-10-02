import asyncio
import json
import logging
import random

from app.core.state import (
    books, vpin_engine, mlofi_engine, footprint_aggregator,
    lighter_client, risk_guard, bot_logs, connected_websockets,
    log_bot_activity, ingestors, fire_and_forget
)
from app.core.config import global_bot_config
from app.db import DBRepository

logger = logging.getLogger("OrderFlowApp")

async def telemetry_broadcast_loop():
    """High-frequency telemetry broadcast loop to frontend clients (~5-10 Hz)."""
    from app.core import state
    while True:
        try:
            await asyncio.sleep(0.15)  # ~6.6 updates per second
            if not state.connected_websockets:
                continue

            # Sync live account balance & positions from Lighter
            await state.lighter_client.sync_account_state()

            # Update MLOFI from primary book (Binance)
            mlofi_data = state.mlofi_engine.update(
                state.books["binance"].get_top_bids(5),
                state.books["binance"].get_top_asks(5)
            )

            # Build comprehensive telemetry packet
            packet = {
                "type": "TELEMETRY_UPDATE",
                "timestamp": asyncio.get_event_loop().time(),
                "orderbooks": {k: b.to_dict(depth=10) for k, b in state.books.items()},
                "vpin": state.vpin_engine.to_dict(),
                "mlofi": mlofi_data,
                "cvd": state.footprint_aggregator.get_cvd_summary(),
                "footprint_bars": state.footprint_aggregator.get_recent_bars(count=8),
                "execution": state.lighter_client.get_state(),
                "open_orders": state.lighter_client.get_open_orders(),
                "risk": state.risk_guard.get_status(),
                "connections": {k: ing.get_telemetry() for k, ing in state.ingestors.items()},
                "bot_active": state.bot_active,
                "bot_logs": list(state.bot_logs),
                "config": global_bot_config.model_dump()
            }
            msg = json.dumps(packet)

            # Broadcast to all connected web clients
            disconnected = set()
            for ws in state.connected_websockets:
                try:
                    await ws.send_text(msg)
                except Exception:
                    disconnected.add(ws)
            state.connected_websockets.difference_update(disconnected)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Broadcast loop error: {e}")
            await asyncio.sleep(1.0)


async def autonomous_bot_loop():
    """Autonomous trading bot loop reacting to OrderFlow signals"""
    from app.core import state
    while True:
        try:
            await asyncio.sleep(1.0)
            if not state.bot_active:
                continue
                
            if state.risk_guard.kill_switch_active:
                state.log_bot_activity("Kill switch active. Bot operations halted.", "error")
                continue

            # Retrieve signals
            vpin_toxic = state.vpin_engine.current_vpin > state.vpin_engine.toxicity_threshold
            mlofi_data = state.mlofi_engine.history[-1] if state.mlofi_engine.history else {}
            imbalance = mlofi_data.get("weighted_mlofi", 0)
            
            top_bid = state.books["binance"].get_top_bids(1)
            top_ask = state.books["binance"].get_top_asks(1)
            if not top_bid or not top_ask:
                continue
                
            # Order Sizing & SL/TP Parameters from config
            cfg = global_bot_config
            
            # Simple simulation logic for placing orders based on MLOFI
            if not vpin_toxic:
                current_equity = state.lighter_client.get_state().get("equity_usd", 10000.0)
                
                if imbalance > cfg.mlofi_imbalance_threshold:  # Strong Buy Signal
                    # Randomize placing order so it's not spamming every second
                    if random.random() < 0.6:
                        px = top_bid[0][0]
                        amount = round((current_equity * cfg.risk_per_trade_pct) / px, 4)
                        if amount >= 0.0001:
                            ord_res = await state.lighter_client.place_order(symbol="BTC", side="BUY", price=px, amount=amount, post_only=True)
                            state.log_bot_activity(f"Placed BUY {amount} BTC @ {px} (Imbalance: {imbalance:.2f})", "buy")
                            tp_px = round(px * (1 + cfg.tp_percentage), 1)
                            sl_px = round(px * (1 - cfg.sl_percentage), 1)
                            state.log_bot_activity(f"Target TP: {tp_px} (+{cfg.tp_percentage*100}%), SL: {sl_px} (-{cfg.sl_percentage*100}%)", "info")
                            
                            # Persist Order to DB asynchronously
                            if ord_res:
                                state.fire_and_forget(DBRepository.save_order({
                                    "client_order_index": ord_res.client_order_index,
                                    "exchange_order_id": ord_res.exchange_order_id,
                                    "symbol": "BTCUSDT",
                                    "side": "BUY",
                                    "order_type": "LIMIT",
                                    "price": px,
                                    "amount": amount,
                                    "filled_amount": ord_res.filled_amount,
                                    "status": ord_res.status,
                                    "reduce_only": False,
                                    "is_simulation": state.lighter_client.is_simulation,
                                }))
                                
                                if ord_res.status == "FILLED":
                                    state.fire_and_forget(DBRepository.record_trade({
                                        "client_order_index": ord_res.client_order_index,
                                        "symbol": "BTCUSDT",
                                        "side": "BUY",
                                        "exec_price": px,
                                        "exec_amount": amount,
                                        "is_simulation": state.lighter_client.is_simulation,
                                    }))
                                    await state.lighter_client.place_order(symbol="BTC", side="SELL", price=tp_px, amount=amount, post_only=True, reduce_only=True)
                                    state.log_bot_activity(f"Placed TP SELL {amount} BTC @ {tp_px} (Reduce-Only)", "sell")
                            
                elif imbalance < -cfg.mlofi_imbalance_threshold: # Strong Sell Signal
                    if random.random() < 0.6:
                        px = top_ask[0][0]
                        amount = round((current_equity * cfg.risk_per_trade_pct) / px, 4)
                        if amount >= 0.0001:
                            ord_res = await state.lighter_client.place_order(symbol="BTC", side="SELL", price=px, amount=amount, post_only=True)
                            state.log_bot_activity(f"Placed SELL {amount} BTC @ {px} (Imbalance: {imbalance:.2f})", "sell")
                            tp_px = round(px * (1 - cfg.tp_percentage), 1)
                            sl_px = round(px * (1 + cfg.sl_percentage), 1)
                            state.log_bot_activity(f"Target TP: {tp_px} (+{cfg.tp_percentage*100}%), SL: {sl_px} (-{cfg.sl_percentage*100}%)", "info")
                            
                            # Persist Order to DB asynchronously
                            if ord_res:
                                state.fire_and_forget(DBRepository.save_order({
                                    "client_order_index": ord_res.client_order_index,
                                    "exchange_order_id": ord_res.exchange_order_id,
                                    "symbol": "BTCUSDT",
                                    "side": "SELL",
                                    "order_type": "LIMIT",
                                    "price": px,
                                    "amount": amount,
                                    "filled_amount": ord_res.filled_amount,
                                    "status": ord_res.status,
                                    "reduce_only": False,
                                    "is_simulation": state.lighter_client.is_simulation,
                                }))

                                if ord_res.status == "FILLED":
                                    state.fire_and_forget(DBRepository.record_trade({
                                        "client_order_index": ord_res.client_order_index,
                                        "symbol": "BTCUSDT",
                                        "side": "SELL",
                                        "exec_price": px,
                                        "exec_amount": amount,
                                        "is_simulation": state.lighter_client.is_simulation,
                                    }))
                                    await state.lighter_client.place_order(symbol="BTC", side="BUY", price=tp_px, amount=amount, post_only=True, reduce_only=True)
                                    state.log_bot_activity(f"Placed TP BUY {amount} BTC @ {tp_px} (Reduce-Only)", "buy")
            else:
                state.log_bot_activity(f"VPIN {state.vpin_engine.current_vpin:.2f} > {state.vpin_engine.toxicity_threshold}. Skipping passive orders.", "warn")
            
            # Active Position Sizing/Inventory check & Cancel old orders
            # Limit active inventory to max active positions
            open_orders = state.lighter_client.get_open_orders()
            if len(open_orders) > cfg.max_active_positions:
                if random.random() < 0.3:
                    o = open_orders[0]
                    await state.lighter_client.cancel_order(o["client_order_index"])
                    state.log_bot_activity(f"Canceled Order #{o['client_order_index']}", "info")
                    state.fire_and_forget(DBRepository.update_order_status(o["client_order_index"], "CANCELED"))
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Autonomous Bot loop error: {e}")
            state.log_bot_activity(f"Bot loop error: {e}", "error")
            await asyncio.sleep(1.0)


async def analytics_snapshot_loop():
    """Periodically persist time-series snapshots of VPIN and MLOFI into DB."""
    from app.core import state
    while True:
        try:
            await asyncio.sleep(60.0) # Every 1 minute
            top_bid = state.books["binance"].get_top_bids(1)
            top_ask = state.books["binance"].get_top_asks(1)
            mid_px = (top_bid[0][0] + top_ask[0][0]) / 2.0 if (top_bid and top_ask) else 0.0
            spread = (top_ask[0][0] - top_bid[0][0]) if (top_bid and top_ask) else 0.0
            
            await DBRepository.record_analytics_snapshot({
                "symbol": global_bot_config.symbol,
                "vpin_value": state.vpin_engine.current_vpin,
                "vpin_is_toxic": state.vpin_engine.is_toxic,
                "mlofi_imbalance": state.mlofi_engine.compute_integrated_imbalance(),
                "mid_price": mid_px,
                "spread": spread,
                "cvd_delta": state.footprint_aggregator.get_cvd_summary().get("delta_1m", 0.0),
                "active_leverage": 1.0,
            })
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Analytics snapshot loop error: {e}")
