"""
Asynchronous Repository for Database Operations.
Encapsulates non-blocking CRUD actions with automatic exception handling so DB operations
never interrupt or block high-frequency orderbook or execution loops.
"""
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, update, desc
from .session import async_session_factory
from .models import OrderModel, TradeModel, AnalyticsSnapshotModel, BotSessionModel

logger = logging.getLogger("DBRepository")

class DBRepository:
    @staticmethod
    async def save_order(order_data: Dict[str, Any]) -> Optional[int]:
        """Save a new order record into the database."""
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    stmt = select(OrderModel).where(OrderModel.client_order_index == order_data["client_order_index"])
                    res = await session.execute(stmt)
                    order = res.scalar_one_or_none()
                    if order:
                        order.status = order_data.get("status", order.status)
                        order.price = float(order_data["price"])
                        order.amount = float(order_data["amount"])
                        order.updated_at = datetime.utcnow()
                    else:
                        order = OrderModel(
                            client_order_index=order_data["client_order_index"],
                            exchange_order_id=order_data.get("exchange_order_id"),
                            symbol=order_data.get("symbol", "BTCUSDT"),
                            side=order_data["side"],
                            order_type=order_data.get("order_type", "LIMIT"),
                            price=float(order_data["price"]),
                            amount=float(order_data["amount"]),
                            filled_amount=float(order_data.get("filled_amount", 0.0)),
                            status=order_data.get("status", "OPEN"),
                            reduce_only=bool(order_data.get("reduce_only", False)),
                            is_simulation=bool(order_data.get("is_simulation", True)),
                            leverage=float(order_data.get("leverage", 1.0)),
                        )
                        session.add(order)
                return order.id
        except Exception as e:
            logger.error(f"Error saving order to DB: {e}")
            return None

    @staticmethod
    async def update_order_status(
        client_order_index: int, 
        status: str, 
        filled_amount: Optional[float] = None,
        exchange_order_id: Optional[str] = None
    ) -> bool:
        """Update status and fill progress for an existing order."""
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    stmt = select(OrderModel).where(OrderModel.client_order_index == client_order_index)
                    res = await session.execute(stmt)
                    order = res.scalar_one_or_none()
                    if order:
                        order.status = status
                        order.updated_at = datetime.utcnow()
                        if filled_amount is not None:
                            order.filled_amount = filled_amount
                        if exchange_order_id:
                            order.exchange_order_id = exchange_order_id
                        return True
            return False
        except Exception as e:
            logger.error(f"Error updating order status in DB: {e}")
            return False

    @staticmethod
    async def record_trade(trade_data: Dict[str, Any]) -> Optional[int]:
        """Record an executed trade fill."""
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    trade = TradeModel(
                        order_id=trade_data.get("order_id"),
                        client_order_index=trade_data.get("client_order_index"),
                        symbol=trade_data.get("symbol", "BTCUSDT"),
                        side=trade_data["side"],
                        exec_price=float(trade_data["exec_price"]),
                        exec_amount=float(trade_data["exec_amount"]),
                        fee_paid=float(trade_data.get("fee_paid", 0.0)),
                        realized_pnl=float(trade_data.get("realized_pnl", 0.0)),
                        is_simulation=bool(trade_data.get("is_simulation", True)),
                    )
                    session.add(trade)
                return trade.id
        except Exception as e:
            logger.error(f"Error recording trade to DB: {e}")
            return None

    @staticmethod
    async def record_analytics_snapshot(snapshot_data: Dict[str, Any]):
        """Persist periodic time-series snapshot of VPIN and MLOFI."""
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    snap = AnalyticsSnapshotModel(
                        symbol=snapshot_data.get("symbol", "BTCUSDT"),
                        vpin_value=float(snapshot_data.get("vpin_value", 0.0)),
                        vpin_is_toxic=bool(snapshot_data.get("vpin_is_toxic", False)),
                        mlofi_imbalance=float(snapshot_data.get("mlofi_imbalance", 0.0)),
                        mid_price=float(snapshot_data.get("mid_price", 0.0)),
                        spread=float(snapshot_data.get("spread", 0.0)),
                        cvd_delta=float(snapshot_data.get("cvd_delta", 0.0)),
                        active_leverage=float(snapshot_data.get("active_leverage", 1.0)),
                    )
                    session.add(snap)
        except Exception as e:
            logger.error(f"Error saving analytics snapshot to DB: {e}")

    @staticmethod
    async def get_recent_orders(limit: int = 50) -> List[dict]:
        """Fetch latest orders from DB."""
        try:
            async with async_session_factory() as session:
                stmt = select(OrderModel).order_by(desc(OrderModel.created_at)).limit(limit)
                res = await session.execute(stmt)
                orders = res.scalars().all()
                return [o.to_dict() for o in orders]
        except Exception as e:
            logger.error(f"Error fetching orders from DB: {e}")
            return []

    @staticmethod
    async def get_recent_trades(limit: int = 50, offset: int = 0) -> List[dict]:
        """Fetch latest trades from DB."""
        try:
            async with async_session_factory() as session:
                stmt = select(TradeModel).order_by(desc(TradeModel.executed_at)).offset(offset).limit(limit)
                res = await session.execute(stmt)
                trades = res.scalars().all()
                return {"trades": [t.to_dict() for t in trades], "next_cursor": None}
        except Exception as e:
            logger.error(f"Error fetching trades from DB: {e}")
            return {"trades": [], "next_cursor": None}

    @staticmethod
    async def get_analytics_history(limit: int = 100) -> List[dict]:
        """Fetch historical VPIN/MLOFI time-series data."""
        try:
            async with async_session_factory() as session:
                stmt = select(AnalyticsSnapshotModel).order_by(desc(AnalyticsSnapshotModel.timestamp)).limit(limit)
                res = await session.execute(stmt)
                snaps = res.scalars().all()
                return [s.to_dict() for s in reversed(snaps)]
        except Exception as e:
            logger.error(f"Error fetching analytics history from DB: {e}")
            return []

    @staticmethod
    async def get_app_config() -> dict:
        """Fetch the global application configuration."""
        from .models import AppConfigModel
        try:
            async with async_session_factory() as session:
                stmt = select(AppConfigModel).where(AppConfigModel.id == 1)
                res = await session.execute(stmt)
                config = res.scalar_one_or_none()
                if not config:
                    # Create default config if it doesn't exist
                    config = AppConfigModel(id=1)
                    session.add(config)
                    await session.commit()
                return config.to_dict()
        except Exception as e:
            logger.error(f"Error fetching app config from DB: {e}")
            return {}

    @staticmethod
    async def update_app_config(updates: dict) -> bool:
        """Update the global application configuration."""
        from .models import AppConfigModel
        try:
            async with async_session_factory() as session:
                async with session.begin():
                    stmt = select(AppConfigModel).where(AppConfigModel.id == 1)
                    res = await session.execute(stmt)
                    config = res.scalar_one_or_none()
                    if not config:
                        config = AppConfigModel(id=1)
                        session.add(config)
                    
                    for key, value in updates.items():
                        if hasattr(config, key):
                            setattr(config, key, value)
                return True
        except Exception as e:
            logger.error(f"Error updating app config in DB: {e}")
            return False
