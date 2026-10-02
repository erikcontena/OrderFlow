"""
SQLAlchemy ORM Data Models for OrderFlow Database Persistence.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, 
    DateTime, ForeignKey, Numeric, Index, Text
)
from sqlalchemy.orm import relationship
from .session import Base

class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    client_order_index = Column(BigInteger, unique=True, nullable=False, index=True)
    exchange_order_id = Column(String(100), nullable=True, index=True)
    symbol = Column(String(20), nullable=False, default="BTCUSDT")
    side = Column(String(10), nullable=False)              # "BUY" or "SELL"
    order_type = Column(String(20), nullable=False)        # "LIMIT", "MARKET", "STOP_LOSS", "TAKE_PROFIT"
    price = Column(Float, nullable=False)
    amount = Column(Float, nullable=False)
    filled_amount = Column(Float, default=0.0)
    status = Column(String(20), nullable=False, default="PENDING", index=True)  # PENDING, OPEN, FILLED, CANCELED, REJECTED
    reduce_only = Column(Boolean, default=False)
    is_simulation = Column(Boolean, default=True)
    leverage = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    trades = relationship("TradeModel", back_populates="order", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "client_order_index": self.client_order_index,
            "exchange_order_id": self.exchange_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "amount": self.amount,
            "filled_amount": self.filled_amount,
            "status": self.status,
            "reduce_only": self.reduce_only,
            "is_simulation": self.is_simulation,
            "leverage": self.leverage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TradeModel(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    client_order_index = Column(BigInteger, nullable=True, index=True)
    symbol = Column(String(20), nullable=False, default="BTCUSDT")
    side = Column(String(10), nullable=False)              # "BUY" or "SELL"
    exec_price = Column(Float, nullable=False)
    exec_amount = Column(Float, nullable=False)
    fee_paid = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    is_simulation = Column(Boolean, default=True)
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)

    order = relationship("OrderModel", back_populates="trades")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "client_order_index": self.client_order_index,
            "symbol": self.symbol,
            "side": self.side,
            "exec_price": self.exec_price,
            "exec_amount": self.exec_amount,
            "fee_paid": self.fee_paid,
            "realized_pnl": self.realized_pnl,
            "is_simulation": self.is_simulation,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class AnalyticsSnapshotModel(Base):
    __tablename__ = "analytics_snapshots"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    symbol = Column(String(20), nullable=False, default="BTCUSDT")
    vpin_value = Column(Float, nullable=False)
    vpin_is_toxic = Column(Boolean, nullable=False, default=False)
    mlofi_imbalance = Column(Float, nullable=False)
    mid_price = Column(Float, nullable=False)
    spread = Column(Float, nullable=False, default=0.0)
    cvd_delta = Column(Float, nullable=False, default=0.0)
    active_leverage = Column(Float, default=1.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.symbol,
            "vpin_value": round(self.vpin_value, 4),
            "vpin_is_toxic": self.vpin_is_toxic,
            "mlofi_imbalance": round(self.mlofi_imbalance, 4),
            "mid_price": self.mid_price,
            "spread": self.spread,
            "cvd_delta": round(self.cvd_delta, 2),
            "active_leverage": self.active_leverage,
        }


class BotSessionModel(Base):
    __tablename__ = "bot_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_start = Column(DateTime, default=datetime.utcnow, index=True)
    session_end = Column(DateTime, nullable=True)
    mode = Column(String(10), nullable=False, default="TESTNET")
    starting_equity = Column(Float, nullable=False)
    ending_equity = Column(Float, nullable=True)
    total_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "session_start": self.session_start.isoformat() if self.session_start else None,
            "session_end": self.session_end.isoformat() if self.session_end else None,
            "mode": self.mode,
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "max_drawdown": self.max_drawdown,
            "notes": self.notes,
        }

class AppConfigModel(Base):
    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True) # Always 1
    # Execution Settings
    network_mode = Column(String(20), default="TESTNET")
    is_paper_trading = Column(Boolean, default=True)
    testnet_account_index = Column(String(100), default="0")
    testnet_api_key_index = Column(String(100), default="4")
    mainnet_account_index = Column(String(100), default="0")
    mainnet_api_key_index = Column(String(100), default="4")
    
    # Bot Settings
    bot_active = Column(Boolean, default=False)
    leverage = Column(Float, default=1.0)
    risk_per_trade_pct = Column(Float, default=0.01)
    tp_percentage = Column(Float, default=0.05)
    sl_percentage = Column(Float, default=0.02)
    max_active_positions = Column(Integer, default=3)
    vpin_toxicity_threshold = Column(Float, default=0.85)
    mlofi_imbalance_threshold = Column(Float, default=0.7)

    def to_dict(self) -> dict:
        return {
            "network_mode": self.network_mode,
            "is_paper_trading": self.is_paper_trading,
            "testnet_account_index": self.testnet_account_index,
            "testnet_api_key_index": self.testnet_api_key_index,
            "mainnet_account_index": self.mainnet_account_index,
            "mainnet_api_key_index": self.mainnet_api_key_index,
            "bot_active": self.bot_active,
            "leverage": self.leverage,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "tp_percentage": self.tp_percentage,
            "sl_percentage": self.sl_percentage,
            "max_active_positions": self.max_active_positions,
            "vpin_toxicity_threshold": self.vpin_toxicity_threshold,
            "mlofi_imbalance_threshold": self.mlofi_imbalance_threshold,
        }
