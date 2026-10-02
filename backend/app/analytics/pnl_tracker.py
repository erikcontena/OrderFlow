"""
Real-time Non-Blocking PnL & Equity Curve Tracker for OrderFlow HFT.

Design Constraints:
- Pure O(1) complexity per market tick and execution fill.
- NON-BLOCKING: Zero disk/database I/O or pandas DataFrame conversions in the hot path.
- Memory leak prevention: Bounded ring buffers (collections.deque) with fixed capacity.
- Supports Mark-to-Market (MtM) pricing, High Water Mark (HWM), and running drawdown calculation.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List


# TELEMETRY: Compact snapshot structure stored in the equity ring buffer.
@dataclass(slots=True)
class EquitySnapshot:
    timestamp: float        # Unix epoch seconds (float)
    total_equity: float     # Initial balance + Realized PnL + Unrealized PnL
    realized_pnl: float     # Cumulative closed PnL
    unrealized_pnl: float   # Mark-to-market PnL on open inventory
    running_drawdown: float # % drawdown from High Water Mark (0.0 to 100.0)
    high_water_mark: float  # All-time peak equity
    position_size: float    # Base asset net inventory (+ Long, - Short, 0 Flat)
    entry_price: float      # Weighted average entry price of open position
    mark_price: float       # Latest aggregated mid-price


@dataclass(slots=True)
class ClosedTradeRecord:
    timestamp: float
    client_order_index: Optional[int]
    symbol: str
    side: str               # "BUY" or "SELL" (closing side)
    entry_price: float
    exit_price: float
    size: float
    realized_pnl: float
    fee: float
    holding_time_sec: float
    action: str             # e.g. "EXIT_TP", "EXIT_SL", "FLATTEN"


class PnLTracker:
    """
    Real-time Portfolio PnL and Equity Curve Engine.

    Tracks:
    1. realized_pnl: Cumulative profit/loss from closed positions.
    2. unrealized_pnl: MtM valuation on open positions vs latest aggregated mid-price.
    3. total_equity: initial_balance + realized_pnl + unrealized_pnl.
    4. running_drawdown: Percentage decline from peak equity (High Water Mark).
    5. snapshots: Fixed-capacity ring buffer (collections.deque) recording equity
       curves at 1-second resolution without memory leaks.
    """

    def __init__(
        self,
        initial_balance: float = 10000.0,
        max_snapshots: int = 86400,        # 24 hours at 1 snapshot/second
        max_trade_history: int = 2000,     # Last 2000 closed trades in RAM
        snapshot_interval_sec: float = 1.0,
    ) -> None:
        self.initial_balance: float = float(initial_balance)
        self.realized_pnl: float = 0.0
        self.position_size: float = 0.0     # + Long, - Short, 0 Flat
        self.avg_entry_price: float = 0.0
        self.position_open_time: float = 0.0
        self.last_mark_price: float = 0.0

        # High Water Mark initialized to starting capital
        self.high_water_mark: float = float(initial_balance)
        self.max_drawdown_pct: float = 0.0

        # NON_BLOCKING: Bounded ring buffers to guarantee fixed memory footprint over days
        self._snapshots: deque[EquitySnapshot] = deque(maxlen=max_snapshots)
        self._trade_history: deque[ClosedTradeRecord] = deque(maxlen=max_trade_history)

        self.snapshot_interval_sec: float = snapshot_interval_sec
        self._last_snapshot_ts: float = 0.0

        # Seed initial snapshot
        now = time.time()
        self._last_snapshot_ts = now
        self._snapshots.append(
            EquitySnapshot(
                timestamp=now,
                total_equity=self.initial_balance,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                running_drawdown=0.0,
                high_water_mark=self.initial_balance,
                position_size=0.0,
                entry_price=0.0,
                mark_price=0.0,
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Hot-Path Valuation Properties (O(1))
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def unrealized_pnl(self) -> float:
        """
        Mark-to-Market (MtM) calculation on active position.
        NON_BLOCKING: O(1) arithmetic, no pandas or allocations.
        """
        if self.position_size == 0.0 or self.last_mark_price <= 0.0 or self.avg_entry_price <= 0.0:
            return 0.0

        if self.position_size > 0.0:
            # Long position
            return (self.last_mark_price - self.avg_entry_price) * self.position_size
        else:
            # Short position
            return (self.avg_entry_price - self.last_mark_price) * abs(self.position_size)

    @property
    def total_equity(self) -> float:
        """Total portfolio equity (Initial + Realized + Unrealized)."""
        return self.initial_balance + self.realized_pnl + self.unrealized_pnl

    @property
    def running_drawdown(self) -> float:
        """
        Current drawdown percentage from High Water Mark.
        Calculated as: ((HWM - Equity) / HWM) * 100.
        """
        equity = self.total_equity
        if self.high_water_mark <= 0.0:
            return 0.0
        if equity >= self.high_water_mark:
            return 0.0
        return ((self.high_water_mark - equity) / self.high_water_mark) * 100.0

    # ──────────────────────────────────────────────────────────────────────────
    # State Updates
    # ──────────────────────────────────────────────────────────────────────────

    def update_mark_price(self, mid_price: float, timestamp: Optional[float] = None) -> None:
        """
        Updates latest mark price and samples equity curve if interval elapsed.
        Called on every book/trade event in the hot path.

        NON_BLOCKING: Runs in O(1) time without blocking event loop.
        """
        if mid_price <= 0.0:
            return

        self.last_mark_price = mid_price
        ts = timestamp if timestamp is not None else time.time()

        # Update High Water Mark
        current_eq = self.total_equity
        if current_eq > self.high_water_mark:
            self.high_water_mark = current_eq

        # Update Max Drawdown seen
        dd = self.running_drawdown
        if dd > self.max_drawdown_pct:
            self.max_drawdown_pct = dd

        # TELEMETRY: Periodic non-blocking ring-buffer snapshot
        if (ts - self._last_snapshot_ts) >= self.snapshot_interval_sec:
            self._record_snapshot(ts, current_eq, dd)

    def record_fill(
        self,
        side: str,
        price: float,
        size: float,
        fee: float = 0.0,
        timestamp: Optional[float] = None,
        client_order_index: Optional[int] = None,
        symbol: str = "BTCUSDT",
        action: str = "EXECUTION",
    ) -> Optional[ClosedTradeRecord]:
        """
        Records an execution fill from the execution engine (Lighter).
        Handles:
        - Opening new position.
        - Scaling into existing position (weighted average entry price).
        - Partially or fully closing position (realizing PnL).
        - Flipping position from Long to Short or vice versa.

        NON_BLOCKING: O(1) position math.

        Returns
        -------
        ClosedTradeRecord if a position was closed/reduced, else None.
        """
        if size <= 0.0 or price <= 0.0:
            return None

        ts = timestamp if timestamp is not None else time.time()
        side_upper = side.upper()
        closed_record: Optional[ClosedTradeRecord] = None

        # Determine incoming direction: + for BUY, - for SELL
        incoming_delta = size if side_upper == "BUY" else -size

        # Case 1: Currently Flat -> Open new position
        if abs(self.position_size) < 1e-8:
            self.position_size = incoming_delta
            self.avg_entry_price = price
            self.position_open_time = ts

        # Case 2: Adding to existing position in same direction
        elif (self.position_size > 0 and incoming_delta > 0) or (self.position_size < 0 and incoming_delta < 0):
            total_size = abs(self.position_size) + size
            self.avg_entry_price = (
                (abs(self.position_size) * self.avg_entry_price) + (size * price)
            ) / total_size
            self.position_size += incoming_delta

        # Case 3: Opposite side trade -> Reducing, Closing, or Flipping
        else:
            current_abs = abs(self.position_size)
            closed_size = min(current_abs, size)
            remaining_after_close = current_abs - closed_size

            # Compute realized PnL on the closed portion
            if self.position_size > 0:
                # Closing Long with SELL
                trade_pnl = (price - self.avg_entry_price) * closed_size - fee
            else:
                # Closing Short with BUY
                trade_pnl = (self.avg_entry_price - price) * closed_size - fee

            self.realized_pnl += trade_pnl
            holding_time = max(0.0, ts - self.position_open_time)

            # TELEMETRY: Record closed trade metrics for post-trade analysis
            closed_record = ClosedTradeRecord(
                timestamp=ts,
                client_order_index=client_order_index,
                symbol=symbol,
                side=side_upper,
                entry_price=self.avg_entry_price,
                exit_price=price,
                size=closed_size,
                realized_pnl=round(trade_pnl, 4),
                fee=round(fee, 6),
                holding_time_sec=round(holding_time, 2),
                action=action,
            )
            self._trade_history.append(closed_record)

            # Check if there is an excess size flipping the position
            flipped_size = size - closed_size
            if flipped_size > 1e-8:
                # Position flipped
                self.position_size = flipped_size if side_upper == "BUY" else -flipped_size
                self.avg_entry_price = price
                self.position_open_time = ts
            elif remaining_after_close > 1e-8:
                # Position partially closed in same direction
                self.position_size = (
                    remaining_after_close if self.position_size > 0 else -remaining_after_close
                )
            else:
                # Position completely flat
                self.position_size = 0.0
                self.avg_entry_price = 0.0
                self.position_open_time = 0.0

        # Update peak equity and drawdown after trade fill
        current_eq = self.total_equity
        if current_eq > self.high_water_mark:
            self.high_water_mark = current_eq
        dd = self.running_drawdown
        if dd > self.max_drawdown_pct:
            self.max_drawdown_pct = dd

        # Force a snapshot at the moment of fill
        self._record_snapshot(ts, current_eq, dd)
        return closed_record

    def _record_snapshot(self, ts: float, equity: float, drawdown: float) -> None:
        """Internal helper to append snapshot into bounded ring buffer."""
        # NON_BLOCKING: deque.append on maxlen deque automatically drops oldest item (O(1))
        self._last_snapshot_ts = ts
        self._snapshots.append(
            EquitySnapshot(
                timestamp=ts,
                total_equity=round(equity, 4),
                realized_pnl=round(self.realized_pnl, 4),
                unrealized_pnl=round(self.unrealized_pnl, 4),
                running_drawdown=round(drawdown, 4),
                high_water_mark=round(self.high_water_mark, 4),
                position_size=round(self.position_size, 6),
                entry_price=round(self.avg_entry_price, 2),
                mark_price=round(self.last_mark_price, 2),
            )
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Telemetry Query Interfaces (Non-blocking memory reads)
    # ──────────────────────────────────────────────────────────────────────────

    def get_equity_curve(self, limit: int = 1000, downsample_step: int = 1) -> List[List[Any]]:
        """
        Returns equity curve array: [[timestamp, total_equity, running_drawdown], ...]
        Optimized for direct serialization into Grafana/Streamlit/TradingView line charts.

        NON_BLOCKING: Memory slice only, zero disk or database overhead.
        """
        snapshots = list(self._snapshots)
        if not snapshots:
            now = time.time()
            return [[now, self.initial_balance, 0.0]]

        # Optional slicing and downsampling to maintain low bandwidth
        selected = snapshots[-limit:] if limit > 0 else snapshots
        if downsample_step > 1:
            selected = selected[::downsample_step]

        return [
            [s.timestamp, s.total_equity, s.running_drawdown]
            for s in selected
        ]

    def get_equity_snapshots(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Returns list of rich EquitySnapshot dictionaries."""
        snapshots = list(self._snapshots)
        selected = snapshots[-limit:] if limit > 0 else snapshots
        return [asdict(s) for s in selected]

    def get_trade_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Returns closed trades history for Win/Loss analysis."""
        trades = list(self._trade_history)
        selected = trades[-limit:] if limit > 0 else trades
        return [asdict(t) for t in reversed(selected)]

    def get_state(self) -> Dict[str, Any]:
        """Provides instant summary of the portfolio health and PnL."""
        eq = self.total_equity
        return {
            "initial_balance": self.initial_balance,
            "total_equity": round(eq, 2),
            "realized_pnl": round(self.realized_pnl, 4),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "running_drawdown_pct": round(self.running_drawdown, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "high_water_mark": round(self.high_water_mark, 2),
            "position_size": round(self.position_size, 6),
            "avg_entry_price": round(self.avg_entry_price, 2),
            "last_mark_price": round(self.last_mark_price, 2),
            "closed_trades_count": len(self._trade_history),
            "snapshots_recorded": len(self._snapshots),
        }
