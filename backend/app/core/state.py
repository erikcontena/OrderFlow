"""
Global application state for the OrderFlow HFT Engine.

Architecture:
    TimeSynchronizer  -> resamples async multi-exchange ticks into 100ms logical buckets
    VolumeNormalizer  -> computes Z-scores (Welford O(1)), RVOL, market-share weights per bucket
    handle_trade()    -> central dispatcher: stamps local receive time, feeds normalizer,
                         then updates VPIN / Footprint / Risk with normalized context
"""
import asyncio
import logging
import time
from collections import deque
from typing import Optional, Set

from fastapi import WebSocket

from app.analytics.orderbook import LimitOrderBook
from app.analytics.vpin import VPINEngine
from app.analytics.mlofi import MLOFIEngine
from app.analytics.footprint import FootprintAggregator
from app.analytics.normalizer import VolumeNormalizer, NormalizationResult
from app.ingestion.time_sync import TimeSynchronizer, ExchangeTick
from app.execution.lighter_client import LighterExecutionClient
from app.execution.risk_guard import RiskGuard
from app.analytics.pnl_tracker import PnLTracker
from app.services.signal_logger import SignalTelemetry
from app.core.config import global_bot_config

logger = logging.getLogger("OrderFlowApp")

# ── Bot State ──────────────────────────────────────────────────────────────────
bot_active = True
bot_logs = deque(maxlen=20)

# State-driven Order & Position Tracking
active_order_id: Optional[int] = None
active_order_price: Optional[float] = None
active_order_side: Optional[str] = None
last_entry_fill_time: float = 0.0
last_close_fill_time: float = 0.0

# Active Position Tracking for Dynamic SL/TP & Minimum Hold Time
active_position_side: Optional[str] = None       # "BUY" (Long) or "SELL" (Short)
active_position_entry_price: float = 0.0
active_position_size: float = 0.0
active_position_sl: float = 0.0
active_position_tp: float = 0.0

def log_bot_activity(message: str, level: str = "info"):
    try:
        timestamp = asyncio.get_event_loop().time()
    except RuntimeError:
        timestamp = time.time()
    bot_logs.appendleft({"timestamp": timestamp, "message": message, "level": level})

# ── Background Tasks Reference (Fire & Forget) ─────────────────────────────────
_background_tasks = set()

def fire_and_forget(coro):
    """Safely launch fire-and-forget coroutine without risk of premature GC."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

# ── Orderbooks per venue ───────────────────────────────────────────────────────
books = {
    "binance": LimitOrderBook("Binance", global_bot_config.symbol),
    "hyperliquid": LimitOrderBook("Hyperliquid", global_bot_config.coin),
    "bitget": LimitOrderBook("Bitget", global_bot_config.symbol),
    "bybit": LimitOrderBook("Bybit", global_bot_config.symbol),
    "lighter": LimitOrderBook("Lighter", global_bot_config.symbol),
}

# ── Analytics Engines ──────────────────────────────────────────────────────────
vpin_engine = VPINEngine(
    base_bucket_size=2.0,
    window_size=50,
    student_t_df=4,
    toxicity_threshold=global_bot_config.vpin_toxicity_threshold,
)
mlofi_engine = MLOFIEngine(depth_levels=5, decay_lambda=0.4)
footprint_aggregator = FootprintAggregator(timeframe_seconds=5.0, max_bars=30)

# ── HFT Normalization & Time Synchronization Layer ─────────────────────────────
# TimeSynchronizer: resamples async multi-exchange ticks into 100ms logical buckets.
# Ignores exchange timestamps entirely — uses local receive time (time.time_ns()).
# HFT_OPTIMIZATION: O(1) per tick via integer division + dict lookup
time_sync = TimeSynchronizer(
    bucket_ms=100.0,          # 100ms logical buckets
    history_buckets=200,      # ~20 seconds of sealed bucket history
    known_exchanges=["binance", "bybit", "hyperliquid", "bitget", "lighter"],
)

# VolumeNormalizer: Welford online Z-score + RVOL + market-share weights.
# All computations O(1) per tick, O(W/N) amortized for window eviction.
volume_normalizer = VolumeNormalizer(
    exchange_ids=["binance", "bybit", "hyperliquid", "bitget", "lighter"],
    zscore_window_sec=30 * 60.0,    # 30-minute rolling Z-score window per exchange
    market_share_window_sec=60.0,   # 60-second rolling market-share window
)

# Latest normalization result — updated every sealed 100ms bucket.
# QUANT_LOGIC: Read by orchestrator to pass z_scores to MLOFI and
# market_weights to footprint aggregation.
norm_result: Optional[NormalizationResult] = None

# ── Execution & Risk ───────────────────────────────────────────────────────────
lighter_client = LighterExecutionClient()
risk_guard = RiskGuard(
    execution_client=lighter_client,
    vpin_cutoff_threshold=global_bot_config.vpin_toxicity_threshold,
)

# ── Telemetry & PnL Tracking ──────────────────────────────────────────────────
# NON_BLOCKING: In-memory O(1) PnL calculation & high-throughput async signal queue
pnl_tracker = PnLTracker(initial_balance=10000.0)
signal_telemetry = SignalTelemetry()

# ── Connected Web Dashboard Clients ───────────────────────────────────────────
connected_websockets: Set[WebSocket] = set()

# ── Ingestors (initialized after state is set up) ─────────────────────────────
ingestors = {}


# ── Central Trade Handler ──────────────────────────────────────────────────────

def handle_trade(
    price: float,
    volume: float,
    is_buyer_maker: bool,
    exchange_id: str = "unknown",
) -> None:
    """
    Central trade handler — called from every ingestor's on_trade callback.

    Integration Flow:
        1. Stamp with local receive time (time.time_ns) — NOT exchange timestamp.
           Exchange clocks drift. LRT is the only trusted reference.
        2. Build ExchangeTick and record into TimeSynchronizer.
           If a 100ms logical bucket just sealed, returns it for normalization.
        3. If bucket sealed:
           a. Aggregate per-exchange volumes from the sealed bucket.
           b. Run VolumeNormalizer.process_bucket() -> Z-scores, RVOL, market weights.
           c. Apply RVOL multiplier to VPIN bucket_size dynamically.
              (High RVOL = busy market = larger bucket to prevent VPIN noise.)
        4. Run VPIN, Footprint CVD, and Risk (always per-tick for time-sensitivity).
        5. Lightweight per-tick market-share update (runs in O(1), separate from Z-score).

    Parameters
    ----------
    price : float
        Last traded price.
    volume : float
        Trade size in base asset (BTC).
    is_buyer_maker : bool
        True if the aggressor was a SELLER (Binance/Lighter convention).
    exchange_id : str
        Canonical exchange name: "binance", "bybit", "hyperliquid", "bitget", "lighter".
    """
    global norm_result

    # STEP 1: Local Receive Time — the single authoritative clock
    # HFT_OPTIMIZATION: time.time_ns() is a single syscall, O(1)
    local_recv_ns: int = time.time_ns()

    # STEP 2: Build normalized tick and feed to TimeSynchronizer
    tick = ExchangeTick(
        exchange_id=exchange_id,
        local_recv_ns=local_recv_ns,
        price=price,
        volume=volume,
        is_buyer_maker=is_buyer_maker,
        # NOTE: bid_levels/ask_levels are populated separately in on_book callbacks
        # to avoid the LOB copy cost on every single trade tick.
    )
    sealed_bucket = time_sync.record_tick(tick)

    # STEP 3: Per-bucket normalization (triggered when a 100ms bucket seals)
    # QUANT_LOGIC: Normalization runs at bucket granularity to amortize Welford
    # updates across all ticks in the 100ms window, not per individual tick.
    if sealed_bucket is not None:
        # Collect non-stale exchange volumes from the sealed bucket
        bucket_vols = {
            ex: slot.total_buy_vol + slot.total_sell_vol
            for ex, slot in sealed_bucket.slots.items()
            if not slot.is_stale
        }
        sealed_time_s = sealed_bucket.close_ns / 1_000_000_000.0
        norm_result = volume_normalizer.process_bucket(bucket_vols, recv_time_s=sealed_time_s)

        # Apply RVOL to VPIN bucket size
        # QUANT_LOGIC: bucket_size = base * RVOL
        #   RVOL=1.0 -> normal market, use base bucket size
        #   RVOL=2.0 -> 2x volume vs historical average -> double bucket size
        #               so VPIN doesn't fire on normal high-volume periods
        #   RVOL=0.5 -> thin market -> shrink bucket to stay sensitive
        vpin_engine.bucket_size = round(
            vpin_engine.base_bucket_size * norm_result.rvol_multiplier, 4
        )

    # STEP 4: Core per-tick analytics (must run every tick for accuracy)
    # Update VPIN volume clock
    vpin_engine.process_trade(price, volume, is_taker_buyer=(not is_buyer_maker))
    # Update Footprint & CVD
    footprint_aggregator.process_trade(price, volume, is_buyer_maker)
    # Async risk check (fire-and-forget, doesn't block the hot path)
    fire_and_forget(risk_guard.evaluate_vpin(vpin_engine.current_vpin))

    # STEP 5: Lightweight per-tick market-share update
    # HFT_OPTIMIZATION: This only updates the running volume sum (O(1)), not the
    # full Z-score computation which happens at bucket seal time.
    volume_normalizer.process_trade(exchange_id, volume, recv_time_s=local_recv_ns / 1_000_000_000.0)

    # STEP 6: Real-time Mark-to-Market PnL & Equity Curve update
    # NON_BLOCKING: O(1) arithmetic updating position MtM and 1s-sampled ring buffer
    pnl_tracker.update_mark_price(price, timestamp=local_recv_ns / 1_000_000_000.0)
