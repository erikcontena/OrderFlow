import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import state
from app.db import init_db
from app.api.routes.api_routes import router as api_router
from app.api.routes.ws_routes import ws_router
from app.api.telemetry_endpoints import router as telemetry_router
from app.services.orchestrator import (
    telemetry_broadcast_loop,
    autonomous_bot_loop,
    analytics_snapshot_loop
)

from app.ingestion.binance import BinanceIngestor
from app.ingestion.hyperliquid import HyperliquidIngestor
from app.ingestion.bitget import BitgetIngestor
from app.ingestion.bybit import BybitIngestor
from app.ingestion.lighter import LighterIngestor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("OrderFlowApp")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing OrderFlow Database & Backend Engines...")
    await init_db()
    
    from app.db import DBRepository
    from app.core.config import global_bot_config
    
    # Load settings from database
    db_config = await DBRepository.get_app_config()
    if db_config:
        global_bot_config.leverage = db_config.get("leverage", 1.0)
        global_bot_config.risk_per_trade_pct = db_config.get("risk_per_trade_pct", 0.01)
        global_bot_config.tp_percentage = db_config.get("tp_percentage", 0.05)
        global_bot_config.sl_percentage = db_config.get("sl_percentage", 0.02)
        global_bot_config.max_active_positions = db_config.get("max_active_positions", 3)
        global_bot_config.vpin_toxicity_threshold = db_config.get("vpin_toxicity_threshold", 0.85)
        global_bot_config.mlofi_imbalance_threshold = db_config.get("mlofi_imbalance_threshold", 0.7)
        
        state.bot_active = db_config.get("bot_active", False)
        state.vpin_engine.toxicity_threshold = global_bot_config.vpin_toxicity_threshold
        state.risk_guard.vpin_cutoff_threshold = global_bot_config.vpin_toxicity_threshold
        
        state.lighter_client.leverage = global_bot_config.leverage
        state.lighter_client.is_simulation = db_config.get("is_paper_trading", True)
        
        # Apply correct account/api indexes based on saved network mode
        network_mode = db_config.get("network_mode", "TESTNET").upper()
        if network_mode == "MAINNET":
            raw_acc = db_config.get("mainnet_account_index", 0)
            state.lighter_client.account_index = int(raw_acc) if str(raw_acc).isdigit() else raw_acc
            state.lighter_client.api_key_index = int(db_config.get("mainnet_api_key_index", 4))
        else:
            raw_acc = db_config.get("testnet_account_index", 0)
            state.lighter_client.account_index = int(raw_acc) if str(raw_acc).isdigit() else raw_acc
            state.lighter_client.api_key_index = int(db_config.get("testnet_api_key_index", 4))
        
        state.lighter_client.switch_mode(network_mode)
        logger.info(f"Loaded config from DB: Mode={network_mode}, BotActive={state.bot_active}, Paper={state.lighter_client.is_simulation}")
    # Initialize ingestors here since they depend on state.handle_trade and state.lighter_client.mode
    # Build per-exchange on_trade callbacks that include exchange_id
    # HFT_OPTIMIZATION: lambda captures exchange_id at definition time — zero overhead per call
    def make_trade_handler(ex_id: str):
        return lambda price, vol, is_buyer_maker: state.handle_trade(price, vol, is_buyer_maker, exchange_id=ex_id)

    state.ingestors = {
        "binance":      BinanceIngestor(symbol=state.books["binance"].symbol,       orderbook=state.books["binance"],      on_trade=make_trade_handler("binance")),
        "hyperliquid":  HyperliquidIngestor(coin=state.books["hyperliquid"].symbol, orderbook=state.books["hyperliquid"],  on_trade=make_trade_handler("hyperliquid")),
        "bitget":       BitgetIngestor(symbol=state.books["bitget"].symbol,         orderbook=state.books["bitget"],       on_trade=make_trade_handler("bitget")),
        "bybit":        BybitIngestor(symbol=state.books["bybit"].symbol,           orderbook=state.books["bybit"],        on_trade=make_trade_handler("bybit")),
        "lighter":      LighterIngestor(symbol="BTC", orderbook=state.books["lighter"], on_trade=make_trade_handler("lighter"), mode=state.lighter_client.mode),
    }

    for ing in state.ingestors.values():
        await ing.start()

    # Start non-blocking telemetry background disk writer
    await state.signal_telemetry.start()
        
    broadcast_task = asyncio.create_task(telemetry_broadcast_loop())
    bot_task = asyncio.create_task(autonomous_bot_loop())
    snapshot_task = asyncio.create_task(analytics_snapshot_loop())
    
    yield
    
    logger.info("Shutting down OrderFlow Engines...")
    broadcast_task.cancel()
    bot_task.cancel()
    snapshot_task.cancel()
    await state.signal_telemetry.stop()
    for ing in state.ingestors.values():
        await ing.stop()
    await state.lighter_client.aclose()
    from app.db.session import engine
    await engine.dispose()
    logger.info("OrderFlow shutdown complete.")

app = FastAPI(title="OrderFlow HFT Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(telemetry_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
