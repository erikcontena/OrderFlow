"""
Logical Clock & Resampling Engine for Multi-Exchange Tick Synchronization.

PROBLEM STATEMENT:
    Exchange timestamps are unreliable due to:
    1. Clock drift between exchange servers (can be 50-500ms off)
    2. Batching/buffering delays inside exchange matching engines
    3. Network propagation asymmetry per region

SOLUTION:
    - Ignore exchange-provided timestamps entirely.
    - Use `time.time_ns()` at local message receipt as the authoritative clock (Local Receive Time / LRT).
    - Resample all ticks into fixed-width "Logical Time Buckets" (e.g. 100ms grid).
    - Any exchange whose latest LRT falls > 2 buckets behind the current bucket is marked `is_stale`
      and excluded from that bucket's aggregation. This prevents "zombie" data from poisoning signals.

MATH:
    Bucket index for a timestamp t (ns): floor(t / bucket_ns)
    Staleness threshold: current_bucket_idx - last_seen_bucket_idx > STALE_BUCKET_THRESHOLD

COMPLEXITY:
    - `record_tick()` : O(1) — dict lookup + deque append
    - `get_bucket()` : O(E) where E is number of exchanges (typically 4-6, effectively O(1))
    - Memory: O(W * E) where W is the deque window (capped)
"""

from __future__ import annotations

import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("TimeSynchronizer")

# ─── Constants ─────────────────────────────────────────────────────────────────

NS_PER_MS: int = 1_000_000
NS_PER_S: int = 1_000_000_000

# How many buckets behind before an exchange is considered stale
STALE_BUCKET_THRESHOLD: int = 2


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ExchangeTick:
    """A single normalized tick received from one exchange.

    exchange_id  : canonical lowercase name ("binance", "bybit", …)
    local_recv_ns: `time.time_ns()` at the moment the WS message was decoded —
                   the ONLY clock used for synchronization.
    price        : last trade price (0 if LOB-only update)
    volume       : absolute volume traded (0 if LOB-only update)
    is_buyer_maker: True if the aggressor was a taker-seller (maker = buyer)
    bid_levels   : [(price, qty), …] top-N bids from this exchange
    ask_levels   : [(price, qty), …] top-N asks from this exchange
    """
    exchange_id: str
    local_recv_ns: int
    price: float
    volume: float
    is_buyer_maker: bool
    bid_levels: List[Tuple[float, float]] = field(default_factory=list)
    ask_levels: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class BucketSlot:
    """Aggregated data for a single exchange within one logical time bucket.

    is_stale: True if this exchange arrived > STALE_BUCKET_THRESHOLD buckets late.
              Stale slots are excluded from cross-exchange aggregation.
    """
    exchange_id: str
    ticks: List[ExchangeTick] = field(default_factory=list)
    total_buy_vol: float = 0.0
    total_sell_vol: float = 0.0
    last_price: float = 0.0
    bid_levels: List[Tuple[float, float]] = field(default_factory=list)
    ask_levels: List[Tuple[float, float]] = field(default_factory=list)
    is_stale: bool = False
    tick_count: int = 0


@dataclass
class LogicalBucket:
    """One completed or active time-bucket containing data for all active exchanges.

    bucket_idx  : integer index = floor(open_time_ns / bucket_ns)
    open_ns     : bucket start in nanoseconds
    close_ns    : bucket end in nanoseconds (open_ns + bucket_ns - 1)
    is_complete : True once the bucket has been sealed and is ready for analytics
    slots       : per-exchange data (only non-stale exchanges have meaningful data)
    active_exchanges: exchanges that contributed fresh (non-stale) data
    """
    bucket_idx: int
    open_ns: int
    close_ns: int
    is_complete: bool = False
    slots: Dict[str, BucketSlot] = field(default_factory=dict)
    active_exchanges: List[str] = field(default_factory=list)


# ─── TimeSynchronizer ─────────────────────────────────────────────────────────

class TimeSynchronizer:
    """
    Resamples multi-exchange async ticks into fixed Logical Time Buckets.

    Usage (called from each ingestor's on_trade / on_book callback):

        # In BinanceIngestor.on_trade:
        tick = ExchangeTick(
            exchange_id="binance",
            local_recv_ns=time.time_ns(),   # <- THE ONLY TRUSTED CLOCK
            price=price, volume=volume, is_buyer_maker=is_buyer_maker,
            bid_levels=lob.get_top_bids(5), ask_levels=lob.get_top_asks(5),
        )
        completed_bucket = time_sync.record_tick(tick)
        if completed_bucket:
            analytics_pipeline(completed_bucket)

    Parameters
    ----------
    bucket_ms : float
        Width of each logical time bucket in milliseconds (default 100ms).
        Use 500ms for slower strategies or lower-frequency data.
    history_buckets : int
        Number of past completed buckets to retain in memory.
    known_exchanges : list[str]
        All exchange IDs we expect. Used to pre-register slots and detect missing
        exchanges. Order-insensitive.
    """

    def __init__(
        self,
        bucket_ms: float = 100.0,
        history_buckets: int = 200,
        known_exchanges: Optional[List[str]] = None,
    ) -> None:
        # HFT_OPTIMIZATION: store bucket_ns as int to avoid float arithmetic in hot path
        self.bucket_ns: int = int(bucket_ms * NS_PER_MS)
        self.history_buckets = history_buckets
        self.known_exchanges: List[str] = known_exchanges or [
            "binance", "bybit", "hyperliquid", "bitget", "lighter"
        ]

        # ── State ──────────────────────────────────────────────────────────────
        # Current open (in-flight) bucket
        self._current_bucket: Optional[LogicalBucket] = None

        # Ring buffer of sealed buckets; O(1) append/rotate
        self._history: Deque[LogicalBucket] = deque(maxlen=history_buckets)

        # Per-exchange: most recent bucket_idx this exchange contributed to
        # Used for staleness detection (O(1) lookup)
        self._last_exchange_bucket: Dict[str, int] = {
            ex: -1 for ex in self.known_exchanges
        }

        # Monotonic sealing counter (for debugging / telemetry)
        self._sealed_count: int = 0

        # Last seen bucket_idx globally (the "frontier")
        self._frontier_idx: int = -1

    # ── Public API ─────────────────────────────────────────────────────────────

    def record_tick(self, tick: ExchangeTick) -> Optional[LogicalBucket]:
        """
        Ingest one tick from any exchange.

        Assigns the tick to the correct logical bucket based on `local_recv_ns`.
        If the new tick falls into a future bucket, the current bucket is sealed
        and returned as a completed `LogicalBucket` for downstream processing.

        Returns
        -------
        LogicalBucket | None
            The newly sealed bucket if a bucket boundary was crossed, else None.
        """
        # HFT_OPTIMIZATION: single integer division to find bucket index
        tick_bucket_idx: int = tick.local_recv_ns // self.bucket_ns

        # ── Bootstrap: first tick ever ─────────────────────────────────────────
        if self._current_bucket is None:
            self._current_bucket = self._new_bucket(tick_bucket_idx)
            self._frontier_idx = tick_bucket_idx

        sealed: Optional[LogicalBucket] = None

        # ── Bucket boundary crossed -> seal current, open new ─────────────────
        if tick_bucket_idx > self._current_bucket.bucket_idx:
            sealed = self._seal_bucket(self._current_bucket)
            self._history.append(sealed)
            self._sealed_count += 1
            self._current_bucket = self._new_bucket(tick_bucket_idx)
            self._frontier_idx = tick_bucket_idx

        # ── Determine if tick is stale ─────────────────────────────────────────
        # QUANT_LOGIC: An exchange is stale if it's feeding data that belongs to a
        # bucket that is > STALE_BUCKET_THRESHOLD buckets behind the frontier.
        lag_buckets: int = self._frontier_idx - tick_bucket_idx
        if lag_buckets > STALE_BUCKET_THRESHOLD:
            logger.debug(
                f"[TimeSync] Stale tick from {tick.exchange_id}: "
                f"lag={lag_buckets} buckets ({lag_buckets * self.bucket_ns / NS_PER_MS:.0f}ms)"
            )
            return None  # Stale data discarded silently

        # ── Assign tick to current bucket slot ────────────────────────────────
        self._assign_to_slot(self._current_bucket, tick)
        self._last_exchange_bucket[tick.exchange_id] = tick_bucket_idx

        return sealed  # None if no boundary crossed, else the newly sealed bucket

    def get_latest_bucket(self) -> Optional[LogicalBucket]:
        """Return the most recently sealed (complete) bucket."""
        return self._history[-1] if self._history else None

    def get_current_bucket(self) -> Optional[LogicalBucket]:
        """Return the currently open, in-progress bucket (not yet sealed)."""
        return self._current_bucket

    def get_exchange_staleness_ms(self) -> Dict[str, float]:
        """
        Returns per-exchange staleness in milliseconds relative to the frontier bucket.

        HFT_OPTIMIZATION: O(E) scan, called at telemetry intervals only (not per-tick).
        """
        now_bucket = time.time_ns() // self.bucket_ns
        result: Dict[str, float] = {}
        for ex, last_idx in self._last_exchange_bucket.items():
            lag_buckets = now_bucket - last_idx if last_idx >= 0 else 9999
            result[ex] = lag_buckets * self.bucket_ns / NS_PER_MS
        return result

    def get_telemetry(self) -> dict:
        """Snapshot of synchronizer state for dashboard/monitoring."""
        return {
            "sealed_bucket_count": self._sealed_count,
            "frontier_bucket_idx": self._frontier_idx,
            "bucket_ms": self.bucket_ns / NS_PER_MS,
            "exchange_staleness_ms": self.get_exchange_staleness_ms(),
        }

    # ── Private Methods ────────────────────────────────────────────────────────

    def _new_bucket(self, idx: int) -> LogicalBucket:
        """Construct a fresh LogicalBucket for the given index."""
        open_ns = idx * self.bucket_ns
        return LogicalBucket(
            bucket_idx=idx,
            open_ns=open_ns,
            close_ns=open_ns + self.bucket_ns - 1,
            slots={ex: BucketSlot(exchange_id=ex) for ex in self.known_exchanges},
        )

    def _assign_to_slot(self, bucket: LogicalBucket, tick: ExchangeTick) -> None:
        """
        Merge tick data into the appropriate BucketSlot.

        QUANT_LOGIC: We aggregate buy/sell volume separately per exchange within
        each bucket. This preserves per-exchange order flow imbalance BEFORE
        cross-exchange normalization is applied downstream.
        """
        # HFT_OPTIMIZATION: one dict lookup, avoid repeated key access
        if tick.exchange_id not in bucket.slots:
            bucket.slots[tick.exchange_id] = BucketSlot(exchange_id=tick.exchange_id)
        slot = bucket.slots[tick.exchange_id]

        slot.tick_count += 1
        slot.last_price = tick.price

        # Volume classification:
        # is_buyer_maker=True  -> taker was SELLER -> sell-initiated
        # is_buyer_maker=False -> taker was BUYER  -> buy-initiated
        if tick.volume > 0:
            if tick.is_buyer_maker:
                slot.total_sell_vol += tick.volume
            else:
                slot.total_buy_vol += tick.volume

        # Keep last-seen LOB snapshot from this exchange for this bucket
        if tick.bid_levels:
            slot.bid_levels = tick.bid_levels
        if tick.ask_levels:
            slot.ask_levels = tick.ask_levels

    def _seal_bucket(self, bucket: LogicalBucket) -> LogicalBucket:
        """
        Finalize a bucket: mark stale slots, collect active exchanges.

        QUANT_LOGIC: An exchange is stale for this bucket if it contributed
        zero ticks AND its last known bucket lag exceeds threshold.
        """
        active: List[str] = []
        for ex, slot in bucket.slots.items():
            last_idx = self._last_exchange_bucket.get(ex, -1)
            lag = bucket.bucket_idx - last_idx
            if lag > STALE_BUCKET_THRESHOLD or slot.tick_count == 0:
                slot.is_stale = True
            else:
                active.append(ex)

        bucket.active_exchanges = active
        bucket.is_complete = True
        return bucket
