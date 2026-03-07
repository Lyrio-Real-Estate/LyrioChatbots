"""
Performance Chart Component for Jorge Real Estate AI Dashboard.

Displays time-series chart of qualification metrics.
"""
from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit as st

from bots.shared.dashboard_models import PerformanceMetrics


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


def render_performance_chart(performance: PerformanceMetrics) -> None:
    """
    Render performance analytics chart.

    Args:
        performance: PerformanceMetrics dataclass from DashboardDataService
    """
    st.subheader("Performance Analytics (24h)")

    # Generate hourly time series for last 24 hours
    now = datetime.now()
    hours = [now - timedelta(hours=i) for i in range(24, 0, -1)]
    hour_labels = [h.strftime("%H:%M") for h in hours]

    # Mock time-series data (in production, this comes from PerformanceTracker)
    # For now, use current metrics as baseline
    qual_rates = [performance.qualification_rate + (i - 12) * 0.02 for i in range(24)]
    response_times = [performance.avg_response_time + (i - 12) * 0.5 for i in range(24)]

    theme_mode = _current_theme_mode()
    is_light = theme_mode == "light"

    # Create dual-axis chart
    fig = go.Figure()

    # Qualification rate (left y-axis)
    fig.add_trace(go.Scatter(
        x=hour_labels,
        y=[r * 100 for r in qual_rates],  # Convert to percentage
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

    with col1:
        st.metric(
            "Budget Performance",
            f"{performance.budget_performance * 100:.1f}%",
            delta=f"{(performance.budget_performance - 1) * 100:+.1f}%"
        )

    with col2:
        st.metric(
            "Timeline Performance",
            f"{performance.timeline_performance * 100:.1f}%",
            delta=f"{(performance.timeline_performance - 1) * 100:+.1f}%"
        )

    with col3:
        st.metric(
            "Commission Performance",
            f"{performance.commission_performance * 100:.1f}%",
            delta=f"{(performance.commission_performance - 1) * 100:+.1f}%"
        )
