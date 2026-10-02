import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.core import state

logger = logging.getLogger("OrderFlowApp")
ws_router = APIRouter()

@ws_router.websocket("/telemetry")
async def ws_telemetry(websocket: WebSocket):
    await websocket.accept()
    state.connected_websockets.add(websocket)
    logger.info(f"Dashboard client connected. Total clients: {len(state.connected_websockets)}")
    try:
        while True:
            # Keep receiving any client commands or pings
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        state.connected_websockets.discard(websocket)
        logger.info(f"Dashboard client disconnected. Remaining: {len(state.connected_websockets)}")
