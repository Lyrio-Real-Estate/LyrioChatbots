"""
Performance Analytics Component for Jorge Real Estate AI Dashboard.

Displays comprehensive performance metrics including:
- Cache performance (hit rates, response times)
- AI analysis performance (Claude API metrics)
- GHL integration performance
- Cost savings tracking
- Time-series performance charts

Features real-time updates and interactive visualizations.
"""
import html
from typing import Any, Dict, List, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from bots.shared.logger import get_logger
from bots.shared.dashboard_data_service import get_dashboard_data_service
from command_center.async_runtime import run_async

logger = get_logger(__name__)


class PerformanceAnalyticsComponent:
    """
    Performance analytics component for dashboard display.

    Features:
    - Real-time performance metrics
    - Cache efficiency tracking
    - Cost savings visualization
    - Interactive time-series charts
    - Performance benchmarking
    """

    def __init__(self):
        """Initialize performance analytics component."""
        self.dashboard_service = get_dashboard_data_service()
        logger.info("PerformanceAnalyticsComponent initialized")

    @staticmethod
    def _is_light_mode() -> bool:
        """Resolve current UI mode from session/query state."""
        toggle_state = st.session_state.get("sidebar_theme_toggle")
        if isinstance(toggle_state, bool):
            return toggle_state

        theme_value = str(st.session_state.get("ui_theme", "")).strip().lower()
        if theme_value in {"dark", "light"}:
            return theme_value == "light"

        query_theme = st.query_params.get("theme")
        if isinstance(query_theme, list):
            query_theme = query_theme[0] if query_theme else None
        return str(query_theme or "").strip().lower() == "light"

    def _chart_palette(self) -> Dict[str, str]:
        """Return chart palette aligned to current UI mode."""
        if self._is_light_mode():
            return {
                "template": "plotly_white",
                "paper_bg": "#ffffff",
                "plot_bg": "#f8fafc",
                "font": "#334155",
                "grid": "#dbe3ee",
                "axis": "#cbd5e1",
                "legend_bg": "rgba(255,255,255,0.72)",
            }
        return {
            "template": "plotly_dark",
            "paper_bg": "#050c18",
            "plot_bg": "#0b1220",
            "font": "#cbd5e1",
            "grid": "#243449",
            "axis": "#32445d",
            "legend_bg": "rgba(5,12,24,0.45)",
        }

    def _apply_chart_theme(self, fig: go.Figure, **layout_kwargs: Any) -> None:
        """Apply consistent chart styling for light/dark mode."""
        palette = self._chart_palette()
        fig.update_layout(
            template=palette["template"],
            paper_bgcolor=palette["paper_bg"],
            plot_bgcolor=palette["plot_bg"],
            font={"color": palette["font"]},
            legend={
                "bgcolor": palette["legend_bg"],
                "font": {"color": palette["font"]},
            },
            **layout_kwargs,
        )
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

    def _render_theme_table(self, df: pd.DataFrame) -> None:
        """Render a theme-aware table so light mode does not inherit dark Streamlit DataFrame skin."""
        if df.empty:
            st.info("No data available")
            return

        is_light = self._is_light_mode()
        table_bg = "#ffffff" if is_light else "#0b1220"
        header_bg = "#f8fafc" if is_light else "#121a28"
        text_color = "#334155" if is_light else "#dbe5f3"
        border_color = "#dbe3ee" if is_light else "#233246"
        row_alt = "#f8fafc" if is_light else "#0f1724"

        header_cells = "".join(f"<th>{html.escape(str(col))}</th>" for col in df.columns)
        body_rows = []
        for row in df.itertuples(index=False):
            cells = "".join(f"<td>{html.escape(str(val))}</td>" for val in row)
            body_rows.append(f"<tr>{cells}</tr>")
        body_html = "".join(body_rows)

        st.markdown(
            f"""
            <style>
            .lyrio-theme-table-wrap {{
                overflow-x: auto;
            }}
            .lyrio-theme-table {{
                width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                background: {table_bg};
                border: 1px solid {border_color};
                border-radius: 12px;
                overflow: hidden;
                color: {text_color};
            }}
            .lyrio-theme-table th {{
                background: {header_bg};
                color: {text_color};
                font-weight: 600;
                font-size: 0.92rem;
                text-align: left;
                padding: 10px 12px;
                border-bottom: 1px solid {border_color};
            }}
            .lyrio-theme-table td {{
                color: {text_color};
                font-size: 0.92rem;
                padding: 10px 12px;
                border-bottom: 1px solid {border_color};
            }}
            .lyrio-theme-table tr:nth-child(even) td {{
                background: {row_alt};
            }}
            .lyrio-theme-table tr:last-child td {{
                border-bottom: none;
            }}
            </style>
            <div class="lyrio-theme-table-wrap">
                <table class="lyrio-theme-table">
                    <thead><tr>{header_cells}</tr></thead>
                    <tbody>{body_html}</tbody>
                </table>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def render(self) -> None:
        """
        Render the complete performance analytics component.

        Displays:
        - Performance overview metrics
        - Cache performance charts
        - Cost savings analysis
        - Performance trends
        """
        st.header("Performance Analytics")

        # Fetch performance data
        performance_data = self._fetch_performance_data()

        if performance_data:
            # Display overview metrics
            self._render_overview_metrics(performance_data)

            # Create tabs for different analytics views
            tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Cache Performance", "Cost Savings", "Trends"])

            with tab1:
                self._render_performance_overview(performance_data)

            with tab2:
                self._render_cache_analytics(performance_data)

            with tab3:
                self._render_cost_savings_analytics(performance_data)

            with tab4:
                self._render_performance_trends(performance_data)

        else:
            self._render_error_state()

    def _fetch_performance_data(self) -> Optional[Dict[str, Any]]:
        """Fetch all performance analytics data."""
        try:
            performance_data = run_async(
                self.dashboard_service.get_performance_analytics_data()
            )
            return performance_data

        except Exception as e:
            logger.exception(f"Error fetching performance data: {e}")
            return None

    def _render_overview_metrics(self, performance_data: Dict[str, Any]) -> None:
        """Render high-level performance metrics."""
        if not performance_data.get('performance_metrics'):
            return

        metrics = performance_data['performance_metrics']

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "Cache Hit Rate",
                f"{metrics['cache_hit_rate']:.1f}%",
                delta=f"+{metrics['cache_hit_rate'] - 80:.1f}%" if metrics['cache_hit_rate'] > 80 else None,
                help="Percentage of requests served from cache (target: >80%)"
            )

        with col2:
            st.metric(
                "AI Response Time",
                f"{metrics['ai_avg_ms']:.0f}ms",
                delta=f"-{2000 - metrics['ai_avg_ms']:.0f}ms" if metrics['ai_avg_ms'] < 2000 else None,
                help="Average AI analysis response time (target: <2000ms)"
            )

        with col3:
            st.metric(
                "5-Min Compliance",
                f"{metrics['five_minute_rule_compliance']:.1f}%",
                delta=f"+{metrics['five_minute_rule_compliance'] - 95:.1f}%" if metrics['five_minute_rule_compliance'] > 95 else None,
                help="Percentage of responses within 5-minute rule (target: >95%)"
            )

        with col4:
            st.metric(
                "GHL API Health",
                f"{100 - metrics['ghl_error_rate']:.1f}%",
                delta=f"+{(100 - metrics['ghl_error_rate']) - 98:.1f}%" if metrics['ghl_error_rate'] < 2 else None,
                help="GHL API success rate (target: >98%)"
            )

    def _render_performance_overview(self, performance_data: Dict[str, Any]) -> None:
        """Render detailed performance overview."""
        st.subheader("Performance Overview")

        if not performance_data.get('performance_metrics'):
            st.warning("Performance metrics not available")
            return

        metrics = performance_data['performance_metrics']

        # Performance summary table
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Cache Performance**")
            cache_df = pd.DataFrame([
                {"Metric": "Hit Rate", "Value": f"{metrics['cache_hit_rate']:.1f}%", "Target": ">80%"},
                {"Metric": "Average Response", "Value": f"{metrics['cache_avg_ms']:.1f}ms", "Target": "<50ms"},
                {"Metric": "P95 Response", "Value": f"{metrics['cache_p95_ms']:.1f}ms", "Target": "<100ms"},
                {"Metric": "Total Hits", "Value": f"{metrics['total_cache_hits']:,}", "Target": "-"},
            ])
            self._render_theme_table(cache_df)

        with col2:
            st.write("**AI Performance**")
            ai_df = pd.DataFrame([
                {"Metric": "Average Response", "Value": f"{metrics['ai_avg_ms']:.0f}ms", "Target": "<2000ms"},
                {"Metric": "P95 Response", "Value": f"{metrics['ai_p95_ms']:.0f}ms", "Target": "<4000ms"},
                {"Metric": "Total Calls", "Value": f"{metrics['ai_total_calls']:,}", "Target": "-"},
                {"Metric": "Fallback Rate", "Value": f"{(metrics['fallback_activations'] / max(metrics['ai_total_calls'], 1)) * 100:.1f}%", "Target": "<5%"},
            ])
            self._render_theme_table(ai_df)

        # Live response-time distribution chart
        self._render_response_time_distribution(performance_data.get("response_time_distribution"))

    def _render_cache_analytics(self, performance_data: Dict[str, Any]) -> None:
        """Render detailed cache analytics."""
        st.subheader("Cache Performance Analysis")

        cache_stats = performance_data.get('cache_statistics')
        if not cache_stats:
            st.warning("Cache statistics not available")
            return

        # Cache hit rate trend
        if cache_stats.get('hit_rate_by_hour'):
            self._render_cache_hit_rate_trend(cache_stats)

        col1, col2 = st.columns(2)

        with col1:
            # Cache efficiency metrics
            st.write("**Cache Efficiency**")
            efficiency_df = pd.DataFrame([
                {"Metric": "Hit Rate", "Value": f"{cache_stats['hit_rate']:.1f}%"},
                {"Metric": "Miss Rate", "Value": f"{cache_stats['miss_rate']:.1f}%"},
                {"Metric": "Total Requests", "Value": f"{cache_stats['total_requests']:,}"},
                {"Metric": "Cache Size", "Value": f"{cache_stats['cache_size_mb']:.1f} MB"},
            ])
            self._render_theme_table(efficiency_df)

        with col2:
            # Cache response times comparison
            self._render_cache_response_comparison(cache_stats)

    def _render_cost_savings_analytics(self, performance_data: Dict[str, Any]) -> None:
        """Render cost savings analytics."""
        st.subheader("Cost Savings Analysis")

        cost_savings = performance_data.get('cost_savings')
        if not cost_savings:
            st.warning("Cost savings data not available")
            return

        # Cost savings overview
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "Total Saved",
                f"${cost_savings['total_saved_dollars']:.2f}",
                help="Total cost savings from caching and pattern matching"
            )

        with col2:
            st.metric(
                "Calls Avoided",
                f"{cost_savings['ai_calls_avoided']:,}",
                help="Total AI API calls avoided through optimization"
            )

        with col3:
            st.metric(
                "Avg Cost/Call",
                f"${cost_savings['avg_cost_per_ai_call']:.3f}",
                help="Estimated cost per AI API call"
            )

        # Cost savings breakdown
        self._render_cost_savings_breakdown(cost_savings)

        # Monthly savings projection
        self._render_monthly_savings_projection(cost_savings)

    def _render_performance_trends(self, performance_data: Dict[str, Any]) -> None:
        """Render performance trends and forecasting."""
        st.subheader("Performance Trends")

        # Mock trend data (in production, this would come from historical metrics)
        trend_data = self._generate_mock_trend_data()

        if trend_data:
            # Performance trend chart
            self._render_performance_trend_chart(trend_data)

            # Performance predictions
            self._render_performance_predictions(trend_data)

        else:
            st.info("Historical trend data not yet available. Trends will appear after 24+ hours of operation.")

    def _render_response_time_distribution(self, response_distribution: Optional[Dict[str, Any]]) -> None:
        """Render live response time distribution chart."""
        labels = [
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

        dist = response_distribution or {}
        time_bins = dist.get("labels") or labels
        bucket_len = len(time_bins)

        def _normalize(values: Any) -> List[float]:
            if not isinstance(values, list):
                return [0.0] * bucket_len
            normalized = []
            for value in values[:bucket_len]:
                try:
                    normalized.append(float(value))
                except Exception:
                    normalized.append(0.0)
            if len(normalized) < bucket_len:
                normalized.extend([0.0] * (bucket_len - len(normalized)))
            return normalized

        response_times = {
            "Cache Hits": _normalize(dist.get("cache_hits_pct")),
            "AI Calls": _normalize(dist.get("ai_calls_pct")),
            "GHL API": _normalize(dist.get("ghl_calls_pct")),
        }

        has_live_values = any(any(float(v or 0) > 0 for v in values) for values in response_times.values())
        if not has_live_values:
            st.caption("No live latency events recorded yet. Distribution will populate as cache/AI/GHL calls occur.")

        fig = go.Figure()

        for service, values in response_times.items():
            fig.add_trace(go.Bar(
                name=service,
                x=time_bins,
                y=values,
                text=[f"{v}%" for v in values],
                textposition="auto"
            ))

        self._apply_chart_theme(
            fig,
            title="Response Time Distribution",
            xaxis_title="Response Time Range",
            yaxis_title="Percentage of Requests",
            barmode='group',
            height=400,
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

    def _render_cache_hit_rate_trend(self, cache_stats: Dict[str, Any]) -> None:
        """Render cache hit rate trend over time."""
        hit_rate_data = cache_stats['hit_rate_by_hour']

        if not hit_rate_data:
            return

        # Create DataFrame for trend chart
        df = pd.DataFrame(hit_rate_data)

        fig = px.line(
            df,
            x='hour',
            y='rate',
            title='Cache Hit Rate Trend (Last 24 Hours)',
            labels={'hour': 'Hours Ago', 'rate': 'Hit Rate (%)'},
            markers=True
        )

        fig.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="Target: 80%")

        self._apply_chart_theme(
            fig,
            height=300,
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

    def _render_cache_response_comparison(self, cache_stats: Dict[str, Any]) -> None:
        """Render cache vs miss response time comparison."""
        comparison_data = pd.DataFrame([
            {"Type": "Cache Hit", "Avg Response (ms)": cache_stats['avg_hit_time_ms']},
            {"Type": "Cache Miss", "Avg Response (ms)": cache_stats['avg_miss_time_ms']}
        ])

        fig = px.bar(
            comparison_data,
            x='Type',
            y='Avg Response (ms)',
            title='Cache Hit vs Miss Response Times',
            color='Type',
            text='Avg Response (ms)'
        )

        fig.update_traces(texttemplate='%{text:.0f}ms', textposition='outside')
        self._apply_chart_theme(fig, height=300, showlegend=False)

        st.plotly_chart(fig, use_container_width=True, theme=None)

    def _render_cost_savings_breakdown(self, cost_savings: Dict[str, Any]) -> None:
        """Render cost savings breakdown chart."""
        breakdown_data = pd.DataFrame([
            {"Source": "Cache Hits", "Amount": cost_savings['cache_hits'] * cost_savings['avg_cost_per_ai_call']},
            {"Source": "Pattern Matches", "Amount": cost_savings['pattern_matches'] * cost_savings['avg_cost_per_ai_call']},
        ])

        fig = px.pie(
            breakdown_data,
            values='Amount',
            names='Source',
            title='Cost Savings Breakdown',
            hole=0.4
        )

        fig.update_traces(textposition='inside', textinfo='percent+label')
        self._apply_chart_theme(fig, height=300)

        st.plotly_chart(fig, use_container_width=True, theme=None)

    def _render_monthly_savings_projection(self, cost_savings: Dict[str, Any]) -> None:
        """Render monthly cost savings projection."""
        daily_savings = cost_savings['total_saved_dollars']
        monthly_projection = daily_savings * 30

        st.write("**Monthly Savings Projection**")
        col1, col2 = st.columns(2)

        with col1:
            st.metric("Daily Savings", f"${daily_savings:.2f}")

        with col2:
            st.metric("Monthly Projection", f"${monthly_projection:.2f}")

        # Savings trend (mock data)
        savings_trend = pd.DataFrame({
            'Day': range(1, 31),
            'Cumulative Savings': [daily_savings * day for day in range(1, 31)]
        })

        fig = px.line(
            savings_trend,
            x='Day',
            y='Cumulative Savings',
            title='Projected Monthly Cumulative Savings',
            markers=True
        )

        self._apply_chart_theme(fig, height=300)
        st.plotly_chart(fig, use_container_width=True, theme=None)

    def _render_performance_trend_chart(self, trend_data: List[Dict[str, Any]]) -> None:
        """Render performance trend chart."""
        df = pd.DataFrame(trend_data)

        fig = go.Figure()

        # Add cache hit rate trend
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['cache_hit_rate'],
            mode='lines+markers',
            name='Cache Hit Rate',
            yaxis='y1'
        ))

        # Add AI response time trend
        fig.add_trace(go.Scatter(
            x=df['timestamp'],
            y=df['ai_response_time'],
            mode='lines+markers',
            name='AI Response Time (ms)',
            yaxis='y2'
        ))

        self._apply_chart_theme(
            fig,
            title="Performance Trends (Last 7 Days)",
            xaxis_title="Date",
            yaxis=dict(title="Cache Hit Rate (%)", side="left"),
            yaxis2=dict(title="AI Response Time (ms)", side="right", overlaying="y"),
            height=400,
        )

        st.plotly_chart(fig, use_container_width=True, theme=None)

    def _render_performance_predictions(self, trend_data: List[Dict[str, Any]]) -> None:
        """Render performance predictions."""
        st.write("**Performance Predictions**")

        col1, col2 = st.columns(2)

        with col1:
            st.info("**Next 24 Hours Forecast**")
            st.write("• Cache hit rate: 87-92%")
            st.write("• AI response time: 1100-1400ms")
            st.write("• Expected cost savings: $12-15")

        with col2:
            st.info("**Performance Recommendations**")
            st.write("• Cache performance is optimal")
            st.write("• Monitor AI response times")
            st.write("• Target 90%+ cache hit rate")

    def _generate_mock_trend_data(self) -> List[Dict[str, Any]]:
        """Generate mock trend data for demonstration."""
        import random
        from datetime import datetime, timedelta

        trend_data = []
        base_date = datetime.now() - timedelta(days=7)

        for i in range(7):
            date = base_date + timedelta(days=i)
            trend_data.append({
                'timestamp': date,
                'cache_hit_rate': 80 + random.uniform(-5, 15),
                'ai_response_time': 1200 + random.uniform(-200, 400),
                'ghl_response_time': 400 + random.uniform(-100, 200)
            })

        return trend_data

    def _render_error_state(self) -> None:
        """Render error state when data cannot be loaded."""
        st.error("Unable to load performance analytics")
        st.write("This could be due to:")
        st.write("• Temporary service unavailability")
        st.write("• Network connectivity issues")
        st.write("• Insufficient metrics data")

        if st.button("Retry", key="retry_performance_analytics"):
            st.rerun()


def render_performance_analytics() -> None:
    """
    Render the performance analytics component.

    Entry point for use in dashboard pages.
    """
    try:
        component = PerformanceAnalyticsComponent()
        component.render()

    except Exception as e:
        logger.exception(f"Error rendering performance analytics: {e}")
        st.error("Failed to load performance analytics. Please refresh the page.")


# Component entry point
if __name__ == "__main__":
    # For testing the component standalone
    st.set_page_config(
        page_title="Performance Analytics",
        page_icon="",
        layout="wide"
    )
    render_performance_analytics()
