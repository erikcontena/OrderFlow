"""
Strategy Engine Playbook.
Integrates signals from MLOFI, VPIN, and Footprint to generate precise execution signals.
"""
from typing import Dict, Any, Optional

class StrategyEngine:
    def __init__(self, mlofi_threshold: float = 0.5, vpin_kill_threshold: float = 0.85):
        self.mlofi_threshold = mlofi_threshold
        self.vpin_kill_threshold = vpin_kill_threshold

    def evaluate(self, current_mlofi: dict, current_vpin: dict, current_footprint: dict) -> Optional[Dict[str, Any]]:
        """
        Evaluates current telemetry against defined Strategy Plays.
        Returns a signal dictionary if a play is triggered, else None.
        
        Format:
        signal = strategy_engine.evaluate(current_mlofi, current_vpin, current_footprint)
        """
        vpin_value = current_vpin.get("vpin", 0.0)
        
        # NEW: FILTER WAJIB (KILL SWITCH)
        if vpin_value > self.vpin_kill_threshold:
            return {
                "action": "FLATTEN",
                "reason": f"VPIN {vpin_value} > {self.vpin_kill_threshold}. Toxic flow detected."
            }
            
        recent_bars = current_footprint.get("recent_bars", [])
        if len(recent_bars) < 2:
            return None
            
        last_bar = recent_bars[-1]
        prev_bar = recent_bars[-2]
        
        mlofi_value = current_mlofi.get("weighted_mlofi", 0.0)
        
        # Helper footprint metrics
        delta = last_bar.get("delta", 0.0)
        is_delta_positive = delta > 0.1
        is_closing_higher = last_bar.get("close", 0.0) > last_bar.get("open", 0.0)
        
        # PLAY A: Momentum Continuation (Breakout)
        # 1. MLOFI > threshold positif (ada tekanan beli bertingkat di LOB).
        # 2. VPIN < 0.65 (flow masih sehat, belum toxic).
        # 3. Footprint menunjukkan delta positif yang konsisten dan tidak ada tanda absorption di level ask terdekat.
        if mlofi_value > self.mlofi_threshold and vpin_value < 0.65:
            # If delta is highly positive and closes higher, no absorption
            if is_delta_positive and is_closing_higher:
                return {
                    "action": "BUY",
                    "type": "MARKET",
                    "reason": "PLAY A: Momentum Continuation"
                }
                
        # PLAY B: Absorption Reversal (Mean Reversion)
        # 1. Harga membuat higher high, tapi MLOFI menunjukkan divergensi (tekanan beli melemah).
        # 2. Footprint menunjukkan high positive delta tapi harga gagal naik (indikasi iceberg seller / absorption).
        # 3. VPIN melonjak > 0.70 (indikasi informed trader/smart money sedang mendistribusikan posisi short).
        is_higher_high = last_bar.get("high", 0.0) > prev_bar.get("high", 0.0)
        mlofi_divergence = mlofi_value < 0.0 # Price made HH but MLOFI is negative
        
        # Delta is positive but failed to close higher -> absorbed by passive sellers
        is_absorption = is_delta_positive and not is_closing_higher
        
        if is_higher_high and mlofi_divergence and is_absorption and vpin_value > 0.70:
            return {
                "action": "SELL",
                "type": "LIMIT",
                "reason": "PLAY B: Absorption Reversal"
            }
            
        return None
