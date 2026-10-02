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
from app.services.strategy_engine import StrategyEngine

logger = logging.getLogger("OrderFlowApp")
strategy_engine = StrategyEngine(mlofi_threshold=0.25, vpin_kill_threshold=0.85)

async def telemetry_broadcast_loop():
    """High-frequency telemetry broadcast loop to frontend clients (~5-10 Hz)."""
    from app.core import state
    while True:
        try:
            await asyncio.sleep(0.15)  # ~6.6 updates per second

            # Continuously update MLOFI from primary book (Binance) at ~150ms intervals
            mlofi_data = state.mlofi_engine.update(
                state.books["binance"].get_top_bids(5),
                state.books["binance"].get_top_asks(5)
            )

            if not state.connected_websockets:
                continue

            # Sync live account balance & positions from Lighter
            await state.lighter_client.sync_account_state()

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

            # Retrieve latest analytics
            vpin_toxic = state.vpin_engine.current_vpin > state.vpin_engine.toxicity_threshold
            mlofi_data = state.mlofi_engine.history[-1] if state.mlofi_engine.history else {
                "weighted_mlofi": 0.0
            }
            vpin_data = state.vpin_engine.to_dict()
            footprint_data = {
                "recent_bars": state.footprint_aggregator.get_recent_bars(count=5)
            }
            
            top_bid = state.books["binance"].get_top_bids(1)
            top_ask = state.books["binance"].get_top_asks(1)
            if not top_bid or not top_ask:
                continue

            mid_px = (top_bid[0][0] + top_ask[0][0]) / 2.0
            spread_px = top_ask[0][0] - top_bid[0][0]
            z_scores = state.norm_result.z_scores if state.norm_result else {}
            vpin_val = state.vpin_engine.current_vpin
            bucket_sz = state.vpin_engine.bucket_size
            recent_bars = footprint_data["recent_bars"]
            fp_delta = recent_bars[-1]["delta"] if recent_bars else 0.0

            # 1. First priority: Strategy Playbook evaluation (Play A Breakout, Play B Absorption, Kill Switch)
            strat_signal = strategy_engine.evaluate(
                current_mlofi=mlofi_data,
                current_vpin=vpin_data,
                current_footprint=footprint_data,
            )

            cfg = global_bot_config
            current_equity = state.lighter_client.get_state().get("equity_usd", 10000.0)

            # 2. If strategy playbook has signal, execute via StrategyEngine
            if strat_signal:
                action = strat_signal.get("action", "UNKNOWN")
                reason = strat_signal.get("reason", "")
                
                if action == "FLATTEN":
                    state.signal_telemetry.record_decision(
                        action="FLATTEN",
                        symbol="BTCUSDT",
                        mid_price=mid_px,
                        spread=spread_px,
                        mlofi_score=mlofi_data.get("weighted_mlofi", 0.0),
                        z_scores=z_scores,
                        vpin_value=vpin_val,
                        bucket_size=bucket_sz,
                        footprint_delta=fp_delta,
                        is_absorption=False,
                        reason=reason,
                    )
                    state.log_bot_activity(f"SIGNAL FLATTEN: {reason}", "error")
                    await state.lighter_client.cancel_all_orders()
                    continue

                side = strat_signal.get("side", "BUY" if "LONG" in action else "SELL")
                px = top_bid[0][0] if side == "BUY" else top_ask[0][0]
                amount = round((current_equity * cfg.risk_per_trade_pct) / px, 4)

                if amount >= 0.0001:
                    ord_res = await strategy_engine.execute_signal(
                        signal=strat_signal,
                        symbol="BTCUSDT",
                        price=px,
                        amount=amount,
                        mid_price=mid_px,
                        spread=spread_px,
                        current_mlofi=mlofi_data,
                        current_vpin=vpin_data,
                        current_footprint=footprint_data,
                        z_scores=z_scores,
                        lighter_client=state.lighter_client,
                        signal_telemetry=state.signal_telemetry,
                        pnl_tracker=state.pnl_tracker,
                        risk_guard=state.risk_guard,
                    )
                    if ord_res:
                        state.log_bot_activity(f"Executed {action} {amount} BTC @ {px} ({reason})", "buy" if side == "BUY" else "sell")
                continue

            # 3. Fallback: Direct MLOFI Flow Trigger if imbalance exceeds threshold
            imbalance = mlofi_data.get("weighted_mlofi", 0.0)
            threshold = min(cfg.mlofi_imbalance_threshold, 0.3)  # Responsive threshold

            if not vpin_toxic and abs(imbalance) >= threshold:
                if imbalance >= threshold:
                    action = "ENTRY_LONG"
                    side = "BUY"
                    px = top_bid[0][0]
                else:
                    action = "ENTRY_SHORT"
                    side = "SELL"
                    px = top_ask[0][0]

                amount = round((current_equity * cfg.risk_per_trade_pct) / px, 4)
                if amount >= 0.0001:
                    # TELEMETRY: Record State of the World snapshot
                    snap = state.signal_telemetry.record_decision(
                        action=action,
                        symbol="BTCUSDT",
                        mid_price=mid_px,
                        spread=spread_px,
                        mlofi_score=imbalance,
                        z_scores=z_scores,
                        vpin_value=vpin_val,
                        bucket_size=bucket_sz,
                        footprint_delta=fp_delta,
                        is_absorption=False,
                        reason=f"MLOFI Imbalance {imbalance:.2f} >= {threshold:.2f}",
                    )

                    ord_res = await state.lighter_client.place_order(
                        symbol="BTC", side=side, price=px, amount=amount, post_only=True
                    )
                    state.log_bot_activity(f"Placed {action} {amount} BTC @ {px} (Imbalance: {imbalance:.2f})", "buy" if side == "BUY" else "sell")

                    if ord_res and ord_res.status == "FILLED":
                        fill_px = ord_res.price if ord_res.price > 0 else px
                        snap.execution_details = {
                            "client_order_index": ord_res.client_order_index,
                            "exchange_order_id": ord_res.exchange_order_id,
                            "fill_price": fill_px,
                            "fill_amount": ord_res.filled_amount,
                            "slippage_bps": 0.0,
                            "order_type": "LIMIT",
                        }
                        state.pnl_tracker.record_fill(
                            side=side,
                            price=fill_px,
                            size=ord_res.filled_amount,
                            fee=0.0,
                            client_order_index=ord_res.client_order_index,
                            symbol="BTCUSDT",
                            action=action,
                        )
            elif vpin_toxic:
                state.log_bot_activity(f"VPIN {vpin_val:.2f} > {state.vpin_engine.toxicity_threshold}. Skipping passive orders.", "warn")
            
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
