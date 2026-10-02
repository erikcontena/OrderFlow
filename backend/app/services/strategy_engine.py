"""
Strategy Engine Playbook.
Integrates signals from MLOFI, VPIN, Footprint, and Multi-Exchange Normalization
to generate and execute precise quantitative signals on Lighter.
"""

from __future__ import annotations

import time
import logging
from typing import Dict, Any, Optional

from app.analytics.pnl_tracker import PnLTracker
from app.services.signal_logger import SignalTelemetry
from app.execution.lighter_client import LighterExecutionClient
from app.execution.risk_guard import RiskGuard

logger = logging.getLogger("StrategyEngine")


class StrategyEngine:
    def __init__(
        self,
        mlofi_threshold: float = 0.5,
        vpin_kill_threshold: float = 0.85,
    ) -> None:
        self.mlofi_threshold: float = mlofi_threshold
        self.vpin_kill_threshold: float = vpin_kill_threshold

    def evaluate(
        self,
        current_mlofi: Dict[str, Any],
        current_vpin: Dict[str, Any],
        current_footprint: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluates current telemetry against defined Strategy Plays.
        Returns a signal dictionary if a play is triggered, else None.
        
        Format:
        signal = strategy_engine.evaluate(current_mlofi, current_vpin, current_footprint)
        """
        vpin_value = current_vpin.get("vpin", 0.0)
        
        # FILTER WAJIB (KILL SWITCH)
        if vpin_value > self.vpin_kill_threshold:
            return {
                "action": "FLATTEN",
                "type": "MARKET",
                "reason": f"VPIN {vpin_value:.3f} > {self.vpin_kill_threshold}. Toxic flow detected.",
                "is_absorption": False,
            }
            
        recent_bars = current_footprint.get("recent_bars", [])
        if len(recent_bars) < 2:
            return None
            
        last_bar = recent_bars[-1]
        prev_bar = recent_bars[-2]
        
        mlofi_value = current_mlofi.get("weighted_mlofi", 0.0)
        
        # Helper footprint metrics
        delta = last_bar.get("delta", 0.0)
        is_delta_positive = delta > 0.1
        is_closing_higher = last_bar.get("close", 0.0) > last_bar.get("open", 0.0)
        
        # PLAY A: Momentum Continuation (Breakout)
        # 1. MLOFI > threshold positif (ada tekanan beli bertingkat di LOB).
        # 2. VPIN < 0.65 (flow masih sehat, belum toxic).
        # 3. Footprint menunjukkan delta positif yang konsisten dan tidak ada tanda absorption.
        if mlofi_value > self.mlofi_threshold and vpin_value < 0.65:
            if is_delta_positive and is_closing_higher:
                return {
                    "action": "ENTRY_LONG",
                    "side": "BUY",
                    "type": "MARKET",
                    "reason": "PLAY A: Momentum Continuation",
                    "is_absorption": False,
                }
                
        # PLAY B: Absorption Reversal (Mean Reversion)
        # 1. Harga membuat higher high, tapi MLOFI menunjukkan divergensi (tekanan beli melemah).
        # 2. Footprint menunjukkan high positive delta tapi harga gagal naik (indikasi iceberg seller).
        # 3. VPIN melonjak > 0.70 (indikasi informed trader sedang mendistribusikan posisi short).
        is_higher_high = last_bar.get("high", 0.0) > prev_bar.get("high", 0.0)
        mlofi_divergence = mlofi_value < 0.0
        is_absorption = is_delta_positive and not is_closing_higher
        
        if is_higher_high and mlofi_divergence and is_absorption and vpin_value > 0.70:
            return {
                "action": "ENTRY_SHORT",
                "side": "SELL",
                "type": "LIMIT",
                "reason": "PLAY B: Absorption Reversal",
                "is_absorption": True,
            }
            
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # Execution & Telemetry Integration Example
    # ──────────────────────────────────────────────────────────────────────────

    async def execute_signal(
        self,
        signal: Dict[str, Any],
        symbol: str,
        price: float,
        amount: float,
        mid_price: float,
        spread: float,
        current_mlofi: Dict[str, Any],
        current_vpin: Dict[str, Any],
        current_footprint: Dict[str, Any],
        z_scores: Dict[str, float],
        lighter_client: LighterExecutionClient,
        signal_telemetry: SignalTelemetry,
        pnl_tracker: PnLTracker,
        risk_guard: RiskGuard,
    ) -> Optional[Any]:
        """
        Executes a strategy signal with non-blocking State of the World telemetry.

        Workflow:
        1. Pre-execution Risk Guard validation.
        2. Snapshot State of the World EXACTLY at decision time via SignalTelemetry.
        3. Dispatch order to Lighter exchange (or simulation).
        4. Track latency & slippage and register fill into PnLTracker.
        """
        action = signal.get("action", "UNKNOWN")
        side = signal.get("side", "BUY" if "LONG" in action else "SELL")
        order_type = signal.get("type", "MARKET")
        reason = signal.get("reason", "")
        is_absorption = signal.get("is_absorption", False)

        # 1. Pre-trade Risk Management Check
        if not risk_guard.can_open_position() and "ENTRY" in action:
            logger.warning(f"[StrategyEngine] RiskGuard blocked {action}: Exposure or Cooldown active.")
            return None

        # 2. Self-Trade Prevention (STP) check
        if risk_guard.check_self_trade(side=side, price=price):
            logger.warning(f"[StrategyEngine] STP Guard blocked order for {side} @ {price}.")
            return None

        # TELEMETRY: Record State of the World snapshot at the exact millisecond decision is taken
        # NON_BLOCKING: record_decision dispatches snapshot to an internal asyncio.Queue without blocking the event loop
        mlofi_val = current_mlofi.get("weighted_mlofi", 0.0)
        vpin_val = current_vpin.get("vpin", 0.0)
        bucket_size = current_vpin.get("bucket_size", 2.0)
        recent_bars = current_footprint.get("recent_bars", [])
        footprint_delta = recent_bars[-1].get("delta", 0.0) if recent_bars else 0.0

        decision_ns = time.time_ns()
        telemetry_snapshot = signal_telemetry.record_decision(
            action=action,
            symbol=symbol,
            mid_price=mid_price,
            spread=spread,
            mlofi_score=mlofi_val,
            z_scores=z_scores,
            vpin_value=vpin_val,
            bucket_size=bucket_size,
            footprint_delta=footprint_delta,
            is_absorption=is_absorption,
            reason=reason,
            local_recv_ns=decision_ns,
        )

        # 3. Order Dispatch to Lighter (HFT Hot-Path)
        t_start = time.perf_counter()
        post_only = (order_type == "LIMIT")

        try:
            ord_res = await lighter_client.place_order(
                symbol=symbol,
                side=side,
                price=price,
                amount=amount,
                post_only=post_only,
            )
        except Exception as e:
            logger.error(f"[StrategyEngine] Failed to dispatch order to Lighter: {e}")
            return None

        rtt_ms = (time.perf_counter() - t_start) * 1000.0

        # 4. Fill Recording & Slippage Calculation
        if ord_res:
            exec_price = ord_res.price if ord_res.price > 0 else price
            slippage_bps = ((exec_price - mid_price) / mid_price) * 10000.0 if mid_price > 0 else 0.0
            if side == "SELL":
                slippage_bps = -slippage_bps

            # TELEMETRY: Enrich execution details on telemetry snapshot
            telemetry_snapshot.execution_details = {
                "client_order_index": ord_res.client_order_index,
                "exchange_order_id": ord_res.exchange_order_id,
                "status": ord_res.status,
                "fill_price": exec_price,
                "fill_amount": ord_res.filled_amount if ord_res.status == "FILLED" else amount,
                "slippage_bps": round(slippage_bps, 2),
                "rtt_ms": round(rtt_ms, 2),
                "order_type": order_type,
            }

            if ord_res.status == "FILLED":
                # NON_BLOCKING: Real-time O(1) PnL calculation and High Water Mark update
                closed_record = pnl_tracker.record_fill(
                    side=side,
                    price=exec_price,
                    size=ord_res.filled_amount,
                    fee=0.0,  # Zero-fee on Lighter DEX
                    client_order_index=ord_res.client_order_index,
                    symbol=symbol,
                    action=action,
                )

                # Update Risk Guard with closed trade PnL for daily limits & anti-revenge cooldown
                if closed_record is not None:
                    telemetry_snapshot.pnl_usd = closed_record.realized_pnl
                    risk_guard.register_fill(pnl_usd=closed_record.realized_pnl, is_close=True)
                else:
                    risk_guard.register_fill(pnl_usd=0.0, is_close=False)
            elif ord_res.status == "OPEN":
                logger.info(f"[StrategyEngine] Order #{ord_res.client_order_index} accepted on Lighter (tx: {ord_res.exchange_order_id})")

        return ord_res
