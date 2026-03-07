"""
Performance Chart Component for Jorge Real Estate AI Dashboard.

Displays time-series chart of qualification metrics.
"""
from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit as st

from bots.shared.dashboard_data_service import DashboardDataService
from bots.shared.dashboard_models import PerformanceMetrics
from command_center.async_runtime import run_async


def _current_theme_mode() -> str:
    """Resolve dashboard theme mode from session/query params."""
    toggle_state = st.session_state.get("sidebar_theme_toggle")
    if isinstance(toggle_state, bool):
        return "light" if toggle_state else "dark"

    theme_value = str(st.session_state.get("ui_theme", "")).strip().lower()
    if theme_value in {"dark", "light"}:
        return theme_value

    query_theme = st.query_params.get("theme")
    if isinstance(query_theme, list):
        query_theme = query_theme[0] if query_theme else None
    query_theme_value = str(query_theme or "").strip().lower()
    if query_theme_value in {"dark", "light"}:
        return query_theme_value

    return "dark"


def _format_target_delta(value: float, summary_has_data: bool) -> str:
    """
    Format KPI delta against a 100% target.

    When all summary values are zero (typical no-data fallback), display a neutral
    0.0% delta instead of a misleading -100.0%.
    """
    if not summary_has_data and float(value or 0.0) <= 0.0:
        return "0.0%"
    return f"{(float(value or 0.0) - 1.0) * 100:+.1f}%"


@st.cache_data(ttl=60)
def _load_hourly_performance_trends(hours: int = 24, location_id: str = "") -> dict:
    """Load real hourly trend data from dashboard service."""
    try:
        service = DashboardDataService()
        trends = run_async(
            service.get_hourly_performance_trends(
                hours=hours,
                location_id=(location_id or "").strip() or None,
            )
        )
        return trends if isinstance(trends, dict) else {}
    except Exception:
        return {}


def render_performance_chart(performance: PerformanceMetrics) -> None:
    """
    Render performance analytics chart.

    Args:
        performance: PerformanceMetrics dataclass from DashboardDataService
    """
    st.subheader("Performance Analytics (24h)")

    # Load true hourly series from DB-backed dashboard service.
    location_id = str(
        st.session_state.get("oauth_location_id")
        or st.session_state.get("location_id")
        or ""
    ).strip()
    hourly_trends = _load_hourly_performance_trends(hours=24, location_id=location_id)
    hour_labels = hourly_trends.get("labels") if isinstance(hourly_trends, dict) else None
    qual_rates = hourly_trends.get("qualification_rate_pct") if isinstance(hourly_trends, dict) else None
    response_times = hourly_trends.get("avg_response_time_min") if isinstance(hourly_trends, dict) else None

    if not isinstance(hour_labels, list) or not hour_labels:
        now = datetime.now()
        fallback_hours = [now - timedelta(hours=i) for i in range(24, 0, -1)]
        hour_labels = [h.strftime("%H:%M") for h in fallback_hours]

    if not isinstance(qual_rates, list) or len(qual_rates) != len(hour_labels):
        qual_rates = [round(performance.qualification_rate * 100.0, 2) for _ in hour_labels]
    else:
        qual_rates = [round(float(value or 0.0), 2) for value in qual_rates]

    if not isinstance(response_times, list) or len(response_times) != len(hour_labels):
        response_times = [round(float(performance.avg_response_time or 0.0), 2) for _ in hour_labels]
    else:
        response_times = [round(float(value or 0.0), 2) for value in response_times]

    theme_mode = _current_theme_mode()
    is_light = theme_mode == "light"

    # Create dual-axis chart
    fig = go.Figure()

    # Qualification rate (left y-axis)
    fig.add_trace(go.Scatter(
        x=hour_labels,
        y=qual_rates,
        name="Qualification Rate",
        mode='lines+markers',
        line=dict(color='#2E7D32', width=2),
        yaxis='y1'
    ))

    # Response time (right y-axis)
    fig.add_trace(go.Scatter(
        x=hour_labels,
        y=response_times,
        name="Avg Response Time",
        mode='lines+markers',
        line=dict(color='#D32F2F', width=2),
        yaxis='y2'
    ))

    # Update layout
    if is_light:
        plot_bgcolor = "#ffffff"
        paper_bgcolor = "#f8fafc"
        font_color = "#334155"
        title_font_color = "#0f172a"
        grid_color = "#dbe3ee"
        axis_line_color = "#cbd5e1"
        legend_bg = "rgba(255, 255, 255, 0.86)"
    else:
        plot_bgcolor = "#020817"
        paper_bgcolor = "#020817"
        font_color = "#cbd5e1"
        title_font_color = "#e2e8f0"
        grid_color = "#334155"
        axis_line_color = "#475569"
        legend_bg = "rgba(15, 23, 42, 0.55)"

    fig.update_layout(
        title="24-Hour Performance Trends",
        xaxis=dict(
            title="Time",
            gridcolor=grid_color,
            linecolor=axis_line_color,
            tickfont=dict(color=font_color),
            title_font=dict(color=font_color),
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="Qualification Rate (%)", font=dict(color='#2E7D32')),
            tickfont=dict(color='#2E7D32'),
            gridcolor=grid_color,
            linecolor=axis_line_color,
            zeroline=False,
        ),
        yaxis2=dict(
            title=dict(text="Response Time (min)", font=dict(color='#D32F2F')),
            tickfont=dict(color='#D32F2F'),
            overlaying='y',
            side='right',
            gridcolor=grid_color,
            linecolor=axis_line_color,
            zeroline=False,
        ),
        plot_bgcolor=plot_bgcolor,
        paper_bgcolor=paper_bgcolor,
        font=dict(color=font_color),
        title_font=dict(color=title_font_color),
        legend=dict(
            bgcolor=legend_bg,
            borderwidth=0,
            font=dict(color=font_color),
            yanchor="top",
            y=0.98,
        ),
        margin=dict(t=70, r=32, b=48, l=32),
        hovermode='x unified',
        height=400
    )

    # Disable Streamlit's injected Plotly theme so our light/dark styles apply reliably.
    st.plotly_chart(fig, use_container_width=True, theme=None)

    # Summary metrics below chart
    col1, col2, col3 = st.columns(3)
    summary_has_data = any(
        float(metric or 0.0) > 0.0
        for metric in (
            performance.budget_performance,
            performance.timeline_performance,
            performance.commission_performance,
        )
    )

    with col1:
        st.metric(
            "Budget Performance",
            f"{performance.budget_performance * 100:.1f}%",
            delta=_format_target_delta(performance.budget_performance, summary_has_data),
        )

    with col2:
        st.metric(
            "Timeline Performance",
            f"{performance.timeline_performance * 100:.1f}%",
            delta=_format_target_delta(performance.timeline_performance, summary_has_data),
        )

    with col3:
        st.metric(
            "Commission Performance",
            f"{performance.commission_performance * 100:.1f}%",
            delta=_format_target_delta(performance.commission_performance, summary_has_data),
        )
