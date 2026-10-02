import asyncio
import logging
from collections import deque
from typing import Set

from fastapi import WebSocket

from app.analytics.orderbook import LimitOrderBook
from app.analytics.vpin import VPINEngine
from app.analytics.mlofi import MLOFIEngine
from app.analytics.footprint import FootprintAggregator
from app.execution.lighter_client import LighterExecutionClient
from app.execution.risk_guard import RiskGuard
from app.core.config import global_bot_config

logger = logging.getLogger("OrderFlowApp")

# Bot State
bot_active = True
bot_logs = deque(maxlen=20)

def log_bot_activity(message: str, level: str = "info"):
    try:
        timestamp = asyncio.get_event_loop().time()
    except RuntimeError:
        import time
        timestamp = time.time()
    bot_logs.appendleft({"timestamp": timestamp, "message": message, "level": level})

# Background Tasks Reference (Fire & Forget)
_background_tasks = set()

def fire_and_forget(coro):
    """Safely launch fire-and-forget coroutine without risk of premature GC."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

# Orderbooks per venue
books = {
    "binance": LimitOrderBook("Binance", global_bot_config.symbol),
    "hyperliquid": LimitOrderBook("Hyperliquid", global_bot_config.coin),
    "bitget": LimitOrderBook("Bitget", global_bot_config.symbol),
    "bybit": LimitOrderBook("Bybit", global_bot_config.symbol),
    "lighter": LimitOrderBook("Lighter", global_bot_config.symbol),
}

# Analytics Engines
vpin_engine = VPINEngine(bucket_size=2.0, window_size=50, student_t_df=4, toxicity_threshold=global_bot_config.vpin_toxicity_threshold)
mlofi_engine = MLOFIEngine(depth_levels=5, decay_lambda=0.4)
footprint_aggregator = FootprintAggregator(timeframe_seconds=5.0, max_bars=30)

# Execution & Risk
lighter_client = LighterExecutionClient()
risk_guard = RiskGuard(execution_client=lighter_client, vpin_cutoff_threshold=global_bot_config.vpin_toxicity_threshold)

# Connected Web Dashboard Clients
connected_websockets: Set[WebSocket] = set()

# Ingestors (to be initialized after state is set up)
ingestors = {}

def handle_trade(price: float, volume: float, is_buyer_maker: bool):
    # Update VPIN
    vpin_engine.process_trade(price, volume, is_taker_buyer=(not is_buyer_maker))
    # Update Footprint & CVD
    footprint_aggregator.process_trade(price, volume, is_buyer_maker)
    # Check risk
    fire_and_forget(risk_guard.evaluate_vpin(vpin_engine.current_vpin))
