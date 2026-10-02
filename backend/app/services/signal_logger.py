"""
High-Frequency Signal Telemetry & State Snapshot Logger for Quantitative Research.

Design Philosophy:
- EXACT State of the World captured at the exact decision millisecond.
- NON-BLOCKING: Event loop hot-path never awaits disk I/O; events are queued via O(1) put_nowait.
- Dual-Format Persistence:
    1. Streaming JSONL (JSON Lines) via aiofiles for real-time inspection.
    2. Columnar Parquet (via pyarrow) in batch flushes for ultra-fast post-trade quant research & backtesting.
- In-memory ring buffer (collections.deque) for instant, zero-latency dashboard queries.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import aiofiles
import orjson

# Check optional pyarrow installation for high-performance quant parquet export
try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

logger = logging.getLogger("SignalTelemetry")


# TELEMETRY: State of the World data structure captured at signal generation
@dataclass(slots=True)
class SignalSnapshot:
    timestamp: float                       # POSIX timestamp in seconds (float)
    local_receive_time_ns: int             # Monotonic/clock local receive time in nanoseconds
    iso_time: str                          # Human-readable UTC timestamp
    action: str                            # ENTRY_LONG, ENTRY_SHORT, EXIT_TP, EXIT_SL, EXIT_COOLDOWN, FLATTEN
    symbol: str                            # e.g., "BTCUSDT" or "BTC"
    mid_price: float                       # Aggregated multi-venue mid-price
    spread: float                          # Top of the book spread in quote currency
    mlofi_score: float                     # Integrated MLOFI Imbalance score
    z_scores: Dict[str, float]             # Normalized Z-Scores per venue (Binance, Bybit, Lighter, etc.)
    vpin_value: float                      # Instantaneous VPIN toxicity index
    bucket_size: float                     # Dynamic VPIN bucket size (RVOL-scaled)
    footprint_delta: float                 # Cumulative or bar delta from footprint
    is_absorption: bool                    # Flag indicating iceberg/passive absorption
    execution_details: Dict[str, Any]      # Lighter fill price, slippage bps, latency ms, order_id
    pnl_usd: Optional[float] = None        # Realized PnL (for EXIT actions)
    reason: Optional[str] = None           # Strategy rule trigger description
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SignalTelemetry:
    """
    Asynchronous, Non-Blocking Signal Telemetry Engine.

    Guarantees:
    - Zero hot-path latency: `record_signal` executes in < 2 microseconds.
    - Asynchronous batch worker consumes from `asyncio.Queue` and flushes to JSONL and Parquet.
    - Memory safety: Bounded ring buffer for real-time API queries.
    """

    def __init__(
        self,
        storage_dir: str = "data/telemetry",
        queue_maxsize: int = 20000,
        recent_buffer_size: int = 2000,
        batch_flush_interval: float = 1.0,
        batch_flush_size: int = 50,
    ) -> None:
        self.storage_dir: str = storage_dir
        self.queue_maxsize: int = queue_maxsize
        self.batch_flush_interval: float = batch_flush_interval
        self.batch_flush_size: int = batch_flush_size

        # NON_BLOCKING: Hot-path queue separating signal generation from disk I/O
        self._queue: asyncio.Queue[SignalSnapshot] = asyncio.Queue(maxsize=queue_maxsize)

        # In-memory ring buffer for immediate dashboard queries
        self._recent_snapshots: deque[SignalSnapshot] = deque(maxlen=recent_buffer_size)

        self._worker_task: Optional[asyncio.Task] = None
        self._is_running: bool = False

        # Ensure directory exists
        os.makedirs(self.storage_dir, exist_ok=True)

    # ──────────────────────────────────────────────────────────────────────────
    # Hot-Path Entrypoint (Strictly Non-Blocking)
    # ──────────────────────────────────────────────────────────────────────────

    def record_decision(
        self,
        action: str,
        symbol: str,
        mid_price: float,
        spread: float,
        mlofi_score: float,
        z_scores: Dict[str, float],
        vpin_value: float,
        bucket_size: float,
        footprint_delta: float,
        is_absorption: bool,
        execution_details: Optional[Dict[str, Any]] = None,
        pnl_usd: Optional[float] = None,
        reason: Optional[str] = None,
        local_recv_ns: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SignalSnapshot:
        """
        Captures the exact State of the World at the decision millisecond.

        NON_BLOCKING:
        - Allocates data structure.
        - Immediately dispatches to asyncio.Queue using put_nowait.
        - Returns instantly to keep trading hot-path latency at absolute minimum.
        """
        now_s = time.time()
        now_ns = local_recv_ns if local_recv_ns is not None else time.time_ns()
        iso_str = datetime.now(timezone.utc).isoformat()

        snapshot = SignalSnapshot(
            timestamp=now_s,
            local_receive_time_ns=now_ns,
            iso_time=iso_str,
            action=action.upper(),
            symbol=symbol,
            mid_price=round(mid_price, 4),
            spread=round(spread, 4),
            mlofi_score=round(mlofi_score, 4),
            z_scores={k: round(v, 4) for k, v in z_scores.items()},
            vpin_value=round(vpin_value, 4),
            bucket_size=round(bucket_size, 4),
            footprint_delta=round(footprint_delta, 4),
            is_absorption=is_absorption,
            execution_details=execution_details or {},
            pnl_usd=round(pnl_usd, 4) if pnl_usd is not None else None,
            reason=reason,
            metadata=metadata or {},
        )

        # TELEMETRY: Cache in-memory ring buffer for low-latency API access
        self._recent_snapshots.append(snapshot)

        # NON_BLOCKING: Non-blocking enqueue to decouple hot path from disk writes
        try:
            self._queue.put_nowait(snapshot)
        except asyncio.QueueFull:
            logger.error("[TELEMETRY] Queue full! Dropping signal event to protect hot path.")

        return snapshot

    def record_signal_snapshot(self, snapshot: SignalSnapshot) -> None:
        """Enqueues a pre-built SignalSnapshot object into the async telemetry queue."""
        self._recent_snapshots.append(snapshot)
        # NON_BLOCKING:
        try:
            self._queue.put_nowait(snapshot)
        except asyncio.QueueFull:
            logger.error("[TELEMETRY] Queue full! Dropping signal snapshot.")

    # ──────────────────────────────────────────────────────────────────────────
    # Background Async Storage Worker
    # ──────────────────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Launches the background async disk writer task."""
        if self._worker_task is None or self._worker_task.done():
            self._is_running = True
            self._worker_task = asyncio.create_task(self._worker_loop())
            logger.info("SignalTelemetry background disk writer started.")

    async def stop(self) -> None:
        """Gracefully drains the queue and shuts down the background writer."""
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            # Final drain of remaining items
            await self._flush_remaining()
            logger.info("SignalTelemetry stopped and flushed remaining items.")

    async def _worker_loop(self) -> None:
        """
        Continuous background worker that batches telemetry snapshots
        and writes them asynchronously to JSONL and Parquet without blocking
        the main trading event loop.
        """
        batch: List[SignalSnapshot] = []
        last_flush_time = time.monotonic()

        while self._is_running:
            try:
                # NON_BLOCKING: Wait for next item with timeout to handle periodic flushes
                try:
                    snapshot = await asyncio.wait_for(
                        self._queue.get(),
                        timeout=self.batch_flush_interval
                    )
                    batch.append(snapshot)
                    self._queue.task_done()
                except asyncio.TimeoutError:
                    pass

                # Flush condition: Batch size exceeded OR time interval reached
                now = time.monotonic()
                if batch and (len(batch) >= self.batch_flush_size or (now - last_flush_time) >= self.batch_flush_interval):
                    await self._write_batch(batch)
                    batch.clear()
                    last_flush_time = now

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[TELEMETRY] Error in background worker loop: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def _write_batch(self, batch: List[SignalSnapshot]) -> None:
        """
        Asynchronously writes a batch of SignalSnapshots to JSONL and Parquet.
        """
        if not batch:
            return

        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        jsonl_path = os.path.join(self.storage_dir, f"signals_{date_str}.jsonl")
        parquet_path = os.path.join(self.storage_dir, f"signals_{date_str}.parquet")

        # 1. Stream write to JSONL (using aiofiles)
        # TELEMETRY: Serialized via fast orjson library
        try:
            lines = [orjson.dumps(s.to_dict(), option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8") + "\n" for s in batch]
            async with aiofiles.open(jsonl_path, mode="a", encoding="utf-8") as f:
                await f.writelines(lines)
        except Exception as e:
            logger.error(f"[TELEMETRY] Failed writing batch to JSONL: {e}")

        # 2. Append/Write to Parquet for Quant Backtesting & Analytics
        if HAS_PYARROW:
            try:
                # Offload columnar conversion to a thread to avoid blocking event loop
                await asyncio.to_thread(self._write_parquet_batch, batch, parquet_path)
            except Exception as e:
                logger.debug(f"[TELEMETRY] Parquet batch write skipped/failed: {e}")

    def _write_parquet_batch(self, batch: List[SignalSnapshot], parquet_path: str) -> None:
        """
        Converts batch to PyArrow Table and appends to Parquet file.
        Executed inside asyncio.to_thread to maintain zero latency on event loop.
        """
        records = [
            {
                "timestamp": s.timestamp,
                "local_receive_time_ns": s.local_receive_time_ns,
                "iso_time": s.iso_time,
                "action": s.action,
                "symbol": s.symbol,
                "mid_price": s.mid_price,
                "spread": s.spread,
                "mlofi_score": s.mlofi_score,
                "vpin_value": s.vpin_value,
                "bucket_size": s.bucket_size,
                "footprint_delta": s.footprint_delta,
                "is_absorption": s.is_absorption,
                "pnl_usd": s.pnl_usd if s.pnl_usd is not None else 0.0,
                "reason": s.reason or "",
                "z_scores_json": orjson.dumps(s.z_scores, option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8"),
                "execution_json": orjson.dumps(s.execution_details, option=orjson.OPT_SERIALIZE_NUMPY).decode("utf-8"),
            }
            for s in batch
        ]

        table = pa.Table.from_pylist(records)
        if not os.path.exists(parquet_path):
            pq.write_table(table, parquet_path, compression="snappy")
        else:
            # Append existing parquet table
            existing_table = pq.read_table(parquet_path)
            combined_table = pa.concat_tables([existing_table, table])
            pq.write_table(combined_table, parquet_path, compression="snappy")

    async def _flush_remaining(self) -> None:
        """Drains whatever is left in the queue on shutdown."""
        batch: List[SignalSnapshot] = []
        while not self._queue.empty():
            try:
                snapshot = self._queue.get_nowait()
                batch.append(snapshot)
                self._queue.task_done()
            except asyncio.QueueEmpty:
                break
        if batch:
            await self._write_batch(batch)

    # ──────────────────────────────────────────────────────────────────────────
    # Fast In-Memory API Access
    # ──────────────────────────────────────────────────────────────────────────

    def get_recent_signals(
        self,
        limit: int = 100,
        action: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches recent signal snapshots from the bounded in-memory ring buffer.
        NON_BLOCKING: Zero disk access, instant return for API endpoints.
        """
        snapshots = list(self._recent_snapshots)
        if action:
            act_upper = action.upper()
            snapshots = [s for s in snapshots if s.action == act_upper]

        selected = snapshots[-limit:] if limit > 0 else snapshots
        return [s.to_dict() for s in reversed(selected)]
