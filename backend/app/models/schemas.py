from pydantic import BaseModel
from typing import Optional

class OrderRequest(BaseModel):
    symbol: str = "BTC"
    side: str  # "BUY" or "SELL"
    price: float
    amount: float
    post_only: bool = True
    reduce_only: bool = False

class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "Web UI Trigger"

class BotToggleRequest(BaseModel):
    active: bool

class ModeSwitchRequest(BaseModel):
    mode: str

class AccountRequest(BaseModel):
    account: str

class PaperTradingRequest(BaseModel):
    paper: bool

class LeverageRequest(BaseModel):
    leverage: float

class ApiKeyRequest(BaseModel):
    api_key_index: str
