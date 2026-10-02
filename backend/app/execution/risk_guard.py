"""
Risk Manager, Self-Trade Prevention (STP), and Desert Mode Monitor.
Guards the bot against:
1. Toxic VPIN spikes (auto-canceling passive maker orders).
2. Internal self-trade execution (STP filter).
3. Extreme RTT network latency degradation.
4. L1 Zero-Knowledge Rollup Desert Mode detection (contract heartbeat).
5. Manual or automated emergency Kill-Switch.
"""
import time
import logging
from typing import Optional, List
from .lighter_client import LighterExecutionClient

logger = logging.getLogger("RiskGuard")

class RiskGuard:
    def __init__(
        self,
        execution_client: LighterExecutionClient,
        vpin_cutoff_threshold: float = 0.65,
        max_rtt_ms: float = 350.0,
        desert_mode_days_limit: int = 14,
        max_concurrent_positions: int = 1,      # NEW: Prevents double exposure
        max_daily_loss_usd: float = 100.0,      # NEW: Daily hard kill switch
        post_loss_cooldown_seconds: int = 300,  # NEW: Time-out after a loss to prevent revenge trading
    ):
        self.client = execution_client
        self.vpin_cutoff_threshold = vpin_cutoff_threshold
        self.max_rtt_ms = max_rtt_ms
        self.desert_mode_days_limit = desert_mode_days_limit
        
        self.max_concurrent_positions = max_concurrent_positions
        self.max_daily_loss_usd = max_daily_loss_usd
        self.post_loss_cooldown_seconds = post_loss_cooldown_seconds

        self.kill_switch_active: bool = False
        self.passive_quoting_paused: bool = False
        self.last_rollup_checkpoint_ts: float = time.time()
        self.desert_mode_active: bool = False
        self.stp_blocked_count: int = 0
        self.alerts: List[str] = []
        
        self.daily_pnl_usd: float = 0.0
        self.last_loss_timestamp: float = 0.0
        self.current_positions: int = 0

    def can_open_position(self) -> bool:
        """
        NEW: Quant risk management check before emitting entry signals.
        """
        if self.kill_switch_active:
            return False
            
        # Check exposure limit
        if self.current_positions >= self.max_concurrent_positions:
            return False
            
        # Check hard daily loss limit
        if self.daily_pnl_usd <= -self.max_daily_loss_usd:
            logger.warning(f"[RiskGuard] Daily loss limit breached (${abs(self.daily_pnl_usd):.2f} >= ${self.max_daily_loss_usd:.2f}). Trading halted.")
            return False
            
        # Check post-loss cooldown
        if time.time() - self.last_loss_timestamp < self.post_loss_cooldown_seconds:
            logger.info("[RiskGuard] In post-loss cooldown period. Deferring entry.")
            return False
            
        return True

    def register_fill(self, pnl_usd: float, is_close: bool = False):
        """
        NEW: Updates internal state after an execution.
        """
        if is_close:
            self.current_positions = max(0, self.current_positions - 1)
            self.daily_pnl_usd += pnl_usd
            if pnl_usd < 0:
                self.last_loss_timestamp = time.time()
                logger.info(f"[RiskGuard] Loss registered (${abs(pnl_usd):.2f}). Initiating {self.post_loss_cooldown_seconds}s cooldown.")
        else:
            self.current_positions += 1

    def check_self_trade(self, side: str, price: float) -> bool:
        """
        Self-Trade Prevention (STP):
        Ensures a new order does not cross with an existing open order in memory.
        """
        for order in self.client.orders.values():
            if order.status == "OPEN":
                if side.upper() == "BUY" and order.side == "SELL" and price >= order.price:
                    self.stp_blocked_count += 1
                    logger.warning(f"[STP Guard] Blocked BUY order at {price} crossing existing open SELL at {order.price}!")
                    return True
                elif side.upper() == "SELL" and order.side == "BUY" and price <= order.price:
                    self.stp_blocked_count += 1
                    logger.warning(f"[STP Guard] Blocked SELL order at {price} crossing existing open BUY at {order.price}!")
                    return True
        return False

    async def evaluate_vpin(self, current_vpin: float):
        """
        Adverse Selection Protection:
        If VPIN exceeds toxic threshold, automatically cancel all resting maker orders.
        """
        if current_vpin >= self.vpin_cutoff_threshold:
            if not self.passive_quoting_paused:
                self.passive_quoting_paused = True
                msg = f"CRITICAL: Toxic VPIN Spike detected ({current_vpin:.4f} >= {self.vpin_cutoff_threshold}). Canceling passive maker orders!"
                logger.warning(f"[RiskGuard] {msg}")
                self.alerts.append(msg)
                await self.client.cancel_all_orders()
        else:
            if self.passive_quoting_paused:
                self.passive_quoting_paused = False
                logger.info(f"[RiskGuard] VPIN normalized ({current_vpin:.4f}). Resuming passive quoting.")

    def check_latency(self, rtt_ms: float) -> bool:
        if rtt_ms > self.max_rtt_ms:
            logger.warning(f"[RiskGuard] High latency detected ({rtt_ms}ms > {self.max_rtt_ms}ms). Execution deferred.")
            return False
        return True

    def check_desert_mode(self) -> bool:
        """Checks if sequencer has stopped committing L1 roots for >= 14 days."""
        elapsed_days = (time.time() - self.last_rollup_checkpoint_ts) / (86400)
        if elapsed_days >= self.desert_mode_days_limit:
            self.desert_mode_active = True
            self.kill_switch_active = True
            msg = f"EMERGENCY: L1 Rollup state inactivity {elapsed_days:.1f} days >= {self.desert_mode_days_limit} days. Desert Mode / Escape Hatch triggered!"
            logger.error(f"[RiskGuard] {msg}")
            if msg not in self.alerts:
                self.alerts.append(msg)
            return True
        return False

    async def trigger_kill_switch(self, reason: str = "Manual User Trigger"):
        self.kill_switch_active = True
        logger.error(f"[RiskGuard] KILL-SWITCH TRIGGERED: {reason}. Liquidating and canceling all orders.")
        await self.client.cancel_all_orders()
        self.alerts.append(f"KILL-SWITCH ENGAGED: {reason}")

    def reset_kill_switch(self):
        self.kill_switch_active = False
        logger.info("[RiskGuard] Kill-switch disengaged. Normal operations resumed.")

    def get_status(self) -> dict:
        return {
            "kill_switch_active": self.kill_switch_active,
            "passive_quoting_paused": self.passive_quoting_paused,
            "desert_mode_active": self.desert_mode_active,
            "stp_blocked_count": self.stp_blocked_count,
            "vpin_threshold": self.vpin_cutoff_threshold,
            "daily_pnl_usd": round(self.daily_pnl_usd, 2),
            "current_positions": self.current_positions,
            "recent_alerts": self.alerts[-5:],
        }
