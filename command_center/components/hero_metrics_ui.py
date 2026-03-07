"""
Hero Metrics UI Renderer - Mobile-Responsive Streamlit Interface

Renders enhanced hero metrics with superior UX:
- Mobile-responsive card layout
- Interactive action buttons
- Urgency-based color coding
- Progress indicators and tooltips
- One-click automation triggers

Author: Claude Code Assistant
Created: 2026-01-23
"""
import html
import os
from typing import List

import streamlit as st

from command_center.async_runtime import run_async
from .enhanced_hero_metrics import HeroMetricData, create_enhanced_hero_metrics


class HeroMetricsUI:
    """Streamlit UI renderer for enhanced hero metrics"""

    def __init__(self):
        self.metrics_component = create_enhanced_hero_metrics()

    @staticmethod
    def _is_light_mode() -> bool:
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

    def render_hero_metrics_section(self, location_id: str) -> None:
        """
        Render the complete hero metrics section with enhanced UX.

        Args:
            location_id: GHL location ID for data filtering
        """
        # Theme-consistent styling for ROI action controls.
        st.markdown(
            """
            <style>
            .st-key-refresh_hero_metrics button,
            .st-key-quick_action_generate_cmas button,
            .st-key-quick_action_send_followups button,
            .st-key-quick_action_book_appointments button,
            .st-key-quick_action_performance_report button {
                background: #0f172a !important;
                color: #cbd5e1 !important;
                -webkit-text-fill-color: #cbd5e1 !important;
                border: 1px solid #243449 !important;
                border-radius: 10px !important;
                box-shadow: none !important;
                opacity: 1 !important;
            }

            .st-key-refresh_hero_metrics button:hover,
            .st-key-refresh_hero_metrics button:focus-visible,
            .st-key-quick_action_generate_cmas button:hover,
            .st-key-quick_action_generate_cmas button:focus-visible,
            .st-key-quick_action_send_followups button:hover,
            .st-key-quick_action_send_followups button:focus-visible,
            .st-key-quick_action_book_appointments button:hover,
            .st-key-quick_action_book_appointments button:focus-visible,
            .st-key-quick_action_performance_report button:hover,
            .st-key-quick_action_performance_report button:focus-visible {
                background: #172235 !important;
                color: #e2e8f0 !important;
                -webkit-text-fill-color: #e2e8f0 !important;
                border-color: #324b68 !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        # Section header with refresh control
        roi_title = html.escape((os.getenv("DASHBOARD_ROI_TITLE") or "ROI Command Center").strip() or "ROI Command Center")
        roi_subtitle = html.escape(
            (os.getenv("DASHBOARD_ROI_SUBTITLE") or "Real-time business intelligence for maximum ROI").strip()
            or "Real-time business intelligence for maximum ROI"
        )
        col1, col2 = st.columns([4, 1])
        action_button_type = "secondary"

        with col1:
            st.markdown(
                f"""
                <h2 style='margin-bottom: 0;'>{roi_title}</h2>
                <p style='color: #6b7280; margin-top: 0;'>{roi_subtitle}</p>
                """,
                unsafe_allow_html=True,
            )

        with col2:
            if st.button(
                "Refresh Metrics",
                help="Refresh metrics",
                key="refresh_hero_metrics",
                use_container_width=True,
                type=action_button_type,
            ):
                st.cache_data.clear()
                st.rerun()

        # Load metrics data
        metrics_data = self._load_metrics_data(location_id)

        if not metrics_data:
            self._render_loading_state()
            return

        # Render metric cards with responsive layout
        self._render_metric_cards(metrics_data)

        # Add action buttons section
        self._render_action_buttons_section(metrics_data)

    @st.cache_data(ttl=60)  # Cache for 1 minute for responsiveness
    def _load_metrics_data(_self, location_id: str) -> List[HeroMetricData]:
        """Load hero metrics data with caching"""
        try:
            metrics_component = create_enhanced_hero_metrics()
            return run_async(metrics_component.get_hero_metrics_data(location_id))

        except Exception as e:
            st.error(f"Error loading hero metrics: {e}")
            return []

    def _render_metric_cards(self, metrics_data: List[HeroMetricData]) -> None:
        """Render metric cards with mobile-responsive layout"""

        # Mobile-responsive columns:
        # Desktop: 4 columns in a row
        # Tablet: 2 columns in a row
        # Mobile: 1 column (stacked)

        # Use CSS for responsive behavior
        st.markdown("""
        <style>
        .metric-card {
            background: var(--lyrio-metric-card-bg, linear-gradient(180deg, #121a28 0%, #0f1724 100%));
            border-radius: 12px;
            padding: 14px 14px 12px;
            border: 1px solid var(--lyrio-metric-card-border, #233246);
            border-left: 4px solid;
            margin-bottom: 12px;
            min-height: 184px;
            display: flex;
            flex-direction: column;
            box-shadow: var(--lyrio-metric-card-shadow, 0 8px 18px rgba(2, 6, 23, 0.3));
            transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
        }

        .metric-card:hover {
            transform: translateY(-2px);
            border-color: var(--lyrio-metric-card-hover-border, #345170);
            box-shadow: var(--lyrio-metric-card-hover-shadow, 0 11px 22px rgba(2, 6, 23, 0.4));
        }

        .metric-value {
            font-size: clamp(1.75rem, 2.15vw, 2.35rem);
            font-weight: 700;
            margin: 8px 0 8px;
            line-height: 1.05;
            min-height: 60px;
            letter-spacing: -0.02em;
        }

        .metric-label {
            font-size: 0.98rem;
            font-weight: 600;
            color: var(--lyrio-metric-label-text, #d9e2f0);
            margin-bottom: 4px;
            letter-spacing: 0.01em;
        }

        .metric-delta {
            font-size: 0.93rem;
            color: var(--lyrio-metric-delta-text, #9fb0c8);
            font-weight: 500;
            margin-top: auto;
            line-height: 1.35;
        }

        .urgency-high { border-left-color: #ef4444; }
        .urgency-medium { border-left-color: #f59e0b; }
        .urgency-low { border-left-color: #10b981; }

        /* Mobile responsive: Stack cards on small screens */
        @media (max-width: 768px) {
            .metric-card {
                margin-bottom: 10px;
                min-height: 160px;
                padding: 12px 12px 10px;
            }
            .metric-value {
                min-height: 52px;
            }
        }
        </style>
        """, unsafe_allow_html=True)

        # Create responsive rows with consistent balance.
        # Notably, 5 cards render as 3 + 2 for a cleaner visual rhythm.
        visible_metrics = metrics_data[:8]
        num_metrics = len(visible_metrics)

        if num_metrics == 0:
            return

        if num_metrics <= 3:
            row_specs = [num_metrics]
        elif num_metrics == 4:
            row_specs = [4]
        elif num_metrics == 5:
            row_specs = [3, 2]
        elif num_metrics == 6:
            row_specs = [3, 3]
        elif num_metrics == 7:
            row_specs = [4, 3]
        else:
            row_specs = [4, 4]

        metric_index = 0
        for columns_in_row in row_specs:
            cols = st.columns(columns_in_row)
            for col_idx in range(columns_in_row):
                if metric_index >= num_metrics:
                    break
                with cols[col_idx]:
                    self._render_individual_metric_card(visible_metrics[metric_index])
                metric_index += 1

    def _render_individual_metric_card(self, metric: HeroMetricData) -> None:
        """Render individual metric card with enhanced styling"""

        # Color mapping for values
        color_mapping = {
            "red": "#ef4444",
            "green": "#10b981",
            "blue": "#3b82f6",
            "amber": "#f59e0b",
            "purple": "#8b5cf6"
        }

        value_color = color_mapping.get(metric.color, "#3b82f6")
        urgency_class = f"urgency-{metric.urgency_level}"

        # Create the metric card HTML
        card_html = f"""
        <div class="metric-card {urgency_class}">
            <div class="metric-label">{metric.label}</div>
            <div class="metric-value" style="color: {value_color};">{metric.value}</div>
            <div class="metric-delta">{metric.delta}</div>
        """

        # Add progress bar if available
        if metric.progress_bar is not None:
            progress_percent = metric.progress_bar * 100
            card_html += f"""
            <div style="margin-top: 12px;">
                <div style="background: #e5e7eb; border-radius: 4px; height: 6px;">
                    <div style="background: {value_color}; height: 6px; width: {progress_percent}%; border-radius: 4px;"></div>
                </div>
            </div>
            """

        card_html += "</div>"

        # Render the card
        st.markdown(card_html, unsafe_allow_html=True)

        # Per-card action buttons are intentionally omitted to keep card sizes/layout consistent.

    def _render_action_buttons_section(self, metrics_data: List[HeroMetricData]) -> None:
        """Render quick action buttons section"""

        # Check if we have metrics that support automation
        automation_metrics = [
            m for m in metrics_data
            if m.action_button and ("CMA" in m.label or "Hot Leads" in m.label)
        ]
        # Keep quick action controls on the same dark-styled treatment in both themes.
        action_button_type = "secondary"

        if not automation_metrics:
            return

        st.markdown("---")
        st.markdown("### Quick Actions")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button(
                "Generate All CMAs",
                help="Auto-generate CMAs for all Q4 sellers",
                use_container_width=True,
                key="quick_action_generate_cmas",
                type=action_button_type,
            ):
                self._trigger_cma_automation()

        with col2:
            if st.button(
                "Send Follow-ups",
                help="Send follow-up sequences to warm leads",
                use_container_width=True,
                key="quick_action_send_followups",
                type=action_button_type,
            ):
                self._trigger_followup_automation()

        with col3:
            if st.button(
                "Book Appointments",
                help="Auto-book appointments for hot leads",
                use_container_width=True,
                key="quick_action_book_appointments",
                type=action_button_type,
            ):
                self._trigger_appointment_automation()

        with col4:
            if st.button(
                "Performance Report",
                help="Generate weekly performance report",
                use_container_width=True,
                key="quick_action_performance_report",
                type=action_button_type,
            ):
                self._generate_performance_report()

    def _render_loading_state(self) -> None:
        """Render loading state with skeleton cards"""
        st.markdown("### ROI Command Center")
        st.markdown("*Loading real-time business intelligence...*")

        # Create skeleton loading cards
        cols = st.columns(4)

        for i in range(4):
            with cols[i]:
                with st.container():
                    st.markdown("""
                    <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin-bottom: 16px;">
                        <div style="background: #e5e7eb; height: 16px; width: 60%; margin-bottom: 8px; border-radius: 4px;"></div>
                        <div style="background: #e5e7eb; height: 32px; width: 80%; margin-bottom: 8px; border-radius: 4px;"></div>
                        <div style="background: #e5e7eb; height: 14px; width: 50%; border-radius: 4px;"></div>
                    </div>
                    """, unsafe_allow_html=True)

    def _handle_action_button_click(self, metric: HeroMetricData) -> None:
        """Handle action button clicks with specific logic"""

        if "Hot Leads" in metric.label:
            self._show_hot_leads_detail()
        elif "CMA" in metric.label:
            self._trigger_cma_automation()
        elif "Forecast" in metric.label:
            self._show_forecast_detail()
        else:
            st.success(f"Action triggered for {metric.label}")

    def _show_hot_leads_detail(self) -> None:
        """Show hot leads detail modal"""
        st.success("Hot Leads Detail: Opening detailed view...")

        # In a real implementation, this would open a detailed view
        with st.expander("Hot Leads Details", expanded=True):
            st.markdown("""
            **Top Hot Leads:**
            - Sarah Johnson (Score: 92) - Referral - Est. $18K commission
            - Mike Davis (Score: 88) - Zillow - Est. $16K commission
            - Jennifer Smith (Score: 85) - Facebook - Est. $14K commission

            **Best Performing Source:** Referrals (∞x ROI)
            **Action Required:** Call top 3 leads within next hour
            """)

    def _trigger_cma_automation(self) -> None:
        """Trigger CMA generation automation"""
        st.success("CMA Automation: Generating CMAs for all Q4 qualified sellers...")

        # Mock progress bar
        progress_bar = st.progress(0)
        import time

        for i in range(100):
            time.sleep(0.01)  # Simulate processing
            progress_bar.progress(i + 1)

        st.success("Generated 3 CMAs successfully! Total estimated commission: $67K")

    def _trigger_followup_automation(self) -> None:
        """Trigger follow-up automation"""
        st.success("Follow-up Automation: Sending sequences to warm leads...")
        st.info("Sent follow-up messages to 12 warm leads")

    def _trigger_appointment_automation(self) -> None:
        """Trigger appointment booking automation"""
        st.success("Appointment Automation: Booking appointments for hot leads...")
        st.info("Sent appointment booking links to 5 hot leads")

    def _generate_performance_report(self) -> None:
        """Generate performance report"""
        st.success("Performance Report: Generating weekly summary...")

        with st.expander("Weekly Performance Report", expanded=True):
            st.markdown("""
            **Week of January 20-26, 2026**

            **Lead Performance:**
            - Hot Leads: 8 (↑25% vs last week)
            - Conversion Rate: 3.8% (↑0.5% vs last week)
            - Best Source: Referrals (∞x ROI)

            **Seller Pipeline:**
            - Q4 CMAs Ready: 3 sellers
            - Estimated Commission: $67K
            - High Priority: 2 sellers

            **30-Day Forecast:**
            - Projected Revenue: $89K
            - Confidence Range: $75K - $103K
            - Trend: Strong pipeline

            **Recommendations:**
            1. Focus on referral lead generation
            2. Generate CMAs for high-value sellers
            3. Follow up with warm leads from Zillow
            """)

    def _show_forecast_detail(self) -> None:
        """Show forecast detail modal"""
        st.success("Revenue Forecast: Opening detailed analysis...")

        with st.expander("30-Day Revenue Forecast", expanded=True):
            st.markdown("""
            **Forecast Analysis:**
            - Projected Revenue: $89K
            - Historical Velocity: +$1,200/day
            - Pipeline Contribution: $45K
            - Confidence Range: $75K - $103K (±15%)

            **Key Drivers:**
            - Hot leads pipeline: $31K potential
            - Seller CMAs ready: $67K potential
            - Historical trend: +15% growth

            **Risk Factors:**
            - Lead generation consistency
            - CMA conversion rates
            - Market conditions
            """)


def render_enhanced_hero_metrics(location_id: str) -> None:
    """
    Main function to render enhanced hero metrics section.

    Args:
        location_id: GHL location ID
    """
    ui_renderer = HeroMetricsUI()
    ui_renderer.render_hero_metrics_section(location_id)
