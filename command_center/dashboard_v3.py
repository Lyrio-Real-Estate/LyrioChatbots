"""
Dashboard V3.
Consolidated command center with navigation and auth gating.
"""
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import streamlit as st

# Ensure repo root is importable when launched from different working dirs.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bots.shared.dashboard_data_service import DashboardDataService
from bots.shared.config import settings
from command_center.async_runtime import run_async
from command_center.components.active_conversations import ActiveConversationsComponent
from command_center.components.active_conversations_table import render_active_conversations
from command_center.components.activity_feed import ActivityFeed
from command_center.components.auth_component import (
    check_authentication,
    clear_session,
    render_login_form,
    render_password_change_form,
    require_permission,
)
from command_center.components.commission_tracking import CommissionTrackingComponent
from command_center.components.export_manager import ExportManager
from command_center.components.field_access_dashboard import create_field_access_dashboard, get_sample_sync_queue
from command_center.components.ghl_integration_status import create_ghl_integration_status
from command_center.components.ghl_status_ui import GHLStatusUI
from command_center.components.global_filters import GlobalFilters
from command_center.components.hero_metrics_card import render_hero_metrics
from command_center.components.hero_metrics_ui import HeroMetricsUI
from command_center.components.lead_intelligence_dashboard import LeadIntelligenceDashboard
from command_center.components.mobile_dashboard_integration import (
    get_jorge_ai_branding_css,
    get_sample_real_estate_data,
    render_mobile_dashboard_tab,
)
from command_center.components.mobile_metrics_cards import get_sample_metrics, render_mobile_metrics_cards
from command_center.components.mobile_navigation import create_mobile_navigation_component, demo_mobile_navigation
from command_center.components.mobile_responsive_layout import (
    apply_responsive_layout_system,
    create_responsive_card,
    create_responsive_container,
    create_responsive_grid,
)
from command_center.components.offline_indicator import (
    ConnectionStatus,
    NetworkMetrics,
    SyncItem,
    SyncItemStatus,
    SyncPriority,
    create_offline_indicator,
)
from command_center.components.performance_analytics import PerformanceAnalyticsComponent
from command_center.components.performance_chart import render_performance_chart
from command_center.components.touch_optimized_charts import ChartConfig, ChartType, render_touch_optimized_chart


def _dashboard_title() -> str:
    default_title = "Lyrio AI Dashboard"
    title = (os.getenv("DASHBOARD_TITLE") or os.getenv("APP_NAME") or default_title).strip()
    if not title:
        return default_title
    if title.lower() == "ai dashboard":
        return default_title
    return title


def _dashboard_subtitle() -> str:
    subtitle = (os.getenv("DASHBOARD_SUBTITLE") or "Real-time qualification, analytics, and automation").strip()
    return subtitle or "Real-time qualification, analytics, and automation"


# Page config
st.set_page_config(
    page_title=_dashboard_title(),
    layout="wide",
    initial_sidebar_state="expanded",
)

def _serialize(obj: Any) -> Any:
    """Convert dataclasses/enums/datetimes to JSON-friendly structures."""
    if hasattr(obj, "__dataclass_fields__"):
        return _serialize(asdict(obj))
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {key: _serialize(val) for key, val in obj.items()}
    if isinstance(obj, list):
        return [_serialize(val) for val in obj]
    return obj


@st.cache_data(ttl=30)
def load_dashboard_data():
    """Load dashboard data with 30-second cache."""
    service = DashboardDataService()
    return run_async(service.get_dashboard_data())


def render_overview(location_id: str) -> None:
    st.subheader("Overview")
    with st.spinner("Loading dashboard data..."):
        dashboard_data = load_dashboard_data()

    render_hero_metrics(dashboard_data.hero_metrics)
    st.markdown("---")
    render_performance_chart(dashboard_data.performance_metrics)

    st.markdown("---")
    if location_id:
        HeroMetricsUI().render_hero_metrics_section(location_id)
    else:
        st.info("No authorized GHL location is configured for this account.")


def render_conversations(location_id: str) -> None:
    st.subheader("Conversations")
    tab1, tab2, tab3 = st.tabs(["Table", "Advanced", "Activity Feed"])

    with tab1:
        dashboard_data = load_dashboard_data()
        render_active_conversations(
            conversations=dashboard_data.active_conversations.conversations,
            page=st.session_state.page,
            page_size=10,
        )

    with tab2:
        ActiveConversationsComponent().render()

    with tab3:
        lead_port = os.getenv("LEAD_BOT_PORT", "8001")
        lead_api_base = os.getenv("LEAD_BOT_URL", f"http://localhost:{lead_port}").rstrip("/")
        lead_public_base = os.getenv("LEAD_BOT_PUBLIC_URL", lead_api_base).rstrip("/")
        ws_base = os.getenv("LEAD_BOT_WEBSOCKET_URL", "").rstrip("/")
        if not ws_base:
            if lead_public_base.startswith("https://"):
                ws_base = "wss://" + lead_public_base[len("https://"):]
            elif lead_public_base.startswith("http://"):
                ws_base = "ws://" + lead_public_base[len("http://"):]
            else:
                ws_base = f"ws://{lead_public_base}"
        websocket_url = ws_base if "/ws/" in ws_base else f"{ws_base}/ws/dashboard"

        ActivityFeed(
            websocket_url=websocket_url,
            api_base_url=lead_api_base,
        ).render()

def render_analytics(location_id: str) -> None:
    st.subheader("Analytics")
    tab1, tab2, tab3 = st.tabs(["Performance", "Commission", "Lead Intelligence"])

    with tab1:
        PerformanceAnalyticsComponent().render()

    with tab2:
        CommissionTrackingComponent().render()

    with tab3:
        lead_location = location_id or "default"
        LeadIntelligenceDashboard().render_lead_intelligence_section(lead_location)


def render_integrations(location_id: str) -> None:
    st.subheader("Integrations")
    tab1, tab2 = st.tabs(["GHL Status UI", "Raw Status Data"])

    with tab1:
        if location_id:
            GHLStatusUI().render_ghl_status_section(location_id)
        else:
            st.info("No authorized GHL location is configured for this account.")

    with tab2:
        if location_id:
            try:
                status_component = run_async(create_ghl_integration_status())
                status_data = run_async(status_component.get_integration_status(location_id))
                st.json(_serialize(status_data))
            except Exception as exc:
                st.error(f"Failed to load raw integration data: {exc}")
        else:
            st.info("No authorized GHL location is configured for this account.")


def render_mobile(location_id: str) -> None:
    st.subheader("Mobile Experience")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            "Integrated Demo",
            "Metrics Cards",
            "Navigation",
            "Responsive Layout",
            "Touch Charts",
            "Offline Indicator",
            "Field Access",
        ]
    )

    sample_data = get_sample_real_estate_data()

    with tab1:
        apply_responsive_layout_system()
        st.markdown(get_jorge_ai_branding_css(), unsafe_allow_html=True)
        tab_choice = st.selectbox(
            "Mobile Tab",
            ["overview", "analytics", "quick-add", "chats", "profile"],
            index=0,
        )
        render_mobile_dashboard_tab(tab_choice, sample_data)
        create_mobile_navigation_component(current_tab=tab_choice, show_on_desktop=True)

    with tab2:
        metrics = get_sample_metrics()
        render_mobile_metrics_cards(metrics, title="Key Metrics", show_refresh=True)

    with tab3:
        demo_mobile_navigation()

    with tab4:
        apply_responsive_layout_system()
        cards = [
            create_responsive_card(
                f"<h4>Mobile Card {i + 1}</h4><p>Responsive layout preview.</p>",
                interactive=True,
                jorge_branded=True,
            )
            for i in range(6)
        ]
        grid_html = create_responsive_grid(cards, mobile_cols=1, tablet_cols=2, desktop_cols=3)
        container_html = create_responsive_container(grid_html, max_width="lg")
        st.markdown(container_html, unsafe_allow_html=True)

    with tab5:
        chart_data = sample_data["leads_data"].head(30)
        chart = ChartConfig(
            chart_type=ChartType.LINE,
            title="Lead Velocity",
            data=chart_data,
            x_column="date",
            y_column="leads",
            color_column="source",
            height=260,
        )
        render_touch_optimized_chart(chart)

    with tab6:
        sync_queue = [
            SyncItem(
                id="sync_1",
                item_type="lead_update",
                timestamp=datetime.now(),
                priority=SyncPriority.NORMAL,
                status=SyncItemStatus.SYNCING,
                data_size=1200,
            ),
            SyncItem(
                id="sync_2",
                item_type="photo_upload",
                timestamp=datetime.now(),
                priority=SyncPriority.URGENT,
                status=SyncItemStatus.PENDING,
                data_size=4200,
            ),
        ]
        network_metrics = NetworkMetrics(
            latency=120.0,
            bandwidth=450.0,
            packet_loss=0.2,
            connection_type="wifi",
            signal_strength=82,
        )
        create_offline_indicator(
            connection_status=ConnectionStatus.ONLINE,
            sync_queue=sync_queue,
            network_metrics=network_metrics,
            expanded=True,
        )

    with tab7:
        create_field_access_dashboard(
            current_location=(32.7767, -96.7970),
            address="Dallas, TX",
            gps_accuracy=8.2,
            sync_queue=get_sample_sync_queue(),
            online_status=True,
        )


def render_exports(location_id: str) -> None:
    st.subheader("Exports")
    dashboard_data = load_dashboard_data()
    ExportManager().render_export_controls(data=dashboard_data)
    st.info("Use the sidebar controls to generate exports.")


def render_filters(location_id: str) -> None:
    st.subheader("Filters")
    GlobalFilters().render_sidebar_filters()
    st.info("Global filters appear in the sidebar for this section.")


def render_leads(location_id: str) -> None:
    st.subheader("Leads")
    lead_location = location_id or "default"
    LeadIntelligenceDashboard().render_lead_intelligence_section(lead_location)


@dataclass(frozen=True)
class SidebarNavItem:
    key: str
    label: str
    icon: str
    section: str
    render_fn: Callable[[str, Any], None]


SIDEBAR_NAV_ITEMS = [
    SidebarNavItem(
        key="overview",
        label="Overview",
        icon="",
        section="Core",
        render_fn=lambda location_id, user: render_overview(location_id),
    ),
    SidebarNavItem(
        key="conversations",
        label="Conversations",
        icon="",
        section="Core",
        render_fn=lambda location_id, user: render_conversations(location_id),
    ),
    SidebarNavItem(
        key="leads",
        label="Leads",
        icon="",
        section="Core",
        render_fn=lambda location_id, user: render_leads(location_id),
    ),
    SidebarNavItem(
        key="analytics",
        label="Analytics",
        icon="",
        section="Insights",
        render_fn=lambda location_id, user: render_analytics(location_id),
    ),
    SidebarNavItem(
        key="integrations",
        label="Integrations",
        icon="",
        section="Platform",
        render_fn=lambda location_id, user: render_integrations(location_id),
    ),
]

SIDEBAR_SECTION_ORDER = ["Core", "Insights", "Platform"]
SIDEBAR_ITEMS_BY_KEY = {item.key: item for item in SIDEBAR_NAV_ITEMS}


def _normalize_theme(theme: Any) -> str:
    theme_value = str(theme or "").strip().lower()
    return theme_value if theme_value in {"dark", "light"} else "dark"


def _apply_sidebar_navigation_css(theme_mode: str) -> None:
    current_theme = _normalize_theme(theme_mode)
    if current_theme == "light":
        theme_variables = """
            --lyrio-app-bg: #f3f6fb;
            --lyrio-app-surface: #ffffff;
            --lyrio-text-primary: #0f172a;
            --lyrio-text-secondary: #475569;
            --lyrio-sidebar-bg-start: #f8fafc;
            --lyrio-sidebar-bg-end: #f2f6fb;
            --lyrio-sidebar-border: #dbe3ee;
            --lyrio-brand-text: #0f172a;
            --lyrio-subtle-text: #64748b;
            --lyrio-section-text: #64748b;
            --lyrio-nav-text: #334155;
            --lyrio-nav-hover-bg: #edf2fa;
            --lyrio-nav-hover-border: #cfd9e6;
            --lyrio-nav-hover-text: #0f172a;
            --lyrio-nav-active-bg: #e8f1ff;
            --lyrio-nav-active-text: #0f172a;
            --lyrio-nav-active-border: #bfdbfe;
            --lyrio-nav-active-accent: #2563eb;
            --primary-color: #94a3b8;
            --lyrio-divider: #dbe3ee;
            --lyrio-muted-text: #64748b;
            --lyrio-select-bg: #ffffff;
            --lyrio-select-border: #cbd5e1;
            --lyrio-toggle-off: #e2e8f0;
            --lyrio-toggle-on: #94a3b8;
            --lyrio-toggle-knob: #ffffff;
            --lyrio-metric-card-bg: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            --lyrio-metric-card-border: #dbe3ee;
            --lyrio-metric-card-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
            --lyrio-metric-card-hover-border: #b8c8dd;
            --lyrio-metric-card-hover-shadow: 0 12px 24px rgba(15, 23, 42, 0.12);
            --lyrio-metric-label-text: #1e293b;
            --lyrio-metric-delta-text: #64748b;
            --lyrio-main-btn-bg: #ffffff;
            --lyrio-main-btn-text: #1f2937;
            --lyrio-main-btn-border: #cbd5e1;
            --lyrio-main-btn-hover-bg: #eff6ff;
            --lyrio-main-btn-hover-text: #1e3a8a;
            --lyrio-main-btn-hover-border: #93c5fd;
            --lyrio-main-btn-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
        """
    else:
        theme_variables = """
            --lyrio-app-bg: #030712;
            --lyrio-app-surface: #050c18;
            --lyrio-text-primary: #e5e7eb;
            --lyrio-text-secondary: #94a3b8;
            --lyrio-sidebar-bg-start: #0b0f16;
            --lyrio-sidebar-bg-end: #0a0d13;
            --lyrio-sidebar-border: #1d2533;
            --lyrio-brand-text: #f4f7ff;
            --lyrio-subtle-text: #93a2b8;
            --lyrio-section-text: #7687a0;
            --lyrio-nav-text: #9ba9bd;
            --lyrio-nav-hover-bg: #111926;
            --lyrio-nav-hover-border: #243349;
            --lyrio-nav-hover-text: #ebf1fa;
            --lyrio-nav-active-bg: #0f1724;
            --lyrio-nav-active-text: #ffffff;
            --lyrio-nav-active-border: #27364b;
            --lyrio-nav-active-accent: #60a5fa;
            --primary-color: #60a5fa;
            --lyrio-divider: #202b3a;
            --lyrio-muted-text: #8796ad;
            --lyrio-select-bg: #0f1724;
            --lyrio-select-border: #27364b;
            --lyrio-toggle-off: #223247;
            --lyrio-toggle-on: #60a5fa;
            --lyrio-toggle-knob: #ffffff;
            --lyrio-metric-card-bg: linear-gradient(180deg, #121a28 0%, #0f1724 100%);
            --lyrio-metric-card-border: #233246;
            --lyrio-metric-card-shadow: 0 8px 18px rgba(2, 6, 23, 0.3);
            --lyrio-metric-card-hover-border: #345170;
            --lyrio-metric-card-hover-shadow: 0 11px 22px rgba(2, 6, 23, 0.4);
            --lyrio-metric-label-text: #d9e2f0;
            --lyrio-metric-delta-text: #9fb0c8;
            --lyrio-main-btn-bg: #0f172a;
            --lyrio-main-btn-text: #cbd5e1;
            --lyrio-main-btn-border: #243449;
            --lyrio-main-btn-hover-bg: #172235;
            --lyrio-main-btn-hover-text: #e2e8f0;
            --lyrio-main-btn-hover-border: #324b68;
            --lyrio-main-btn-shadow: none;
        """

    shell_css = """
        <style>
        :root {
            --lyrio-sidebar-width: 18.5rem;
            --lyrio-main-top-offset: 0.45rem;
            __THEME_VARIABLES__
        }

        /* Hide Streamlit native top bar/header for app-shell look. */
        header[data-testid="stHeader"] {
            display: none !important;
        }

        [data-testid="stToolbar"] {
            display: none !important;
        }

        [data-testid="stDecoration"] {
            display: none !important;
        }

        [data-testid="stAppViewContainer"] {
            margin-top: 0 !important;
            background: var(--lyrio-app-bg) !important;
        }

        /* Offset main content so it does not render beneath the fixed sidebar. */
        [data-testid="stAppViewContainer"] [data-testid="stMain"],
        [data-testid="stAppViewContainer"] .main {
            margin-left: var(--lyrio-sidebar-width);
            background: var(--lyrio-app-bg) !important;
            color: var(--lyrio-text-primary) !important;
        }

        [data-testid="stAppViewContainer"] [data-testid="stMain"] .block-container,
        [data-testid="stAppViewContainer"] .main .block-container {
            max-width: 100%;
            padding-top: var(--lyrio-main-top-offset);
            padding-left: 2rem;
            padding-right: 2rem;
            box-sizing: border-box;
            color: var(--lyrio-text-primary) !important;
            background: transparent !important;
        }

        [data-testid="stAppViewContainer"] [data-testid="stMain"] .block-container > div:first-child,
        [data-testid="stAppViewContainer"] .main .block-container > div:first-child {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }

        [data-testid="stAppViewContainer"] [data-testid="stMain"] p,
        [data-testid="stAppViewContainer"] [data-testid="stMain"] span,
        [data-testid="stAppViewContainer"] .main p,
        [data-testid="stAppViewContainer"] .main span {
            color: var(--lyrio-text-secondary);
        }

        /* Main area actions (Refresh Metrics + Quick Actions) */
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button,
        [data-testid="stAppViewContainer"] .main .stButton > button {
            background: var(--lyrio-main-btn-bg) !important;
            color: var(--lyrio-main-btn-text) !important;
            -webkit-text-fill-color: var(--lyrio-main-btn-text) !important;
            border: 1px solid var(--lyrio-main-btn-border) !important;
            border-radius: 10px !important;
            box-shadow: var(--lyrio-main-btn-shadow) !important;
            opacity: 1 !important;
        }
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button:hover,
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .stButton > button:focus-visible,
        [data-testid="stAppViewContainer"] .main .stButton > button:hover,
        [data-testid="stAppViewContainer"] .main .stButton > button:focus-visible {
            background: var(--lyrio-main-btn-hover-bg) !important;
            color: var(--lyrio-main-btn-hover-text) !important;
            -webkit-text-fill-color: var(--lyrio-main-btn-hover-text) !important;
            border-color: var(--lyrio-main-btn-hover-border) !important;
        }

        /* Align first main heading baseline with sidebar top content. */
        [data-testid="stAppViewContainer"] [data-testid="stMain"] .block-container h1,
        [data-testid="stAppViewContainer"] .main .block-container h1 {
            margin-top: 0 !important;
            padding-top: 0 !important;
            color: var(--lyrio-text-primary);
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--lyrio-sidebar-bg-start) 0%, var(--lyrio-sidebar-bg-end) 100%);
            border-right: 1px solid var(--lyrio-sidebar-border);
            min-width: var(--lyrio-sidebar-width);
            max-width: var(--lyrio-sidebar-width);
            position: fixed !important;
            left: 0;
            top: 0;
            bottom: 0;
            height: 100dvh;
            z-index: 100;
            overflow: hidden;
        }

        [data-testid="stSidebar"] > div:first-child {
            height: 100%;
        }

        /* Remove Streamlit's internal sidebar top inset so content starts near the top edge. */
        [data-testid="stSidebarContent"] {
            padding-top: 0 !important;
        }

        [data-testid="stSidebarUserContent"] {
            padding-top: 0.35rem !important;
            margin-top: 0 !important;
        }

        [data-testid="stSidebar"] .block-container {
            padding-top: 0.55rem;
            padding-bottom: 0.7rem;
            height: 100%;
            display: flex;
            flex-direction: column;
            overflow-y: hidden;
            overflow-x: hidden;
        }

        /* Keep the app sidebar persistent (hide open/close controls). */
        [data-testid="stSidebarCollapseButton"] {
            display: none !important;
        }

        [data-testid="collapsedControl"] {
            display: none !important;
        }

        button[aria-label="Close sidebar"],
        button[aria-label="Open sidebar"],
        [data-testid="stSidebar"] button[kind="header"] {
            display: none !important;
        }

        /* Defensive fallback in case Streamlit toggles collapsed state. */
        [data-testid="stSidebar"][aria-expanded="false"] {
            min-width: var(--lyrio-sidebar-width) !important;
            max-width: var(--lyrio-sidebar-width) !important;
            transform: translateX(0) !important;
            margin-left: 0 !important;
        }

        [data-testid="stSidebar"][aria-expanded="false"] > div:first-child {
            margin-left: 0 !important;
        }

        .lyrio-sidebar-brand {
            padding: 0.95rem 0.2rem 0.65rem 0.2rem;
        }

        .lyrio-sidebar-brand-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: var(--lyrio-brand-text);
            letter-spacing: 0.01em;
            line-height: 1.2;
        }

        .lyrio-sidebar-workspace {
            margin-top: 0.28rem;
            color: var(--lyrio-subtle-text);
            font-size: 0.69rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 600;
        }

        .lyrio-sidebar-section {
            margin: 0.58rem 0 0.22rem 0.2rem;
            color: var(--lyrio-section-text);
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }

        [data-testid="stSidebar"] .stButton > button {
            width: 100%;
            justify-content: flex-start;
            border-radius: 10px;
            border: 1px solid transparent;
            padding: 0.42rem 0.58rem;
            font-size: 0.88rem;
            font-weight: 500;
            background: transparent;
            color: var(--lyrio-nav-text);
            transition: 120ms ease all;
        }

        [data-testid="stSidebar"] .stButton > button:hover {
            background: var(--lyrio-nav-hover-bg);
            border-color: var(--lyrio-nav-hover-border);
            color: var(--lyrio-nav-hover-text);
        }

        [data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: var(--lyrio-nav-active-bg);
            color: var(--lyrio-nav-active-text);
            border: 1px solid var(--lyrio-nav-active-border);
            border-left: 3px solid var(--lyrio-nav-active-accent);
            font-weight: 600;
        }

        .lyrio-sidebar-divider {
            margin: 0.68rem 0 0.46rem 0;
            border-top: 1px solid var(--lyrio-divider);
        }

        .lyrio-sidebar-spacer {
            margin-top: auto;
        }

        .lyrio-last-updated {
            margin: 0.45rem 0.2rem 0.1rem 0.2rem;
            color: var(--lyrio-muted-text);
            font-size: 0.74rem;
            line-height: 1.35;
        }

        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: var(--lyrio-select-bg);
            border-color: var(--lyrio-select-border);
            color: var(--lyrio-nav-text);
        }

        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
            color: var(--lyrio-nav-text);
        }

        [data-testid="stSidebar"] [data-baseweb="switch"] {
            margin-top: 0.1rem;
        }

        [data-testid="stSidebar"] [data-baseweb="switch"] [role="switch"] {
            background: var(--lyrio-toggle-off) !important;
            border: 1px solid var(--lyrio-nav-hover-border) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="switch"] [role="switch"][aria-checked="true"] {
            background: var(--lyrio-toggle-on) !important;
            border-color: var(--lyrio-toggle-on) !important;
        }

        [data-testid="stSidebar"] [data-baseweb="switch"] [role="switch"] > div,
        [data-testid="stSidebar"] [role="switch"] > div {
            background: var(--lyrio-toggle-knob) !important;
        }

        [data-testid="stSidebar"] [role="switch"] {
            background: var(--lyrio-toggle-off) !important;
            border-color: var(--lyrio-nav-hover-border) !important;
        }

        [data-testid="stSidebar"] [role="switch"][aria-checked="true"] {
            background: var(--lyrio-toggle-on) !important;
            border-color: var(--lyrio-toggle-on) !important;
        }

        [data-testid="stSidebar"] input[type="checkbox"] {
            accent-color: var(--lyrio-toggle-on) !important;
        }

        .st-key-sidebar_logout {
            margin-top: 0.45rem;
        }
        </style>
        """
    shell_css = shell_css.replace("__THEME_VARIABLES__", theme_variables)
    st.markdown(shell_css, unsafe_allow_html=True)


def _resolve_workspace_label(location_id: str) -> str:
    configured_label = os.getenv("DASHBOARD_WORKSPACE_LABEL", "").strip()
    if configured_label:
        return configured_label
    if location_id:
        return f"Workspace · {location_id}"
    return "Workspace · Default"


def _initialize_navigation_state() -> None:
    if "page" not in st.session_state:
        st.session_state.page = 1
    if "last_refresh" not in st.session_state:
        st.session_state.last_refresh = datetime.now()
    if "active_page_key" not in st.session_state:
        st.session_state.active_page_key = "overview"
    if "ui_theme" not in st.session_state:
        env_theme = _normalize_theme(os.getenv("DASHBOARD_THEME", "dark"))
        st.session_state.ui_theme = env_theme

    requested_view = st.query_params.get("view")
    if isinstance(requested_view, list):
        requested_view = requested_view[0] if requested_view else None
    if requested_view in SIDEBAR_ITEMS_BY_KEY:
        st.session_state.active_page_key = requested_view

    requested_theme = st.query_params.get("theme")
    if isinstance(requested_theme, list):
        requested_theme = requested_theme[0] if requested_theme else None
    normalized_requested_theme = _normalize_theme(requested_theme)
    if requested_theme and normalized_requested_theme != st.session_state.ui_theme:
        st.session_state.ui_theme = normalized_requested_theme


def _handle_manual_refresh() -> None:
    load_dashboard_data.clear()
    st.session_state.last_refresh = datetime.now()
    st.rerun()


def _render_sidebar_navigation(location_id: str) -> str:
    workspace_label = _resolve_workspace_label(location_id)
    active_page_key = st.session_state.active_page_key
    current_theme = _normalize_theme(st.session_state.get("ui_theme"))

    with st.sidebar:
        st.markdown(
            f"""
            <div class="lyrio-sidebar-brand">
                <div class="lyrio-sidebar-brand-title">Lyrio AI</div>
                <div class="lyrio-sidebar-workspace">{workspace_label}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for section_name in SIDEBAR_SECTION_ORDER:
            st.markdown(f'<div class="lyrio-sidebar-section">{section_name}</div>', unsafe_allow_html=True)
            section_items = [item for item in SIDEBAR_NAV_ITEMS if item.section == section_name]
            for item in section_items:
                is_active = item.key == active_page_key
                button_label = f"{item.icon}  {item.label}" if item.icon else item.label
                if st.button(
                    button_label,
                    key=f"nav_{item.key}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    st.session_state.active_page_key = item.key
                    st.query_params["view"] = item.key
                    st.rerun()

        st.markdown('<div class="lyrio-sidebar-spacer"></div>', unsafe_allow_html=True)
        st.markdown('<div class="lyrio-sidebar-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="lyrio-sidebar-section">Utility</div>', unsafe_allow_html=True)

        use_light_mode = st.toggle(
            "Light Mode",
            value=(current_theme == "light"),
            key="sidebar_theme_toggle",
            label_visibility="visible",
        )
        selected_theme = "light" if use_light_mode else "dark"
        if selected_theme != current_theme:
            st.session_state.ui_theme = selected_theme
            st.query_params["theme"] = selected_theme
            st.rerun()

        if st.button("Refresh Data", key="sidebar_refresh_data", use_container_width=True):
            _handle_manual_refresh()

        st.markdown(
            f'<div class="lyrio-last-updated">Last updated {st.session_state.last_refresh.strftime("%b %d, %Y · %I:%M:%S %p")}</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="lyrio-sidebar-divider"></div>', unsafe_allow_html=True)
        if st.button("Log Out", key="sidebar_logout", use_container_width=True):
            clear_session()
            st.rerun()

    return st.session_state.active_page_key


# Initialize session state
_initialize_navigation_state()


# Authentication gating
user = check_authentication()
if not user:
    render_login_form()
    st.stop()

if st.session_state.get("must_change_password"):
    render_password_change_form(user)
    st.stop()

if not require_permission(user, "dashboard", "read"):
    st.stop()

# Page header (authenticated view only)
st.title(_dashboard_title())
st.markdown(f"**{_dashboard_subtitle()}**")


# Sidebar controls + navigation
location_id = (
    st.session_state.get("oauth_location_id")
    or st.session_state.get("location_id")
    or settings.ghl_location_id
    or os.getenv("GHL_LOCATION_ID", "")
).strip()
st.session_state.location_id = location_id
_apply_sidebar_navigation_css(_normalize_theme(st.session_state.get("ui_theme")))
selected_page_key = _render_sidebar_navigation(location_id)
auto_refresh = os.getenv("DASHBOARD_AUTO_REFRESH", "false").strip().lower() in {"1", "true", "yes", "on"}


# Main content
try:
    selected_item = SIDEBAR_ITEMS_BY_KEY.get(selected_page_key, SIDEBAR_ITEMS_BY_KEY["overview"])
    selected_item.render_fn(location_id, user)
except Exception as exc:
    st.error(f"Error loading dashboard section: {exc}")
    st.info("Try refreshing or selecting a different section.")


# Auto-refresh logic
if auto_refresh:
    import time

    time.sleep(30)
    load_dashboard_data.clear()
    st.session_state.last_refresh = datetime.now()
    st.rerun()
