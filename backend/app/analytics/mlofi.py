"""
Multi-Level Order-Flow Imbalance (MLOFI) Engine.
Extends the Cont-Kukanov-Stoikov OFI framework to multiple depth levels.
Computes order flow vector, depth-weighted imbalance, and short-term price pressure signals.
"""
from typing import List, Tuple, Dict, Optional
from collections import deque
import numpy as np
import time

class MLOFIEngine:
    def __init__(self, depth_levels: int = 5, decay_lambda: float = 0.4, history_len: int = 100):
        self.depth_levels = depth_levels
        self.decay_lambda = decay_lambda
        self.history_len = history_len
        
        # Exponential weights for levels 1..K
        raw_weights = [np.exp(-decay_lambda * k) for k in range(depth_levels)]
        weight_sum = sum(raw_weights)
        self.weights = [w / weight_sum for w in raw_weights]

        self.prev_bids: List[Tuple[float, float]] = []
        self.prev_asks: List[Tuple[float, float]] = []
        
        self.history: Deque[dict] = deque(maxlen=history_len)
        self.cumulative_ofi: float = 0.0

    def update(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]) -> dict:
        """
        Receives current top-K bids and asks [(price, qty), ...].
        Computes the level-by-level flow imbalance vector.
        """
        now = time.time()
        k = min(self.depth_levels, len(bids), len(asks))
        if k == 0:
            return {"weighted_mlofi": 0.0, "level_ofi": [], "cumulative_ofi": self.cumulative_ofi}

        current_bids = bids[:k]
        current_asks = asks[:k]

        if not self.prev_bids or not self.prev_asks:
            self.prev_bids = current_bids
            self.prev_asks = current_asks
            return {
                "weighted_mlofi": 0.0,
                "level_ofi": [0.0] * k,
                "cumulative_ofi": self.cumulative_ofi,
                "timestamp": now
            }

        level_ofi = []
        for i in range(k):
            # Bid flow I_b
            curr_bp, curr_bq = current_bids[i]
            prev_bp, prev_bq = self.prev_bids[i] if i < len(self.prev_bids) else (curr_bp, curr_bq)
            
            if curr_bp > prev_bp:
                ib = curr_bq
            elif curr_bp == prev_bp:
                ib = curr_bq - prev_bq
            else:
                ib = -prev_bq

            # Ask flow I_a
            curr_ap, curr_aq = current_asks[i]
            prev_ap, prev_aq = self.prev_asks[i] if i < len(self.prev_asks) else (curr_ap, curr_aq)

            if curr_ap < prev_ap:
                ia = curr_aq
            elif curr_ap == prev_ap:
                ia = curr_aq - prev_aq
            else:
                ia = -prev_aq

            # Net OFI at level i (positive means bullish buying pressure)
            ofi_level = ib - ia
            level_ofi.append(round(ofi_level, 4))

        # Depth-weighted MLOFI scalar
        weighted_mlofi = sum(level_ofi[i] * self.weights[i] for i in range(len(level_ofi)))
        self.cumulative_ofi += weighted_mlofi

        self.prev_bids = current_bids
        self.prev_asks = current_asks

        result = {
            "weighted_mlofi": round(weighted_mlofi, 4),
            "level_ofi": level_ofi,
            "cumulative_ofi": round(self.cumulative_ofi, 4),
            "signal": "BULLISH" if weighted_mlofi > 0.5 else ("BEARISH" if weighted_mlofi < -0.5 else "NEUTRAL"),
            "timestamp": now
        }
        self.history.append(result)
        return result
