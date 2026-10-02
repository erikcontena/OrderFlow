"""
Orchestrator and Trading Engine Service.

Audited and refactored per 5-panel quantitative review:
- AUDIT FIX #1: Zero random.random() - 100% deterministic state-driven lifecycle.
- AUDIT FIX #2: StrategyEngine.evaluate(mlofi, vpin, footprint) as the SOLE entry source.
- AUDIT FIX #3: RiskGuard.can_open_position() mandatory gate before processing entry.
- AUDIT FIX #4: Separated price reference - Binance LOB for signals, Lighter LOB for execution.
- AUDIT FIX #5: State-driven Cancel-Replace tracking active_order_id, price drift > 2 ticks, max 1 order per side.
- AUDIT FIX #6: Minimum Hold Time (>= 5.0 seconds) enforced before evaluating position exits.
- AUDIT FIX #7: Signal Cooldown (>= 10.0 seconds) enforced after closing position before new entry.
- AUDIT FIX #8: Mandatory state.risk_guard.register_fill(pnl_usd, is_close) on every fill.
- AUDIT FIX #9: Dynamic SL/TP from Lighter Order Book support/resistance (fallback to % if none in +/-0.5%).
"""

import asyncio
import json
import logging
import time
from typing import Optional, Tuple, Dict, Any, List

from app.core.state import (
    books, vpin_engine, mlofi_engine, footprint_aggregator,
    lighter_client, risk_guard, bot_logs, connected_websockets,
    log_bot_activity, ingestors, fire_and_forget
)
from app.core.config import global_bot_config
from app.db import DBRepository
# AUDIT_FIX #2: Import StrategyEngine
from app.services.strategy_engine import StrategyEngine

logger = logging.getLogger("OrderFlowApp")

# AUDIT_FIX #2: Instantiate StrategyEngine with institutional risk thresholds
strategy_engine = StrategyEngine(mlofi_threshold=0.25, vpin_kill_threshold=0.85)


# AUDIT_FIX #4: Helper to extract execution prices strictly from Lighter Order Book
def get_lighter_bbo(state) -> Tuple[Optional[float], Optional[float]]:
    """Retrieve Best Bid and Best Ask from Lighter Order Book.
    
    AUDIT_FIX #4: Lighter LOB is the SOLE reference for execution pricing.
    Binance LOB is used strictly for alpha signal generation.
    """
    lighter_ob = state.books.get("lighter")
    if lighter_ob:
        top_bids = lighter_ob.get_top_bids(1)
        top_asks = lighter_ob.get_top_asks(1)
        if top_bids and top_asks:
            return float(top_bids[0][0]), float(top_asks[0][0])
    return None, None


# AUDIT_FIX #9: Dynamic SL/TP from Lighter OB support & resistance levels
def compute_dynamic_sl_tp(
    side: str,
    entry_price: float,
    state,
    cfg,
    spec: dict,
) -> Tuple[float, float]:
    """AUDIT_FIX #9: Compute Dynamic SL/TP using Lighter Order Book liquidity clusters.
    
    Rules:
    - Bids represent support; Asks represent resistance.
    - Search for valid OB levels within +/-0.5% (50 bps) window.
    - Fallback to configured percentage ONLY if no valid OB level exists within +/-0.5%.
    """
    price_decimals = int(spec.get("price_decimals", 1))
    lighter_ob = state.books.get("lighter")
    bids = lighter_ob.get_top_bids(10) if lighter_ob else []
    asks = lighter_ob.get_top_asks(10) if lighter_ob else []

    # 50 bps (+/-0.5%) boundary definition
    upper_boundary = entry_price * 1.0050
    lower_boundary = entry_price * 0.9950

    tp_price: Optional[float] = None
    sl_price: Optional[float] = None

    if side == "BUY":
        # LONG Position:
        # TP = Resistance level (Asks) in range [entry * 1.0005, entry * 1.0050]
        valid_resistance = [a[0] for a in asks if entry_price * 1.0005 <= a[0] <= upper_boundary]
        if valid_resistance:
            # Target the 2nd resistance level for conservative execution if available
            tp_price = valid_resistance[min(1, len(valid_resistance) - 1)]

        # SL = Support level (Bids) in range [entry * 0.9950, entry * 0.9995]
        valid_support = [b[0] for b in bids if lower_boundary <= b[0] <= entry_price * 0.9995]
        if valid_support:
            # Structural breakdown level behind depth
            sl_price = valid_support[min(1, len(valid_support) - 1)]

        # Fallback to % if no valid OB level exists within +/-0.5%
        if tp_price is None:
            tp_price = entry_price * (1.0 + cfg.tp_percentage)
        if sl_price is None:
            sl_price = entry_price * (1.0 - cfg.sl_percentage)

    else:
        # SHORT Position:
        # TP = Support level (Bids) in range [entry * 0.9950, entry * 0.9995]
        valid_support = [b[0] for b in bids if lower_boundary <= b[0] <= entry_price * 0.9995]
        if valid_support:
            tp_price = valid_support[min(1, len(valid_support) - 1)]

        # SL = Resistance level (Asks) in range [entry * 1.0005, entry * 1.0050]
        valid_resistance = [a[0] for a in asks if entry_price * 1.0005 <= a[0] <= upper_boundary]
        if valid_resistance:
            sl_price = valid_resistance[min(1, len(valid_resistance) - 1)]

        # Fallback to % if no valid OB level exists within +/-0.5%
        if tp_price is None:
            tp_price = entry_price * (1.0 - cfg.tp_percentage)
        if sl_price is None:
            sl_price = entry_price * (1.0 + cfg.sl_percentage)

    return round(tp_price, price_decimals), round(sl_price, price_decimals)


async def telemetry_broadcast_loop():
    """High-frequency telemetry broadcast loop (~6-8 Hz) supplying all 5 frontend panels."""
    from app.core import state
    while True:
        try:
            await asyncio.sleep(0.15)

            # Update MLOFI from primary alpha book (Binance)
            mlofi_data = state.mlofi_engine.update(
                state.books["binance"].get_top_bids(5),
                state.books["binance"].get_top_asks(5)
            )

            if not state.connected_websockets:
                continue

            # Sync live account balance & positions from Lighter execution client
            await state.lighter_client.sync_account_state()

            # Determine signal status badge for dashboard
            vpin_val = state.vpin_engine.current_vpin
            vpin_toxic = vpin_val > state.vpin_engine.toxicity_threshold
            footprint_bars = state.footprint_aggregator.get_recent_bars(count=8)
            now_ts = time.time()

            time_since_close = now_ts - state.last_close_fill_time
            time_since_loss = now_ts - state.risk_guard.last_loss_timestamp
            is_post_close_cooldown = time_since_close < 10.0
            is_post_loss_cooldown = time_since_loss < state.risk_guard.post_loss_cooldown_seconds

            strat_signal = strategy_engine.evaluate(
                current_mlofi=mlofi_data,
                current_vpin=state.vpin_engine.to_dict(),
                current_footprint={"recent_bars": footprint_bars},
            )

            # Signal badge calculation
            if state.risk_guard.kill_switch_active:
                signal_badge = "KILL_SWITCH"
            elif is_post_loss_cooldown or is_post_close_cooldown:
                signal_badge = "COOLDOWN"
            elif state.active_position_side is not None:
                signal_badge = f"POSITION_{state.active_position_side}"
            elif strat_signal:
                action = strat_signal.get("action", "")
                if action == "ENTRY_LONG":
                    signal_badge = "BUY"
                elif action == "ENTRY_SHORT":
                    signal_badge = "SELL"
                elif action == "FLATTEN":
                    signal_badge = "FLATTEN"
                else:
                    signal_badge = "HOLD"
            else:
                signal_badge = "HOLD"

            # Rich Telemetry Packet mapped for the 5 Quant Panels
            packet = {
                "type": "TELEMETRY_UPDATE",
                "timestamp": asyncio.get_event_loop().time(),
                
                # Panel 1: Equity Curve & PnL
                "equity_pnl": {
                    "total_equity": state.pnl_tracker.total_equity,
                    "realized_pnl": round(state.pnl_tracker.realized_pnl, 2),
                    "unrealized_pnl": round(state.pnl_tracker.unrealized_pnl, 2),
                    "daily_pnl_usd": round(state.risk_guard.daily_pnl_usd, 2),
                    "running_drawdown_pct": round(state.pnl_tracker.running_drawdown, 2),
                    "high_water_mark": round(state.pnl_tracker.high_water_mark, 2),
                    "closed_trades_today": len(state.pnl_tracker._trade_history),
                    "snapshots": state.pnl_tracker.get_equity_snapshots(limit=60),
                },

                # Panel 2: Signal Monitor
                "signal_monitor": {
                    "status_badge": signal_badge,
                    "signal_action": strat_signal.get("action", "HOLD") if strat_signal else "HOLD",
                    "signal_reason": strat_signal.get("reason", "Scanning micro-structure flow") if strat_signal else "OrderFlow neutral",
                    "mlofi_imbalance": round(float(mlofi_data.get("weighted_mlofi", 0.0)), 4),
                    "z_scores": state.norm_result.z_scores if state.norm_result else {},
                    "vpin_value": round(vpin_val, 4),
                    "vpin_threshold": state.vpin_engine.toxicity_threshold,
                    "vpin_is_toxic": vpin_toxic,
                    "footprint_delta_recent": footprint_bars[-1]["delta"] if footprint_bars else 0.0,
                    "cooldown_remaining_sec": max(0.0, round(10.0 - time_since_close, 1)),
                    "loss_cooldown_remaining_sec": max(0.0, round(state.risk_guard.post_loss_cooldown_seconds - time_since_loss, 1)),
                },

                # Panel 3: Active Position & Order & Recent Trades
                "active_position": {
                    "side": state.active_position_side,
                    "entry_price": state.active_position_entry_price,
                    "size": state.active_position_size,
                    "sl": state.active_position_sl,
                    "tp": state.active_position_tp,
                    "hold_time_sec": round(now_ts - state.last_entry_fill_time, 1) if state.active_position_side else 0.0,
                    "min_hold_remaining": max(0.0, round(5.0 - (now_ts - state.last_entry_fill_time), 1)) if state.active_position_side else 0.0,
                    "unrealized_pnl": round(state.pnl_tracker.unrealized_pnl, 2),
                },
                "active_order": {
                    "id": state.active_order_id,
                    "price": state.active_order_price,
                    "side": state.active_order_side,
                },
                "recent_trades": state.pnl_tracker.get_trade_history(limit=10),

                # Panel 4: Risk Guard Status
                "risk_guard": {
                    "kill_switch_active": state.risk_guard.kill_switch_active,
                    "can_open_position": state.risk_guard.can_open_position(),
                    "current_positions": state.risk_guard.current_positions,
                    "max_concurrent_positions": state.risk_guard.max_concurrent_positions,
                    "daily_pnl_usd": round(state.risk_guard.daily_pnl_usd, 2),
                    "max_daily_loss_usd": state.risk_guard.max_daily_loss_usd,
                    "post_loss_cooldown_active": is_post_loss_cooldown,
                    "post_loss_cooldown_sec": max(0.0, round(state.risk_guard.post_loss_cooldown_seconds - time_since_loss, 1)),
                    "stp_blocked_count": state.risk_guard.stp_blocked_count,
                    "desert_mode_active": state.risk_guard.desert_mode_active,
                    "alerts": state.risk_guard.alerts[-5:],
                    "rtt_ms": state.lighter_client.get_state().get("rtt_ms", 0.0) or (state.ingestors.get("binance").rtt_ms if "binance" in state.ingestors else 0.0),
                },

                # Panel 5: Exchange Health & Time Synchronization
                "exchange_health": {
                    "connections": {k: ing.get_telemetry() for k, ing in state.ingestors.items()},
                    "staleness_ms": state.time_sync.get_exchange_staleness_ms() if hasattr(state.time_sync, "get_exchange_staleness_ms") else {},
                    "volume_z_scores": state.norm_result.z_scores if state.norm_result else {},
                    "market_weights": state.norm_result.market_weights if state.norm_result else {},
                    "rvol_multiplier": state.norm_result.rvol_multiplier if state.norm_result else 1.0,
                },

                # Backward-compatible baseline fields
                "orderbooks": {k: b.to_dict(depth=10) for k, b in state.books.items()},
                "vpin": state.vpin_engine.to_dict(),
                "mlofi": mlofi_data,
                "cvd": state.footprint_aggregator.get_cvd_summary(),
                "footprint_bars": footprint_bars,
                "execution": state.lighter_client.get_state(),
                "open_orders": state.lighter_client.get_open_orders(),
                "risk": state.risk_guard.get_status(),
                "connections": {k: ing.get_telemetry() for k, ing in state.ingestors.items()},
                "bot_active": state.bot_active,
                "bot_logs": list(state.bot_logs),
                "config": global_bot_config.model_dump(),
            }
            msg = json.dumps(packet)

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


# AUDIT_FIX #1: Zero random.random() - completely deterministic autonomous execution loop
async def autonomous_bot_loop():
    """Deterministic Autonomous HFT Trading Loop adhering to all 9 Audit Rules."""
    from app.core import state

    last_cancel_confirmed_at: float = 0.0

    while True:
        try:
            await asyncio.sleep(0.5)

            # Bot toggle check: clean up active resting maker orders if bot is toggled off
            if not state.bot_active:
                if state.active_order_id is not None:
                    try:
                        await state.lighter_client.cancel_order(state.active_order_id)
                        last_cancel_confirmed_at = time.time()
                        state.log_bot_activity(f"Bot deactivated. Canceled active order #{state.active_order_id}", "warn")
                    except Exception as ce:
                        logger.error(f"Failed to cancel order #{state.active_order_id} on deactivation: {ce}")
                    state.active_order_id = None
                    state.active_order_price = None
                    state.active_order_side = None
                continue

            # Hard stop if Risk Guard kill switch is triggered
            if state.risk_guard.kill_switch_active:
                state.log_bot_activity("Kill switch active. Bot operations halted.", "error")
                if state.active_order_id is not None:
                    await state.lighter_client.cancel_order(state.active_order_id)
                    last_cancel_confirmed_at = time.time()
                    state.active_order_id = None
                    state.active_order_price = None
                    state.active_order_side = None
                continue

            # -----------------------------------------------------------------
            # 1. ALPHA SIGNAL GENERATION (Binance LOB & Order Flow Feeds)
            # -----------------------------------------------------------------
            mlofi_data = state.mlofi_engine.history[-1] if state.mlofi_engine.history else {
                "weighted_mlofi": 0.0
            }
            imbalance = float(mlofi_data.get("weighted_mlofi", 0.0))
            vpin_data = state.vpin_engine.to_dict()
            vpin_val = state.vpin_engine.current_vpin
            vpin_toxic = vpin_val > state.vpin_engine.toxicity_threshold
            footprint_data = {
                "recent_bars": state.footprint_aggregator.get_recent_bars(count=5)
            }

            binance_top_bid = state.books["binance"].get_top_bids(1)
            binance_top_ask = state.books["binance"].get_top_asks(1)
            if not binance_top_bid or not binance_top_ask:
                continue

            binance_mid_px = (binance_top_bid[0][0] + binance_top_ask[0][0]) / 2.0
            binance_spread_px = binance_top_ask[0][0] - binance_top_bid[0][0]
            z_scores = state.norm_result.z_scores if state.norm_result else {}
            bucket_sz = state.vpin_engine.bucket_size
            recent_bars = footprint_data["recent_bars"]
            fp_delta = recent_bars[-1]["delta"] if recent_bars else 0.0

            cfg = global_bot_config
            current_equity = state.lighter_client.get_state().get("equity_usd", 10000.0)

            # AUDIT_FIX #4: Execution prices MUST come from Lighter OB
            lighter_bid, lighter_ask = get_lighter_bbo(state)
            if lighter_bid is None or lighter_ask is None:
                # Skip iteration until Lighter LOB is populated to guarantee safe pricing
                continue

            spec = await state.lighter_client.get_market_spec("BTC")
            price_decimals = int(spec.get("price_decimals", 1))
            tick_size = 10.0 ** (-price_decimals)  # 0.1 for BTC
            drift_threshold = 2.0 * tick_size      # 2 ticks = $0.2

            # AUDIT_FIX #2: Evaluate StrategyEngine as SOLE entry signal source
            strat_signal = strategy_engine.evaluate(
                current_mlofi=mlofi_data,
                current_vpin=vpin_data,
                current_footprint=footprint_data,
            )

            # -----------------------------------------------------------------
            # 2. ACTIVE POSITION MANAGEMENT (AUDIT_FIX #6, #8, #9)
            # -----------------------------------------------------------------
            if state.active_position_side is not None and state.active_position_size > 0:
                pos_side = state.active_position_side
                hold_duration = time.time() - state.last_entry_fill_time

                # AUDIT_FIX #6: Minimum Hold Time (5 seconds)
                if hold_duration < 5.0:
                    # Minimum hold time not reached. Skip exit evaluation.
                    continue

                # Exit evaluation after minimum hold duration
                current_market_px = lighter_bid if pos_side == "BUY" else lighter_ask
                trigger_exit = False
                exit_reason = ""

                # AUDIT_FIX #9: Dynamic SL / TP Triggers
                if pos_side == "BUY":
                    if current_market_px <= state.active_position_sl:
                        trigger_exit = True
                        exit_reason = f"Dynamic SL Hit (${current_market_px:,.1f} <= ${state.active_position_sl:,.1f})"
                    elif current_market_px >= state.active_position_tp:
                        trigger_exit = True
                        exit_reason = f"Dynamic TP Hit (${current_market_px:,.1f} >= ${state.active_position_tp:,.1f})"
                else:  # SHORT
                    if current_market_px >= state.active_position_sl:
                        trigger_exit = True
                        exit_reason = f"Dynamic SL Hit (${current_market_px:,.1f} >= ${state.active_position_sl:,.1f})"
                    elif current_market_px <= state.active_position_tp:
                        trigger_exit = True
                        exit_reason = f"Dynamic TP Hit (${current_market_px:,.1f} <= ${state.active_position_tp:,.1f})"

                # Check FLATTEN signal from StrategyEngine or Toxic VPIN Kill-Switch
                if strat_signal and strat_signal.get("action") == "FLATTEN":
                    trigger_exit = True
                    exit_reason = f"FLATTEN Signal: {strat_signal.get('reason', '')}"
                elif vpin_toxic:
                    trigger_exit = True
                    exit_reason = f"Toxic VPIN Spike ({vpin_val:.2f})"

                if trigger_exit:
                    state.log_bot_activity(f"Closing position: {exit_reason}", "warn")
                    close_side = "SELL" if pos_side == "BUY" else "BUY"
                    # AUDIT_FIX #4: Lighter OB based slippage protection
                    close_px = round(lighter_bid * 0.998 if close_side == "SELL" else lighter_ask * 1.002, price_decimals)

                    close_res = await state.lighter_client.place_order(
                        symbol="BTC",
                        side=close_side,
                        price=close_px,
                        amount=state.active_position_size,
                        post_only=False,  # IOC Taker for guaranteed immediate closure
                        reduce_only=True,
                    )

                    if close_res:
                        actual_close_px = close_res.price if close_res.price > 0 else close_px
                        # Calculate realized PnL
                        if pos_side == "BUY":
                            realized_pnl = (actual_close_px - state.active_position_entry_price) * state.active_position_size
                        else:
                            realized_pnl = (state.active_position_entry_price - actual_close_px) * state.active_position_size

                        # AUDIT_FIX #8: Register fill into RiskGuard (is_close=True)
                        state.risk_guard.register_fill(pnl_usd=realized_pnl, is_close=True)

                        # Record in PnL Tracker for real-time equity curve
                        state.pnl_tracker.record_fill(
                            side=close_side,
                            price=actual_close_px,
                            size=state.active_position_size,
                            fee=0.0,
                            client_order_index=close_res.client_order_index,
                            symbol="BTCUSDT",
                            action="EXIT_" + pos_side,
                        )

                        # AUDIT_FIX #7: Record close timestamp for 10-second signal cooldown
                        state.last_close_fill_time = time.time()
                        state.log_bot_activity(
                            f"Closed {pos_side} position @ ${actual_close_px:,.1f}. Realized PnL: ${realized_pnl:+,.2f}",
                            "buy" if realized_pnl >= 0 else "sell"
                        )

                        # Reset active position state
                        state.active_position_side = None
                        state.active_position_entry_price = 0.0
                        state.active_position_size = 0.0
                        state.active_position_sl = 0.0
                        state.active_position_tp = 0.0
                        state.active_order_id = None
                        state.active_order_price = None
                        state.active_order_side = None

                continue

            # -----------------------------------------------------------------
            # 3. ENTRY SIGNAL VALIDATION (AUDIT_FIX #2, #3, #7)
            # -----------------------------------------------------------------
            # AUDIT_FIX #7: Signal Cooldown (10 seconds after closing)
            time_since_close = time.time() - state.last_close_fill_time
            if time_since_close < 10.0:
                continue

            # AUDIT_FIX #2: Only proceed if StrategyEngine emitted an ENTRY signal
            if not strat_signal or strat_signal.get("action") not in ("ENTRY_LONG", "ENTRY_SHORT"):
                # No entry signal: if an active resting maker order exists, cancel it (signal dissipated)
                if state.active_order_id is not None:
                    tracked = state.lighter_client.orders.get(state.active_order_id)
                    if tracked and tracked.status in ("OPEN", "PENDING"):
                        state.log_bot_activity(f"Signal dissipated. Canceling order #{state.active_order_id}", "info")
                        cancel_ok = await state.lighter_client.cancel_order(state.active_order_id)
                        if cancel_ok:
                            last_cancel_confirmed_at = time.time()
                    state.active_order_id = None
                    state.active_order_price = None
                    state.active_order_side = None
                continue

            # AUDIT_FIX #3: Panggil RiskGuard.can_open_position() SEBELUM proses sinyal BUY/SELL
            if not state.risk_guard.can_open_position():
                logger.debug("[Bot] RiskGuard.can_open_position() returned False. Skipping entry evaluation.")
                continue

            action = strat_signal.get("action")
            side = strat_signal.get("side", "BUY" if "LONG" in action else "SELL")
            reason = strat_signal.get("reason", "")

            # -----------------------------------------------------------------
            # 4. ADAPTIVE EXECUTION MODE (AUDIT_FIX #4: Lighter OB Pricing)
            # -----------------------------------------------------------------
            is_strong_momentum = abs(imbalance) >= 0.8
            if is_strong_momentum:
                # Strong Momentum: IOC / Taker with slippage protection
                post_only = False
                order_type_str = "MARKET"
                if side == "BUY":
                    exec_px = round(lighter_ask * 1.002, price_decimals)
                else:
                    exec_px = round(lighter_bid * 0.998, price_decimals)
            else:
                # Normal Flow: Post-Only Maker sitting at Lighter Best Bid/Ask
                post_only = True
                order_type_str = "LIMIT"
                exec_px = lighter_bid if side == "BUY" else lighter_ask

            # -----------------------------------------------------------------
            # 5. STATE-DRIVEN CANCEL-REPLACE (AUDIT_FIX #5)
            # -----------------------------------------------------------------
            if state.active_order_id is not None:
                tracked = state.lighter_client.orders.get(state.active_order_id)
                is_open = tracked and tracked.status in ("OPEN", "PENDING")

                if not is_open:
                    state.active_order_id = None
                    state.active_order_price = None
                    state.active_order_side = None
                else:
                    price_drift = abs(exec_px - state.active_order_price) if state.active_order_price else 0.0
                    side_changed = (side != state.active_order_side)
                    must_cancel = (price_drift > drift_threshold) or side_changed

                    if must_cancel:
                        state.log_bot_activity(
                            f"[Cancel-Replace] Drift {price_drift:.2f} > {drift_threshold:.2f} (Side: {state.active_order_side}->{side}). Canceling #{state.active_order_id}...",
                            "warn"
                        )
                        cancel_ok = await state.lighter_client.cancel_order(state.active_order_id)
                        if cancel_ok:
                            last_cancel_confirmed_at = time.time()
                        state.active_order_id = None
                        state.active_order_price = None
                        state.active_order_side = None
                        continue
                    else:
                        # Order is still valid on same side within 2 ticks drift. Hold quote.
                        # Never allow > 1 active order per side.
                        continue

            # Cooldown after cancel confirmation before placing new order
            if time.time() - last_cancel_confirmed_at < 1.0:
                continue

            # -----------------------------------------------------------------
            # 6. SIZING & MINIMUM CONSTRAINTS
            # -----------------------------------------------------------------
            min_base = float(spec.get("min_base_amount", 0.0002))
            min_quote = float(spec.get("min_quote_amount", 10.0))
            amount = round((current_equity * cfg.risk_per_trade_pct) / exec_px, 5)

            if amount * exec_px < min_quote:
                amount = round((min_quote * 1.05) / exec_px, 5)
            if amount < min_base:
                amount = min_base

            # Pre-trade Self-Trade Prevention check
            if state.risk_guard.check_self_trade(side=side, price=exec_px):
                logger.warning(f"[Bot] STP Guard blocked order for {side} @ {exec_px}.")
                continue

            # -----------------------------------------------------------------
            # 7. TELEMETRY RECORD & DISPATCH TO LIGHTER
            # -----------------------------------------------------------------
            snap = state.signal_telemetry.record_decision(
                action=action,
                symbol="BTCUSDT",
                mid_price=binance_mid_px,
                spread=binance_spread_px,
                mlofi_score=imbalance,
                z_scores=z_scores,
                vpin_value=vpin_val,
                bucket_size=bucket_sz,
                footprint_delta=fp_delta,
                is_absorption=False,
                reason=f"{reason} (Mode: {'TAKER_IOC' if is_strong_momentum else 'MAKER_POST_ONLY'})",
            )

            t_start = time.perf_counter()
            ord_res = await state.lighter_client.place_order(
                symbol="BTC",
                side=side,
                price=exec_px,
                amount=amount,
                post_only=post_only,
                reduce_only=False,
            )
            rtt_ms = (time.perf_counter() - t_start) * 1000.0

            if ord_res:
                fill_px = ord_res.price if ord_res.price > 0 else exec_px
                slippage_bps = ((fill_px - binance_mid_px) / binance_mid_px) * 10000.0 if binance_mid_px > 0 else 0.0
                if side == "SELL":
                    slippage_bps = -slippage_bps

                snap.execution_details = {
                    "client_order_index": ord_res.client_order_index,
                    "exchange_order_id": ord_res.exchange_order_id,
                    "status": ord_res.status,
                    "fill_price": fill_px,
                    "fill_amount": ord_res.filled_amount if ord_res.status == "FILLED" else amount,
                    "slippage_bps": round(slippage_bps, 2),
                    "rtt_ms": round(rtt_ms, 2),
                    "order_type": order_type_str,
                }

                if ord_res.status == "OPEN":
                    # Register resting order into State-Driven tracker (AUDIT_FIX #5)
                    state.active_order_id = ord_res.client_order_index
                    state.active_order_price = exec_px
                    state.active_order_side = side
                    state.log_bot_activity(
                        f"Placed {order_type_str} {side} {amount} BTC @ ${exec_px:,.1f} on Lighter (Order #{state.active_order_id})",
                        "buy" if side == "BUY" else "sell"
                    )

                elif ord_res.status == "FILLED":
                    # AUDIT_FIX #9: Dynamic SL/TP from Lighter Order Book
                    sl_px, tp_px = compute_dynamic_sl_tp(
                        side=side,
                        entry_price=fill_px,
                        state=state,
                        cfg=cfg,
                        spec=spec,
                    )

                    # Update position state & AUDIT_FIX #6: Minimum Hold Time
                    state.active_position_side = side
                    state.active_position_entry_price = fill_px
                    state.active_position_size = ord_res.filled_amount
                    state.active_position_sl = sl_px
                    state.active_position_tp = tp_px
                    state.last_entry_fill_time = time.time()

                    state.active_order_id = None
                    state.active_order_price = None
                    state.active_order_side = None

                    state.log_bot_activity(
                        f"FILLED {order_type_str} {side} {amount} BTC @ ${fill_px:,.1f} | Dynamic SL: ${sl_px:,.1f}, TP: ${tp_px:,.1f}",
                        "buy" if side == "BUY" else "sell"
                    )

                    # AUDIT_FIX #8: Register fill into RiskGuard (is_close=False)
                    state.risk_guard.register_fill(pnl_usd=0.0, is_close=False)

                    # Record in PnL Tracker
                    state.pnl_tracker.record_fill(
                        side=side,
                        price=fill_px,
                        size=ord_res.filled_amount,
                        fee=0.0,
                        client_order_index=ord_res.client_order_index,
                        symbol="BTCUSDT",
                        action=action,
                    )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Autonomous Bot loop error: {e}", exc_info=True)
            state.log_bot_activity(f"Bot loop error: {e}", "error")
            await asyncio.sleep(1.0)


async def analytics_snapshot_loop():
    """Periodically persist time-series snapshots of VPIN and MLOFI into DB."""
    from app.core import state
    while True:
        try:
            await asyncio.sleep(60.0)  # Every 1 minute
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
