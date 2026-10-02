import asyncio
import logging
from fastapi import APIRouter, HTTPException

from app.core import state
from app.db import DBRepository
from app.models.schemas import (
    OrderRequest, KillSwitchRequest, BotToggleRequest,
    ModeSwitchRequest, AccountRequest, PaperTradingRequest,
    LeverageRequest, ApiKeyRequest
)
from app.core.config import global_bot_config, BotConfig

logger = logging.getLogger("OrderFlowApp")
router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "ok", "app": "OrderFlow Quantitative Trading Engine"}

@router.get("/history/orders")
async def get_history_orders(limit: int = 50):
    return await DBRepository.get_recent_orders(limit=limit)

@router.get("/history/trades")
async def get_history_trades(limit: int = 50):
    live_trades = await state.lighter_client.get_live_trades(limit=limit)
    if live_trades:
        return live_trades
    return await DBRepository.get_recent_trades(limit=limit)

@router.get("/history/analytics")
async def get_history_analytics(limit: int = 100):
    return await DBRepository.get_analytics_history(limit=limit)

@router.get("/state")
async def get_state():
    return {
        "orderbooks": {k: b.to_dict(depth=10) for k, b in state.books.items()},
        "vpin": state.vpin_engine.to_dict(),
        "mlofi": state.mlofi_engine.update(state.books["binance"].get_top_bids(5), state.books["binance"].get_top_asks(5)),
        "cvd": state.footprint_aggregator.get_cvd_summary(),
        "footprint_bars": state.footprint_aggregator.get_recent_bars(count=8),
        "execution": state.lighter_client.get_state(),
        "open_orders": state.lighter_client.get_open_orders(),
        "risk": state.risk_guard.get_status(),
        "connections": {k: ing.get_telemetry() for k, ing in state.ingestors.items()},
        "bot_active": state.bot_active,
    }

@router.post("/bot/toggle")
async def toggle_bot(req: BotToggleRequest):
    state.bot_active = req.active
    await DBRepository.update_app_config({"bot_active": req.active})
    logger.info(f"Autonomous Bot active: {state.bot_active}")
    return {"success": True, "bot_active": state.bot_active}

@router.get("/bot/config")
async def get_bot_config():
    return global_bot_config

@router.post("/bot/config")
async def update_bot_config(req: BotConfig):
    global_bot_config.risk_per_trade_pct = req.risk_per_trade_pct
    global_bot_config.tp_percentage = req.tp_percentage
    global_bot_config.sl_percentage = req.sl_percentage
    global_bot_config.max_active_positions = req.max_active_positions
    global_bot_config.vpin_toxicity_threshold = req.vpin_toxicity_threshold
    global_bot_config.mlofi_imbalance_threshold = req.mlofi_imbalance_threshold
    
    # Update DB
    await DBRepository.update_app_config({
        "risk_per_trade_pct": req.risk_per_trade_pct,
        "tp_percentage": req.tp_percentage,
        "sl_percentage": req.sl_percentage,
        "max_active_positions": req.max_active_positions,
        "vpin_toxicity_threshold": req.vpin_toxicity_threshold,
        "mlofi_imbalance_threshold": req.mlofi_imbalance_threshold
    })
    
    # Update active engine references if needed
    state.vpin_engine.toxicity_threshold = req.vpin_toxicity_threshold
    state.risk_guard.vpin_cutoff_threshold = req.vpin_toxicity_threshold

    logger.info(f"Updated Bot Config: {global_bot_config}")
    return {"success": True, "config": global_bot_config}

@router.post("/execution/mode")
async def switch_mode(req: ModeSwitchRequest):
    mode = req.mode.lower()
    if mode not in ("testnet", "mainnet"):
        raise HTTPException(status_code=400, detail="Mode must be testnet or mainnet")
    
    # Update Execution Client
    state.lighter_client.switch_mode(mode)
    await DBRepository.update_app_config({"network_mode": mode.upper()})
    
    # Reload config for the selected mode
    db_config = await DBRepository.get_app_config()
    if mode == "mainnet":
        state.lighter_client.account_index = db_config.get("mainnet_account_index", "0")
        state.lighter_client.api_key_index = db_config.get("mainnet_api_key_index", "4")
    else:
        state.lighter_client.account_index = db_config.get("testnet_account_index", "0")
        state.lighter_client.api_key_index = db_config.get("testnet_api_key_index", "4")
    
    if not state.lighter_client.is_simulation:
        await state.lighter_client.sync_account_state()
    
    # Update Ingestor and trigger reconnect
    ing = state.ingestors.get("lighter")
    if ing:
        asyncio.create_task(ing.switch_mode(mode))
        
    return {"status": "success", "mode": state.lighter_client.mode}

@router.post("/execution/account")
async def update_account(req: AccountRequest):
    state.lighter_client.set_account_index(req.account)
    
    mode_key = "mainnet_account_index" if state.lighter_client.mode.upper() == "MAINNET" else "testnet_account_index"
    await DBRepository.update_app_config({mode_key: str(req.account)})
    
    await state.lighter_client.sync_account_state()
    return {"status": "success", "account": req.account, "state": state.lighter_client.get_state()}

@router.post("/execution/apikey")
async def update_apikey(req: ApiKeyRequest):
    state.lighter_client.api_key_index = str(req.api_key_index)
    
    mode_key = "mainnet_api_key_index" if state.lighter_client.mode.upper() == "MAINNET" else "testnet_api_key_index"
    await DBRepository.update_app_config({mode_key: str(req.api_key_index)})
    
    # We do not strictly need to sync account state immediately upon changing API key, 
    # but it doesn't hurt and validates it. Let's do it if it's not paper trading.
    if not state.lighter_client.is_simulation:
        await state.lighter_client.sync_account_state()
        
    return {"status": "success", "api_key_index": req.api_key_index, "state": state.lighter_client.get_state()}
@router.post("/execution/paper")
async def set_paper_trading(req: PaperTradingRequest):
    state.lighter_client.set_paper_trading(req.paper)
    await DBRepository.update_app_config({"is_paper_trading": req.paper})
    
    if not req.paper:
        await state.lighter_client.sync_account_state()
        
    return {"status": "success", "paper": req.paper, "state": state.lighter_client.get_state()}

@router.post("/leverage")
async def set_leverage(req: LeverageRequest):
    success = await state.lighter_client.set_leverage(req.leverage)
    if success:
        # Save to DB
        await DBRepository.update_app_config({"leverage": req.leverage})
        # Set to client
        state.lighter_client.leverage = req.leverage
        # Update config global
        global_bot_config.leverage = req.leverage
        return {"success": True, "message": f"Leverage set to {req.leverage}x"}
    raise HTTPException(status_code=400, detail="Failed to set leverage")

@router.post("/order")
async def place_order(req: OrderRequest):
    if state.risk_guard.kill_switch_active:
        raise HTTPException(status_code=403, detail="Kill switch active! Order placement rejected.")
    
    # Check STP
    if state.risk_guard.check_self_trade(req.side, req.price):
        raise HTTPException(status_code=400, detail="Self-Trade Prevention (STP) blocked this order.")

    # Check VPIN cutoff if trying to post maker order
    if req.post_only and state.risk_guard.passive_quoting_paused:
        raise HTTPException(status_code=400, detail="Toxic VPIN condition active! Passive maker orders paused.")

    order = await state.lighter_client.place_order(
        symbol=req.symbol,
        side=req.side,
        price=req.price,
        amount=req.amount,
        post_only=req.post_only,
        reduce_only=req.reduce_only,
    )
    return {"success": True, "order": order.to_dict()}

@router.post("/order/cancel/{client_order_index}")
async def cancel_order(client_order_index: int):
    success = await state.lighter_client.cancel_order(client_order_index)
    if not success:
        raise HTTPException(status_code=404, detail="Order not found or already closed")
    return {"success": True, "client_order_index": client_order_index}

@router.post("/order/cancel-all")
async def cancel_all():
    count = await state.lighter_client.cancel_all_orders()
    return {"success": True, "canceled_count": count}

@router.post("/kill-switch")
async def toggle_kill_switch(req: KillSwitchRequest):
    if req.active:
        await state.risk_guard.trigger_kill_switch(req.reason)
    else:
        state.risk_guard.reset_kill_switch()
    return {"success": True, "kill_switch_active": state.risk_guard.kill_switch_active}
