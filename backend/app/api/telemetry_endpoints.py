"""
FastAPI Endpoints for Telemetry, Equity Curves, and Quantitative Signal Analytics.

Exposes high-speed, non-blocking metrics to external dashboards:
- Grafana / Streamlit / Prometheus / Chart.js
- Real-time Equity Curves (HWM & Drawdown)
- Signal Snapshots & Trade Win/Loss Analysis for MLOFI/VPIN Scatter Plots
- Engine Health, Active Exposure, and Post-Loss Cooldown Status
"""

from __future__ import annotations

import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query, status

from app.core import state

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Analytics"])


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint 1: Equity Curve & Balance Series
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/equity-curve",
    summary="Get real-time equity curve time series for external dashboards",
    status_code=status.HTTP_200_OK,
)
async def get_equity_curve(
    limit: int = Query(default=1000, ge=1, le=86400, description="Number of recent data points"),
    downsample: int = Query(default=1, ge=1, le=60, description="Downsample step (e.g. 5 for 5-second interval)"),
    format: str = Query(default="array", pattern="^(array|json)$", description="Format: 'array' [ts, equity, dd] or 'json' objects"),
) -> Dict[str, Any]:
    """
    Returns the real-time equity curve recorded in the bounded ring buffer.

    NON_BLOCKING:
    - Reads directly from collections.deque in memory.
    - Zero database queries, zero pandas overhead.
    """
    tracker = getattr(state, "pnl_tracker", None)
    if tracker is None:
        now = time.time()
        return {
            "symbol": "BTC",
            "count": 0,
            "data": [[now, 10000.0, 0.0]] if format == "array" else [],
            "summary": {"initial_balance": 10000.0, "total_equity": 10000.0},
        }

    # TELEMETRY: Fetch pre-aggregated equity points
    if format == "array":
        curve_data = tracker.get_equity_curve(limit=limit, downsample_step=downsample)
    else:
        curve_data = tracker.get_equity_snapshots(limit=limit)

    return {
        "status": "success",
        "format": format,
        "count": len(curve_data),
        "data": curve_data,
        "summary": tracker.get_state(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint 2: Signal History & Trade Outcomes (For Quant Research & Scatter Plots)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/signal-history",
    summary="Get signal snapshots and trade outcomes for MLOFI/VPIN strategy evaluation",
    status_code=status.HTTP_200_OK,
)
async def get_signal_history(
    limit: int = Query(default=100, ge=1, le=2000, description="Max number of signal snapshots"),
    action: Optional[str] = Query(default=None, description="Filter action: ENTRY_LONG, ENTRY_SHORT, EXIT_TP, EXIT_SL, FLATTEN"),
    include_closed_trades: bool = Query(default=True, description="Include closed trade records with realized PnL"),
) -> Dict[str, Any]:
    """
    Returns state-of-the-world signal telemetry along with closed trade outcomes.
    Ideal for plotting scatter charts (e.g. MLOFI vs Realized PnL, or VPIN vs Drawdown).

    NON_BLOCKING: Fetched entirely from the high-speed in-memory buffer.
    """
    sig_telemetry = getattr(state, "signal_telemetry", None)
    tracker = getattr(state, "pnl_tracker", None)

    signals: List[Dict[str, Any]] = []
    if sig_telemetry is not None:
        # TELEMETRY: Pull latest decision snapshots from memory ring buffer
        signals = sig_telemetry.get_recent_signals(limit=limit, action=action)

    closed_trades: List[Dict[str, Any]] = []
    if include_closed_trades and tracker is not None:
        closed_trades = tracker.get_trade_history(limit=limit)

    return {
        "status": "success",
        "count": len(signals),
        "signals": signals,
        "closed_trades": closed_trades,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint 3: System Health, Exposure, Daily PnL & Cooldown Status
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    summary="Real-time bot operational health, active positions, daily PnL, and cooldown",
    status_code=status.HTTP_200_OK,
)
async def get_telemetry_health() -> Dict[str, Any]:
    """
    Returns instant operational state of the HFT trading bot:
    - Active position size & MtM unrealized PnL.
    - Daily PnL and current drawdown vs High Water Mark.
    - Post-loss cooldown timer remaining (anti-revenge trading guard).
    - Status of VPIN kill-switch and exchange connectivity.

    NON_BLOCKING: Pure O(1) attribute lookup in state singletons.
    """
    tracker = getattr(state, "pnl_tracker", None)
    rg = getattr(state, "risk_guard", None)
    client = getattr(state, "lighter_client", None)

    # 1. Position & Valuation Metrics
    pnl_summary = tracker.get_state() if tracker else {}
    
    # 2. Risk & Cooldown Metrics
    cooldown_remaining: float = 0.0
    kill_switch_active: bool = False
    daily_pnl_usd: float = 0.0

    if rg is not None:
        kill_switch_active = rg.kill_switch_active
        daily_pnl_usd = getattr(rg, "daily_pnl_usd", 0.0)
        last_loss = getattr(rg, "last_loss_timestamp", 0.0)
        cd_limit = getattr(rg, "post_loss_cooldown_seconds", 300)
        elapsed = time.time() - last_loss
        if elapsed < cd_limit and last_loss > 0:
            cooldown_remaining = round(cd_limit - elapsed, 1)

    # 3. Execution Client Status
    is_simulation = client.is_simulation if client else True
    mode = client.mode if client else "TESTNET"

    # Overall Bot Status
    if kill_switch_active:
        status_label = "KILL_SWITCH_ACTIVE"
    elif cooldown_remaining > 0:
        status_label = "COOLING_DOWN"
    elif not state.bot_active:
        status_label = "PAUSED"
    else:
        status_label = "RUNNING"

    # TELEMETRY: Unified Health Packet
    return {
        "status": status_label,
        "bot_active": state.bot_active,
        "is_simulation": is_simulation,
        "network_mode": mode,
        "cooldown_remaining_sec": cooldown_remaining,
        "kill_switch_active": kill_switch_active,
        "daily_pnl_usd": round(daily_pnl_usd, 4),
        "position": {
            "size": pnl_summary.get("position_size", 0.0),
            "entry_price": pnl_summary.get("avg_entry_price", 0.0),
            "mark_price": pnl_summary.get("last_mark_price", 0.0),
            "unrealized_pnl": pnl_summary.get("unrealized_pnl", 0.0),
        },
        "portfolio": {
            "total_equity": pnl_summary.get("total_equity", 10000.0),
            "realized_pnl": pnl_summary.get("realized_pnl", 0.0),
            "high_water_mark": pnl_summary.get("high_water_mark", 10000.0),
            "running_drawdown_pct": pnl_summary.get("running_drawdown_pct", 0.0),
            "max_drawdown_pct": pnl_summary.get("max_drawdown_pct", 0.0),
        },
        "system_timestamp": time.time(),
    }
