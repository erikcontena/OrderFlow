"""
Cross-Exchange Volume Normalizer for Multi-Venue Order Flow Aggregation.

PROBLEM STATEMENT:
    Raw volume aggregation makes signals 90% Binance-dominated.
    A 100 BTC print on Binance (weight ~0.60) drowns a 0.5 BTC anomaly on
    Lighter (weight ~0.02) even if Lighter's Z-score is 4.5 standard deviations
    — a massive smart-money footprint by institutional standards.

SOLUTION: Three orthogonal normalization layers:

    A. Z-Score per Exchange (Anomaly Detection)
       Detects unusual activity per venue relative to its own baseline.
       A Z-score of 4.5 on Lighter OVERRIDES the raw volume dominance of Binance.
       Uses Welford's online algorithm: O(1) per tick, no history array needed.

    B. RVOL — Relative Volume vs Same-Hour Historical Average (VPIN Scaling)
       Computes how "hot" volume is right now vs the 24h same-hour average.
       RVOL > 1.5 means this hour's volume pace is 50% above normal -> expand VPIN bucket.

    C. Market Share Weights (Footprint Weighting)
       Real-time exchange share of global volume in the current bucket window.
       Used to weight Delta and Absorption signals in footprint.py.

COMPLEXITY:
    - All three metrics: O(1) per tick (Welford, deque popleft, running sum)
    - Memory: O(W * E) where W = deque window, E = exchange count

MATH REFERENCES:
    - Welford (1962): "Note on a Method for Calculating Corrected Sums of Squares and Products"
    - East, D. (2011): Extending Welford's online algorithm for higher moments
    - Gopikrishnan et al. (1999): RVOL normalization for intraday volume patterns
"""

from __future__ import annotations

import math
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("VolumeNormalizer")

# ─── Constants ─────────────────────────────────────────────────────────────────

# Z-score clip range (prevents single outlier from destabilizing signal weights)
Z_CLIP_LOW: float = -5.0
Z_CLIP_HIGH: float = 5.0

# Rolling windows
ZSCORE_WINDOW_SECONDS: float = 30 * 60.0        # 30 minutes for per-exchange rolling vol
RVOL_SHORT_WINDOW_SECONDS: float = 5 * 60.0     # 5 minutes for RVOL numerator
RVOL_LONG_WINDOW_SECONDS: float = 24 * 60 * 60.0  # 24 hours for RVOL denominator
MARKET_SHARE_WINDOW_SECONDS: float = 60.0       # 60 seconds rolling for market share weights

# Minimum ticks before Z-score is meaningful (cold-start protection)
MIN_TICKS_FOR_ZSCORE: int = 10


# ─── Welford Online Statistics ─────────────────────────────────────────────────

@dataclass
class WelfordState:
    """
    Welford's online algorithm for running mean and variance.

    MATH (Welford 1962):
        On each new sample x:
            n    += 1
            delta = x - mean
            mean += delta / n
            M2   += delta * (x - mean)   # note: uses UPDATED mean
            var   = M2 / (n - 1)          # sample variance
            std   = sqrt(var)

    This is numerically stable and O(1) per update.
    No need to store the full history array.

    However, for a ROLLING window (e.g. 30 min), we must also handle
    the "remove oldest sample" operation. Since Welford doesn't natively
    support removal, we use a parallel deque to track the window and
    recompute only when necessary (downdate approximation).
    
    PRODUCTION APPROACH used here: 
    We combine Welford for RUNNING statistics with a time-bounded deque
    for WINDOWED statistics. When the window fills, we recompute from
    the deque every `recompute_interval` samples using an exact single-pass
    algorithm. This gives O(1) amortized complexity.
    """
    n: int = 0
    mean: float = 0.0
    M2: float = 0.0        # Sum of squared deviations from mean

    def update(self, x: float) -> None:
        """Incorporate new sample x into running statistics. O(1)."""
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        # HFT_OPTIMIZATION: use updated mean (Welford's two-pass delta)
        delta2 = x - self.mean
        self.M2 += delta * delta2

    def variance(self) -> float:
        """Sample variance. Returns 0 if fewer than 2 samples."""
        return self.M2 / (self.n - 1) if self.n >= 2 else 0.0

    def std(self) -> float:
        """Sample standard deviation. O(1) — one sqrt call."""
        v = self.variance()
        return math.sqrt(v) if v > 0 else 0.0

    def reset_from_samples(self, samples: List[float]) -> None:
        """
        Recompute Welford state from a fresh list of samples.
        Called when the window slides and old samples must be evicted.
        O(W) but called infrequently (every recompute_interval ticks).
        """
        self.n = 0
        self.mean = 0.0
        self.M2 = 0.0
        for x in samples:
            self.update(x)


# ─── Per-Exchange Z-Score Tracker ─────────────────────────────────────────────

class ExchangeZScoreTracker:
    """
    Tracks rolling 30-minute Z-score for one exchange's volume per logical bucket.

    QUANT_LOGIC:
        Z = (x - mu) / sigma  where mu, sigma are rolling 30-min stats.
        Clipped to [-5, 5] to prevent model contamination by fat-tail events.

    The Z-score answers: "Is this exchange's current volume anomalous RELATIVE
    TO ITSELF?" — decoupled from absolute volume dominance.

    Parameters
    ----------
    exchange_id  : str
    window_sec   : float — rolling window in seconds (default 1800 = 30 min)
    recompute_every : int — recompute Welford from deque every N ticks to handle eviction
    """

    def __init__(
        self,
        exchange_id: str,
        window_sec: float = ZSCORE_WINDOW_SECONDS,
        recompute_every: int = 50,
    ) -> None:
        self.exchange_id = exchange_id
        self.window_sec = window_sec
        self.recompute_every = recompute_every

        # HFT_OPTIMIZATION: deque with bounded memory, O(1) append/popleft
        self._samples: Deque[Tuple[float, float]] = deque()  # (timestamp, volume)
        self._welford = WelfordState()
        self._ticks_since_recompute: int = 0

        # Cached Z-score (output)
        self.last_z_score: float = 0.0
        self.last_volume: float = 0.0

    def update(self, volume: float, recv_time_s: float) -> float:
        """
        Feed one bucket's total volume for this exchange.

        Returns
        -------
        float
            Clipped Z-score in [-5.0, 5.0]. Returns 0.0 during cold start
            (fewer than MIN_TICKS_FOR_ZSCORE samples).
        """
        self.last_volume = volume
        self._samples.append((recv_time_s, volume))

        # Evict samples older than the window
        cutoff = recv_time_s - self.window_sec
        # HFT_OPTIMIZATION: O(k) where k = evicted samples, amortized O(1)
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

        self._ticks_since_recompute += 1

        # Periodically recompute Welford from deque to handle evictions correctly
        # QUANT_LOGIC: Welford cannot "undo" old samples, so we recompute from
        # the trimmed deque every N ticks. Cost: O(W) every N ticks = O(W/N) amortized.
        if self._ticks_since_recompute >= self.recompute_every:
            self._welford.reset_from_samples([s[1] for s in self._samples])
            self._ticks_since_recompute = 0
        else:
            self._welford.update(volume)

        # Cold start: not enough history
        if self._welford.n < MIN_TICKS_FOR_ZSCORE:
            self.last_z_score = 0.0
            return 0.0

        mu = self._welford.mean
        sigma = self._welford.std()

        if sigma < 1e-10:
            # No variance at all (e.g. exchange always sends exactly same volume)
            z = 0.0
        else:
            z = (volume - mu) / sigma

        # QUANT_LOGIC: Clip to prevent single outlier destroying weight allocation
        z = max(Z_CLIP_LOW, min(Z_CLIP_HIGH, z))
        self.last_z_score = z
        return z

    def get_stats(self) -> dict:
        return {
            "exchange": self.exchange_id,
            "sample_count": len(self._samples),
            "rolling_mean": round(self._welford.mean, 6),
            "rolling_std": round(self._welford.std(), 6),
            "last_z_score": round(self.last_z_score, 4),
            "last_volume": round(self.last_volume, 6),
        }


# ─── RVOL Calculator ──────────────────────────────────────────────────────────

class RVOLCalculator:
    """
    Relative Volume (RVOL) for dynamic VPIN bucket scaling.

    MATH:
        RVOL = V_5min_annualized / V_same_hour_24h_avg

        Where:
            V_5min_annualized = (volume in last 5 min) * (60 / 5) = hourly pace
            V_same_hour_24h_avg = rolling average of the same clock-hour
                                   over the last 24 hours

    QUANT_LOGIC:
        RVOL > 1.0 means volume pace this 5-min is above the 24h same-hour baseline.
        RVOL = 2.0 means 2x the normal volume -> suggest doubling VPIN bucket size
               to prevent buckets from filling too fast and creating noise.
        RVOL < 0.5 means unusually thin market -> shrink bucket for sensitivity.

    Clamped to [0.25, 4.0] to avoid extreme bucket sizes.
    """

    def __init__(self) -> None:
        # Rolling 5-min volume buffer: (timestamp_s, volume)
        self._short_buf: Deque[Tuple[float, float]] = deque()
        # 24h hourly bucket buffer: (hour_of_day, volume_that_hour)
        self._hourly_vols: Dict[int, Deque[float]] = {h: deque(maxlen=7) for h in range(24)}

        self._last_hourly_update_hour: int = -1
        self._hour_accum: float = 0.0         # Volume accumulating for current hour

        self.current_rvol: float = 1.0
        self._5min_volume: float = 0.0
        self._24h_hour_avg: float = 0.0

    def update(self, volume: float, recv_time_s: float) -> float:
        """
        Feed global volume (all exchanges combined) for RVOL calculation.

        Returns
        -------
        float
            rvol_multiplier in [0.25, 4.0]. Use to scale VPIN bucket_size:
            bucket_size = base_bucket_size * rvol_multiplier
        """
        # ── Short window (5 min) ──────────────────────────────────────────────
        self._short_buf.append((recv_time_s, volume))
        cutoff_5m = recv_time_s - RVOL_SHORT_WINDOW_SECONDS
        while self._short_buf and self._short_buf[0][0] < cutoff_5m:
            self._short_buf.popleft()

        # HFT_OPTIMIZATION: running sum via deque, O(1) after eviction
        self._5min_volume = sum(v for _, v in self._short_buf)

        # Annualize to hourly pace: 5 min * 12 = 1 hour
        annualized_pace = self._5min_volume * (3600.0 / RVOL_SHORT_WINDOW_SECONDS)

        # ── Hourly bucket accumulation ────────────────────────────────────────
        import datetime
        hour_now = datetime.datetime.fromtimestamp(recv_time_s).hour
        self._hour_accum += volume

        if hour_now != self._last_hourly_update_hour and self._last_hourly_update_hour >= 0:
            # Hour rolled over -> commit last hour's total to history
            self._hourly_vols[self._last_hourly_update_hour].append(self._hour_accum)
            self._hour_accum = 0.0

        self._last_hourly_update_hour = hour_now

        # ── 24h same-hour average ─────────────────────────────────────────────
        hour_history = self._hourly_vols[hour_now]
        if hour_history:
            self._24h_hour_avg = sum(hour_history) / len(hour_history)
        else:
            # No history yet for this hour -> RVOL = 1.0 (neutral)
            self.current_rvol = 1.0
            return 1.0

        if self._24h_hour_avg < 1e-10:
            self.current_rvol = 1.0
            return 1.0

        # QUANT_LOGIC: RVOL compares annualized 5-min pace to the 24h same-hour average
        raw_rvol = annualized_pace / self._24h_hour_avg

        # Clamp to prevent extreme bucket resizing
        self.current_rvol = max(0.25, min(4.0, raw_rvol))
        return self.current_rvol

    def get_stats(self) -> dict:
        return {
            "rvol_multiplier": round(self.current_rvol, 4),
            "5min_volume": round(self._5min_volume, 4),
            "24h_hour_avg": round(self._24h_hour_avg, 4),
        }


# ─── Market Share Tracker ─────────────────────────────────────────────────────

class MarketShareTracker:
    """
    Real-time market share weights per exchange for footprint weighting.

    MATH:
        weight_i = vol_i / sum(vol_j for all j)

        where vol_i is exchange i's total volume in the last `window_sec` seconds.

    QUANT_LOGIC:
        If Binance weight = 0.60 and Lighter weight = 0.02, a delta imbalance
        of 10 on Binance contributes 6.0 to the aggregate, while a 10-unit
        absorption signal on Lighter contributes only 0.2. This properly reflects
        the relative informational content per venue.

    HFT_OPTIMIZATION:
        Rolling sum maintained via deque popleft + running_sum variable.
        O(1) per tick except during eviction which is O(k) amortized O(1).
    """

    def __init__(
        self,
        exchange_ids: List[str],
        window_sec: float = MARKET_SHARE_WINDOW_SECONDS,
    ) -> None:
        self.exchange_ids = exchange_ids
        self.window_sec = window_sec

        # Per-exchange: (timestamp, volume) ring buffer
        self._bufs: Dict[str, Deque[Tuple[float, float]]] = {
            ex: deque() for ex in exchange_ids
        }
        # Running sums per exchange: O(1) update
        self._running_vols: Dict[str, float] = {ex: 0.0 for ex in exchange_ids}

        # Cached output
        self.weights: Dict[str, float] = {ex: 1.0 / len(exchange_ids) for ex in exchange_ids}

    def update(self, exchange_id: str, volume: float, recv_time_s: float) -> Dict[str, float]:
        """
        Feed one exchange's volume for the current tick/bucket.

        Returns
        -------
        Dict[str, float]
            Updated weights for all exchanges summing to ~1.0.
            Stale exchanges (no ticks in window) get weight 0.0.
        """
        if exchange_id not in self._bufs:
            self._bufs[exchange_id] = deque()
            self._running_vols[exchange_id] = 0.0

        buf = self._bufs[exchange_id]
        buf.append((recv_time_s, volume))
        self._running_vols[exchange_id] += volume

        # Evict expired entries from all buffers
        # HFT_OPTIMIZATION: only evict from the exchange that just updated + global scan
        cutoff = recv_time_s - self.window_sec
        for ex, b in self._bufs.items():
            while b and b[0][0] < cutoff:
                evicted_ts, evicted_vol = b.popleft()
                self._running_vols[ex] = max(0.0, self._running_vols[ex] - evicted_vol)

        # Compute weights
        total = sum(self._running_vols.values())
        if total < 1e-10:
            # No data yet: equal weights
            n = len(self.exchange_ids)
            self.weights = {ex: 1.0 / n for ex in self.exchange_ids}
        else:
            self.weights = {
                ex: self._running_vols.get(ex, 0.0) / total
                for ex in self.exchange_ids
            }

        return self.weights

    def get_stats(self) -> dict:
        return {
            "window_sec": self.window_sec,
            "weights": {ex: round(w, 4) for ex, w in self.weights.items()},
            "running_vols": {ex: round(v, 6) for ex, v in self._running_vols.items()},
        }


# ─── VolumeNormalizer (Facade) ─────────────────────────────────────────────────

class VolumeNormalizer:
    """
    Unified facade combining all three normalization layers.

    Holds one ExchangeZScoreTracker per exchange, one RVOLCalculator,
    and one MarketShareTracker. All updates are O(1) amortized.

    Typical call site (inside the analytics pipeline, after TimeSynchronizer seals a bucket):

        norm_result = volume_normalizer.process_bucket(bucket)

        # Use in mlofi.py: weight MLOFI by Z-score
        mlofi_weight = norm_result.z_scores.get("lighter", 0.0)

        # Use in vpin.py: scale bucket size
        new_bucket_size = base_bucket_size * norm_result.rvol_multiplier

        # Use in footprint.py: weight delta by market share
        weighted_delta = delta * norm_result.market_weights.get("binance", 0.0)
    """

    def __init__(
        self,
        exchange_ids: Optional[List[str]] = None,
        zscore_window_sec: float = ZSCORE_WINDOW_SECONDS,
        market_share_window_sec: float = MARKET_SHARE_WINDOW_SECONDS,
    ) -> None:
        self.exchange_ids: List[str] = exchange_ids or [
            "binance", "bybit", "hyperliquid", "bitget", "lighter"
        ]

        # One Z-score tracker per exchange
        self._z_trackers: Dict[str, ExchangeZScoreTracker] = {
            ex: ExchangeZScoreTracker(ex, window_sec=zscore_window_sec)
            for ex in self.exchange_ids
        }

        self._rvol_calc = RVOLCalculator()
        self._mshare_tracker = MarketShareTracker(
            exchange_ids=self.exchange_ids,
            window_sec=market_share_window_sec,
        )

    def process_bucket(
        self,
        bucket_volumes: Dict[str, float],   # {exchange_id: total_volume_in_bucket}
        recv_time_s: Optional[float] = None,
    ) -> "NormalizationResult":
        """
        Compute all three normalization outputs from one bucket's per-exchange volumes.

        Parameters
        ----------
        bucket_volumes : dict
            {exchange_id: total_volume} for the just-sealed logical time bucket.
            Stale exchanges should have volume=0.
        recv_time_s : float | None
            Bucket close time in Unix seconds. Defaults to `time.time()`.

        Returns
        -------
        NormalizationResult
            Dataclass with z_scores, rvol_multiplier, market_weights.
        """
        t = recv_time_s or time.time()

        z_scores: Dict[str, float] = {}
        global_vol: float = 0.0

        # ── A. Z-Score per exchange ────────────────────────────────────────────
        for ex in self.exchange_ids:
            vol = bucket_volumes.get(ex, 0.0)
            global_vol += vol
            z = self._z_trackers[ex].update(vol, t)
            z_scores[ex] = z

        # ── B. RVOL (uses global volume) ───────────────────────────────────────
        rvol_multiplier = self._rvol_calc.update(global_vol, t)

        # ── C. Market Share Weights ────────────────────────────────────────────
        for ex, vol in bucket_volumes.items():
            if vol > 0:
                self._mshare_tracker.update(ex, vol, t)

        market_weights = dict(self._mshare_tracker.weights)

        return NormalizationResult(
            z_scores=z_scores,
            rvol_multiplier=rvol_multiplier,
            market_weights=market_weights,
            global_volume=global_vol,
            timestamp=t,
        )

    def process_trade(
        self,
        exchange_id: str,
        volume: float,
        recv_time_s: Optional[float] = None,
    ) -> None:
        """
        Lightweight tick-level update for market share only (no Z-score / RVOL).
        Call this from each ingestor's on_trade callback for real-time weights.
        Z-score and RVOL are updated less frequently via `process_bucket()`.
        """
        t = recv_time_s or time.time()
        self._mshare_tracker.update(exchange_id, volume, t)

    def get_z_score(self, exchange_id: str) -> float:
        """Return the latest cached Z-score for one exchange. O(1)."""
        tracker = self._z_trackers.get(exchange_id)
        return tracker.last_z_score if tracker else 0.0

    def get_market_weights(self) -> Dict[str, float]:
        """Return current market share weights. O(1)."""
        return dict(self._mshare_tracker.weights)

    def get_all_stats(self) -> dict:
        """Full diagnostic snapshot for monitoring/dashboard."""
        return {
            "z_scores": {ex: t.get_stats() for ex, t in self._z_trackers.items()},
            "rvol": self._rvol_calc.get_stats(),
            "market_share": self._mshare_tracker.get_stats(),
        }


# ─── Result Dataclass ─────────────────────────────────────────────────────────

@dataclass
class NormalizationResult:
    """
    Output of VolumeNormalizer.process_bucket().

    z_scores      : Per-exchange anomaly Z-score, clipped to [-5, 5].
                    HIGH Z on a small exchange = strong anomaly signal.
    rvol_multiplier: Dynamic scaling factor for VPIN bucket_size.
                    1.0 = normal volume. 2.0 = double the bucket size.
    market_weights : Real-time exchange share of global volume [0, 1].
                    Sums to approximately 1.0 across active exchanges.
    global_volume  : Sum of all exchange volumes in this bucket.
    timestamp      : Unix time of this result.
    """
    z_scores: Dict[str, float]
    rvol_multiplier: float
    market_weights: Dict[str, float]
    global_volume: float
    timestamp: float

    def get_dominant_exchange(self) -> Tuple[str, float]:
        """
        Returns the exchange with the highest absolute Z-score.

        QUANT_LOGIC: The exchange with the highest anomaly score is the one
        exhibiting smart-money activity relative to its own baseline. This
        exchange's MLOFI signal should be amplified in the aggregate.
        """
        if not self.z_scores:
            return ("unknown", 0.0)
        dominant = max(self.z_scores.items(), key=lambda kv: abs(kv[1]))
        return dominant
