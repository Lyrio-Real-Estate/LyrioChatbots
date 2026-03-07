"""
Performance Tracker for Jorge Real Estate AI Dashboard.

Tracks and aggregates performance metrics across:
- Cache operations (hits, misses, response times)
- AI analysis (Claude API calls, response times)
- GHL API operations (response times, error rates)

Provides real-time and historical performance data for dashboard visualization.
"""
import time
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from bots.shared.cache_service import get_cache_service
from bots.shared.dashboard_models import (
    CacheStatistics,
    CostSavingsMetrics,
    PerformanceDashboardMetrics,
)
from bots.shared.logger import get_logger

logger = get_logger(__name__)


class PerformanceTracker:
    """
    Tracks real-time performance metrics for dashboard display.

    Collects metrics from cache events, AI operations, and GHL API calls,
    then aggregates and persists them for dashboard visualization.

    Features:
    - Rolling window metrics (last 24 hours)
    - P95 latency calculations
    - Cost savings tracking
    - Multi-tier caching (30s/5min/1hr TTL)
    """

    def __init__(self, window_hours: int = 24):
        """
        Initialize performance tracker.

        Args:
            window_hours: Rolling window size in hours (default: 24)
        """
        self.window_hours = window_hours
        self.cache_service = get_cache_service()

        # In-memory rolling metrics (24-hour window)
        # Using deque for O(1) append and automatic size limiting
        max_size = window_hours * 3600  # Estimate: 1 event per second
        self._cache_hits: deque = deque(maxlen=max_size)
        self._cache_misses: deque = deque(maxlen=max_size)
        self._ai_calls: deque = deque(maxlen=max_size)
        self._ghl_calls: deque = deque(maxlen=max_size)

        # Counters for aggregation
        self._total_cache_hits: int = 0
        self._total_cache_misses: int = 0
        self._total_ai_calls: int = 0
        self._total_ghl_calls: int = 0
        self._fallback_activations: int = 0
        self._ghl_errors: int = 0

        # Cost tracking
        self._ai_calls_avoided: int = 0  # Via cache/patterns
        self._pattern_matches: int = 0

        logger.info(f"PerformanceTracker initialized (window: {window_hours}h)")

    # Response-time distribution buckets used by dashboard charts.
    _RESPONSE_BUCKET_LABELS = [
        "0-100ms",
        "100-200ms",
        "200-400ms",
        "400-800ms",
        "800-1.2s",
        "1.2-2s",
        "2-4s",
        "4-8s",
        "8s+",
    ]
    _RESPONSE_BUCKET_UPPER_BOUNDS_MS = [100, 200, 400, 800, 1200, 2000, 4000, 8000]

    # =================================================================
    # Event Recording Methods
    # =================================================================

    async def record_cache_hit(
        self,
        response_time_ms: float,
        data_size_bytes: int = 0
    ):
        """Record a cache hit event."""
        event = {
            'timestamp': time.time(),
            'response_time_ms': response_time_ms,
            'data_size_bytes': data_size_bytes,
        }
        self._cache_hits.append(event)
        self._total_cache_hits += 1
        self._ai_calls_avoided += 1  # Cache hit avoided AI call

    async def record_cache_miss(self, cache_key: str = ""):
        """Record a cache miss event."""
        event = {
            'timestamp': time.time(),
            'cache_key': cache_key[:50],  # Truncate for privacy
        }
        self._cache_misses.append(event)
        self._total_cache_misses += 1

    async def record_ai_call(
        self,
        response_time_ms: float,
        five_minute_compliant: bool = True,
        was_pattern_match: bool = False,
    ):
        """Record an AI analysis call."""
        event = {
            'timestamp': time.time(),
            'response_time_ms': response_time_ms,
            'five_minute_compliant': five_minute_compliant,
            'was_pattern_match': was_pattern_match,
        }
        self._ai_calls.append(event)
        self._total_ai_calls += 1

        if was_pattern_match:
            self._pattern_matches += 1
            self._ai_calls_avoided += 1  # Pattern match avoided full AI call

        if not five_minute_compliant:
            self._fallback_activations += 1

    async def record_ghl_call(
        self,
        response_time_ms: float,
        success: bool = True,
        endpoint: str = "",
    ):
        """Record a GHL API call."""
        event = {
            'timestamp': time.time(),
            'response_time_ms': response_time_ms,
            'success': success,
            'endpoint': endpoint[:50],
        }
        self._ghl_calls.append(event)
        self._total_ghl_calls += 1

        if not success:
            self._ghl_errors += 1

    # =================================================================
    # Metrics Calculation Methods
    # =================================================================

    def _calculate_avg(self, events: deque, key: str) -> float:
        """Calculate average value for a metric key."""
        if not events:
            return 0.0

        values = [e[key] for e in events if key in e]
        return sum(values) / len(values) if values else 0.0

    def _calculate_p95(self, events: deque, key: str) -> float:
        """Calculate 95th percentile for a metric key."""
        if not events:
            return 0.0

        values = sorted([e[key] for e in events if key in e])
        if not values:
            return 0.0

        idx = int(len(values) * 0.95)
        return values[idx] if idx < len(values) else values[-1]

    def _calculate_rate(self, numerator: int, denominator: int) -> float:
        """Calculate percentage rate."""
        if denominator == 0:
            return 0.0
        return (numerator / denominator) * 100

    def _bucket_index_for_latency(self, latency_ms: float) -> int:
        """Map latency in milliseconds to configured response-time bucket index."""
        for idx, upper in enumerate(self._RESPONSE_BUCKET_UPPER_BOUNDS_MS):
            if latency_ms < upper:
                return idx
        return len(self._RESPONSE_BUCKET_LABELS) - 1

    def _build_latency_distribution(self, events: deque) -> Dict[str, Any]:
        """
        Build percentage distribution for response-time buckets from event deque.

        Returns:
            Dict with `percentages` list (len 9) and `total_events` count.
        """
        counts = [0] * len(self._RESPONSE_BUCKET_LABELS)
        total_events = 0

        for event in events:
            raw_latency = event.get("response_time_ms")
            if raw_latency is None:
                continue
            try:
                latency_ms = float(raw_latency)
            except Exception:
                continue
            if latency_ms < 0:
                continue

            bucket_idx = self._bucket_index_for_latency(latency_ms)
            counts[bucket_idx] += 1
            total_events += 1

        if total_events <= 0:
            return {"percentages": [0.0] * len(self._RESPONSE_BUCKET_LABELS), "total_events": 0}

        percentages = [round((count / total_events) * 100.0, 1) for count in counts]
        return {"percentages": percentages, "total_events": total_events}

    async def get_performance_metrics(self) -> PerformanceDashboardMetrics:
        """
        Get aggregated performance metrics for dashboard.

        Returns comprehensive performance data including:
        - Cache performance (hit rate, response times)
        - AI analysis statistics
        - GHL API performance
        """
        # Cache metrics
        cache_avg_ms = self._calculate_avg(self._cache_hits, 'response_time_ms')
        cache_p95_ms = self._calculate_p95(self._cache_hits, 'response_time_ms')

        total_cache_requests = self._total_cache_hits + self._total_cache_misses
        cache_hit_rate = self._calculate_rate(self._total_cache_hits, total_cache_requests)
        cache_miss_rate = self._calculate_rate(self._total_cache_misses, total_cache_requests)

        # AI metrics
        ai_avg_ms = self._calculate_avg(self._ai_calls, 'response_time_ms')
        ai_p95_ms = self._calculate_p95(self._ai_calls, 'response_time_ms')

        # 5-minute rule compliance
        compliant_calls = sum(
            1 for e in self._ai_calls
            if e.get('five_minute_compliant', True)
        )
        five_minute_compliance = self._calculate_rate(
            compliant_calls,
            len(self._ai_calls)
        )

        # GHL metrics
        ghl_avg_ms = self._calculate_avg(self._ghl_calls, 'response_time_ms')
        ghl_p95_ms = self._calculate_p95(self._ghl_calls, 'response_time_ms')
        ghl_error_rate = self._calculate_rate(
            self._ghl_errors,
            self._total_ghl_calls
        )

        metrics = PerformanceDashboardMetrics(
            cache_avg_ms=cache_avg_ms,
            cache_p95_ms=cache_p95_ms,
            cache_hit_rate=cache_hit_rate,
            cache_miss_rate=cache_miss_rate,
            total_cache_hits=self._total_cache_hits,
            total_cache_misses=self._total_cache_misses,
            ai_avg_ms=ai_avg_ms,
            ai_p95_ms=ai_p95_ms,
            ai_total_calls=self._total_ai_calls,
            five_minute_rule_compliance=five_minute_compliance,
            fallback_activations=self._fallback_activations,
            ghl_avg_ms=ghl_avg_ms,
            ghl_p95_ms=ghl_p95_ms,
            ghl_total_calls=self._total_ghl_calls,
            ghl_error_rate=ghl_error_rate,
        )

        # Cache aggregated metrics (TTL: 30s for real-time dashboard)
        await self.cache_service.set(
            "metrics:performance:latest",
            asdict(metrics),
            ttl=30
        )

        return metrics

    async def get_response_time_distribution(self) -> Dict[str, Any]:
        """
        Get live response-time distribution across Cache, AI, and GHL calls.

        Returns:
            Dict with shared labels and per-service percentage series.

        Cache TTL: 30 seconds (matches performance metrics freshness).
        """
        cache_key = "metrics:performance:response_distribution"
        try:
            cached = await self.cache_service.get(cache_key)
            if cached:
                return cached

            cache_dist = self._build_latency_distribution(self._cache_hits)
            ai_dist = self._build_latency_distribution(self._ai_calls)
            ghl_dist = self._build_latency_distribution(self._ghl_calls)

            distribution = {
                "labels": list(self._RESPONSE_BUCKET_LABELS),
                "cache_hits_pct": cache_dist["percentages"],
                "ai_calls_pct": ai_dist["percentages"],
                "ghl_calls_pct": ghl_dist["percentages"],
                "cache_hits_total": cache_dist["total_events"],
                "ai_calls_total": ai_dist["total_events"],
                "ghl_calls_total": ghl_dist["total_events"],
                "generated_at": datetime.now().isoformat(),
            }

            await self.cache_service.set(cache_key, distribution, ttl=30)
            return distribution
        except Exception as e:
            logger.exception(f"Error building response-time distribution: {e}")
            return {
                "labels": list(self._RESPONSE_BUCKET_LABELS),
                "cache_hits_pct": [0.0] * len(self._RESPONSE_BUCKET_LABELS),
                "ai_calls_pct": [0.0] * len(self._RESPONSE_BUCKET_LABELS),
                "ghl_calls_pct": [0.0] * len(self._RESPONSE_BUCKET_LABELS),
                "cache_hits_total": 0,
                "ai_calls_total": 0,
                "ghl_calls_total": 0,
                "generated_at": datetime.now().isoformat(),
                "error": "Response-time distribution temporarily unavailable",
            }

    async def get_cache_statistics(self) -> CacheStatistics:
        """
        Get detailed cache statistics.

        Returns cache performance data including:
        - Hit/miss rates
        - Response times
        - Time-series data for charting
        """
        total_requests = self._total_cache_hits + self._total_cache_misses
        hit_rate = self._calculate_rate(self._total_cache_hits, total_requests)
        miss_rate = self._calculate_rate(self._total_cache_misses, total_requests)

        avg_hit_time = self._calculate_avg(self._cache_hits, 'response_time_ms')

        # For miss time, we use AI call time since misses trigger computation
        avg_miss_time = self._calculate_avg(self._ai_calls, 'response_time_ms')

        # Calculate cache size (estimate from memory)
        cache_size_mb = (
            sum(e.get('data_size_bytes', 0) for e in self._cache_hits) / (1024 * 1024)
        )

        # Build time-series data (hourly aggregation)
        hit_rate_by_hour = await self._build_hourly_hit_rates()

        stats = CacheStatistics(
            hit_rate=hit_rate,
            miss_rate=miss_rate,
            avg_hit_time_ms=avg_hit_time,
            avg_miss_time_ms=avg_miss_time,
            total_hits=self._total_cache_hits,
            total_misses=self._total_cache_misses,
            total_requests=total_requests,
            cache_size_mb=cache_size_mb,
            ttl_expirations=0,  # Would need Redis KEYS scan to count
            hit_rate_by_hour=hit_rate_by_hour,
        )

        # Cache stats (TTL: 5min for moderately fresh data)
        await self.cache_service.set(
            "metrics:cache:statistics",
            asdict(stats),
            ttl=300
        )

        return stats

    async def get_cost_savings(self) -> CostSavingsMetrics:
        """
        Calculate cost savings from caching and pattern matching.

        Tracks how many AI API calls were avoided through:
        - Cache hits
        - Pattern matches
        """
        # Estimated cost per Claude API call (input + output tokens)
        avg_cost_per_call = 0.05  # $0.05 estimate for lead analysis

        total_saved_dollars = self._ai_calls_avoided * avg_cost_per_call

        # Breakdown by type (cache vs patterns)
        cache_savings = self._total_cache_hits * avg_cost_per_call
        pattern_savings = self._pattern_matches * avg_cost_per_call

        savings = CostSavingsMetrics(
            total_saved_dollars=total_saved_dollars,
            ai_calls_avoided=self._ai_calls_avoided,
            pattern_matches=self._pattern_matches,
            cache_hits=self._total_cache_hits,
            avg_cost_per_ai_call=avg_cost_per_call,
            lead_bot_savings=cache_savings,  # Simplification
            seller_bot_savings=pattern_savings,  # Simplification
        )

        # Cache savings (TTL: 1hr for historical data)
        await self.cache_service.set(
            "metrics:cost:savings",
            asdict(savings),
            ttl=3600
        )

        return savings

    async def _build_hourly_hit_rates(self) -> List[Dict[str, Any]]:
        """Build hourly hit rate time-series data."""
        now = time.time()
        hourly_data = []

        # Group events by hour for last 24 hours
        hour_buckets: Dict[int, Dict[str, int]] = defaultdict(
            lambda: {'hits': 0, 'misses': 0}
        )

        for hit_event in self._cache_hits:
            hour = int((now - hit_event['timestamp']) // 3600)
            if hour < self.window_hours:
                hour_buckets[hour]['hits'] += 1

        for miss_event in self._cache_misses:
            hour = int((now - miss_event['timestamp']) // 3600)
            if hour < self.window_hours:
                hour_buckets[hour]['misses'] += 1

        # Build sorted time-series
        for hour in range(self.window_hours):
            bucket = hour_buckets[hour]
            total = bucket['hits'] + bucket['misses']
            rate = self._calculate_rate(bucket['hits'], total)

            hourly_data.append({
                'hour': self.window_hours - hour - 1,  # 0 = most recent
                'rate': rate,
                'hits': bucket['hits'],
                'misses': bucket['misses'],
            })

        return list(reversed(hourly_data))  # Chronological order

    # =================================================================
    # Persistence Methods
    # =================================================================

    async def persist_snapshot(self):
        """
        Persist current metrics snapshot to Redis.

        Called periodically (e.g., every 5 minutes) to ensure
        metrics survive service restarts.
        """
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'total_cache_hits': self._total_cache_hits,
            'total_cache_misses': self._total_cache_misses,
            'total_ai_calls': self._total_ai_calls,
            'total_ghl_calls': self._total_ghl_calls,
            'ai_calls_avoided': self._ai_calls_avoided,
            'pattern_matches': self._pattern_matches,
            'fallback_activations': self._fallback_activations,
            'ghl_errors': self._ghl_errors,
        }

        await self.cache_service.set(
            "metrics:performance:snapshot",
            snapshot,
            ttl=86400  # 24 hours
        )

        logger.debug("Performance snapshot persisted to Redis")

    async def restore_from_snapshot(self):
        """
        Restore metrics from Redis snapshot.

        Called on service startup to restore metrics from
        previous session.
        """
        snapshot = await self.cache_service.get("metrics:performance:snapshot")

        if snapshot:
            self._total_cache_hits = snapshot.get('total_cache_hits', 0)
            self._total_cache_misses = snapshot.get('total_cache_misses', 0)
            self._total_ai_calls = snapshot.get('total_ai_calls', 0)
            self._total_ghl_calls = snapshot.get('total_ghl_calls', 0)
            self._ai_calls_avoided = snapshot.get('ai_calls_avoided', 0)
            self._pattern_matches = snapshot.get('pattern_matches', 0)
            self._fallback_activations = snapshot.get('fallback_activations', 0)
            self._ghl_errors = snapshot.get('ghl_errors', 0)

            logger.info(f"Restored metrics from snapshot: {self._total_cache_hits} hits")
        else:
            logger.info("No metrics snapshot found, starting fresh")


# Global tracker instance
_performance_tracker: Optional[PerformanceTracker] = None


def get_performance_tracker() -> PerformanceTracker:
    """Get the global performance tracker instance."""
    global _performance_tracker

    if _performance_tracker is None:
        _performance_tracker = PerformanceTracker()

    return _performance_tracker
