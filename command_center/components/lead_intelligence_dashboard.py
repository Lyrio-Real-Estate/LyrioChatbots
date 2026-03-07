"""
Smart Lead Intelligence Dashboard - Advanced Analytics & Predictive Insights

Enhanced lead intelligence with predictive analytics:
- Score distribution analysis with temperature breakdown
- Budget range analysis with Dallas market insights
- Timeline classification with urgency optimization
- Geographic heatmap with ROI by location
- Predictive lead scoring trends
- Source performance analytics

Author: Claude Code Assistant
Created: 2026-01-23
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from bots.shared.logger import get_logger

logger = get_logger(__name__)


class LeadIntelligenceDashboard:
    """
    Smart Lead Intelligence Dashboard with Predictive Analytics

    Features:
    - Interactive score distribution charts
    - Budget range analysis with market insights
    - Timeline classification with urgency optimization
    - Geographic performance heatmap
    - Predictive scoring trends
    - Source performance analytics
    """

    def __init__(self):
        self.logger = get_logger(__name__)

    @staticmethod
    def _is_light_mode() -> bool:
        """Resolve current UI mode from session/query state."""
        toggle_state = st.session_state.get("sidebar_theme_toggle")
        if isinstance(toggle_state, bool):
            return toggle_state

        theme_value = str(st.session_state.get("ui_theme", "")).strip().lower()
        if theme_value in {"dark", "light"}:
            return theme_value == "light"

        query_params = getattr(st, "query_params", {})
        query_theme = query_params.get("theme") if hasattr(query_params, "get") else None
        if isinstance(query_theme, list):
            query_theme = query_theme[0] if query_theme else None
        return str(query_theme or "").strip().lower() == "light"

    def _chart_palette(self) -> Dict[str, str]:
        """Return chart palette aligned to current dashboard theme."""
        if self._is_light_mode():
            return {
                "template": "plotly_white",
                "paper_bg": "#ffffff",
                "plot_bg": "#f8fafc",
                "font": "#334155",
                "grid": "#dbe3ee",
                "axis": "#cbd5e1",
                "legend_bg": "rgba(255,255,255,0.72)",
                "stroke": "#ffffff",
            }
        return {
            "template": "plotly_dark",
            "paper_bg": "#050c18",
            "plot_bg": "#0b1220",
            "font": "#cbd5e1",
            "grid": "#243449",
            "axis": "#32445d",
            "legend_bg": "rgba(5,12,24,0.45)",
            "stroke": "#233246",
        }

    def _apply_chart_theme(
        self,
        fig: go.Figure,
        apply_axes: bool = True,
        **layout_kwargs: Any,
    ) -> None:
        """Apply consistent chart styling for light/dark mode."""
        palette = self._chart_palette()
        custom_font = layout_kwargs.pop("font", None)
        custom_legend = layout_kwargs.pop("legend", None)

        merged_font: Any = {"color": palette["font"]}
        if isinstance(custom_font, dict):
            merged_font.update(custom_font)
        elif custom_font is not None:
            merged_font = custom_font

        merged_legend: Any = {
            "bgcolor": palette["legend_bg"],
            "font": {"color": palette["font"]},
        }
        if isinstance(custom_legend, dict):
            legend_font = dict(merged_legend["font"])
            custom_legend_font = custom_legend.get("font")
            if isinstance(custom_legend_font, dict):
                legend_font.update(custom_legend_font)
            merged_legend.update(custom_legend)
            merged_legend["font"] = legend_font
        elif custom_legend is not None:
            merged_legend = custom_legend

        fig.update_layout(
            template=palette["template"],
            paper_bgcolor=palette["paper_bg"],
            plot_bgcolor=palette["plot_bg"],
            font=merged_font,
            legend=merged_legend,
            **layout_kwargs,
        )
        if apply_axes:
            fig.update_xaxes(
                gridcolor=palette["grid"],
                linecolor=palette["axis"],
                zerolinecolor=palette["grid"],
                tickfont={"color": palette["font"]},
                title_font={"color": palette["font"]},
            )
            fig.update_yaxes(
                gridcolor=palette["grid"],
                linecolor=palette["axis"],
                zerolinecolor=palette["grid"],
                tickfont={"color": palette["font"]},
                title_font={"color": palette["font"]},
            )

    def render_lead_intelligence_section(self, location_id: str) -> None:
        """
        Render the complete lead intelligence dashboard section.

        Args:
            location_id: GHL location ID for data filtering
        """
        # Section header
        st.markdown("""
        <h3 style='margin-bottom: 8px;'>Lead Intelligence Analytics</h3>
        <p style='color: #6b7280; margin-top: 0; margin-bottom: 20px;'>AI-powered lead scoring and market insights</p>
        """, unsafe_allow_html=True)

        # Load lead intelligence data
        lead_data = self._load_lead_intelligence_data(location_id)

        if not lead_data:
            self._render_loading_state()
            return

        # Create three-column layout for charts
        col1, col2, col3 = st.columns(3)

        with col1:
            self._render_score_distribution_chart(lead_data)

        with col2:
            self._render_budget_analysis_chart(lead_data)

        with col3:
            self._render_timeline_classification_chart(lead_data)

        # Second row: Advanced analytics
        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            self._render_geographic_heatmap(lead_data)

        with col2:
            self._render_source_performance_chart(lead_data)

        # Third row: Predictive insights
        st.markdown("---")
        self._render_predictive_insights_section(lead_data)

    @st.cache_data(ttl=300)  # Cache for 5 minutes
    def _load_lead_intelligence_data(_self, location_id: str) -> List[Dict[str, Any]]:
        """Load lead intelligence data with caching"""
        try:
            # Generate mock lead data with realistic patterns
            mock_leads_data = [
                {
                    "id": f"lead_{i}",
                    "score": 85 + (i % 15),  # Scores 85-99
                    "source": ["zillow", "realtor.com", "facebook", "referral", "google"][i % 5],
                    "budget_min": 300000 + (i * 25000),
                    "budget_max": 400000 + (i * 30000),
                    "timeline": ["immediate", "1_month", "2_months", "3_months"][i % 4],
                    "location": ["Dallas", "Plano", "Frisco", "McKinney", "Allen"][i % 5],
                    "financing": ["pre_approved", "cash", "conventional", "fha"][i % 4],
                    "created_at": datetime.now() - timedelta(days=i),
                    "temperature": "hot" if (85 + (i % 15)) >= 90 else "warm" if (85 + (i % 15)) >= 80 else "cold"
                }
                for i in range(25)  # 25 mock leads
            ]

            # Add some lower-scoring leads for realistic distribution
            for i in range(15):
                mock_leads_data.append({
                    "id": f"lead_cold_{i}",
                    "score": 45 + (i % 30),  # Scores 45-74
                    "source": ["zillow", "facebook", "google"][i % 3],
                    "budget_min": 200000 + (i * 15000),
                    "budget_max": 300000 + (i * 20000),
                    "timeline": ["3_months", "6_months", "flexible"][i % 3],
                    "location": ["Dallas", "Garland", "Irving"][i % 3],
                    "financing": ["needs_financing", "conventional"][i % 2],
                    "created_at": datetime.now() - timedelta(days=i + 25),
                    "temperature": "warm" if (45 + (i % 30)) >= 60 else "cold"
                })

            return mock_leads_data

        except Exception as e:
            logger.error(f"Error loading lead intelligence data: {e}")
            return []

    def _render_score_distribution_chart(self, lead_data: List[Dict]) -> None:
        """Render interactive score distribution chart"""
        if not lead_data:
            return

        st.markdown("**Score Distribution**")
        palette = self._chart_palette()

        # Create score ranges
        scores = [lead["score"] for lead in lead_data]
        temperatures = [lead["temperature"] for lead in lead_data]

        # Count by temperature
        temp_counts = {
            "HOT (80-100)": len([s for s, t in zip(scores, temperatures) if t == "hot"]),
            "WARM (60-79)": len([s for s, t in zip(scores, temperatures) if t == "warm"]),
            "COLD (0-59)": len([s for s, t in zip(scores, temperatures) if t == "cold"])
        }

        # Create donut chart
        fig = go.Figure(data=[go.Pie(
            labels=list(temp_counts.keys()),
            values=list(temp_counts.values()),
            hole=0.4,
            marker=dict(
                colors=["#ef4444", "#f59e0b", "#3b82f6"],
                line=dict(color=palette["stroke"], width=2)
            ),
            textinfo='label+percent',
            textposition='outside',
            textfont=dict(size=12)
        )])

        self._apply_chart_theme(
            fig,
            height=300,
            margin=dict(l=0, r=0, t=20, b=0),
            showlegend=False,
            font=dict(size=11, color=palette["font"]),
            annotations=[dict(
                text=f"<b>{len(lead_data)}</b><br>Total Leads",
                x=0.5, y=0.5,
                font=dict(size=14, color=palette["font"]),
                showarrow=False
            )]
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Add summary stats
        hot_count = temp_counts["HOT (80-100)"]
        total_count = len(lead_data)
        hot_percentage = (hot_count / total_count * 100) if total_count > 0 else 0

        if hot_percentage >= 30:
            st.success(f"{hot_percentage:.1f}% hot leads - excellent quality!")
        elif hot_percentage >= 20:
            st.info(f"Warm {hot_percentage:.1f}% hot leads - good performance")
        else:
            st.warning(f"{hot_percentage:.1f}% hot leads - improve lead sources")

    def _render_budget_analysis_chart(self, lead_data: List[Dict]) -> None:
        """Render budget range analysis with Dallas market insights"""
        if not lead_data:
            return

        st.markdown("**Budget Analysis**")
        palette = self._chart_palette()

        # Create budget ranges aligned with Dallas market
        budget_ranges = []
        for lead in lead_data:
            budget_max = lead.get("budget_max", 0)
            if budget_max >= 600000:
                budget_ranges.append("$600K+ (Luxury)")
            elif budget_max >= 500000:
                budget_ranges.append("$500K-$600K (Premium)")
            elif budget_max >= 400000:
                budget_ranges.append("$400K-$500K (Upper Mid)")
            elif budget_max >= 300000:
                budget_ranges.append("$300K-$400K (Mid Market)")
            else:
                budget_ranges.append("Under $300K (Entry)")

        # Count leads by budget range
        budget_df = pd.DataFrame({"budget_range": budget_ranges})
        budget_counts = budget_df["budget_range"].value_counts()

        # Create horizontal bar chart
        fig = go.Figure(data=[go.Bar(
            x=budget_counts.values,
            y=budget_counts.index,
            orientation='h',
            marker=dict(
                color=['#10b981', '#3b82f6', '#6366f1', '#8b5cf6', '#ec4899'],
                opacity=0.8
            ),
            text=budget_counts.values,
            textposition='inside',
            textfont=dict(color='white', size=11)
        )])

        self._apply_chart_theme(
            fig,
            height=300,
            margin=dict(l=0, r=0, t=20, b=40),
            xaxis_title="Number of Leads",
            yaxis_title="",
            font=dict(size=11, color=palette["font"]),
        )
        fig.update_yaxes(showgrid=False)

        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Add market insight
        premium_count = sum(1 for lead in lead_data if lead.get("budget_max", 0) >= 500000)
        total_count = len(lead_data)
        premium_percentage = (premium_count / total_count * 100) if total_count > 0 else 0

        if premium_percentage >= 40:
            st.success(f"{premium_percentage:.1f}% premium buyers - high commission potential")
        else:
            st.info(f"{premium_percentage:.1f}% premium buyers - focus on lead quality")

    def _render_timeline_classification_chart(self, lead_data: List[Dict]) -> None:
        """Render timeline classification with urgency optimization"""
        if not lead_data:
            return

        st.markdown("**Timeline Analysis**")
        palette = self._chart_palette()

        # Create timeline categories with urgency mapping
        timeline_categories = []
        urgency_colors = []

        for lead in lead_data:
            timeline = lead.get("timeline", "unknown")

            if timeline == "immediate":
                timeline_categories.append("Immediate (0-30 days)")
                urgency_colors.append("#ef4444")  # Red for urgent
            elif timeline == "1_month":
                timeline_categories.append("1 Month")
                urgency_colors.append("#f59e0b")  # Amber for medium
            elif timeline == "2_months":
                timeline_categories.append("2 Months")
                urgency_colors.append("#3b82f6")  # Blue for low
            elif timeline == "3_months":
                timeline_categories.append("3 Months")
                urgency_colors.append("#6b7280")  # Gray for flexible
            else:
                timeline_categories.append("6+ Months / Flexible")
                urgency_colors.append("#9ca3af")  # Light gray

        # Count by timeline
        timeline_df = pd.DataFrame({
            "timeline": timeline_categories,
            "color": urgency_colors
        })
        timeline_counts = timeline_df["timeline"].value_counts()

        # Create pie chart with timeline urgency
        colors = []
        for timeline in timeline_counts.index:
            if "Immediate" in timeline:
                colors.append("#ef4444")
            elif "1 Month" in timeline:
                colors.append("#f59e0b")
            elif "2 Months" in timeline:
                colors.append("#3b82f6")
            elif "3 Months" in timeline:
                colors.append("#6b7280")
            else:
                colors.append("#9ca3af")

        fig = go.Figure(data=[go.Pie(
            labels=timeline_counts.index,
            values=timeline_counts.values,
            marker=dict(colors=colors, line=dict(color=palette["stroke"], width=1)),
            textinfo='label+percent',
            textposition='outside',
            textfont=dict(size=10)
        )])

        self._apply_chart_theme(
            fig,
            height=300,
            margin=dict(l=0, r=0, t=20, b=0),
            showlegend=False,
            font=dict(size=11, color=palette["font"]),
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Add urgency insight
        urgent_count = sum(1 for lead in lead_data if lead.get("timeline") in ["immediate", "1_month"])
        total_count = len(lead_data)
        urgent_percentage = (urgent_count / total_count * 100) if total_count > 0 else 0

        if urgent_percentage >= 50:
            st.success(f"{urgent_percentage:.1f}% urgent timeline - prioritize follow-up")
        elif urgent_percentage >= 30:
            st.info(f"{urgent_percentage:.1f}% urgent timeline - good conversion potential")
        else:
            st.warning(f"{urgent_percentage:.1f}% urgent timeline - focus on nurturing")

    def _render_geographic_heatmap(self, lead_data: List[Dict]) -> None:
        """Render geographic performance heatmap"""
        st.markdown("**Geographic Performance**")
        palette = self._chart_palette()

        # Aggregate data by location
        location_data = {}
        for lead in lead_data:
            location = lead.get("location", "Unknown")
            score = lead.get("score", 0)
            budget_max = lead.get("budget_max", 0)

            if location not in location_data:
                location_data[location] = {
                    "count": 0,
                    "avg_score": 0,
                    "total_budget": 0,
                    "hot_count": 0
                }

            location_data[location]["count"] += 1
            location_data[location]["avg_score"] = (
                (location_data[location]["avg_score"] * (location_data[location]["count"] - 1) + score) /
                location_data[location]["count"]
            )
            location_data[location]["total_budget"] += budget_max
            if score >= 80:
                location_data[location]["hot_count"] += 1

        # Create DataFrame for visualization
        geo_df = pd.DataFrame([
            {
                "Location": location,
                "Lead Count": data["count"],
                "Avg Score": data["avg_score"],
                "Total Budget": data["total_budget"],
                "Hot Leads": data["hot_count"],
                "Hot Rate": (data["hot_count"] / data["count"] * 100) if data["count"] > 0 else 0
            }
            for location, data in location_data.items()
        ])

        # Create scatter plot with size = budget, color = score
        fig = px.scatter(
            geo_df,
            x="Location",
            y="Hot Rate",
            size="Lead Count",
            color="Avg Score",
            hover_data=["Lead Count", "Total Budget"],
            color_continuous_scale="RdYlGn",
            title=""
        )

        self._apply_chart_theme(
            fig,
            height=300,
            margin=dict(l=0, r=0, t=20, b=40),
            xaxis_title="Dallas Metro Areas",
            yaxis_title="Hot Lead Rate (%)",
            font=dict(size=11, color=palette["font"]),
            coloraxis_colorbar=dict(
                title="Avg Score",
                titlefont={"color": palette["font"]},
                tickfont={"color": palette["font"]},
            ),
        )

        fig.update_traces(marker=dict(line=dict(width=1, color=palette["stroke"])))

        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Add geographic insight
        best_location = geo_df.loc[geo_df["Hot Rate"].idxmax()]
        st.info(f"Best performing area: {best_location['Location']} ({best_location['Hot Rate']:.1f}% hot rate)")

    def _render_source_performance_chart(self, lead_data: List[Dict]) -> None:
        """Render lead source performance analytics"""
        st.markdown("**Source Performance**")
        palette = self._chart_palette()
        bar_color = "#93c5fd" if self._is_light_mode() else "#7dd3fc"

        # Aggregate data by source
        source_data = {}
        for lead in lead_data:
            source = lead.get("source", "Unknown")
            score = lead.get("score", 0)
            budget_max = lead.get("budget_max", 0)

            if source not in source_data:
                source_data[source] = {
                    "count": 0,
                    "total_score": 0,
                    "total_budget": 0,
                    "hot_count": 0
                }

            source_data[source]["count"] += 1
            source_data[source]["total_score"] += score
            source_data[source]["total_budget"] += budget_max
            if score >= 80:
                source_data[source]["hot_count"] += 1

        # Calculate metrics
        source_metrics = []
        for source, data in source_data.items():
            if data["count"] > 0:
                source_metrics.append({
                    "Source": source.replace("_", " ").title(),
                    "Count": data["count"],
                    "Avg Score": data["total_score"] / data["count"],
                    "Hot Rate": (data["hot_count"] / data["count"]) * 100,
                    "Avg Budget": data["total_budget"] / data["count"]
                })

        source_df = pd.DataFrame(source_metrics)

        # Create dual-axis chart
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # Add bars for lead count
        fig.add_trace(
            go.Bar(
                x=source_df["Source"],
                y=source_df["Count"],
                name="Lead Count",
                marker_color=bar_color,
                opacity=0.7
            ),
            secondary_y=False,
        )

        # Add line for hot rate
        fig.add_trace(
            go.Scatter(
                x=source_df["Source"],
                y=source_df["Hot Rate"],
                mode='lines+markers',
                name="Hot Rate %",
                line=dict(color="#ef4444", width=3),
                marker=dict(size=8)
            ),
            secondary_y=True,
        )

        self._apply_chart_theme(
            fig,
            height=300,
            margin=dict(l=0, r=0, t=20, b=40),
            font=dict(size=11, color=palette["font"]),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                bgcolor=palette["legend_bg"],
                font={"color": palette["font"]},
            ),
        )

        fig.update_xaxes(title_text="Lead Sources")
        fig.update_yaxes(title_text="Lead Count", secondary_y=False)
        fig.update_yaxes(title_text="Hot Rate (%)", secondary_y=True)
        fig.update_yaxes(showgrid=False, secondary_y=True)

        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Add source performance insight
        if len(source_df) > 0:
            best_source = source_df.loc[source_df["Hot Rate"].idxmax()]
            st.success(f"Best source: {best_source['Source']} ({best_source['Hot Rate']:.1f}% hot rate)")

    def _render_predictive_insights_section(self, lead_data: List[Dict]) -> None:
        """Render predictive insights and recommendations"""
        st.markdown("### Predictive Insights & Recommendations")

        col1, col2, col3 = st.columns(3)

        with col1:
            self._render_scoring_trends(lead_data)

        with col2:
            self._render_conversion_predictions(lead_data)

        with col3:
            self._render_actionable_recommendations(lead_data)

    def _render_scoring_trends(self, lead_data: List[Dict]) -> None:
        """Render lead scoring trends over time"""
        st.markdown("**Scoring Trends**")
        palette = self._chart_palette()
        fill_color = "rgba(16, 185, 129, 0.12)" if self._is_light_mode() else "rgba(16, 185, 129, 0.20)"

        # Create time-series data (mock)
        dates = [datetime.now() - timedelta(days=i) for i in range(7, 0, -1)]
        avg_scores = [82.5, 81.2, 83.1, 84.6, 82.9, 85.2, 86.1]  # Mock trend data

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=dates,
            y=avg_scores,
            mode='lines+markers',
            line=dict(color='#10b981', width=3),
            marker=dict(size=8),
            fill='tozeroy',
            fillcolor=fill_color
        ))

        self._apply_chart_theme(
            fig,
            height=200,
            margin=dict(l=0, r=0, t=20, b=40),
            xaxis_title="",
            yaxis_title="Avg Score",
            font=dict(size=10, color=palette["font"]),
            showlegend=False
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

        # Trend analysis
        trend = "+4.8%" if avg_scores[-1] > avg_scores[0] else "-2.1%"
        st.metric("7-Day Trend", f"{avg_scores[-1]:.1f}", trend)

    def _render_conversion_predictions(self, lead_data: List[Dict]) -> None:
        """Render conversion predictions"""
        st.markdown("**Conversion Forecast**")
        palette = self._chart_palette()
        gauge_steps = (
            [
                {"range": [0, 5], "color": "#e2e8f0"},
                {"range": [5, 8], "color": "#fde68a"},
                {"range": [8, 10], "color": "#bbf7d0"},
            ]
            if self._is_light_mode()
            else [
                {"range": [0, 5], "color": "#1f2937"},
                {"range": [5, 8], "color": "#713f12"},
                {"range": [8, 10], "color": "#14532d"},
            ]
        )

        # Mock conversion prediction data
        hot_leads = len([l for l in lead_data if l.get("score", 0) >= 80])
        predicted_conversions = hot_leads * 0.12  # 12% conversion rate

        # Create gauge chart
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=predicted_conversions,
                domain={"x": [0, 1], "y": [0, 1]},
                title={"text": "Expected Conversions", "font": {"color": palette["font"]}},
                number={"font": {"color": palette["font"]}},
                gauge={
                    "axis": {
                        "range": [None, 10],
                        "tickcolor": palette["font"],
                        "tickfont": {"color": palette["font"]},
                    },
                    "bar": {"color": "#3b82f6"},
                    "bgcolor": palette["plot_bg"],
                    "bordercolor": palette["axis"],
                    "borderwidth": 1,
                    "steps": gauge_steps,
                    "threshold": {
                        "line": {"color": "#ef4444", "width": 4},
                        "thickness": 0.75,
                        "value": 8,
                    },
                },
            )
        )

        self._apply_chart_theme(
            fig,
            apply_axes=False,
            height=200,
            margin=dict(l=20, r=20, t=40, b=20),
            font=dict(size=10, color=palette["font"]),
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

        st.metric("This Week", f"{predicted_conversions:.1f} conversions", "+0.8")

    def _render_actionable_recommendations(self, lead_data: List[Dict]) -> None:
        """Render AI-powered actionable recommendations"""
        st.markdown("**Action Items**")

        # Analyze data for recommendations
        hot_count = len([l for l in lead_data if l.get("score", 0) >= 80])
        urgent_count = len([l for l in lead_data if l.get("timeline") in ["immediate", "1_month"]])
        premium_count = len([l for l in lead_data if l.get("budget_max", 0) >= 500000])

        recommendations = []

        if hot_count >= 5:
            recommendations.append("Call top 5 hot leads within 2 hours")

        if urgent_count >= 3:
            recommendations.append("Prioritize urgent timeline leads")

        if premium_count >= 2:
            recommendations.append("Focus on premium budget leads")

        recommendations.extend([
            "Send follow-up to warm Zillow leads",
            "Generate CMAs for Q4 sellers"
        ])

        # Display recommendations as action items
        for i, rec in enumerate(recommendations[:4]):  # Top 4 recommendations
            if st.button(rec, key=f"rec_{i}", use_container_width=True):
                st.success(f"Action triggered: {rec}")

    def _render_loading_state(self) -> None:
        """Render loading state for lead intelligence"""
        st.markdown("### Lead Intelligence Analytics")
        st.markdown("*Loading AI-powered insights...*")

        # Skeleton loading
        cols = st.columns(3)
        for col in cols:
            with col:
                st.markdown("""
                <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin-bottom: 16px;">
                    <div style="background: #e5e7eb; height: 200px; border-radius: 4px;"></div>
                </div>
                """, unsafe_allow_html=True)


# Factory function for component
def render_lead_intelligence_dashboard(location_id: str) -> None:
    """
    Main function to render lead intelligence dashboard.

    Args:
        location_id: GHL location ID
    """
    dashboard = LeadIntelligenceDashboard()
    dashboard.render_lead_intelligence_section(location_id)
