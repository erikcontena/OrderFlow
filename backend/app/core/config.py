import os
from pydantic import BaseModel

class BotConfig(BaseModel):
    symbol: str = "BTCUSDT"
    coin: str = "BTC"
    leverage: float = 1.0
    risk_per_trade_pct: float = 0.05
    tp_percentage: float = 0.02
    sl_percentage: float = 0.01
    max_active_positions: int = 1
    vpin_toxicity_threshold: float = 0.65
    mlofi_imbalance_threshold: float = 0.05

# In-memory config storage
global_bot_config = BotConfig()
