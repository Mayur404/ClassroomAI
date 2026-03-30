"""
Performance monitoring and analytics dashboard backend.
Tracks: response times, cache hit rates, error rates, system health, AI quality metrics
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
import json

from django.db import models
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger(__name__)


# ============================================================================
# PERFORMANCE METRICS MODELS
# ============================================================================

class PerformanceMetric(models.Model):
    """
    Store performance metrics for monitoring.
    """
    class MetricType(models.TextChoices):
        RESPONSE_TIME = "response_time", "Response Time"
        CACHE_HIT = "cache_hit", "Cache Hit"
        ERROR = "error", "Error"
        AI_QUALITY = "ai_quality", "AI Quality"
        VECTOR_SEARCH = "vector_search", "Vector Search"
        PDF_EXTRACTION = "pdf_extraction", "PDF Extraction"
    
    metric_type = models.CharField(max_length=50, choices=MetricType.choices)
    endpoint = models.CharField(max_length=255, null=True, blank=True)
    value = models.FloatField()  # ms for time, percentage for cache, etc.
    tags = models.JSONField(default=dict)  # Additional metadata
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['metric_type', '-created_at']),
            models.Index(fields=['endpoint', '-created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.metric_type}: {self.value} ({self.endpoint})"


class PerformanceMetricsCollector:
    """
    Collects and aggregates performance metrics.
    """
    
    @staticmethod
    def record_metric(metric_type: str, 
                      value: float,
                      endpoint: str = None,
                      tags: Dict = None):
        """
        Record a single performance metric.
        """
        try:
            PerformanceMetric.objects.create(
                metric_type=metric_type,
                value=value,
                endpoint=endpoint,
                tags=tags or {}
            )
        except Exception as e:
            logger.error(f"Failed to record metric: {e}")
    
    @staticmethod
    def record_request_time(endpoint: str, response_time_ms: float):
        """Record API response time."""
        PerformanceMetricsCollector.record_metric(
            PerformanceMetric.MetricType.RESPONSE_TIME,
            response_time_ms,
            endpoint=endpoint,
            tags={"unit": "milliseconds"}
        )
    
    @staticmethod
    def record_cache_hit(endpoint: str, is_hit: bool):
        """Record cache hit/miss."""
        value = 100 if is_hit else 0
        PerformanceMetricsCollector.record_metric(
            PerformanceMetric.MetricType.CACHE_HIT,
            value,
            endpoint=endpoint,
            tags={"hit": is_hit}
        )
    
    @staticmethod
    def record_error(endpoint: str, error_type: str, status_code: int = None):
        """Record error occurrence."""
        PerformanceMetricsCollector.record_metric(
            PerformanceMetric.MetricType.ERROR,
            1,
            endpoint=endpoint,
            tags={"error_type": error_type, "status": status_code}
        )
    
    @staticmethod
    def record_ai_quality(query: str, 
                         quality_score: float,
                         confidence: float = None,
                         answer_length: int = None):
        """
        Record AI answer quality metrics.
        """
        PerformanceMetricsCollector.record_metric(
            PerformanceMetric.MetricType.AI_QUALITY,
            quality_score,
            tags={
                "query_length": len(query),
                "confidence": confidence,
                "answer_length": answer_length,
                "query_hash": hash(query) % 10000,  # Anonymize
            }
        )
    
    @staticmethod
    def record_vector_search(duration_ms: float,
                            num_results: int,
                            model_name: str = None):
        """Record vector search performance."""
        PerformanceMetricsCollector.record_metric(
            PerformanceMetric.MetricType.VECTOR_SEARCH,
            duration_ms,
            tags={
                "results": num_results,
                "model": model_name,
                "unit": "milliseconds"
            }
        )
    
    @staticmethod
    def record_pdf_extraction(duration_ms: float,
                             pages: int,
                             quality_score: float,
                             method: str):
        """Record PDF extraction performance."""
        PerformanceMetricsCollector.record_metric(
            PerformanceMetric.MetricType.PDF_EXTRACTION,
            duration_ms,
            tags={
                "pages": pages,
                "quality": quality_score,
                "method": method,
                "unit": "milliseconds"
            }
        )


# ============================================================================
# METRICS AGGREGATION
# ============================================================================

@dataclass
class AggregatedMetrics:
    """Container for aggregated metrics."""
    metric_type: str
    count: int
    avg_value: float
    min_value: float
    max_value: float
    p50_value: float  # Median
    p95_value: float
    p99_value: float
    timestamp: str


class MetricsAggregator:
    """
    Aggregates raw metrics into dashboarding format.
    """
    
    @staticmethod
    def get_metrics_for_period(metric_type: str,
                               lookback_hours: int = 24) -> AggregatedMetrics:
        """
        Get aggregated metrics for a time period.
        """
        cutoff = timezone.now() - timedelta(hours=lookback_hours)
        
        metrics = PerformanceMetric.objects.filter(
            metric_type=metric_type,
            created_at__gte=cutoff
        ).values_list('value', flat=True)
        
        if not metrics:
            return None
        
        metrics_list = sorted(metrics)
        count = len(metrics_list)
        avg = sum(metrics_list) / count
        
        # Calculate percentiles
        p50_idx = count // 2
        p95_idx = int(count * 0.95)
        p99_idx = int(count * 0.99)
        
        return AggregatedMetrics(
            metric_type=metric_type,
            count=count,
            avg_value=avg,
            min_value=min(metrics_list),
            max_value=max(metrics_list),
            p50_value=metrics_list[p50_idx],
            p95_value=metrics_list[p95_idx] if p95_idx < count else metrics_list[-1],
            p99_value=metrics_list[p99_idx] if p99_idx < count else metrics_list[-1],
            timestamp=timezone.now().isoformat()
        )
    
    @staticmethod
    def get_endpoint_metrics(endpoint: str, lookback_hours: int = 24) -> Dict:
        """
        Get comprehensive metrics for an endpoint.
        """
        cutoff = timezone.now() - timedelta(hours=lookback_hours)
        
        metrics = PerformanceMetric.objects.filter(
            endpoint=endpoint,
            created_at__gte=cutoff
        )
        
        response_times = list(
            metrics.filter(metric_type=PerformanceMetric.MetricType.RESPONSE_TIME)
            .values_list('value', flat=True)
        )
        
        cache_hits = list(
            metrics.filter(metric_type=PerformanceMetric.MetricType.CACHE_HIT)
            .values_list('value', flat=True)
        )
        
        errors = metrics.filter(
            metric_type=PerformanceMetric.MetricType.ERROR
        ).count()
        
        result = {
            "endpoint": endpoint,
            "response_times": {
                "count": len(response_times),
                "avg_ms": sum(response_times) / len(response_times) if response_times else 0,
                "min_ms": min(response_times) if response_times else 0,
                "max_ms": max(response_times) if response_times else 0,
            },
            "cache": {
                "total_requests": len(cache_hits),
                "hit_rate": (sum(cache_hits) / len(cache_hits) * 100) if cache_hits else 0,
            },
            "errors": errors,
            "error_rate": (errors / len(response_times) * 100) if response_times else 0,
        }
        
        return result
    
    @staticmethod
    def get_system_health() -> Dict[str, Any]:
        """
        Get overall system health status.
        """
        # Response time: Good <200ms, OK <500ms, Bad >500ms
        response_agg = MetricsAggregator.get_metrics_for_period(
            PerformanceMetric.MetricType.RESPONSE_TIME,
            lookback_hours=1
        )
        
        response_health = "good"
        if response_agg:
            if response_agg.p95_value > 500:
                response_health = "bad"
            elif response_agg.p95_value > 200:
                response_health = "ok"
        
        # Cache hit rate: Good >80%, OK >50%, Bad <50%
        cache_agg = MetricsAggregator.get_metrics_for_period(
            PerformanceMetric.MetricType.CACHE_HIT,
            lookback_hours=1
        )
        
        cache_health = "good"
        if cache_agg:
            hit_rate = cache_agg.avg_value  # Already in percentage
            if hit_rate < 50:
                cache_health = "bad"
            elif hit_rate < 80:
                cache_health = "ok"
        
        # Error rate: Good <1%, OK <5%, Bad >5%
        error_count = PerformanceMetric.objects.filter(
            metric_type=PerformanceMetric.MetricType.ERROR,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        
        total_requests = PerformanceMetric.objects.filter(
            metric_type=PerformanceMetric.MetricType.RESPONSE_TIME,
            created_at__gte=timezone.now() - timedelta(hours=1)
        ).count()
        
        error_rate = (error_count / total_requests * 100) if total_requests else 0
        
        error_health = "good"
        if error_rate > 5:
            error_health = "bad"
        elif error_rate > 1:
            error_health = "ok"
        
        return {
            "timestamp": timezone.now().isoformat(),
            "overall": determine_overall_health([response_health, cache_health, error_health]),
            "response_time": {
                "status": response_health,
                "p95_ms": response_agg.p95_value if response_agg else None,
                "avg_ms": response_agg.avg_value if response_agg else None,
            },
            "cache": {
                "status": cache_health,
                "hit_rate": cache_agg.avg_value if cache_agg else None,
            },
            "errors": {
                "status": error_health,
                "error_rate": error_rate,
                "count": error_count,
            },
        }
    
    @staticmethod
    def get_ai_quality_metrics() -> Dict:
        """
        Get AI answer quality metrics.
        """
        cutoff = timezone.now() - timedelta(hours=24)
        
        metrics = PerformanceMetric.objects.filter(
            metric_type=PerformanceMetric.MetricType.AI_QUALITY,
            created_at__gte=cutoff
        )
        
        quality_scores = []
        confidence_scores = []
        
        for metric in metrics:
            quality_scores.append(metric.value)
            if metric.tags.get('confidence'):
                confidence_scores.append(metric.tags['confidence'])
        
        return {
            "avg_quality_score": sum(quality_scores) / len(quality_scores) if quality_scores else 0,
            "min_quality_score": min(quality_scores) if quality_scores else 0,
            "max_quality_score": max(quality_scores) if quality_scores else 0,
            "avg_confidence": sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0,
            "sample_size": len(quality_scores),
            "timestamp": timezone.now().isoformat(),
        }


def determine_overall_health(statuses: List[str]) -> str:
    """Determine overall health from individual component statuses."""
    if "bad" in statuses:
        return "bad"
    elif "ok" in statuses:
        return "ok"
    else:
        return "good"


# ============================================================================
# REST API VIEWS FOR DASHBOARD
# ============================================================================

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([IsAdminUser])
def dashboard_metrics(request):
    """
    GET /api/admin/metrics/dashboard/
    
    Return all dashboard metrics.
    """
    lookback_hours = int(request.query_params.get('hours', 24))
    
    metrics = {
        "response_time": asdict(
            MetricsAggregator.get_metrics_for_period(
                PerformanceMetric.MetricType.RESPONSE_TIME,
                lookback_hours
            )
        ) if MetricsAggregator.get_metrics_for_period(
            PerformanceMetric.MetricType.RESPONSE_TIME,
            lookback_hours
        ) else None,
        "cache_hits": asdict(
            MetricsAggregator.get_metrics_for_period(
                PerformanceMetric.MetricType.CACHE_HIT,
                lookback_hours
            )
        ) if MetricsAggregator.get_metrics_for_period(
            PerformanceMetric.MetricType.CACHE_HIT,
            lookback_hours
        ) else None,
        "ai_quality": MetricsAggregator.get_ai_quality_metrics(),
        "system_health": MetricsAggregator.get_system_health(),
    }
    
    return Response(metrics)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def endpoint_performance(request):
    """
    GET /api/admin/metrics/endpoints/
    
    Get performance metrics by endpoint.
    """
    lookback_hours = int(request.query_params.get('hours', 24))
    
    # Get all endpoints with metrics
    endpoints = (
        PerformanceMetric.objects
        .filter(
            endpoint__isnull=False,
            created_at__gte=timezone.now() - timedelta(hours=lookback_hours)
        )
        .values_list('endpoint', flat=True)
        .distinct()
    )
    
    endpoint_metrics = {}
    for endpoint in endpoints:
        endpoint_metrics[endpoint] = MetricsAggregator.get_endpoint_metrics(
            endpoint, lookback_hours
        )
    
    return Response(endpoint_metrics)


@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_health(request):
    """
    GET /api/admin/metrics/health/
    
    Get overall system health status.
    """
    return Response(MetricsAggregator.get_system_health())
