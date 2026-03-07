"""
Enhanced Hero Metrics Component - Jorge's ROI Command Center

Advanced hero metrics with Business Intelligence features:
- Lead Source ROI analysis (which sources drive best commission)
- 30-day revenue forecasting (predictive pipeline value)
- Smart CMA prioritization (order by estimated commission value)
- One-click workflow automation (auto-generate CMAs, send sequences)
- Mobile-responsive design with superior UX

Author: Claude Code Assistant
Created: 2026-01-23
"""
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select

from bots.shared.business_rules import JorgeBusinessRules
from bots.shared.cache_service import MemoryCache
from bots.shared.dashboard_data_service import DashboardDataService
from bots.shared.ghl_client import GHLClient
from bots.shared.logger import get_logger
from bots.shared.metrics_service import get_metrics_service
from database.models import ContactModel, ConversationModel, DealModel, LeadModel
from database.session import AsyncSessionFactory

logger = get_logger(__name__)


@dataclass
class HeroMetricData:
    """Data structure for individual hero metric cards"""
    label: str
    value: str
    delta: str
    color: str  # red, green, blue, purple, amber
    urgency_level: str  # high, medium, low
    action_button: Optional[str] = None
    tooltip: Optional[str] = None
    progress_bar: Optional[float] = None  # 0.0 to 1.0
    trend_direction: str = "neutral"  # up, down, neutral


class LeadSourceROI:
    """Lead source ROI analysis for business intelligence"""

    def __init__(self):
        self.logger = get_logger(__name__)

    def calculate_source_roi(self, leads_data: List[Dict]) -> Dict[str, Dict]:
        """
        Calculate ROI by lead source.

        Args:
            leads_data: List of lead dictionaries with source, commission, cost_per_lead

        Returns:
            Dict mapping source -> ROI metrics
        """
        if not leads_data:
            return {}

        source_metrics = {}

        for lead in leads_data:
            source = lead.get("source", "unknown")
            commission = lead.get("commission", 0)
            cost_per_lead = lead.get("cost_per_lead", 0)

            if source not in source_metrics:
                source_metrics[source] = {
                    "total_commission": 0,
                    "total_cost": 0,
                    "lead_count": 0,
                    "hot_leads_count": 0
                }

            source_metrics[source]["total_commission"] += commission
            source_metrics[source]["total_cost"] += cost_per_lead
            source_metrics[source]["lead_count"] += 1

            if lead.get("status") == "hot" or lead.get("score", 0) >= 80:
                source_metrics[source]["hot_leads_count"] += 1

        # Calculate ROI
        for source, metrics in source_metrics.items():
            if metrics["total_cost"] == 0:
                metrics["roi"] = float('inf') if metrics["total_commission"] > 0 else 0
            else:
                metrics["roi"] = metrics["total_commission"] / metrics["total_cost"]

        return source_metrics

    def get_best_performing_source(self, leads_data: List[Dict]) -> Dict:
        """Get the best performing lead source by ROI"""
        source_metrics = self.calculate_source_roi(leads_data)

        if not source_metrics:
            return {"source": "none", "roi": 0, "hot_leads_count": 0}

        # Find source with highest ROI
        best_source = max(
            source_metrics.items(),
            key=lambda x: x[1]["roi"] if x[1]["roi"] != float('inf') else 999
        )

        return {
            "source": best_source[0].replace("_", " "),
            "roi": best_source[1]["roi"],
            "hot_leads_count": best_source[1]["hot_leads_count"],
            "total_commission": best_source[1]["total_commission"]
        }

    def format_roi_display(self, roi: float) -> str:
        """Format ROI for display"""
        if roi == float('inf'):
            return "∞x ROI"
        elif roi >= 100:
            return f"{int(roi)}x ROI"
        else:
            if roi == 0: return "0x ROI"
        return f"{roi:.1f}x ROI"


class RevenueForecaster:
    """30-day revenue forecasting with predictive analytics"""

    def __init__(self):
        self.logger = get_logger(__name__)

    def calculate_30_day_forecast(
        self,
        historical_data: List[Dict],
        current_pipeline: List[Dict]
    ) -> Dict[str, Any]:
        """
        Calculate 30-day revenue forecast using historical trends + current pipeline.

        Args:
            historical_data: Past commission data with dates
            current_pipeline: Current leads with close probabilities

        Returns:
            Forecast with projected revenue, confidence range, trend direction
        """
        try:
            # Calculate historical velocity
            velocity = self.calculate_velocity_trend(historical_data)

            # Calculate pipeline value
            pipeline_value = self._calculate_pipeline_value(current_pipeline)

            # Calculate base forecast (historical trend)
            base_forecast = velocity * 30  # 30 days

            # Calculate pipeline-adjusted forecast
            projected_revenue = base_forecast + pipeline_value

            # Calculate confidence range (±20%)
            confidence_range = [
                int(projected_revenue * 0.8),
                int(projected_revenue * 1.2)
            ]

            # Determine trend direction
            if velocity > 0:
                trend_direction = "up"
            elif velocity < 0:
                trend_direction = "down"
            else:
                trend_direction = "neutral"

            return {
                "projected_revenue": int(projected_revenue),
                "confidence_range": confidence_range,
                "trend_direction": trend_direction,
                "velocity_per_day": velocity,
                "pipeline_contribution": int(pipeline_value)
            }

        except Exception as e:
            self.logger.error(f"Revenue forecast error: {e}")
            return {
                "projected_revenue": 0,
                "confidence_range": [0, 0],
                "trend_direction": "neutral",
                "error": str(e)
            }

    def calculate_velocity_trend(self, historical_data: List[Dict]) -> float:
        """Calculate daily revenue velocity from historical data"""
        if len(historical_data) < 2:
            return 0.0

        # Sort by date
        sorted_data = sorted(
            historical_data,
            key=lambda x: x.get("date", datetime.min)
        )

        # Calculate daily average for last 30 days vs previous 30 days
        recent_data = sorted_data[-30:]
        previous_data = sorted_data[-60:-30] if len(sorted_data) >= 60 else []

        recent_avg = sum(d.get("commission", 0) for d in recent_data) / max(len(recent_data), 1)

        if previous_data:
            previous_avg = sum(d.get("commission", 0) for d in previous_data) / len(previous_data)
            velocity = recent_avg - previous_avg
        else:
            velocity = recent_avg

        return velocity

    def _calculate_pipeline_value(self, pipeline: List[Dict]) -> float:
        """Calculate expected value from current pipeline for the next 30 days."""
        total_value = 0.0
        now = datetime.utcnow()
        window_end = now + timedelta(days=30)

        for lead in pipeline:
            commission = float(lead.get("commission", 0) or 0.0)
            probability = float(lead.get("probability", 0.5) or 0.5)
            probability = max(0.0, min(1.0, probability))
            if commission <= 0:
                continue

            close_date = self._parse_close_date(lead.get("close_date"))
            if close_date is None:
                window_weight = 0.7
            elif close_date <= window_end:
                window_weight = 1.0
            else:
                window_weight = 0.25

            total_value += commission * probability * window_weight

        return total_value

    @staticmethod
    def _parse_close_date(value: Any) -> Optional[datetime]:
        """Parse close date values from datetime/ISO strings."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                parsed = datetime.fromisoformat(raw)
                return parsed
            except Exception:
                return None
        return None

    def format_forecast_display(self, forecast_data: Dict) -> str:
        """Format forecast for hero card display"""
        projected = forecast_data.get("projected_revenue", 0)
        confidence_range = forecast_data.get("confidence_range", [0, 0])
        trend = forecast_data.get("trend_direction", "neutral")

        # Format amounts
        projected_str = f"${projected//1000}K"
        range_str = f"${confidence_range[0]//1000}K - ${confidence_range[1]//1000}K"

        # Trend arrow
        trend_arrow = {
            "up": "",
            "down": "",
            "neutral": ""
        }.get(trend, "")

        return f"At current pace: {projected_str} | Range: {range_str} {trend_arrow}"


class CMAAnalyzer:
    """CMA prioritization and revenue prediction"""

    def __init__(self):
        self.logger = get_logger(__name__)
        # Jorge's commission rate and offer ratios
        self.commission_rate = 0.06  # 6%
        self.offer_ratio = 0.75  # Jorge offers ~75% of asking

    def calculate_commission_potential(self, seller_data: Dict) -> float:
        """Calculate potential commission for a Q4 seller"""
        price_expectation = seller_data.get("price_expectation", 0)
        if not price_expectation:
            return 0

        # Jorge's formula: Offer = 75% of asking, Commission = 6% of offer
        offer_amount = price_expectation * self.offer_ratio
        commission = offer_amount * self.commission_rate

        return commission

    def prioritize_by_value(self, sellers_data: List[Dict]) -> List[Dict]:
        """Prioritize sellers by commission potential"""
        # Add commission potential to each seller
        for seller in sellers_data:
            seller["commission_potential"] = self.calculate_commission_potential(seller)

        # Sort by commission potential (highest first)
        return sorted(
            sellers_data,
            key=lambda x: x.get("commission_potential", 0),
            reverse=True
        )

    def get_cma_summary(self, sellers_data: List[Dict]) -> Dict[str, Any]:
        """Get comprehensive CMA summary"""
        total_sellers = len(sellers_data)
        total_commission = sum(
            self.calculate_commission_potential(s) for s in sellers_data
        )

        high_priority_count = sum(
            1 for s in sellers_data if s.get("urgency") == "high"
        )

        prioritized_list = self.prioritize_by_value(sellers_data)

        return {
            "total_sellers": total_sellers,
            "total_commission_potential": total_commission,
            "high_priority_count": high_priority_count,
            "prioritized_list": prioritized_list[:5],  # Top 5
            "average_commission": total_commission / max(total_sellers, 1)
        }

    def format_cma_display(self, sellers_data: List[Dict]) -> str:
        """Format CMA data for hero card display"""
        summary = self.get_cma_summary(sellers_data)

        count = summary["total_sellers"]
        commission = summary["total_commission_potential"]
        commission_str = f"${commission/1000:.0f}K" if commission > 1000 else f"${commission:.0f}"

        return f"CMAs Ready: {count} Est. {commission_str} commission"


class EnhancedHeroMetrics:
    """
    Enhanced Hero Metrics Component with Business Intelligence.

    Features:
    - Lead Source ROI analysis
    - 30-day revenue forecasting
    - Smart CMA prioritization
    - One-click automation triggers
    - Mobile-responsive design
    """

    def __init__(self):
        self.logger = get_logger(__name__)
        self.cache = MemoryCache()
        self.lead_source_roi = LeadSourceROI()
        self.revenue_forecaster = RevenueForecaster()
        self.cma_analyzer = CMAAnalyzer()

    async def get_hero_metrics_data(self, location_id: str) -> List[HeroMetricData]:
        """
        Get all enhanced hero metrics data for Jorge's Command Center.

        Returns:
            List of HeroMetricData objects for rendering
        """
        try:
            self.logger.info(f"Generating hero metrics for location {location_id}")

            # Get data from all sources (with fallback handling)
            hot_leads_data = await self._get_hot_leads_data(location_id)
            seller_pipeline_data = await self._get_seller_pipeline_data(location_id)
            historical_commission_data = await self._get_historical_commission_data(location_id)
            ghl_health_data = await self._get_ghl_health_data(location_id)
            performance_data = await self._get_performance_data(location_id)

            metrics = []

            # 1. Enhanced Hot Leads with Source ROI
            metrics.append(await self._create_hot_leads_metric(hot_leads_data))

            # 2. Enhanced CMA Pipeline with Revenue Prediction
            metrics.append(await self._create_cma_metric(seller_pipeline_data))

            # 3. 30-Day Revenue Forecast (NEW)
            metrics.append(
                await self._create_forecast_metric(
                    hot_leads_data,
                    seller_pipeline_data,
                    historical_commission_data,
                )
            )

            # 4. Enhanced System Performance
            metrics.append(await self._create_performance_metric(performance_data))

            # 5. GHL Integration Health (Enhanced)
            metrics.append(await self._create_ghl_metric(ghl_health_data))

            self.logger.info(f"Generated {len(metrics)} hero metrics successfully")
            return metrics

        except Exception as e:
            self.logger.error(f"Error generating hero metrics: {e}")
            return self._create_fallback_metrics()

    async def _create_hot_leads_metric(self, leads_data: Dict) -> HeroMetricData:
        """Create enhanced hot leads metric with source ROI"""
        try:
            hot_count = leads_data.get("count", 0)
            best_source = leads_data.get("best_source", {})

            if best_source:
                roi_text = self.lead_source_roi.format_roi_display(best_source.get("roi", 0))
                source_name = best_source.get("source", "Unknown")
                value_text = f"{hot_count} leads"
                delta_text = f"Best: {source_name} ({roi_text})"
            else:
                value_text = f"{hot_count} leads"
                delta_text = "+{} from yesterday".format(leads_data.get("delta", 0))

            # Determine urgency
            if hot_count >= 10:
                urgency = "high"
                color = "red"
            elif hot_count >= 5:
                urgency = "medium"
                color = "amber"
            else:
                urgency = "low"
                color = "blue"

            return HeroMetricData(
                label="Hot Leads Pipeline",
                value=value_text,
                delta=delta_text,
                color=color,
                urgency_level=urgency,
                action_button="View All Hot Leads" if hot_count > 0 else None,
                tooltip="Leads scoring ≥80 with highest ROI source highlighted"
            )

        except Exception as e:
            self.logger.error(f"Error creating hot leads metric: {e}")
            return HeroMetricData(
                label="Hot Leads Pipeline",
                value="Error loading",
                delta="Check data sources",
                color="red",
                urgency_level="high"
            )

    async def _create_cma_metric(self, seller_data: Dict) -> HeroMetricData:
        """Create enhanced CMA metric with revenue prediction"""
        try:
            q4_sellers = seller_data.get("q4_ready", [])
            commission_potential = seller_data.get("commission_potential", 0)

            count = len(q4_sellers) if isinstance(q4_sellers, list) else q4_sellers
            commission_str = f"${commission_potential/1000:.0f}K" if commission_potential > 1000 else f"${commission_potential:.0f}"

            value_text = f"{count} sellers"
            delta_text = f"Est. {commission_str} commission"

            # Determine urgency based on commission potential
            if commission_potential >= 50000:
                urgency = "high"
                color = "green"
            elif commission_potential >= 25000:
                urgency = "medium"
                color = "amber"
            else:
                urgency = "low"
                color = "blue"

            return HeroMetricData(
                label="Q4 CMAs Ready",
                value=value_text,
                delta=delta_text,
                color=color,
                urgency_level=urgency,
                action_button="Generate All CMAs" if count > 0 else None,
                tooltip="Q4 qualified sellers ready for CMA automation with commission potential"
            )

        except Exception as e:
            self.logger.error(f"Error creating CMA metric: {e}")
            return HeroMetricData(
                label="Q4 CMAs Ready",
                value="Error loading",
                delta="Check seller data",
                color="red",
                urgency_level="high"
            )

    async def _create_forecast_metric(
        self,
        leads_data: Dict,
        seller_data: Dict,
        historical_data: List[Dict[str, Any]],
    ) -> HeroMetricData:
        """Create 30-day revenue forecast metric from live pipeline + deal history."""
        try:
            pipeline_data = self._extract_pipeline_data(leads_data, seller_data)

            forecast = self.revenue_forecaster.calculate_30_day_forecast(
                historical_data, pipeline_data
            )

            projected = forecast.get("projected_revenue", 0)
            trend = forecast.get("trend_direction", "neutral")
            confidence_range = forecast.get("confidence_range", [0, 0])

            value_text = f"${projected//1000}K forecast"
            range_str = f"${confidence_range[0]//1000}K - ${confidence_range[1]//1000}K range"

            # Trend indicators
            trend_indicators = {
                "up": ("green", "Strong pipeline"),
                "down": ("red", "Need lead generation"),
                "neutral": ("blue", "Steady pace")
            }
            color, trend_text = trend_indicators.get(trend, ("blue", "Calculating"))

            return HeroMetricData(
                label="30-Day Forecast",
                value=value_text,
                delta=f"{trend_text} | {range_str}",
                color=color,
                urgency_level="medium",
                tooltip="AI-powered revenue forecast based on current pipeline and historical trends"
            )

        except Exception as e:
            self.logger.error(f"Error creating forecast metric: {e}")
            return HeroMetricData(
                label="30-Day Forecast",
                value="Calculating...",
                delta="Analyzing trends",
                color="blue",
                urgency_level="low"
            )

    async def _create_performance_metric(self, performance_data: Dict) -> HeroMetricData:
        """Create system performance metric"""
        try:
            compliance = performance_data.get("five_min_compliance", 0.0)
            avg_response_minutes = float(performance_data.get("avg_response_time_minutes", 0.0) or 0.0)

            compliance_pct = f"{compliance:.1%}"

            if compliance >= 0.95:
                color = "green"
                urgency = "low"
                status = "Excellent"
            elif compliance >= 0.85:
                color = "amber"
                urgency = "medium"
                status = "Good"
            else:
                color = "red"
                urgency = "high"
                status = "Needs attention"

            return HeroMetricData(
                label="5-Min Rule",
                value=compliance_pct,
                delta=f"{status} | Avg: {avg_response_minutes:.1f}m",
                color=color,
                urgency_level=urgency,
                tooltip="Percentage of leads contacted within 5 minutes (industry best practice)"
            )

        except Exception as e:
            return HeroMetricData(
                label="5-Min Rule",
                value="Error",
                delta="Check system",
                color="red",
                urgency_level="high"
            )

    async def _create_ghl_metric(self, ghl_data: Dict) -> HeroMetricData:
        """Create GHL integration health metric"""
        try:
            healthy = ghl_data.get("healthy", False)
            response_time = ghl_data.get("response_time", 0)
            webhook_count = ghl_data.get("webhook_count", 0)

            if healthy:
                value_text = "Operational"
                delta_text = f"{webhook_count} webhooks | {response_time}ms"
                color = "green"
                urgency = "low"
            else:
                value_text = "Offline"
                delta_text = "Check API connection"
                color = "red"
                urgency = "high"

            return HeroMetricData(
                label="GHL Integration",
                value=value_text,
                delta=delta_text,
                color=color,
                urgency_level=urgency,
                tooltip="GoHighLevel API health and webhook processing status"
            )

        except Exception as e:
            return HeroMetricData(
                label="GHL Integration",
                value="Error",
                delta="Check configuration",
                color="red",
                urgency_level="high"
            )

    async def _get_hot_leads_data(self, location_id: str) -> Dict:
        """Get hot leads data from live leads table with source ROI analysis."""
        try:
            normalized_location = (location_id or "").strip()
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_start = today_start - timedelta(days=1)
            source_costs = self._lead_source_cost_map()

            hot_leads: List[Dict[str, Any]] = []
            roi_source_data: List[Dict[str, Any]] = []
            hot_today = 0
            hot_yesterday = 0

            async with AsyncSessionFactory() as session:
                stmt = select(
                    LeadModel.contact_id,
                    LeadModel.location_id,
                    ContactModel.location_id,
                    LeadModel.score,
                    LeadModel.temperature,
                    LeadModel.budget_min,
                    LeadModel.budget_max,
                    LeadModel.metadata_json,
                    LeadModel.created_at,
                ).select_from(LeadModel).join(
                    ContactModel,
                    ContactModel.contact_id == LeadModel.contact_id,
                    isouter=True,
                )
                if normalized_location:
                    stmt = stmt.where(
                        (LeadModel.location_id == normalized_location)
                        | (
                            LeadModel.location_id.is_(None)
                            & (ContactModel.location_id == normalized_location)
                        )
                    )
                rows = (await session.execute(stmt)).all()

            for row in rows:
                (
                    contact_id,
                    lead_location_id,
                    contact_location_id,
                    score,
                    temperature,
                    budget_min,
                    budget_max,
                    metadata_json,
                    created_at,
                ) = row

                metadata = metadata_json if isinstance(metadata_json, dict) else {}
                source = str(
                    metadata.get("lead_source")
                    or metadata.get("source")
                    or metadata.get("channel")
                    or "unknown"
                ).strip().lower() or "unknown"
                source_key = source.replace(" ", "_")
                score_value = float(score or 0.0)
                temp_value = str(temperature or "").strip().upper()
                is_hot = temp_value == "HOT" or score_value >= 80.0
                budget_for_commission = float(budget_max or budget_min or 0.0)
                estimated_commission = (
                    float(JorgeBusinessRules.calculate_commission(budget_for_commission))
                    if budget_for_commission > 0
                    else 0.0
                )

                roi_source_data.append(
                    {
                        "id": str(contact_id),
                        "source": source_key,
                        "score": score_value,
                        "commission": estimated_commission,
                        "cost_per_lead": float(source_costs.get(source_key, source_costs.get("unknown", 60.0))),
                        "status": "hot" if is_hot else "warm",
                    }
                )

                if not is_hot:
                    continue

                created_at_dt = created_at if isinstance(created_at, datetime) else None
                if created_at_dt and created_at_dt >= today_start:
                    hot_today += 1
                elif created_at_dt and yesterday_start <= created_at_dt < today_start:
                    hot_yesterday += 1

                hot_leads.append(
                    {
                        "id": str(contact_id),
                        "location_id": lead_location_id or contact_location_id,
                        "score": score_value,
                        "temperature": temp_value,
                        "source": source_key,
                        "commission": estimated_commission,
                        "probability": max(0.35, min(0.9, score_value / 100.0)) if score_value > 0 else 0.5,
                        "close_date": metadata.get("close_date"),
                        "created_at": created_at_dt,
                    }
                )

            best_source = self.lead_source_roi.get_best_performing_source(roi_source_data) if roi_source_data else {}

            return {
                "count": len(hot_leads),
                "best_source": best_source,
                "delta": hot_today - hot_yesterday,
                "total_leads": len(rows),
                "hot_leads": hot_leads,
            }
        except Exception as e:
            self.logger.error(f"Error getting hot leads data: {e}")
            return {"count": 0, "best_source": {}, "delta": 0, "total_leads": 0, "hot_leads": []}

    async def _get_seller_pipeline_data(self, location_id: str) -> Dict:
        """Get seller pipeline data from live conversation records."""
        try:
            normalized_location = (location_id or "").strip()
            q4_sellers: List[Dict[str, Any]] = []

            async with AsyncSessionFactory() as session:
                rows = (
                    await session.execute(
                        select(
                            ConversationModel.contact_id,
                            ConversationModel.stage,
                            ConversationModel.questions_answered,
                            ConversationModel.is_qualified,
                            ConversationModel.extracted_data,
                            ConversationModel.metadata_json,
                            ConversationModel.updated_at,
                            ContactModel.location_id,
                            ContactModel.name,
                        ).select_from(ConversationModel).join(
                            ContactModel,
                            ContactModel.contact_id == ConversationModel.contact_id,
                            isouter=True,
                        ).where(ConversationModel.bot_type == "seller")
                    )
                ).all()

            for row in rows:
                (
                    contact_id,
                    stage,
                    questions_answered,
                    is_qualified,
                    extracted_data,
                    metadata_json,
                    updated_at,
                    contact_location_id,
                    contact_name,
                ) = row
                extracted = extracted_data if isinstance(extracted_data, dict) else {}
                metadata = metadata_json if isinstance(metadata_json, dict) else {}
                row_location = str(contact_location_id or metadata.get("location_id") or "").strip()
                if normalized_location and row_location != normalized_location:
                    continue

                stage_upper = str(stage or "").upper()
                ready_for_cma = bool(is_qualified) or stage_upper in {"Q4", "QUALIFIED"} or int(questions_answered or 0) >= 4
                if not ready_for_cma:
                    continue

                price_expectation = self._coerce_price(extracted.get("price_expectation"))
                urgency = str(extracted.get("urgency") or "medium").strip().lower() or "medium"
                if urgency not in {"high", "medium", "low"}:
                    urgency = "medium"

                seller_entry = {
                    "id": str(contact_id),
                    "name": contact_name or metadata.get("contact_name") or str(contact_id),
                    "questions_answered": int(questions_answered or 0),
                    "price_expectation": price_expectation,
                    "urgency": urgency,
                    "close_date": metadata.get("estimated_close_date"),
                    "updated_at": updated_at if isinstance(updated_at, datetime) else None,
                }
                q4_sellers.append(seller_entry)

            commission_potential = sum(
                self.cma_analyzer.calculate_commission_potential(seller)
                for seller in q4_sellers
            )

            return {
                "q4_ready": q4_sellers,
                "commission_potential": commission_potential,
                "high_urgency_count": len([s for s in q4_sellers if s.get("urgency") == "high"]),
            }
        except Exception as e:
            self.logger.error(f"Error getting seller pipeline data: {e}")
            return {"q4_ready": [], "commission_potential": 0.0, "high_urgency_count": 0}

    async def _get_ghl_health_data(self, location_id: str) -> Dict:
        """Get GHL integration health data from live integration status service."""
        try:
            from command_center.components.ghl_integration_status import (
                ConnectionStatus,
                create_ghl_integration_status,
            )

            status_component = await create_ghl_integration_status()
            status = await status_component.get_integration_status(location_id)
            connection_status = status.connection.status
            return {
                "healthy": connection_status != ConnectionStatus.DISCONNECTED,
                "response_time": round(float(status.connection.response_time_ms or 0.0), 1),
                "webhook_count": int(status.webhooks.total_received or 0),
                "connection_status": connection_status.value,
                "errors_last_hour": int(status.connection.errors_last_hour or 0),
            }
        except Exception as e:
            self.logger.warning(f"GHL integration status service unavailable, falling back to basic health check: {e}")
            try:
                ghl_client = GHLClient()
                health_result = await ghl_client.health_check()
                return {
                    "healthy": bool(health_result.get("healthy", False)),
                    "response_time": round(float(health_result.get("response_time_ms", 0.0) or 0.0), 1),
                    "webhook_count": 0,
                    "connection_status": "degraded",
                    "errors_last_hour": 0,
                }
            except Exception as fallback_error:
                self.logger.error(f"Error getting GHL health data: {fallback_error}")
                return {"healthy": False, "response_time": 0.0, "webhook_count": 0, "error": str(fallback_error)}

    async def _get_performance_data(self, location_id: str) -> Dict:
        """Get live 5-minute-rule performance from event-derived trends + tracker stats."""
        try:
            dashboard_service = DashboardDataService()
            trends = await dashboard_service.get_hourly_performance_trends(hours=24, location_id=location_id)

            response_counts = trends.get("first_response_total_counts") if isinstance(trends, dict) else []
            response_within_5_counts = trends.get("first_response_within_5_counts") if isinstance(trends, dict) else []
            avg_response_min = trends.get("avg_response_time_min") if isinstance(trends, dict) else []

            total_responses = (
                int(sum(response_counts))
                if isinstance(response_counts, list)
                else int(trends.get("first_response_total", 0) or 0)
            )
            within_five = (
                int(sum(response_within_5_counts))
                if isinstance(response_within_5_counts, list)
                else int(trends.get("first_response_within_5_min", 0) or 0)
            )
            five_min_compliance = (within_five / total_responses) if total_responses > 0 else 0.0

            if (
                isinstance(avg_response_min, list)
                and isinstance(response_counts, list)
                and len(avg_response_min) == len(response_counts)
                and total_responses > 0
            ):
                weighted_sum = 0.0
                for idx, avg_value in enumerate(avg_response_min):
                    weighted_sum += float(avg_value or 0.0) * float(response_counts[idx] or 0)
                avg_response_minutes = weighted_sum / total_responses
            elif isinstance(avg_response_min, list) and avg_response_min:
                non_zero = [float(value) for value in avg_response_min if float(value or 0.0) > 0.0]
                avg_response_minutes = (sum(non_zero) / len(non_zero)) if non_zero else 0.0
            else:
                avg_response_minutes = 0.0

            perf_metrics = await get_metrics_service().get_performance_metrics()
            cache_hit_rate = float(perf_metrics.cache_hit_rate or 0.0) / 100.0
            api_success_rate = 1.0 - (float(perf_metrics.ghl_error_rate or 0.0) / 100.0)

            return {
                "five_min_compliance": max(0.0, min(1.0, five_min_compliance)),
                "avg_response_time_minutes": round(float(avg_response_minutes or 0.0), 2),
                "sample_size": total_responses,
                "cache_hit_rate": max(0.0, min(1.0, cache_hit_rate)),
                "api_success_rate": max(0.0, min(1.0, api_success_rate)),
            }
        except Exception as e:
            self.logger.error(f"Error getting performance data: {e}")
            return {
                "five_min_compliance": 0.0,
                "avg_response_time_minutes": 0.0,
                "sample_size": 0,
                "cache_hit_rate": 0.0,
                "api_success_rate": 0.0,
            }

    async def _get_historical_commission_data(self, location_id: str, days: int = 60) -> List[Dict[str, Any]]:
        """Load historical closed-commission data from deals for forecasting baseline."""
        try:
            cutoff = datetime.utcnow() - timedelta(days=max(14, int(days or 60)))
            normalized_location = (location_id or "").strip()
            async with AsyncSessionFactory() as session:
                rows = (
                    await session.execute(
                        select(
                            DealModel.closed_at,
                            DealModel.commission,
                            DealModel.metadata_json,
                            ContactModel.location_id,
                        ).select_from(DealModel).join(
                            ContactModel,
                            ContactModel.contact_id == DealModel.contact_id,
                            isouter=True,
                        ).where(
                            DealModel.closed_at.isnot(None),
                            DealModel.closed_at >= cutoff,
                        )
                    )
                ).all()

            data: List[Dict[str, Any]] = []
            for closed_at, commission, metadata_json, contact_location_id in rows:
                closed_at_dt = closed_at if isinstance(closed_at, datetime) else None
                if not closed_at_dt:
                    continue
                metadata = metadata_json if isinstance(metadata_json, dict) else {}
                row_location = str(contact_location_id or metadata.get("location_id") or "").strip()
                if normalized_location and row_location != normalized_location:
                    continue
                data.append(
                    {
                        "date": closed_at_dt,
                        "commission": float(commission or 0.0),
                    }
                )
            return data
        except Exception as e:
            self.logger.error(f"Error loading historical commission data: {e}")
            return []

    def _extract_pipeline_data(self, leads_data: Dict, seller_data: Dict) -> List[Dict]:
        """Extract pipeline data for forecasting"""
        pipeline = []

        # Add hot leads to pipeline
        hot_leads = leads_data.get("hot_leads", []) if isinstance(leads_data, dict) else []
        for lead in hot_leads:
            if not isinstance(lead, dict):
                continue
            pipeline.append({
                "id": str(lead.get("id", "unknown")),
                "commission": float(lead.get("commission", 0.0) or 0.0),
                "probability": float(lead.get("probability", 0.65) or 0.65),
                "close_date": lead.get("close_date"),
            })

        # Add seller pipeline
        sellers = seller_data.get("q4_ready", [])
        for seller in sellers:
            if isinstance(seller, dict):
                commission = self.cma_analyzer.calculate_commission_potential(seller)
                pipeline.append({
                    "id": seller.get("id", "unknown"),
                    "commission": commission,
                    "probability": 0.8 if seller.get("urgency") == "high" else 0.6,
                    "close_date": seller.get("close_date"),
                })

        return pipeline

    @staticmethod
    def _lead_source_cost_map() -> Dict[str, float]:
        """Deterministic per-source CPL assumptions for ROI calculations."""
        return {
            "referral": 0.0,
            "google_ads": 65.0,
            "facebook": 45.0,
            "zillow": 125.0,
            "realtor.com": 150.0,
            "organic": 25.0,
            "unknown": 60.0,
        }

    @staticmethod
    def _coerce_price(value: Any) -> float:
        """Coerce mixed numeric/text price values into float."""
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            normalized = value.strip().replace("$", "").replace(",", "")
            try:
                return float(normalized)
            except Exception:
                return 0.0
        return 0.0

    def _create_fallback_metrics(self) -> List[HeroMetricData]:
        """Create fallback metrics when data sources fail"""
        return [
            HeroMetricData(
                label="Hot Leads Pipeline",
                value="Error loading",
                delta="Please wait",
                color="blue",
                urgency_level="low",
                tooltip="Loading lead data from sources"
            ),
            HeroMetricData(
                label="Q4 CMAs Ready",
                value="Error loading",
                delta="Please wait",
                color="blue",
                urgency_level="low"
            ),
            HeroMetricData(
                label="30-Day Forecast",
                value="Calculating...",
                delta="Analyzing trends",
                color="blue",
                urgency_level="low"
            )
        ]

    def format_metric_card(self, metric: HeroMetricData) -> str:
        """Format metric for Streamlit display (used by tests)"""
        return f"{metric.label}: {metric.value} ({metric.delta})"


# Factory function for component
def create_enhanced_hero_metrics() -> EnhancedHeroMetrics:
    """Create and configure enhanced hero metrics component"""
    return EnhancedHeroMetrics()
