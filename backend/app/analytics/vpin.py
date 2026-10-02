"""
Volume Synchronized Probability of Informed Trading (VPIN) Engine.
Implements:
1. Volume-Synchronized Bucketing (fixed bucket size V).
2. Bulk Volume Classification (BVC) using Student-t distribution for crypto fat-tails.
3. Rolling Window Toxicity calculation (Easley, Lopez de Prado, O'Hara).
4. Real-time toxic flow spike alerts.
"""
from typing import List, Deque, Optional, Tuple
from collections import deque
import numpy as np
from scipy import stats
import time

class VolumeBucket:
    def __init__(self, bucket_size: float, index: int):
        self.bucket_size = bucket_size
        self.index = index
        self.accumulated_volume: float = 0.0
        self.price_volume_sum: float = 0.0
        self.start_time: float = time.time()
        self.end_time: float = 0.0
        self.vwap: float = 0.0
        self.buy_volume: float = 0.0
        self.sell_volume: float = 0.0
        self.is_complete: bool = False

    def add_trade(self, price: float, volume: float) -> float:
        """
        Adds volume to this bucket.
        Returns the remaining volume that exceeded this bucket capacity.
        """
        needed = self.bucket_size - self.accumulated_volume
        if volume <= needed:
            self.accumulated_volume += volume
            self.price_volume_sum += price * volume
            if self.accumulated_volume >= self.bucket_size - 1e-9:
                self.finalize(price)
            return 0.0
        else:
            self.accumulated_volume += needed
            self.price_volume_sum += price * needed
            self.finalize(price)
            return volume - needed

    def finalize(self, last_price: float):
        self.end_time = time.time()
        self.vwap = self.price_volume_sum / self.accumulated_volume if self.accumulated_volume > 0 else last_price
        self.is_complete = True


class VPINEngine:
    def __init__(
        self,
        base_bucket_size: float = 2.0,       # Base Size V in base asset (e.g. 2.0 BTC)
        window_size: int = 50,          # Rolling window of buckets (N)
        student_t_df: int = 4,          # Degrees of freedom for crypto fat tails
        toxicity_threshold: float = 0.65, # Critical VPIN alert threshold
        name: str = "VPIN"
    ):
        self.name = name
        self.base_bucket_size = base_bucket_size
        self.bucket_size = base_bucket_size
        self.window_size = window_size
        self.student_t_df = student_t_df
        self.toxicity_threshold = toxicity_threshold

        self.current_bucket = VolumeBucket(self.bucket_size, 0)
        self.completed_buckets: Deque[VolumeBucket] = deque(maxlen=self.window_size * 4)
        self.price_changes: Deque[float] = deque(maxlen=self.window_size * 2)
        
        self.current_vpin: float = 0.0
        self.is_toxic: bool = False
        self.last_update_time: float = time.time()
        self.bucket_count: int = 0
        
        # Historical VPIN record for percentile calculation
        self.vpin_history: Deque[float] = deque(maxlen=500)
        
        # NEW: Dynamic bucket size based on volatility
        self.recent_prices: Deque[Tuple[float, float]] = deque(maxlen=10000)
        self.last_vol_calc_time = 0.0

    def process_trade(self, price: float, volume: float, is_taker_buyer: Optional[bool] = None):
        """
        Processes incoming tick/trade from exchange stream.
        Handles volume clock slicing across bucket boundaries.
        """
        now = time.time()
        self.last_update_time = now
        self.recent_prices.append((now, price))
        
        # FIX: Dynamic Bucket Sizing based on 5-min realized volatility
        if now - self.last_vol_calc_time > 10.0:  # Recalculate every 10 seconds
            self._update_dynamic_bucket_size(now)
            self.last_vol_calc_time = now

        remaining = volume

        while remaining > 0:
            # Sync bucket capacity if it changed dynamically
            self.current_bucket.bucket_size = self.bucket_size
            remaining = self.current_bucket.add_trade(price, remaining)
            if self.current_bucket.is_complete:
                self._classify_and_append_bucket(self.current_bucket)
                self.bucket_count += 1
                self.current_bucket = VolumeBucket(self.bucket_size, self.bucket_count)

    def _update_dynamic_bucket_size(self, now: float):
        # Remove prices older than 5 minutes (300 seconds)
        while self.recent_prices and now - self.recent_prices[0][0] > 300:
            self.recent_prices.popleft()
            
        if len(self.recent_prices) > 30:
            prices = np.array([p[1] for p in self.recent_prices])
            returns = np.diff(prices) / prices[:-1]
            volatility = np.std(returns)
            
            # Baseline assumptions: 
            # Normal 5m crypto vol might be ~0.001 (0.1%). 
            # We scale bucket size around base_bucket_size based on ratio.
            vol_ratio = volatility / 0.001
            
            # Clamp ratio between 0.5 and 3.0 to prevent extreme bucket sizes
            vol_ratio = max(0.5, min(3.0, vol_ratio))
            
            new_size = self.base_bucket_size * vol_ratio
            self.bucket_size = round(new_size, 2)

    def _classify_and_append_bucket(self, bucket: VolumeBucket):
        """
        Bulk Volume Classification (BVC) using Student-t distribution CDF.
        Evaluates Delta P relative to standard deviation of price changes.
        """
        prev_vwap = self.completed_buckets[-1].vwap if self.completed_buckets else bucket.vwap
        delta_p = bucket.vwap - prev_vwap
        self.price_changes.append(delta_p)

        # Calculate standard deviation of price changes across recent buckets
        if len(self.price_changes) >= 5:
            sigma_dp = float(np.std(self.price_changes))
            if sigma_dp < 1e-8:
                sigma_dp = 1e-8
        else:
            sigma_dp = 1.0

        # Standardized price change Z
        z_score = delta_p / sigma_dp

        # Student-t Cumulative Distribution Function
        # F_nu(z) gives the probability of informed buy volume
        prob_buy = float(stats.t.cdf(z_score, df=self.student_t_df))
        prob_buy = max(0.01, min(0.99, prob_buy))  # Clamp for stability

        bucket.buy_volume = bucket.accumulated_volume * prob_buy
        bucket.sell_volume = bucket.accumulated_volume * (1.0 - prob_buy)

        self.completed_buckets.append(bucket)
        self._compute_vpin()

    def _compute_vpin(self):
        """
        Computes rolling VPIN metric over N buckets:
        VPIN = sum(|V_tau_B - V_tau_S|) / (N * V)
        """
        if len(self.completed_buckets) < min(10, self.window_size):
            return

        active_buckets = list(self.completed_buckets)[-self.window_size:]
        
        # With dynamic buckets, total_vol is the exact sum of accumulated volume
        total_vol = sum(b.accumulated_volume for b in active_buckets)
        if total_vol <= 0:
            return

        abs_imbalance_sum = sum(abs(b.buy_volume - b.sell_volume) for b in active_buckets)
        self.current_vpin = float(abs_imbalance_sum / total_vol)
        self.vpin_history.append(self.current_vpin)

        # Toxic regime trigger
        self.is_toxic = self.current_vpin >= self.toxicity_threshold

        # High-performance percentile calculation cached per bucket fill
        if len(self.vpin_history) >= 20:
            count_below = sum(1 for v in self.vpin_history if v <= self.current_vpin)
            self.current_percentile = (count_below / len(self.vpin_history)) * 100.0
        else:
            self.current_percentile = 50.0

    def get_percentile(self) -> float:
        return getattr(self, "current_percentile", 50.0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "vpin": round(self.current_vpin, 4),
            "is_toxic": self.is_toxic,
            "percentile": round(self.get_percentile(), 1),
            "threshold": self.toxicity_threshold,
            "buckets_completed": self.bucket_count,
            "active_window": min(len(self.completed_buckets), self.window_size),
            "bucket_size": self.bucket_size,
            "current_bucket_progress": round(self.current_bucket.accumulated_volume / self.bucket_size, 3) if self.bucket_size > 0 else 0,
            "timestamp": self.last_update_time
        }
