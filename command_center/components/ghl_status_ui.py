"""
GHL Integration Status UI - Streamlit Renderer

Mobile-responsive Streamlit interface for GHL integration monitoring:
- Real-time connection status
- Automation pipeline health
- Webhook monitoring
- Performance metrics
- One-click automation controls
- Alert management

Author: Claude Code Assistant
Created: 2026-01-23
"""
import os
from datetime import datetime
from typing import Optional, Tuple

import httpx
import streamlit as st

from bots.shared.config import settings
from command_center.async_runtime import run_async
from .ghl_integration_status import (
    AutomationStatus,
    ConnectionStatus,
    GHLIntegrationData,
    create_ghl_integration_status,
)


class GHLStatusUI:
    """Streamlit UI renderer for GHL integration status"""

    def __init__(self):
        self.status_component = None
        lead_port = os.getenv("LEAD_BOT_PORT", "8001")
        self._lead_bot_url = os.getenv("LEAD_BOT_URL", f"http://localhost:{lead_port}")
        self._automation_bot_map = {
            "Lead Qualification Bot": "lead",
            "CMA Generation Pipeline": "seller",
            "Follow-up Sequence": "buyer",
            "Appointment Booking": "seller",
        }

    async def _get_status_component(self):
        """Get or create status component"""
        if self.status_component is None:
            self.status_component = await create_ghl_integration_status()
        return self.status_component

    def _bot_key_for_automation(self, automation_name: str) -> Optional[str]:
        return self._automation_bot_map.get(automation_name)

    def _control_headers(self) -> dict:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        auth_token = st.session_state.get("auth_token")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        if settings.admin_api_key:
            headers["X-Admin-Key"] = settings.admin_api_key
        return headers

    def _set_bot_enabled(self, bot_key: str, enabled: bool) -> Tuple[bool, Optional[str]]:
        endpoint = f"{self._lead_bot_url}/admin/automation-state/{bot_key}"
        try:
            headers = self._control_headers()
            with httpx.Client(timeout=6.0) as client:
                response = client.put(
                    endpoint,
                    json={"enabled": enabled},
                    headers=headers,
                )
            if response.status_code < 400:
                return True, None
            return False, f"Control API error ({response.status_code}): {response.text}"
        except Exception as exc:
            return False, f"Failed to reach Lead Bot control API: {exc}"

    def _refresh_after_control_change(self) -> None:
        st.cache_data.clear()
        st.rerun()

    def render_ghl_status_section(self, location_id: str) -> None:
        """
        Render the complete GHL integration status section

        Args:
            location_id: GHL location ID
        """
        # Section header with refresh control
        col1, col2 = st.columns([4, 1])

        with col1:
            st.markdown("""
            <h2 style='margin-bottom: 0;'>GHL Integration Command Center</h2>
            <p style='color: #6b7280; margin-top: 0;'>Real-time monitoring and automation control</p>
            """, unsafe_allow_html=True)

        with col2:
            if st.button("", help="Refresh status", key="refresh_ghl_status"):
                st.cache_data.clear()
                st.rerun()

        # Load status data
        status_data = self._load_status_data(location_id, st.session_state.get("auth_token"))

        if not status_data:
            self._render_loading_state()
            return

        # Render alert notifications first
        self._render_alerts(status_data)

        # Render main status dashboard
        self._render_status_overview(status_data)

        # Render detailed monitoring sections
        self._render_automation_controls(status_data)
        self._render_performance_metrics(status_data)

    @st.cache_data(ttl=30)  # Cache for 30 seconds for real-time feel
    def _load_status_data(_self, location_id: str, auth_token: Optional[str] = None) -> GHLIntegrationData:
        """Load GHL status data with caching"""
        try:
            ui_instance = GHLStatusUI()
            status_component = run_async(ui_instance._get_status_component())
            return run_async(status_component.get_integration_status(location_id, auth_token=auth_token))

        except Exception as e:
            st.error(f"Error loading GHL status: {e}")
            return None

    def _render_alerts(self, status_data: GHLIntegrationData) -> None:
        """Render alert notifications"""
        if not status_data.alerts:
            return

        st.markdown("### Active Alerts")

        # Group alerts by severity
        critical_alerts = [alert for alert in status_data.alerts if "" in alert or "" in alert]
        warning_alerts = [alert for alert in status_data.alerts if "" in alert]
        info_alerts = [alert for alert in status_data.alerts if "" in alert]

        # Critical alerts
        if critical_alerts:
            for alert in critical_alerts:
                st.error(alert)

        # Warning alerts
        if warning_alerts:
            for alert in warning_alerts:
                st.warning(alert)

        # Info alerts
        if info_alerts:
            for alert in info_alerts:
                st.info(alert)

        st.markdown("---")

    def _render_status_overview(self, status_data: GHLIntegrationData) -> None:
        """Render main status overview cards"""

        # Status overview cards
        col1, col2, col3, col4 = st.columns(4)

        # Connection Status
        with col1:
            status_color = {
                ConnectionStatus.CONNECTED: "#10B981",
                ConnectionStatus.DEGRADED: "#F59E0B",
                ConnectionStatus.RATE_LIMITED: "#F59E0B",
                ConnectionStatus.DISCONNECTED: "#EF4444"
            }.get(status_data.connection.status, "#6B7280")

            status_icon = {
                ConnectionStatus.CONNECTED: "",
                ConnectionStatus.DEGRADED: "Warm",
                ConnectionStatus.RATE_LIMITED: "Warm",
                ConnectionStatus.DISCONNECTED: ""
            }.get(status_data.connection.status, "")

            st.markdown(f"""
            <div style="background: white; padding: 20px; border-radius: 10px;
                       box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 4px solid {status_color};">
                <div style="font-size: 1rem; color: #374151; font-weight: 600;">Connection Status</div>
                <div style="font-size: 1.5rem; margin: 8px 0; color: {status_color};">
                    {status_icon} {status_data.connection.status.value.title()}
                </div>
                <div style="font-size: 0.875rem; color: #6b7280;">
                    Response: {status_data.connection.response_time_ms:.1f}ms<br>
                    Success: {status_data.connection.success_rate:.1f}%
                </div>
            </div>
            """, unsafe_allow_html=True)

        # API Rate Limits
        with col2:
            if status_data.connection.rate_limit_known:
                if status_data.connection.rate_limit_remaining > 2000:
                    rate_color = "#10B981"
                elif status_data.connection.rate_limit_remaining > 500:
                    rate_color = "#F59E0B"
                else:
                    rate_color = "#EF4444"
                rate_display = f"{status_data.connection.rate_limit_remaining:,}"
                reset_display = status_data.connection.rate_limit_reset.strftime('%H:%M')
                remaining_caption = "Remaining calls"
            else:
                rate_color = "#6B7280"
                rate_display = "N/A"
                reset_display = "Unknown"
                remaining_caption = "Header not exposed"

            st.markdown(f"""
            <div style="background: white; padding: 20px; border-radius: 10px;
                       box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 4px solid {rate_color};">
                <div style="font-size: 1rem; color: #374151; font-weight: 600;">API Rate Limits</div>
                <div style="font-size: 1.5rem; margin: 8px 0; color: {rate_color};">
                    {rate_display}
                </div>
                <div style="font-size: 0.875rem; color: #6b7280;">
                    {remaining_caption}<br>
                    Resets: {reset_display}
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Active Automations
        with col3:
            active_automations = sum(1 for a in status_data.automations if a.status == AutomationStatus.ACTIVE)
            total_automations = len(status_data.automations)

            automation_color = "#10B981" if active_automations == total_automations else "#F59E0B" if active_automations > 0 else "#EF4444"

            st.markdown(f"""
            <div style="background: white; padding: 20px; border-radius: 10px;
                       box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 4px solid {automation_color};">
                <div style="font-size: 1rem; color: #374151; font-weight: 600;">Active Automations</div>
                <div style="font-size: 1.5rem; margin: 8px 0; color: {automation_color};">
                    {active_automations}/{total_automations}
                </div>
                <div style="font-size: 0.875rem; color: #6b7280;">
                    Running pipelines<br>
                    {total_automations - active_automations} inactive
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Today's Processing
        with col4:
            total_processed = status_data.daily_stats.get('leads_processed', 0)
            commission_potential = status_data.daily_stats.get('commission_potential', 0)

            st.markdown(f"""
            <div style="background: white; padding: 20px; border-radius: 10px;
                       box-shadow: 0 2px 8px rgba(0,0,0,0.1); border-left: 4px solid #8B5CF6;">
                <div style="font-size: 1rem; color: #374151; font-weight: 600;">Today's Processing</div>
                <div style="font-size: 1.5rem; margin: 8px 0; color: #8B5CF6;">
                    {total_processed:,} leads
                </div>
                <div style="font-size: 0.875rem; color: #6b7280;">
                    ${commission_potential:,} potential<br>
                    Commission value
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Render charts
        col1, col2 = st.columns(2)

        with col1:
            # Status overview chart
            status_component = run_async(self._get_status_component())
            overview_chart = status_component.create_status_overview_chart(status_data)
            st.plotly_chart(overview_chart, use_container_width=True)

        with col2:
            # Webhook health chart
            status_component = run_async(self._get_status_component())
            webhook_chart = status_component.create_webhook_health_chart(status_data)
            st.plotly_chart(webhook_chart, use_container_width=True)

    def _render_automation_controls(self, status_data: GHLIntegrationData) -> None:
        """Render automation control panel"""

        st.markdown("### Automation Control Panel")

        # Quick action buttons
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("Start All", help="Start all paused automations", use_container_width=True):
                self._start_all_automations(status_data)

        with col2:
            if st.button("Pause All", help="Pause all running automations", use_container_width=True):
                self._pause_all_automations(status_data)

        with col3:
            if st.button("Restart Failed", help="Restart failed automations", use_container_width=True):
                self._restart_failed_automations(status_data)

        with col4:
            if st.button("Performance Report", help="Generate automation report", use_container_width=True):
                self._show_automation_report(status_data)

        st.markdown("<br>", unsafe_allow_html=True)

        # Individual automation controls
        for automation in status_data.automations:
            with st.expander(f"{automation.name} - {automation.status.value.title()}",
                           expanded=(automation.status != AutomationStatus.ACTIVE)):

                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.markdown(f"""
                    **Performance Today:**
                    - Leads Processed: {automation.leads_processed:,}
                    - Success Rate: {automation.success_rate:.1f}%
                    - Avg Execution: {automation.avg_execution_time:.1f}s
                    - Errors: {automation.errors_today}
                    - Last Run: {automation.last_run.strftime('%H:%M:%S')}
                    """)

                with col2:
                    status_color = {
                        AutomationStatus.ACTIVE: "#10B981",
                        AutomationStatus.PAUSED: "#F59E0B",
                        AutomationStatus.ERROR: "#EF4444",
                        AutomationStatus.DISABLED: "#6B7280"
                    }.get(automation.status, "#6B7280")

                    st.markdown(f"""
                    <div style="background: {status_color}; color: white; padding: 10px;
                               border-radius: 6px; text-align: center; font-weight: 600;">
                        {automation.status.value.title()}
                    </div>
                    """, unsafe_allow_html=True)

                with col3:
                    if automation.status == AutomationStatus.PAUSED:
                        if st.button("Start", key=f"start_{automation.name}"):
                            self._start_automation(automation.name)
                    elif automation.status == AutomationStatus.ACTIVE:
                        if st.button("Pause", key=f"pause_{automation.name}"):
                            self._pause_automation(automation.name)
                    elif automation.status == AutomationStatus.ERROR:
                        if st.button("Restart", key=f"restart_{automation.name}"):
                            self._restart_automation(automation.name)

        # Automation performance chart
        st.markdown("### Automation Performance")
        status_component = run_async(self._get_status_component())
        performance_chart = status_component.create_automation_performance_chart(status_data)
        st.plotly_chart(performance_chart, use_container_width=True)

    def _render_performance_metrics(self, status_data: GHLIntegrationData) -> None:
        """Render detailed performance metrics"""

        st.markdown("### Performance Metrics")

        # Webhook metrics
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Webhook Performance")

            webhook_success_rate = (status_data.webhooks.successful_processed /
                                  max(status_data.webhooks.total_received, 1)) * 100

            metrics_data = {
                "Total Received": f"{status_data.webhooks.total_received:,}",
                "Successfully Processed": f"{status_data.webhooks.successful_processed:,}",
                "Failed": f"{status_data.webhooks.failed_processed:,}",
                "Success Rate": f"{webhook_success_rate:.1f}%",
                "Avg Processing Time": f"{status_data.webhooks.avg_processing_time:.2f}s",
                "Current Backlog": f"{status_data.webhooks.backlog_count:,}",
                "Last Received": status_data.webhooks.last_received.strftime('%H:%M:%S')
            }

            for metric, value in metrics_data.items():
                st.metric(metric, value)

        with col2:
            st.markdown("#### Daily Performance Summary")

            if status_data.daily_stats:
                daily_metrics = {
                    "Leads Processed": f"{status_data.daily_stats.get('leads_processed', 0):,}",
                    "Automations Triggered": f"{status_data.daily_stats.get('automations_triggered', 0):,}",
                    "CMAs Generated": f"{status_data.daily_stats.get('cmas_generated', 0):,}",
                    "Appointments Booked": f"{status_data.daily_stats.get('appointments_booked', 0):,}",
                    "Commission Potential": f"${status_data.daily_stats.get('commission_potential', 0):,}",
                    "Avg Response Time": f"{status_data.daily_stats.get('response_time_avg', 0):.1f}ms",
                    "Uptime": f"{status_data.daily_stats.get('uptime_percentage', 0):.1f}%"
                }

                for metric, value in daily_metrics.items():
                    st.metric(metric, value)

    def _render_loading_state(self) -> None:
        """Render loading state"""
        st.markdown("### GHL Integration Command Center")
        st.markdown("*Loading integration status...*")

        with st.spinner("Connecting to GHL..."):
            st.empty()

    # Automation control methods
    def _start_all_automations(self, status_data: GHLIntegrationData) -> None:
        """Start all paused automations"""
        bot_keys = {
            self._bot_key_for_automation(automation.name)
            for automation in status_data.automations
        }
        bot_keys = {bot for bot in bot_keys if bot}
        if not bot_keys:
            st.info("No controllable automations found.")
            return

        failed = []
        for bot_key in sorted(bot_keys):
            ok, err = self._set_bot_enabled(bot_key, True)
            if not ok:
                failed.append(bot_key)
                if err:
                    st.error(err)

        if failed:
            st.error(f"Failed to start automations for: {', '.join(failed)}")
            return

        st.success("All automations set to active")
        self._refresh_after_control_change()

    def _pause_all_automations(self, status_data: GHLIntegrationData) -> None:
        """Pause all running automations"""
        bot_keys = {
            self._bot_key_for_automation(automation.name)
            for automation in status_data.automations
        }
        bot_keys = {bot for bot in bot_keys if bot}
        if not bot_keys:
            st.info("No controllable automations found.")
            return

        failed = []
        for bot_key in sorted(bot_keys):
            ok, err = self._set_bot_enabled(bot_key, False)
            if not ok:
                failed.append(bot_key)
                if err:
                    st.error(err)

        if failed:
            st.error(f"Failed to pause automations for: {', '.join(failed)}")
            return

        st.warning("All automations paused")
        self._refresh_after_control_change()

    def _restart_failed_automations(self, status_data: GHLIntegrationData) -> None:
        """Restart failed automations"""
        failed_bots = set()
        for automation in status_data.automations:
            if automation.status == AutomationStatus.ERROR:
                bot_key = self._bot_key_for_automation(automation.name)
                if bot_key:
                    failed_bots.add(bot_key)
        if not failed_bots:
            st.info("No failed automations to restart.")
            return

        restart_failures = []
        for bot_key in sorted(failed_bots):
            ok, err = self._set_bot_enabled(bot_key, True)
            if not ok:
                restart_failures.append(bot_key)
                if err:
                    st.error(err)

        if restart_failures:
            st.error(f"Failed to restart automations for: {', '.join(restart_failures)}")
            return

        st.success(f"Restarted failed automations: {len(failed_bots)}")
        self._refresh_after_control_change()

    def _start_automation(self, automation_name: str) -> None:
        """Start specific automation"""
        bot_key = self._bot_key_for_automation(automation_name)
        if not bot_key:
            st.warning(f"No control mapping for {automation_name}")
            return
        ok, err = self._set_bot_enabled(bot_key, True)
        if not ok:
            if err:
                st.error(err)
            return
        st.success(f"Started {automation_name}")
        self._refresh_after_control_change()

    def _pause_automation(self, automation_name: str) -> None:
        """Pause specific automation"""
        bot_key = self._bot_key_for_automation(automation_name)
        if not bot_key:
            st.warning(f"No control mapping for {automation_name}")
            return
        ok, err = self._set_bot_enabled(bot_key, False)
        if not ok:
            if err:
                st.error(err)
            return
        st.warning(f"Paused {automation_name}")
        self._refresh_after_control_change()

    def _restart_automation(self, automation_name: str) -> None:
        """Restart specific automation"""
        bot_key = self._bot_key_for_automation(automation_name)
        if not bot_key:
            st.warning(f"No control mapping for {automation_name}")
            return
        ok, err = self._set_bot_enabled(bot_key, True)
        if not ok:
            if err:
                st.error(err)
            return
        st.success(f"Restarted {automation_name}")
        self._refresh_after_control_change()

    def _show_automation_report(self, status_data: GHLIntegrationData) -> None:
        """Show automation performance report"""
        st.success("Generating automation performance report...")

        with st.expander("Automation Performance Report", expanded=True):
            st.markdown(f"""
            **Report Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

            **Overall Performance:**
            - Total Automations: {len(status_data.automations)}
            - Active: {sum(1 for a in status_data.automations if a.status == AutomationStatus.ACTIVE)}
            - Average Success Rate: {sum(a.success_rate for a in status_data.automations) / max(len(status_data.automations), 1):.1f}%

            **Top Performers:**
            """)

            # Sort by success rate
            sorted_automations = sorted(status_data.automations, key=lambda x: x.success_rate, reverse=True)
            for i, automation in enumerate(sorted_automations[:3], 1):
                st.markdown(f"{i}. **{automation.name}**: {automation.success_rate:.1f}% success rate")

            st.markdown(f"""
            **Commission Impact:**
            - Today's Potential: ${status_data.daily_stats.get('commission_potential', 0):,}
            - Automations Contribution: 89% of lead processing

            **Recommendations:**
            - Monitor failed automation restart frequency
            - Optimize high-error automations
            - Consider scaling successful patterns
            """)


def render_ghl_integration_status(location_id: str) -> None:
    """
    Main function to render GHL integration status section

    Args:
        location_id: GHL location ID
    """
    ui_renderer = GHLStatusUI()
    ui_renderer.render_ghl_status_section(location_id)
