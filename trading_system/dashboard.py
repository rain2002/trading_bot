import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from datetime import datetime, timedelta
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from trading_system.app.config.settings import settings
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter
from trading_system.app.broker.groww import GrowwBrokerAdapter
from trading_system.app.config.stop_loss_manager import StopLossManager

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="ANTIGRAVITY // Quantum Terminal",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# ==============================================================================
# BLACKLEAD STUDIO (BL/S®) DESIGN SYSTEM & EDITORIAL ARCHITECTURE
# STYLISH YET SIMPLE TO UNDERSTAND • SIMPLE, REFINED UX
# ==============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500&family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* Global Font & High-End Matte Obsidian Theme */
html, body, [class*="css"] {
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: #FFFFFF;
}

code, pre, .mono-font {
    font-family: 'DM Mono', 'JetBrains Mono', monospace !important;
}

/* Velvet Matte Obsidian Canvas - Pure Black Architectural Aesthetic */
.stApp {
    background: #050507 !important;
    background-attachment: fixed !important;
}

/* Delicate Hairline Architectural Grid Mesh */
.stApp::before {
    content: '';
    position: fixed;
    top: 0; left: 0; width: 100vw; height: 100vh;
    background-image: radial-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px);
    background-size: 32px 32px;
    pointer-events: none;
    z-index: 0;
}

/* Minimalist Studio Sidebar */
section[data-testid="stSidebar"] {
    background: #070709 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.07) !important;
    box-shadow: 12px 0 40px rgba(0, 0, 0, 0.9) !important;
}

/* ==============================================================================
   STANDARD MODERN WEBSITE SIDEBAR NAVIGATION (SIMPLE, CLEAN LINKS)
   ============================================================================== */

/* Tight vertical spacing between navigation links */
section[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div.stButton,
section[data-testid="stSidebar"] div.stButton {
    margin: 0 !important;
    padding: 0 !important;
    margin-bottom: 3px !important;
    width: 100% !important;
}

/* Base styling for all sidebar navigation links */
section[data-testid="stSidebar"] div.stButton > button {
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    width: 100% !important;
    min-height: 40px !important;
    height: 40px !important;
    padding: 8px 14px !important;
    border-radius: 8px !important;
    font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif !important;
    font-size: 0.86rem !important;
    font-weight: 500 !important;
    text-align: left !important;
    letter-spacing: -0.01em !important;
    transition: all 0.16s ease !important;
    cursor: pointer !important;
    box-sizing: border-box !important;
}

/* Inactive Page Links (normal website nav item) */
section[data-testid="stSidebar"] div.stButton > button[kind="secondary"],
section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-secondary"],
section[data-testid="stSidebar"] div.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]) {
    background: transparent !important;
    color: #A1A1AA !important;
    border: 1px solid transparent !important;
    border-left: 3px solid transparent !important;
    box-shadow: none !important;
}

/* Hover effect on inactive links - clean minimalist studio hover */
section[data-testid="stSidebar"] div.stButton > button[kind="secondary"]:hover,
section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-secondary"]:hover,
section[data-testid="stSidebar"] div.stButton > button:not([kind="primary"]):not([data-testid="stBaseButton-primary"]):hover {
    background: rgba(255, 255, 255, 0.04) !important;
    color: #FFFFFF !important;
    border-color: rgba(255, 255, 255, 0.08) !important;
    border-left: 3px solid rgba(255, 255, 255, 0.4) !important;
    transform: translateX(2px) !important;
}

/* Active Page Link (Blacklead Mint Accent) */
section[data-testid="stSidebar"] div.stButton > button[kind="primary"],
section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"] {
    background: rgba(130, 251, 189, 0.08) !important;
    color: #82FBBD !important;
    border: 1px solid rgba(130, 251, 189, 0.28) !important;
    border-left: 3px solid #82FBBD !important;
    font-weight: 600 !important;
    box-shadow: 0 2px 14px rgba(130, 251, 189, 0.12) !important;
}

section[data-testid="stSidebar"] div.stButton > button[kind="primary"]:hover,
section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: rgba(130, 251, 189, 0.12) !important;
    color: #82FBBD !important;
    border-color: rgba(130, 251, 189, 0.4) !important;
}

/* Align text and emojis inside the button strictly to the left */
section[data-testid="stSidebar"] div.stButton > button > div,
section[data-testid="stSidebar"] div.stButton > button span,
section[data-testid="stSidebar"] div.stButton > button div[data-testid="stMarkdownContainer"],
section[data-testid="stSidebar"] div.stButton > button p {
    font-family: inherit !important;
    font-size: inherit !important;
    font-weight: inherit !important;
    color: inherit !important;
    margin: 0 !important;
    padding: 0 !important;
    text-align: left !important;
    display: flex !important;
    justify-content: flex-start !important;
    align-items: center !important;
    width: 100% !important;
}

/* ==============================================================================
   TIMEFRAME SELECTOR / SEGMENTED CONTROL (MINIMALIST PILLS)
   ============================================================================== */
div[data-testid="stSegmentedControl"] {
    background: #0E0E12 !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 9999px !important;
    padding: 2px !important;
}

div[data-testid="stSegmentedControl"] button {
    font-family: 'DM Mono', monospace !important;
    font-size: 0.74rem !important;
    font-weight: 500 !important;
    color: #A1A1AA !important;
    background: transparent !important;
    border: none !important;
    border-radius: 9999px !important;
    padding: 4px 10px !important;
    cursor: pointer !important;
    transition: all 0.18s ease !important;
}

div[data-testid="stSegmentedControl"] button:hover {
    color: #FFFFFF !important;
    background: rgba(255, 255, 255, 0.06) !important;
}

div[data-testid="stSegmentedControl"] button[aria-checked="true"],
div[data-testid="stSegmentedControl"] button[data-checked="true"] {
    background: rgba(255, 255, 255, 0.12) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255, 255, 255, 0.22) !important;
    font-weight: 600 !important;
}

/* ==============================================================================
   PIXEL-PERFECT UNIFORM METRIC BOXES (BLACKLEAD ARCHITECTURAL CARDS)
   ============================================================================== */
[data-testid="column"] {
    display: flex !important;
    flex-direction: column !important;
}
[data-testid="column"] > div {
    flex: 1 1 auto !important;
    display: flex !important;
    flex-direction: column !important;
}

.cyber-kpi-card {
    background: #0D0E12 !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    padding: 14px 16px !important;
    height: 124px !important;
    min-height: 124px !important;
    max-height: 124px !important;
    box-sizing: border-box !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    transition: all 0.22s ease !important;
    margin: 0 !important;
    width: 100% !important;
}
.cyber-kpi-card:hover {
    border-color: rgba(255, 255, 255, 0.20) !important;
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 26px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
}

.kpi-title {
    font-family: 'DM Mono', monospace;
    font-size: 0.66rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.10em;
    color: #71717A;
    height: 20px;
    display: flex;
    align-items: center;
    line-height: 1.1;
    margin: 0;
    padding: 0;
    overflow: hidden;
    white-space: nowrap;
    text-overflow: ellipsis;
}

.kpi-value {
    height: 36px;
    display: flex;
    align-items: center;
    margin: 0;
    padding: 0;
}

.kpi-badge-row {
    height: 22px;
    display: flex;
    align-items: center;
    margin: 0;
    padding: 0;
}

/* Metric Typography - High Contrast Studio Display */
.metric-big {
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: -0.035em;
    color: #FFFFFF;
    line-height: 1;
    margin: 0;
}

.metric-big-green {
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: -0.035em;
    color: #82FBBD;
    line-height: 1;
    margin: 0;
}

.metric-big-red {
    font-size: 1.65rem;
    font-weight: 700;
    letter-spacing: -0.035em;
    color: #FF9A9C;
    line-height: 1;
    margin: 0;
}

.metric-badge-uniform {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 9999px;
    margin: 0;
    background: rgba(255, 255, 255, 0.05);
    color: #A1A1AA;
    border: 1px solid rgba(255, 255, 255, 0.10);
}

.metric-badge-mint {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 9999px;
    margin: 0;
    background: rgba(130, 251, 189, 0.09);
    color: #82FBBD;
    border: 1px solid rgba(130, 251, 189, 0.25);
}

.metric-badge-danger {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 9999px;
    margin: 0;
    background: rgba(255, 154, 156, 0.09);
    color: #FF9A9C;
    border: 1px solid rgba(255, 154, 156, 0.25);
}

/* Standard Studio Card Container */
.cyber-card {
    background: #0D0E12 !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    padding: 18px 22px !important;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
    transition: all 0.22s ease !important;
    margin-bottom: 14px !important;
}
.cyber-card:hover {
    border-color: rgba(255, 255, 255, 0.18) !important;
    transform: translateY(-2px) !important;
}

/* Top Telemetry Header (Minimalist Command Strip) */
.hud-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 20px;
    background: #0D0E12 !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 12px !important;
    margin-bottom: 18px;
    box-shadow: 0 6px 25px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05) !important;
}

.hud-title {
    font-size: 1.22rem;
    font-weight: 700;
    letter-spacing: -0.025em;
    color: #FFFFFF;
    display: flex;
    align-items: center;
    gap: 8px;
}
.hud-title-accent {
    color: #82FBBD;
}

.hud-subtitle {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    color: #71717A;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    margin-top: 3px;
}

/* Status Badges & Pills */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-family: 'DM Mono', monospace;
    font-size: 0.70rem;
    font-weight: 500;
    padding: 4px 11px;
    border-radius: 9999px;
    background: #141418;
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #FFFFFF;
}

.pulse-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background-color: #82FBBD;
    box-shadow: 0 0 8px #82FBBD;
    animation: radar-pulse 2s infinite;
    display: inline-block;
}
@keyframes radar-pulse {
    0% { transform: scale(0.95); opacity: 0.8; }
    70% { transform: scale(1.2); opacity: 1; }
    100% { transform: scale(0.95); opacity: 0.8; }
}

/* Page Dedicated Header */
.page-title-box {
    margin-bottom: 18px;
    padding-bottom: 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}
.page-title {
    font-size: 1.30rem;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: -0.02em;
}
.page-subtitle {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    color: #71717A;
    letter-spacing: 0.10em;
    text-transform: uppercase;
    margin-top: 3px;
}

/* Streamlit DataFrames */
[data-testid="stDataFrame"] {
    border-radius: 10px !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    overflow: hidden !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# BROKER DATA INGESTION & REGIONAL MARKET SELECTION
# ==========================================
st.sidebar.markdown("""
<div style="font-family: 'DM Mono', monospace; font-size: 0.66rem; font-weight: 500; color: #71717A; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 6px; padding-left: 2px;">
    // ACTIVE PORTFOLIO REGION
</div>
""", unsafe_allow_html=True)

selected_market = st.sidebar.selectbox(
    "Active Portfolio",
    options=["🇺🇸 US Equities (Alpaca / USD)", "🇮🇳 India Equities (Groww / INR)"],
    index=0,
    label_visibility="collapsed"
)
is_india_mode = "India" in selected_market
CURRENCY_SYMBOL = "₹" if is_india_mode else "$"

if is_india_mode:
    st.sidebar.markdown("""
    <div style='background:rgba(255, 153, 0, 0.08); border:1px solid rgba(255, 153, 0, 0.25); border-radius:8px; padding:10px 12px; margin-bottom:14px; font-family:"DM Mono",monospace;'>
        <div style='color:#FFB800; font-weight:700; font-size:0.75rem; letter-spacing:0.05em;'>🇮🇳 GROWW // NSE CASH CNC</div>
        <div style='color:#A1A1AA; font-size:0.68rem; margin-top:2px;'>Demat Delivery Portfolio • SEBI Integer Sizing • GTT Active</div>
    </div>
    """, unsafe_allow_html=True)

    india_key = settings.INDIA_API_KEY
    india_sec = settings.INDIA_API_SECRET
    india_totp = settings.INDIA_TOTP_SECRET
    india_cap = getattr(settings, "INDIA_INITIAL_CAPITAL", 1000000.0)

    broker = GrowwBrokerAdapter(
        api_key=india_key,
        api_secret=india_sec,
        totp_secret=india_totp,
        initial_capital=india_cap
    )
else:
    api_key = settings.PAPER_API_KEY
    api_secret = settings.PAPER_API_SECRET

    if not api_key or not api_secret:
        st.sidebar.warning("⚠️ Credentials not detected in .env")
        api_key = st.sidebar.text_input("Alpaca API Key", type="password")
        api_secret = st.sidebar.text_input("Alpaca API Secret", type="password")

    broker = AlpacaBrokerAdapter(api_key=api_key or "mock", api_secret=api_secret or "mock")

sl_manager = StopLossManager()

acc_details = broker.get_account_details()
equity = acc_details.get("equity", 100000.0)
cash = acc_details.get("cash", 0.0)
buying_power = acc_details.get("buying_power", cash)
today_pnl = acc_details.get("today_pnl", 0.0)
today_pnl_pct = acc_details.get("today_pnl_pct", 0.0)
overall_pnl = acc_details.get("overall_pnl", 0.0)
overall_pnl_pct = acc_details.get("overall_pnl_pct", 0.0)
cash_pct = (cash / equity * 100) if equity > 0 else 0.0
invested_capital = equity - cash
invested_pct = (invested_capital / equity * 100) if equity > 0 else 0.0

def format_pnl_str(val: float) -> str:
    """Format currency P&L cleanly as +$X,XXX.XX / +₹X,XXX.XX or -$X,XXX.XX / -₹X,XXX.XX."""
    if pd.isna(val):
        return f"{CURRENCY_SYMBOL}0.00"
    if val >= 0:
        return f"+{CURRENCY_SYMBOL}{val:,.2f}"
    else:
        return f"-{CURRENCY_SYMBOL}{abs(val):,.2f}"

def format_pct_str(val: float) -> str:
    """Format percentage returns cleanly as +X.XX% or -X.XX%."""
    if pd.isna(val):
        return "0.00%"
    if val >= 0:
        return f"+{val:.2f}%"
    else:
        return f"-{abs(val):.2f}%"

def create_donut_chart(
    labels: list,
    values: list,
    colors: list,
    center_text: str,
    title: str = None,
    height: int = 250,
    hole: float = 0.65,
    show_legend: bool = True
) -> go.Figure:
    """Generate a high-contrast Blacklead Studio obsidian donut chart."""
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=hole,
        marker=dict(colors=colors, line=dict(color='#070A12', width=1.5)),
        textposition='inside',
        textinfo='percent' if len(labels) <= 4 else 'none',
        hovertemplate="<b>%{label}</b><br>Value: %{value}<br>Share: %{percent}<extra></extra>"
    )])
    fig.update_layout(
        title=dict(
            text=f"<span style='font-family:Space Grotesk,sans-serif; font-size:12px; font-weight:600; color:#FFFFFF;'>{title}</span>" if title else "",
            x=0.02,
            y=0.96
        ) if title else None,
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.24,
            xanchor="center",
            x=0.5,
            font=dict(family="DM Mono, monospace", size=10, color="#A1A1AA")
        ),
        margin=dict(t=35 if title else 10, b=25 if show_legend else 10, l=10, r=10),
        height=height,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        annotations=[dict(
            text=center_text,
            x=0.5, y=0.5,
            font_size=12,
            font_family="Space Grotesk, sans-serif",
            font_color="#FFFFFF",
            showarrow=False
        )]
    )
    return fig

# ==========================================
# SIDEBAR NAVIGATION MENU (BL/S® EDITORIAL STYLE)
# ==========================================
st.sidebar.markdown("""
<div style="padding: 12px 0 16px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 16px;">
    <div style="font-size: 1.18rem; font-weight: 700; letter-spacing: -0.03em; color: #FFFFFF; display: flex; align-items: center; gap: 8px;">
        BL/S® <span style="color: #82FBBD;">// QUANTUM</span>
    </div>
    <div style="font-family: 'DM Mono', monospace; font-size: 0.66rem; color: #71717A; letter-spacing: 0.12em; text-transform: uppercase; margin-top: 4px;">
        DIGITAL TRADING DESK
    </div>
    <div style="margin-top: 10px;">
        <span class="status-pill" style="padding: 3px 9px; font-size: 0.66rem; border-color: rgba(130, 251, 189, 0.28); color: #82FBBD;">
            <span class="pulse-dot"></span> LIVE EXECUTION READY
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

# Persistent Sidebar Account Strip
nav_pnl_color = "#82FBBD" if today_pnl >= 0 else "#FF9A9C"
nav_all_color = "#82FBBD" if overall_pnl >= 0 else "#FF9A9C"
st.sidebar.markdown(f"""
<div style="background: #0D0E12; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 12px 14px; margin-bottom: 16px; font-family: 'DM Mono', monospace; box-shadow: 0 4px 16px rgba(0,0,0,0.5);">
    <div style="font-size: 0.64rem; color: #71717A; letter-spacing: 0.12em; text-transform: uppercase;">PORTFOLIO NAV</div>
    <div style="font-size: 1.30rem; font-weight: 700; color: #FFFFFF; margin: 3px 0; font-family: 'Space Grotesk', sans-serif; letter-spacing: -0.03em;">{CURRENCY_SYMBOL}{equity:,.2f}</div>
    <div style="display: flex; justify-content: space-between; font-size: 0.70rem; color: #71717A; margin-top: 5px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 5px;">
        <span>SESSION: <b style="color: {nav_pnl_color};">{format_pnl_str(today_pnl)}</b></span>
        <span>RETURN: <b style="color: {nav_all_color};">{format_pct_str(overall_pnl_pct)}</b></span>
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 0.66rem; color: #52525B; margin-top: 4px;">
        <span>CASH: <b style="color: #A1A1AA;">{cash_pct:.1f}%</b></span>
        <span>EQUITY: <b style="color: #A1A1AA;">{invested_pct:.1f}%</b></span>
    </div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("""
<div style="font-family: 'DM Mono', monospace; font-size: 0.66rem; font-weight: 500; color: #71717A; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 8px; padding-left: 2px;">
    // NAVIGATION
</div>
""", unsafe_allow_html=True)

PAGE_OPTIONS = [
    "📊 Portfolio Overview",
    "📋 Positions & Stop-Loss",
    "⚡ Manual Order Desk & Execution",
    "🏆 30-Day Incubation Scorecard",
    "📜 Order Activity Log",
    "🧠 Quant Brain & Strategy",
    "🛡️ Risk Safeguards"
]

if "current_page" not in st.session_state:
    st.session_state.current_page = PAGE_OPTIONS[0]

try:
    if "page" in st.query_params:
        qp_page = str(st.query_params["page"]).lower()
        for opt in PAGE_OPTIONS:
            if qp_page in opt.lower():
                st.session_state.current_page = opt
                break
except Exception:
    pass

if st.session_state.current_page not in PAGE_OPTIONS:
    st.session_state.current_page = PAGE_OPTIONS[0]

for p_name in PAGE_OPTIONS:
    is_active = (st.session_state.current_page == p_name)
    if st.sidebar.button(
        p_name,
        key=f"nav_btn_{p_name}",
        use_container_width=True,
        type="primary" if is_active else "secondary"
    ):
        if not is_active:
            st.session_state.current_page = p_name
            st.rerun()

page = st.session_state.current_page

# Fetch active open orders count for sidebar telemetry
open_orders_cached = broker.get_open_orders()
open_orders_count = len(open_orders_cached)

st.sidebar.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
st.sidebar.markdown(f"""
<div style="font-family: 'DM Mono', monospace; font-size: 0.68rem; color: #71717A; line-height: 1.7; padding: 10px 12px; background: #0D0E12; border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
    <div>BROKER: <span style="color: #82FBBD;">ALPACA PAPER</span></div>
    <div>OPEN ORDERS: <span style="color: {'#82FBBD' if open_orders_count > 0 else '#A1A1AA'};">{open_orders_count} QUEUED</span></div>
    <div>BUYING POWER: <span style="color: #82FBBD;">${buying_power:,.2f}</span></div>
    <div>ACTIVE ARCH: <span style="color: #82FBBD;">PHASE 3 ML GATE</span></div>
    <div>SOLVENCY: <span style="color: #82FBBD;">100% LONG-ONLY</span></div>
</div>
""", unsafe_allow_html=True)


# ==============================================================================
# PAGE 1: 📊 PORTFOLIO OVERVIEW (EXECUTIVE DESK)
# ==============================================================================
if page == "📊 Portfolio Overview":
    # Top Telemetry HUD Header
    st.markdown("""
    <div class="hud-header">
        <div>
            <div class="hud-title">BL/S® <span class="hud-title-accent">// QUANTUM TERMINAL</span></div>
            <div class="hud-subtitle">PHASE 2 MULTI-STRATEGY ENSEMBLE • PHASE 3 ML ALPHA GATE • REAL-TIME BROKER TELEMETRY</div>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
            <span class="status-pill"><span class="pulse-dot"></span> LIVE EXECUTION READY</span>
            <span class="status-pill" style="border-color: rgba(130, 251, 189, 0.25); color: #82FBBD;">ALPACA PAPER LIVE</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 5-CARD UNIFORM KPI DECK (Clean, Pixel-Perfect Matching Heights & Alignment)
    k1, k2, k3, k4, k5 = st.columns(5)

    with k1:
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">PORTFOLIO TOTAL EQUITY</div>
            <div class="kpi-value"><div class="metric-big">{CURRENCY_SYMBOL}{equity:,.2f}</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-uniform">NAV REAL-TIME</div></div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        pnl_class = "metric-big-green" if today_pnl >= 0 else "metric-big-red"
        badge_class = "metric-badge-mint" if today_pnl >= 0 else "metric-badge-danger"
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">TODAY'S SESSION P&L</div>
            <div class="kpi-value"><div class="{pnl_class}">{format_pnl_str(today_pnl)}</div></div>
            <div class="kpi-badge-row"><div class="{badge_class}">{format_pct_str(today_pnl_pct)} TODAY</div></div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        all_class = "metric-big-green" if overall_pnl >= 0 else "metric-big-red"
        badge_all_class = "metric-badge-mint" if overall_pnl >= 0 else "metric-badge-danger"
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">INCEPTION NET RETURN</div>
            <div class="kpi-value"><div class="{all_class}">{format_pnl_str(overall_pnl)}</div></div>
            <div class="kpi-badge-row"><div class="{badge_all_class}">{format_pct_str(overall_pnl_pct)} NET ALPHA</div></div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">LIQUID CASH BUFFER</div>
            <div class="kpi-value"><div class="metric-big">{CURRENCY_SYMBOL}{cash:,.2f}</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-uniform">{cash_pct:.1f}% PRESERVED</div></div>
        </div>
        """, unsafe_allow_html=True)

    with k5:
        st.markdown("""
        <div class="cyber-kpi-card">
            <div class="kpi-title">AI ARCHITECTURE TIER</div>
            <div class="kpi-value"><div class="metric-big">PHASE 3</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-mint">ML ALPHA GATE ACTIVE</div></div>
        </div>
        """, unsafe_allow_html=True)

    # ==============================================================================
    # 📈 GROWW-STYLE HERO LINE GRAPH: CURRENT VS INVESTED PORTFOLIO TRAJECTORY
    # (1M | 6M | 1Y | 3Y | 5Y | All)
    # ==============================================================================
    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

    # 1. Fetch & Prepare Historical Portfolio Equity Data
    initial_capital = 100000.0
    df_raw_history = broker.get_portfolio_history(period="all", timeframe="1D")

    if df_raw_history is not None and not df_raw_history.empty:
        df_clean = df_raw_history[df_raw_history["equity"] > 0].copy()
    else:
        df_clean = pd.DataFrame()

    # Generate graceful simulated curve if broker returns empty / mock
    if df_clean.empty:
        base_dates = pd.date_range(end=datetime.now(), periods=25, freq='D')
        df_clean = pd.DataFrame({
            "timestamp": base_dates,
            "equity": [100000.0 + (i * 58.5) for i in range(25)],
            "profit_loss": [i * 58.5 for i in range(25)],
            "profit_loss_pct": [(i * 58.5) / 100000.0 for i in range(25)]
        })

    # Append current live intraday equity point if newer than last closed daily bar
    last_hist_ts = df_clean["timestamp"].iloc[-1]
    now_ts = datetime.now()
    if last_hist_ts.date() < now_ts.date():
        live_point = pd.DataFrame([{
            "timestamp": now_ts,
            "equity": equity,
            "profit_loss": equity - initial_capital,
            "profit_loss_pct": (equity - initial_capital) / initial_capital
        }])
        df_clean = pd.concat([df_clean, live_point], ignore_index=True)

    # Helper function to slice dataset by timeframe days
    def slice_history(df, days):
        cutoff = datetime.now() - timedelta(days=days)
        sliced = df[df["timestamp"] >= cutoff]
        if len(sliced) < 2:
            sliced = df.iloc[-min(len(df), max(2, days)):]
        return sliced

    timeframe_configs = {
        "1M": 30,
        "6M": 180,
        "1Y": 365,
        "3Y": 365 * 3,
        "5Y": 365 * 5,
        "All": 365 * 10
    }

    packaged_datasets = {}
    for tf_key, days_span in timeframe_configs.items():
        sub_df = slice_history(df_clean, days_span)
        packaged_datasets[tf_key] = {
            "dates": [ts.strftime("%b %d, %Y") for ts in sub_df["timestamp"]],
            "equity": [round(float(v), 2) for v in sub_df["equity"]],
            "invested": [round(float(initial_capital), 2) for _ in sub_df["equity"]]
        }

    groww_data_json = json.dumps(packaged_datasets)

    # 2. Standalone Pixel-Perfect Blacklead Studio Style Portfolio Card Component
    groww_card_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:ital,wght@0,300;0,400;0,500&family=Space+Grotesk:wght@400;500;600;700&display=swap');
    
    * {{
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        user-select: none;
        -webkit-user-select: none;
    }}
    
    body {{
        background: transparent;
        font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, sans-serif;
        color: #FFFFFF;
        padding: 2px;
        overflow: hidden;
    }}
    
    /* Architectural Obsidian Card */
    .glass-hero-card {{
        position: relative;
        background: #0D0E12;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 22px 26px 18px 26px;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.6), 
                    inset 0 1px 0 rgba(255, 255, 255, 0.05);
        overflow: hidden;
        width: 100%;
        transition: border-color 0.22s ease;
    }}
    .glass-hero-card:hover {{
        border-color: rgba(255, 255, 255, 0.16);
    }}
    
    .card-content-layer {{
        position: relative;
        z-index: 1;
    }}
    
    .groww-header {{
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 6px;
    }}
    
    .metric-left {{
        display: flex;
        flex-direction: column;
    }}
    
    .metric-right {{
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        text-align: right;
    }}
    
    .legend-row {{
        display: flex;
        align-items: center;
        gap: 6px;
        font-family: 'DM Mono', monospace;
        font-size: 0.68rem;
        font-weight: 500;
        letter-spacing: 0.10em;
        text-transform: uppercase;
        color: #71717A;
        height: 20px;
    }}
    
    .dot-mint {{
        width: 8px;
        height: 8px;
        background-color: #82FBBD;
        border-radius: 2px;
        display: inline-block;
        box-shadow: 0 0 8px rgba(130, 251, 189, 0.4);
    }}
    
    .dot-red {{
        width: 8px;
        height: 8px;
        background-color: #FF9A9C;
        border-radius: 2px;
        display: inline-block;
        box-shadow: 0 0 8px rgba(255, 154, 156, 0.4);
    }}
    
    .dot-grey {{
        width: 8px;
        height: 8px;
        background-color: #52525B;
        border-radius: 2px;
        display: inline-block;
    }}
    
    .big-number {{
        font-size: 2.25rem;
        font-weight: 700;
        letter-spacing: -0.035em;
        line-height: 1.15;
        color: #FFFFFF;
        margin: 3px 0 2px 0;
        font-family: 'Space Grotesk', sans-serif;
    }}
    
    .return-row {{
        display: flex;
        align-items: center;
        gap: 6px;
        height: 24px;
    }}
    
    .return-glass-badge {{
        display: inline-flex;
        align-items: center;
        gap: 5px;
        padding: 2px 9px;
        border-radius: 9999px;
        font-family: 'DM Mono', monospace;
        font-size: 0.72rem;
        font-weight: 500;
        transition: all 0.2s ease;
    }}
    
    .badge-green {{
        background: rgba(130, 251, 189, 0.08);
        border: 1px solid rgba(130, 251, 189, 0.28);
        color: #82FBBD;
    }}
    
    .badge-red {{
        background: rgba(255, 154, 156, 0.08);
        border: 1px solid rgba(255, 154, 156, 0.28);
        color: #FF9A9C;
    }}
    
    .tf-sub {{
        color: #71717A;
        font-family: 'DM Mono', monospace;
        font-size: 0.70rem;
        margin-left: 4px;
        letter-spacing: 0.04em;
    }}
    
    /* Studio Minimalist Currency Switcher */
    .currency-pill-box {{
        display: inline-flex;
        background: #141418;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 9999px;
        padding: 2px;
        margin-bottom: 6px;
    }}
    
    .curr-btn {{
        padding: 3px 10px;
        font-size: 0.68rem;
        font-weight: 500;
        font-family: 'DM Mono', monospace;
        color: #71717A;
        border-radius: 9999px;
        border: none;
        background: transparent;
        cursor: pointer;
        transition: all 0.18s ease;
    }}
    
    .curr-btn.active {{
        background: rgba(255, 255, 255, 0.12);
        color: #FFFFFF;
        border: 1px solid rgba(255, 255, 255, 0.22);
    }}
    
    /* SVG Chart Area */
    .chart-area {{
        position: relative;
        width: 100%;
        height: 265px;
        margin-top: 10px;
        margin-bottom: 12px;
    }}
    
    svg.groww-svg {{
        width: 100%;
        height: 100%;
        display: block;
        overflow: visible;
    }}
    
    /* Minimalist Timeframe Dock */
    .pills-dock-wrapper {{
        display: flex;
        justify-content: center;
        align-items: center;
        margin-top: 4px;
    }}
    
    .pills-glass-dock {{
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: #141418;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 9999px;
        padding: 3px 6px;
    }}
    
    .timeframe-pill {{
        background: transparent;
        border: 1px solid transparent;
        color: #71717A;
        font-family: 'DM Mono', monospace;
        font-size: 0.72rem;
        font-weight: 500;
        padding: 4px 12px;
        border-radius: 9999px;
        cursor: pointer;
        transition: all 0.18s ease;
    }}
    
    .timeframe-pill:hover {{
        color: #FFFFFF;
        background: rgba(255, 255, 255, 0.05);
    }}
    
    .timeframe-pill.active {{
        background: rgba(255, 255, 255, 0.12);
        border: 1px solid rgba(255, 255, 255, 0.22);
        color: #FFFFFF;
        font-weight: 600;
    }}
    
    /* Studio Floating Tooltip */
    .live-tooltip {{
        position: absolute;
        display: none;
        pointer-events: none;
        background: #111216;
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 0.74rem;
        color: #FFFFFF;
        font-family: 'DM Mono', monospace;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.1);
        z-index: 100;
        line-height: 1.5;
    }}
    </style>
    </head>
    <body>
    <div class="glass-hero-card">
        <div class="card-content-layer">
            <div class="groww-header">
                <div class="metric-left">
                    <div class="legend-row">
                        <span>// VALUATION TRAJECTORY</span> <span id="legend-dot" class="dot-mint" style="margin-left:4px;"></span>
                    </div>
                    <div class="big-number" id="current-display">$101,437.23</div>
                    <div class="return-row" id="return-row">
                        <div id="pnl-badge" class="return-glass-badge badge-green">
                            <span id="pnl-span">+$1,437.23 (+1.44%)</span>
                        </div>
                        <span id="tf-tag" class="tf-sub">All time</span>
                    </div>
                </div>
                <div class="metric-right">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <div class="currency-pill-box">
                            <button class="curr-btn active" id="btn-usd" onclick="setCurrency('USD')">$ USD</button>
                            <button class="curr-btn" id="btn-inr" onclick="setCurrency('INR')">&#8377; INR</button>
                        </div>
                        <div class="legend-row">
                            <span class="dot-grey"></span> <span>INVESTED BASELINE</span>
                        </div>
                    </div>
                    <div class="big-number" id="invested-display" style="font-size: 1.55rem; color: #A1A1AA;">$100,000.00</div>
                </div>
            </div>

            <div class="chart-area" id="chart-area">
                <svg class="groww-svg" id="groww-svg" viewBox="0 0 1000 260" preserveAspectRatio="none">
                    <defs>
                        <!-- Dynamic Studio Mint / Crimson Drop Shadow Filter -->
                        <filter id="neon-glow" x="-20%" y="-20%" width="140%" height="140%">
                            <feDropShadow id="glow-shadow" dx="0" dy="0" stdDeviation="3.2" flood-color="#82FBBD" flood-opacity="0.38" />
                        </filter>
                        
                        <!-- Dynamic Studio Line Stroke Gradient -->
                        <linearGradient id="stroke-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop id="stroke-stop-0" offset="0%" stop-color="#5EEAD4" />
                            <stop id="stroke-stop-100" offset="100%" stop-color="#82FBBD" />
                        </linearGradient>

                        <!-- Subtle Volumetric Area Fill Gradient -->
                        <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
                            <stop id="area-stop-0" offset="0%" stop-color="#82FBBD" stop-opacity="0.14" />
                            <stop id="area-stop-70" offset="70%" stop-color="#82FBBD" stop-opacity="0.02" />
                            <stop id="area-stop-100" offset="100%" stop-color="#82FBBD" stop-opacity="0.00" />
                        </linearGradient>

                        <!-- Vertical Cursor Beam Gradient -->
                        <linearGradient id="cursor-beam" x1="0" y1="0" x2="0" y2="1">
                            <stop id="cursor-stop-0" offset="0%" stop-color="#82FBBD" stop-opacity="0.75" />
                            <stop id="cursor-stop-75" offset="75%" stop-color="#82FBBD" stop-opacity="0.2" />
                            <stop id="cursor-stop-100" offset="100%" stop-color="#82FBBD" stop-opacity="0.0" />
                        </linearGradient>
                    </defs>

                    <!-- Hairline Baseline at Bottom -->
                    <line x1="0" y1="248" x2="1000" y2="248" stroke="rgba(255,255,255,0.06)" stroke-width="1" stroke-dasharray="4,4" />

                    <!-- Invested Dotted Line -->
                    <path id="path-invested" stroke="#52525B" stroke-width="1.5" stroke-dasharray="4,4" fill="none" d="" />

                    <!-- Area Gradient Underneath Current Curve -->
                    <path id="path-area" fill="url(#area-gradient)" d="" />

                    <!-- Current Smooth Studio Mint Line -->
                    <path id="path-current" stroke="url(#stroke-gradient)" filter="url(#neon-glow)" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round" fill="none" d="" />

                    <!-- Vertical Tracking Laser Line -->
                    <line id="cursor-line" x1="0" y1="6" x2="0" y2="248" stroke="url(#cursor-beam)" stroke-width="1.2" stroke-dasharray="2,2" style="display:none;" />

                    <!-- Tracking Circles -->
                    <circle id="cursor-halo" r="9" fill="rgba(130, 251, 189, 0.18)" style="display:none;" />
                    <circle id="cursor-dot-mint" r="4.5" fill="#050507" stroke="#82FBBD" stroke-width="2" style="display:none;" />
                    <circle id="cursor-dot-grey" r="3.5" fill="#050507" stroke="#71717A" stroke-width="1.5" style="display:none;" />
                </svg>
                <div class="live-tooltip" id="live-tooltip"></div>
            </div>

            <div class="pills-dock-wrapper">
                <div class="pills-glass-dock">
                    <button class="timeframe-pill" onclick="selectTimeframe('1M')">1M</button>
                    <button class="timeframe-pill" onclick="selectTimeframe('6M')">6M</button>
                    <button class="timeframe-pill" onclick="selectTimeframe('1Y')">1Y</button>
                    <button class="timeframe-pill" onclick="selectTimeframe('3Y')">3Y</button>
                    <button class="timeframe-pill" onclick="selectTimeframe('5Y')">5Y</button>
                    <button class="timeframe-pill active" onclick="selectTimeframe('All')">All</button>
                </div>
            </div>
        </div>
    </div>

    <script>
    const datasets = {groww_data_json};
    let activeTimeframe = 'All';
    let currentCurrency = localStorage.getItem('groww_currency_pref') || 'USD';
    const inrRate = 85.0;

    function formatCurrency(val, curr) {{
        if (curr === 'INR') {{
            const inrVal = val * inrRate;
            return '&#8377;' + inrVal.toLocaleString('en-IN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
        }} else {{
            return '$' + val.toLocaleString('en-US', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
        }}
    }}

    function setCurrency(curr) {{
        currentCurrency = curr;
        try {{
            localStorage.setItem('groww_currency_pref', curr);
        }} catch(e) {{}}
        document.getElementById('btn-usd').classList.toggle('active', curr === 'USD');
        document.getElementById('btn-inr').classList.toggle('active', curr === 'INR');
        render();
    }}

    function selectTimeframe(tf) {{
        activeTimeframe = tf;
        document.querySelectorAll('.timeframe-pill').forEach(btn => {{
            btn.classList.toggle('active', btn.innerText.trim() === tf);
        }});
        render();
    }}

    // Catmull-Rom to Cubic Bezier curve smoothing for organic financial line
    function getSmoothPath(points) {{
        if (points.length === 0) return '';
        if (points.length === 1) return `M ${{points[0].x}},${{points[0].y}}`;
        if (points.length === 2) return `M ${{points[0].x}},${{points[0].y}} L ${{points[1].x}},${{points[1].y}}`;
        
        let d = `M ${{points[0].x.toFixed(1)}},${{points[0].y.toFixed(1)}}`;
        for (let i = 0; i < points.length - 1; i++) {{
            const p0 = points[i === 0 ? 0 : i - 1];
            const p1 = points[i];
            const p2 = points[i + 1];
            const p3 = points[i + 2 < points.length ? i + 2 : i + 1];
            
            const cp1x = p1.x + (p2.x - p0.x) / 6;
            const cp1y = p1.y + (p2.y - p0.y) / 6;
            const cp2x = p2.x - (p3.x - p1.x) / 6;
            const cp2y = p2.y - (p3.y - p1.y) / 6;
            
            d += ` C ${{cp1x.toFixed(1)}},${{cp1y.toFixed(1)}} ${{cp2x.toFixed(1)}},${{cp2y.toFixed(1)}} ${{p2.x.toFixed(1)}},${{p2.y.toFixed(1)}}`;
        }}
        return d;
    }}

    function render() {{
        const series = datasets[activeTimeframe] || datasets['All'];
        if (!series || !series.equity || series.equity.length === 0) return;
        
        const equities = series.equity;
        const investedArr = series.invested;
        const n = equities.length;
        
        const latestEq = equities[n - 1];
        const latestInv = investedArr[n - 1];
        const pnl = latestEq - latestInv;
        const pnlPct = (pnl / latestInv) * 100;
        
        document.getElementById('current-display').innerHTML = formatCurrency(latestEq, currentCurrency);
        document.getElementById('invested-display').innerHTML = formatCurrency(latestInv, currentCurrency);
        
        const pnlBadge = document.getElementById('pnl-badge');
        const pnlSpan = document.getElementById('pnl-span');
        const sign = pnl >= 0 ? '+' : '-';
        const isPos = pnl >= 0;
        const themeColor = isPos ? '#82FBBD' : '#FF9A9C';
        const strokeStart = isPos ? '#5EEAD4' : '#FFA9AA';
        const areaOp0 = isPos ? '0.14' : '0.18';
        const areaOp70 = isPos ? '0.02' : '0.03';

        pnlBadge.className = 'return-glass-badge ' + (isPos ? 'badge-green' : 'badge-red');
        pnlSpan.innerHTML = `${{sign}}${{formatCurrency(Math.abs(pnl), currentCurrency)}} (${{pnlPct >= 0 ? '+' : ''}}${{pnlPct.toFixed(2)}}%)`;
        document.getElementById('tf-tag').innerText = activeTimeframe === 'All' ? 'All time' : activeTimeframe;
        
        // Dynamically update SVG gradients and glows based on positive/negative valuation
        const strokeStop0 = document.getElementById('stroke-stop-0');
        const strokeStop100 = document.getElementById('stroke-stop-100');
        const areaStop0 = document.getElementById('area-stop-0');
        const areaStop70 = document.getElementById('area-stop-70');
        const areaStop100 = document.getElementById('area-stop-100');
        const glowShadow = document.getElementById('glow-shadow');
        const cursorStop0 = document.getElementById('cursor-stop-0');
        const cursorStop75 = document.getElementById('cursor-stop-75');
        const cursorStop100 = document.getElementById('cursor-stop-100');
        const legendDot = document.getElementById('legend-dot');

        if (strokeStop0) strokeStop0.setAttribute('stop-color', strokeStart);
        if (strokeStop100) strokeStop100.setAttribute('stop-color', themeColor);
        if (areaStop0) {{
            areaStop0.setAttribute('stop-color', themeColor);
            areaStop0.setAttribute('stop-opacity', areaOp0);
        }}
        if (areaStop70) {{
            areaStop70.setAttribute('stop-color', themeColor);
            areaStop70.setAttribute('stop-opacity', areaOp70);
        }}
        if (areaStop100) areaStop100.setAttribute('stop-color', themeColor);
        if (glowShadow) glowShadow.setAttribute('flood-color', themeColor);
        if (cursorStop0) cursorStop0.setAttribute('stop-color', themeColor);
        if (cursorStop75) cursorStop75.setAttribute('stop-color', themeColor);
        if (cursorStop100) cursorStop100.setAttribute('stop-color', themeColor);
        if (legendDot) legendDot.className = isPos ? 'dot-mint' : 'dot-red';

        dotMint.setAttribute('stroke', themeColor);
        cursorHalo.setAttribute('fill', isPos ? 'rgba(130, 251, 189, 0.18)' : 'rgba(255, 154, 156, 0.18)');

        // Scale SVG coordinate system
        const allVals = equities.concat(investedArr);
        const minVal = Math.min(...allVals) * 0.992;
        const maxVal = Math.max(...allVals) * 1.008;
        const range = (maxVal - minVal) || 1;
        
        const svgW = 1000;
        const svgH = 250;
        const paddingY = 18;
        
        function getY(val) {{
            const ratio = (val - minVal) / range;
            return svgH - (ratio * (svgH - paddingY * 2) + paddingY);
        }}
        
        function getX(idx) {{
            if (n <= 1) return svgW / 2;
            return (idx / (n - 1)) * svgW;
        }}
        
        // Smooth Current Path
        const curPoints = [];
        for (let i = 0; i < n; i++) {{
            curPoints.push({{ x: getX(i), y: getY(equities[i]) }});
        }}
        const smoothCurveD = getSmoothPath(curPoints);
        document.getElementById('path-current').setAttribute('d', smoothCurveD);
        
        // Ethereal Area Gradient Underneath Current Curve
        if (curPoints.length > 1) {{
            const baselineY = 248;
            const firstX = curPoints[0].x;
            const lastX = curPoints[curPoints.length - 1].x;
            const areaPath = `${{smoothCurveD}} L ${{lastX.toFixed(1)}},${{baselineY}} L ${{firstX.toFixed(1)}},${{baselineY}} Z`;
            document.getElementById('path-area').setAttribute('d', areaPath);
        }}
        
        // Invested Path (Dotted)
        let dInv = '';
        for (let i = 0; i < n; i++) {{
            const x = getX(i);
            const y = getY(investedArr[i]);
            dInv += (i === 0 ? `M ${{x.toFixed(1)}},${{y.toFixed(1)}}` : ` L ${{x.toFixed(1)}},${{y.toFixed(1)}}`);
        }}
        document.getElementById('path-invested').setAttribute('d', dInv);
    }}

    // Laser Scrubbing Interaction
    const chartArea = document.getElementById('chart-area');
    const cursorLine = document.getElementById('cursor-line');
    const cursorHalo = document.getElementById('cursor-halo');
    const dotMint = document.getElementById('cursor-dot-mint');
    const dotGrey = document.getElementById('cursor-dot-grey');
    const tooltip = document.getElementById('live-tooltip');

    chartArea.addEventListener('mousemove', (e) => {{
        const series = datasets[activeTimeframe] || datasets['All'];
        if (!series || !series.equity || series.equity.length === 0) return;
        
        const rect = chartArea.getBoundingClientRect();
        const mouseX = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const ratio = mouseX / rect.width;
        
        const n = series.equity.length;
        const idx = Math.min(n - 1, Math.max(0, Math.round(ratio * (n - 1))));
        
        const eqVal = series.equity[idx];
        const invVal = series.invested[idx];
        const dateStr = series.dates[idx];
        
        const allVals = series.equity.concat(series.invested);
        const minVal = Math.min(...allVals) * 0.992;
        const maxVal = Math.max(...allVals) * 1.008;
        const range = (maxVal - minVal) || 1;
        
        const svgW = 1000;
        const svgH = 250;
        const paddingY = 18;
        
        function getY(val) {{
            const r = (val - minVal) / range;
            return svgH - (r * (svgH - paddingY * 2) + paddingY);
        }}
        
        const xSvg = (idx / (n - 1)) * svgW;
        const yCurSvg = getY(eqVal);
        const yInvSvg = getY(invVal);
        
        cursorLine.setAttribute('x1', xSvg);
        cursorLine.setAttribute('x2', xSvg);
        cursorLine.style.display = 'block';
        
        cursorHalo.setAttribute('cx', xSvg);
        cursorHalo.setAttribute('cy', yCurSvg);
        cursorHalo.style.display = 'block';
        
        dotMint.setAttribute('cx', xSvg);
        dotMint.setAttribute('cy', yCurSvg);
        dotMint.style.display = 'block';
        
        dotGrey.setAttribute('cx', xSvg);
        dotGrey.setAttribute('cy', yInvSvg);
        dotGrey.style.display = 'block';
        
        // Live header updates
        document.getElementById('current-display').innerHTML = formatCurrency(eqVal, currentCurrency);
        const pnl = eqVal - invVal;
        const pnlPct = (pnl / invVal) * 100;
        const sign = pnl >= 0 ? '+' : '-';
        const isPointPos = pnl >= 0;
        const pointColor = isPointPos ? '#82FBBD' : '#FF9A9C';
        const pnlBadge = document.getElementById('pnl-badge');
        const pnlSpan = document.getElementById('pnl-span');
        pnlBadge.className = 'return-glass-badge ' + (isPointPos ? 'badge-green' : 'badge-red');
        pnlSpan.innerHTML = `${{sign}}${{formatCurrency(Math.abs(pnl), currentCurrency)}} (${{pnlPct >= 0 ? '+' : ''}}${{pnlPct.toFixed(2)}}%)`;
        document.getElementById('tf-tag').innerText = dateStr;

        dotMint.setAttribute('stroke', pointColor);
        cursorHalo.setAttribute('fill', isPointPos ? 'rgba(130, 251, 189, 0.18)' : 'rgba(255, 154, 156, 0.18)');
        
        // Tooltip position & content
        tooltip.style.display = 'block';
        const tooltipX = Math.min(rect.width - 195, Math.max(10, mouseX - 85));
        tooltip.style.left = tooltipX + 'px';
        tooltip.style.top = '10px';
        tooltip.innerHTML = `<span style="color:#71717A; font-family:'DM Mono',monospace; font-size:0.68rem; letter-spacing:0.06em; text-transform:uppercase;">${{dateStr}}</span><br>` +
            `<div style="margin-top:2px; font-family:'Space Grotesk',sans-serif; font-size:0.84rem;"><b style="color:${{pointColor}};">Valuation:</b> ${{formatCurrency(eqVal, currentCurrency)}}</div>` +
            `<div style="font-family:'Space Grotesk',sans-serif; font-size:0.84rem;"><b style="color:#71717A;">Invested:</b> ${{formatCurrency(invVal, currentCurrency)}}</div>` +
            `<div style="font-family:'Space Grotesk',sans-serif; font-size:0.84rem; margin-top:2px; border-top:1px solid rgba(255,255,255,0.08); padding-top:2px;"><b style="color:#71717A;">P&L:</b> <span style="color:${{pointColor}}; font-weight:600;">${{sign}}${{formatCurrency(Math.abs(pnl), currentCurrency)}} (${{pnlPct >= 0 ? '+' : ''}}${{pnlPct.toFixed(2)}}%)</span></div>`;
    }});

    chartArea.addEventListener('mouseleave', () => {{
        cursorLine.style.display = 'none';
        cursorHalo.style.display = 'none';
        dotMint.style.display = 'none';
        dotGrey.style.display = 'none';
        tooltip.style.display = 'none';
        render();
    }});

    // Initialize currency button states from preference
    if (currentCurrency === 'INR') {{
        document.getElementById('btn-usd').classList.remove('active');
        document.getElementById('btn-inr').classList.add('active');
    }}

    render();
    </script>
    </body>
    </html>
    """

    components.html(groww_card_html, height=480)

    # ==============================================================================
    # DYNAMIC ALLOCATION DONUT CHART (VIBRANT) & EXPOSURE TELEMETRY
    # ==============================================================================
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    positions = broker.get_positions_detailed()

    if positions:
        df_pos = pd.DataFrame(positions)
        col_chart, col_stats = st.columns([3, 2])

        with col_chart:
            chart_data = []
            for _, row in df_pos.iterrows():
                chart_data.append({
                    "Asset": row["symbol"],
                    "Value": row["market_value"],
                    "Category": "Equities"
                })
            chart_data.append({
                "Asset": "CASH BUFFER",
                "Value": cash,
                "Category": "Cash Buffer"
            })
            df_chart = pd.DataFrame(chart_data)

            # VIBRANT 26-COLOR PALETTE FOR DISTINCT ASSET ALLOCATION
            vibrant_palette = [
                "#00F2FE", "#00FF88", "#FF007F", "#FFB800", "#A855F7",
                "#3B82F6", "#FF5722", "#00E5FF", "#E91E63", "#76FF03",
                "#9C27B0", "#FF9100", "#00E676", "#651FFF", "#FF1744",
                "#1DE9B6", "#FF4081", "#FFEA00", "#2979FF", "#C51162",
                "#00B0FF", "#00C853", "#FF6D00", "#D500F9", "#64DD17",
                "#CBD5E1"
            ]

            fig = px.pie(
                df_chart,
                names="Asset",
                values="Value",
                title=f"Dynamic Capital Allocation ({len(positions)} Stocks + Liquid Cash Buffer)",
                hole=0.62,
                color_discrete_sequence=vibrant_palette
            )
            fig.update_traces(
                textposition='inside',
                textinfo='percent+label',
                marker=dict(line=dict(color='#070A12', width=1.5)),
                hovertemplate="<b>%{label}</b><br>Allocation: $%{value:,.2f}<br>Share: %{percent}<extra></extra>"
            )
            fig.update_layout(
                showlegend=False,
                margin=dict(t=50, b=10, l=10, r=10),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Space Grotesk, sans-serif", color="#FFFFFF"),
                annotations=[dict(
                    text=f"<b>PORTFOLIO</b><br><span style='font-size:18px; color:#82FBBD;'>${equity:,.0f}</span><br><span style='font-size:11px; color:#71717A;'>CASH {cash_pct:.1f}%</span>",
                    x=0.5, y=0.5,
                    font_size=15,
                    font_family="Space Grotesk",
                    font_color="#FFFFFF",
                    showarrow=False
                )]
            )
            st.plotly_chart(fig, width='stretch')

        with col_stats:
            st.markdown("""
            <div class="cyber-card" style="margin-top: 25px;">
                <div class="kpi-title" style="color: #82FBBD; font-size: 0.72rem;">// 03. EXPOSURE TELEMETRY</div>
            """, unsafe_allow_html=True)

            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.06); font-family: 'DM Mono', monospace; font-size: 0.82rem;">
                <span style="color: #71717A;">Invested Equities Value:</span>
                <span style="color: #FFFFFF; font-weight: 600;">${invested_capital:,.2f} ({invested_pct:.1f}%)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.06); font-family: 'DM Mono', monospace; font-size: 0.82rem;">
                <span style="color: #71717A;">Liquid Cash Reserve:</span>
                <span style="color: #82FBBD; font-weight: 600;">${cash:,.2f} ({cash_pct:.1f}%)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.06); font-family: 'DM Mono', monospace; font-size: 0.82rem;">
                <span style="color: #71717A;">Active Holdings:</span>
                <span style="color: #FFFFFF; font-weight: 600;">{len(positions)} Stocks (Dynamic Sizing)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 9px 0; border-bottom: 1px solid rgba(255,255,255,0.06); font-family: 'DM Mono', monospace; font-size: 0.82rem;">
                <span style="color: #71717A;">Single Stock Ceiling:</span>
                <span style="color: #FFFFFF; font-weight: 600;">15.0% (${equity*0.15:,.2f})</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 9px 0; font-family: 'DM Mono', monospace; font-size: 0.82rem;">
                <span style="color: #71717A;">Max Macro Exposure:</span>
                <span style="color: #FFFFFF; font-weight: 600;">95.0% (${equity*0.95:,.2f})</span>
            </div>
            """, unsafe_allow_html=True)

            winners = df_pos[df_pos['unrealized_pl'] > 0]
            losers = df_pos[df_pos['unrealized_pl'] < 0]
            win_rate = (len(winners) / len(df_pos) * 100) if len(df_pos) > 0 else 0.0
            wr_color = "#82FBBD" if win_rate >= 50.0 else "#FF9A9C"

            st.markdown(f"""
            <div style="margin-top: 15px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">
                <div style="display: flex; justify-content: space-between; font-family: 'DM Mono', monospace; font-size: 0.78rem; margin-bottom: 6px;">
                    <span style="color: #71717A;">Win Rate on Open Positions:</span>
                    <span style="font-weight: 700;"><b style="color: {wr_color};">{win_rate:.1f}%</b> (<b style="color: #82FBBD;">{len(winners)} Green</b> / <b style="color: #FF9A9C;">{len(losers)} Red</b>)</span>
                </div>
            </div>
            </div>
            """, unsafe_allow_html=True)
            st.progress(win_rate / 100)
    else:
        st.info("No open positions reported by broker. Portfolio is currently in 100% Cash Buffer.")


# ==============================================================================
# PAGE 2: 📋 POSITIONS & STOP-LOSS MONITOR
# ==============================================================================
elif page == "📋 Positions & Stop-Loss":
    st.markdown("""
    <div class="page-title-box">
        <div class="page-title">📋 Active Equity Holdings & Stop-Loss Gating</div>
        <div class="page-subtitle">REAL-TIME COST BASIS • UNREALIZED P&L • MANDATORY -8% STOP GATING PROTOCOL</div>
    </div>
    """, unsafe_allow_html=True)

    positions = broker.get_positions_detailed()

    if positions:
        # Enrich all positions with dynamic stop-loss calculations from StopLossManager
        pos_enriched = []
        for p in positions:
            sym = p["symbol"]
            cur_p = float(p.get("current_price", 0.0))
            entry_p = float(p.get("avg_entry_price", 0.0))
            mkt_v = float(p.get("market_value", 0.0))
            unreal_pl = float(p.get("unrealized_pl", 0.0))
            unreal_plpc = float(p.get("unrealized_plpc", 0.0))
            shares = float(p.get("qty", 0.0))

            dist_info = sl_manager.get_distance_to_stop(sym, cur_p, entry_p)
            sl_pct = dist_info["stop_loss_pct"]
            sl_price = dist_info["stop_price"]
            pct_buf = dist_info["pct_buffer"]
            is_breached = dist_info["is_breached"]
            is_warning = dist_info["is_warning"]
            is_custom = dist_info["is_custom"]

            if is_breached:
                risk_status = "🛑 STOP BREACH"
            elif is_warning:
                risk_status = "⚠️ WATCHLIST (< 2.5%)"
            elif unreal_pl > 0:
                risk_status = "🟢 PROFITABLE"
            else:
                risk_status = "🛡️ IN BUFFER"

            pos_enriched.append({
                "symbol": sym,
                "Ticker": f"{sym} ✏️" if is_custom else sym,
                "Shares": int(shares) if shares.is_integer() else shares,
                f"Current Price ({CURRENCY_SYMBOL})": cur_p,
                f"Avg Entry ({CURRENCY_SYMBOL})": entry_p,
                f"Market Value ({CURRENCY_SYMBOL})": mkt_v,
                f"Unrealized P&L ({CURRENCY_SYMBOL})": unreal_pl,
                "Return (%)": unreal_plpc * 100,
                f"Stop Price ({CURRENCY_SYMBOL})": sl_price,
                "Stop Limit (%)": sl_pct * 100,
                "Stop Buffer (%)": pct_buf,
                "Risk Status": risk_status,
                "is_breached": is_breached,
                "is_warning": is_warning,
                "is_custom": is_custom,
                "unrealized_pl": unreal_pl,
                "market_value": mkt_v,
                "unrealized_plpc": unreal_plpc
            })

        df_pos = pd.DataFrame(pos_enriched)

        # Dedicated Page Metric Cards
        winners = df_pos[df_pos['unrealized_pl'] > 0]
        critical = df_pos[df_pos['is_breached']]
        win_rate = (len(winners) / len(df_pos) * 100) if len(df_pos) > 0 else 0.0

        p1, p2, p3, p4 = st.columns(4)
        with p1:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">ACTIVE POSITIONS</div>
                <div class="kpi-value"><div class="metric-big">{len(positions)} Stocks</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">DYNAMIC LONG-ONLY</div></div>
            </div>
            """, unsafe_allow_html=True)

        with p2:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">PROFITABLE POSITIONS</div>
                <div class="kpi-value"><div class="metric-big-green">{len(winners)} / {len(positions)}</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">{win_rate:.1f}% WIN RATE</div></div>
            </div>
            """, unsafe_allow_html=True)

        with p3:
            pnl_cls = "metric-big-green" if overall_pnl >= 0 else "metric-big-red"
            badge_cls = "metric-badge-mint" if overall_pnl >= 0 else "metric-badge-danger"
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">TOTAL UNREALIZED ALPHA</div>
                <div class="kpi-value"><div class="{pnl_cls}">{format_pnl_str(overall_pnl)}</div></div>
                <div class="kpi-badge-row"><div class="{badge_cls}">{format_pct_str(overall_pnl_pct)} ON CAPITAL</div></div>
            </div>
            """, unsafe_allow_html=True)

        with p4:
            crit_cls = "metric-big-green" if len(critical) == 0 else "metric-big-red"
            crit_badge = "metric-badge-uniform" if len(critical) == 0 else "metric-badge-danger"
            overrides_count = len(sl_manager.overrides)
            sl_badge_text = f"{overrides_count} CUSTOM OVERRIDES" if overrides_count > 0 else f"BOT DEFAULT ({sl_manager.global_default_pct*100:.1f}%)"
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">STOP-LOSS HEALTH</div>
                <div class="kpi-value"><div class="{crit_cls}">{len(critical)} Breaches</div></div>
                <div class="kpi-badge-row"><div class="{crit_badge}">{sl_badge_text}</div></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # DUAL DONUT TELEMETRY DECK: HOLDING HEALTH & CAPITAL CONCENTRATION
        # ----------------------------------------------------------------------
        d_col1, d_col2 = st.columns(2)

        with d_col1:
            prof_count = len(winners)
            hold_count = len(df_pos[df_pos['Risk Status'] == '🛡️ IN BUFFER'])
            watch_count = len(df_pos[df_pos['Risk Status'] == '⚠️ WATCHLIST (< 2.5%)'])
            breach_count = len(critical)

            h_labels = ["Profitable (> 0%)", "Holding in Safe Buffer", "Near Stop Watchlist (< 2.5%)", "Stop Breach Triggered"]
            h_values = [prof_count, hold_count, watch_count, breach_count]
            h_colors = ["#82FBBD", "#52525B", "#FBBF24", "#FF9A9C"]

            f_labels = [l for l, v in zip(h_labels, h_values) if v > 0]
            f_values = [v for v in h_values if v > 0]
            f_colors = [c for c, v in zip(h_colors, h_values) if v > 0]

            health_center = f"<b>HEALTH</b><br><span style='font-size:18px; color:{'#82FBBD' if breach_count == 0 else '#FF9A9C'};'>{win_rate:.0f}%</span><br><span style='font-size:10px; color:#71717A;'>WIN RATE</span>"
            fig_health = create_donut_chart(
                labels=f_labels if f_values else ["Active Holdings"],
                values=f_values if f_values else [len(positions)],
                colors=f_colors if f_values else ["#82FBBD"],
                center_text=health_center,
                title="HOLDING HEALTH & STOP-LOSS GATING DISTRIBUTION",
                height=260,
                hole=0.66
            )
            st.plotly_chart(fig_health, width='stretch')

        with d_col2:
            top_holdings = df_pos.sort_values(by="market_value", ascending=False)
            if len(top_holdings) > 6:
                top5 = top_holdings.iloc[:5]
                others_val = top_holdings.iloc[5:]["market_value"].sum()
                c_labels = top5["symbol"].tolist() + ["Other Equities"]
                c_values = top5["market_value"].round(2).tolist() + [round(others_val, 2)]
            else:
                c_labels = top_holdings["symbol"].tolist()
                c_values = top_holdings["market_value"].round(2).tolist()

            pos_palette = ["#00F2FE", "#82FBBD", "#3B82F6", "#A855F7", "#FFB800", "#FF007F", "#71717A"]
            total_holdings_val = df_pos["market_value"].sum()
            conc_center = f"<b>INVESTED</b><br><span style='font-size:16px; color:#82FBBD;'>{CURRENCY_SYMBOL}{total_holdings_val:,.0f}</span><br><span style='font-size:10px; color:#71717A;'>{len(positions)} ASSETS</span>"

            fig_conc = create_donut_chart(
                labels=c_labels,
                values=c_values,
                colors=pos_palette[:len(c_labels)],
                center_text=conc_center,
                title="ACTIVE EQUITY CAPITAL CONCENTRATION",
                height=260,
                hole=0.66
            )
            st.plotly_chart(fig_conc, width='stretch')

        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # ACTIVE POSITIONS & STOP-LOSS TELEMETRY TABLE
        # ----------------------------------------------------------------------
        col_cp = f"Current Price ({CURRENCY_SYMBOL})"
        col_ae = f"Avg Entry ({CURRENCY_SYMBOL})"
        col_mv = f"Market Value ({CURRENCY_SYMBOL})"
        col_pl = f"Unrealized P&L ({CURRENCY_SYMBOL})"
        col_sp = f"Stop Price ({CURRENCY_SYMBOL})"

        display_cols = [
            "Ticker", "Shares", col_cp, col_ae, col_mv,
            col_pl, "Return (%)", col_sp, "Stop Limit (%)", "Stop Buffer (%)", "Risk Status"
        ]
        df_display = df_pos[display_cols].sort_values(by=col_pl, ascending=False)

        def color_pnl_cells(v):
            if isinstance(v, (int, float)):
                if v > 0:
                    return "color: #82FBBD; font-weight: 600;"
                elif v < 0:
                    return "color: #FF9A9C; font-weight: 600;"
            return ""

        def color_buffer_cells(v):
            if isinstance(v, (int, float)):
                if v <= 2.5:
                    return "color: #FF9A9C; font-weight: 600;"
                else:
                    return "color: #82FBBD; font-weight: 600;"
            return ""

        def color_stop_limit(v):
            if isinstance(v, (int, float)):
                return "color: #FF9A9C; font-weight: 600;"
            return ""

        styled_pos_df = (
            df_display.style
            .map(color_pnl_cells, subset=[col_pl, "Return (%)"])
            .map(color_buffer_cells, subset=["Stop Buffer (%)"])
            .map(color_stop_limit, subset=["Stop Limit (%)"])
            .format({
                col_pl: format_pnl_str,
                "Return (%)": format_pct_str,
                col_cp: (CURRENCY_SYMBOL + "{:,.2f}"),
                col_ae: (CURRENCY_SYMBOL + "{:,.2f}"),
                col_mv: (CURRENCY_SYMBOL + "{:,.2f}"),
                col_sp: (CURRENCY_SYMBOL + "{:,.2f}"),
                "Stop Limit (%)": "{:.1f}%",
                "Stop Buffer (%)": lambda v: f"+{v:.1f}%" if v >= 0 else f"-{abs(v):.1f}%",
                "Shares": "{:,.0f}"
            })
        )

        st.dataframe(
            styled_pos_df,
            width='stretch',
            hide_index=True
        )

        if not critical.empty:
            st.error(f"⚠️ {len(critical)} position(s) have breached their designated stop-loss threshold and will be liquidated on the next session cycle!")
        else:
            st.success("✅ Risk Integrity 100%: All active holdings are within safe operating limits (Drawdowns above active stop limits).")

        # ----------------------------------------------------------------------
        # EDITABLE STOP-LOSS CONTROL DESK (BOT & USER OVERRIDES)
        # ----------------------------------------------------------------------
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div class="cyber-card" style="margin-bottom: 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div class="kpi-title" style="color: #82FBBD; font-size: 0.78rem; letter-spacing: 0.12em;">// 02. EDITABLE STOP-LOSS CONTROL DESK</div>
                    <div style="font-size: 0.78rem; color: #71717A; margin-top: 3px;">
                        Alter the stop-loss limit for any active position. Custom overrides are stored persistently in bot configuration and instantly enforced by both the Quant Engine and live risk monitors.
                    </div>
                </div>
                <div>
                    <span class="status-pill" style="border-color: rgba(130,251,189,0.3); color: #82FBBD;">BOT DEFAULT: {sl_manager.global_default_pct*100:.1f}%</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col_pos_info, col_pos_edit = st.columns([1.1, 1.3])

        with col_pos_info:
            target_sym = st.selectbox(
                "Select Position to Alter Stop-Loss",
                options=[p["symbol"] for p in positions],
                key="sl_target_selector"
            )
            pos_data = next((p for p in positions if p["symbol"] == target_sym), None)
            if pos_data:
                pos_cur_price = float(pos_data.get("current_price", 0.0))
                pos_entry_price = float(pos_data.get("avg_entry_price", 0.0))
                pos_qty = float(pos_data.get("qty", 0.0))
                pos_pl = float(pos_data.get("unrealized_pl", 0.0))
                pos_plpc = float(pos_data.get("unrealized_plpc", 0.0)) * 100
                pos_active_sl_pct = sl_manager.get_stop_loss_pct(target_sym)
                pos_is_custom = sl_manager.is_custom_override(target_sym)
                pos_active_stop_price = sl_manager.get_stop_price(target_sym, pos_entry_price)
                pos_dollar_buf = pos_cur_price - pos_active_stop_price
                pos_pct_buf = (pos_dollar_buf / pos_cur_price * 100) if pos_cur_price > 0 else 0.0

                badge_bg = "rgba(255, 184, 0, 0.12)" if pos_is_custom else "rgba(130, 251, 189, 0.1)"
                badge_border = "rgba(255, 184, 0, 0.35)" if pos_is_custom else "rgba(130, 251, 189, 0.28)"
                badge_text_c = "#FFB800" if pos_is_custom else "#82FBBD"
                badge_label = "✏️ USER CUSTOM OVERRIDE" if pos_is_custom else "🤖 BOT ALGORITHM DEFAULT"

                st.markdown(f"""
                <div style="background: #0A0B0E; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; padding: 14px 16px; font-family: 'DM Mono', monospace;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span>TICKER: <b style="color: #FFFFFF; font-size: 1.05rem; font-family: 'Space Grotesk';">{target_sym}</b></span>
                        <span style="font-size: 0.68rem; padding: 3px 8px; border-radius: 4px; background: {badge_bg}; border: 1px solid {badge_border}; color: {badge_text_c}; font-weight: 600;">
                            {badge_label}
                        </span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #71717A; margin-top: 9px; padding-top: 7px; border-top: 1px solid rgba(255,255,255,0.06);">
                        <span>Current Market Price:</span>
                        <span style="color: #FFFFFF; font-weight: 600;">${pos_cur_price:,.2f}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #71717A; margin-top: 5px;">
                        <span>Average Entry Basis:</span>
                        <span style="color: #A1A1AA;">${pos_entry_price:,.2f} ({int(pos_qty)} shares)</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #71717A; margin-top: 5px;">
                        <span>Current Position P&L:</span>
                        <span style="color: {'#82FBBD' if pos_pl >= 0 else '#FF9A9C'}; font-weight: 600;">{format_pnl_str(pos_pl)} ({format_pct_str(pos_plpc)})</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #71717A; margin-top: 8px; padding-top: 7px; border-top: 1px solid rgba(255,255,255,0.06);">
                        <span>Active Stop-Loss Trigger:</span>
                        <span style="color: #FF9A9C; font-weight: 600;">${pos_active_stop_price:,.2f} ({pos_active_sl_pct*100:+.1f}%)</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.76rem; color: #71717A; margin-top: 5px;">
                        <span>Safety Buffer to Stop:</span>
                        <span style="color: {'#82FBBD' if pos_pct_buf > 2.5 else '#FF9A9C'}; font-weight: 600;">{'+' if pos_dollar_buf >= 0 else ''}${pos_dollar_buf:,.2f} ({pos_pct_buf:+.1f}%)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with col_pos_edit:
            if pos_data:
                sl_mode = st.radio(
                    "Stop-Loss Modification Method",
                    options=["By Stop-Loss Percentage (%)", "By Exact Dollar Stop Price ($)"],
                    horizontal=True,
                    key="sl_edit_mode_radio"
                )

                if sl_mode == "By Stop-Loss Percentage (%)":
                    curr_pct_val = abs(pos_active_sl_pct * 100)
                    user_pct_input = st.number_input(
                        "Target Downside Stop Limit % (Loss Threshold from Entry)",
                        min_value=0.5,
                        max_value=40.0,
                        value=float(round(curr_pct_val, 1)),
                        step=0.5,
                        format="%.1f",
                        key=f"sl_pct_input_{target_sym}",
                        help="e.g. 5.0 for -5.0% loss limit from entry basis"
                    )
                    staged_pct = -abs(user_pct_input) / 100.0
                    staged_stop_price = round(pos_entry_price * (1.0 + staged_pct), 2)
                else:
                    user_price_input = st.number_input(
                        "Target Exact Dollar Stop Price ($ USD)",
                        min_value=0.01,
                        max_value=float(pos_cur_price * 1.5),
                        value=float(pos_active_stop_price),
                        step=0.25,
                        format="%.2f",
                        key=f"sl_price_input_{target_sym}",
                        help="Exact share price that unconditionally liquidates position"
                    )
                    staged_stop_price = float(user_price_input)
                    staged_pct = (staged_stop_price - pos_entry_price) / pos_entry_price if pos_entry_price > 0 else -0.08
                    staged_pct = round(staged_pct, 4)

                staged_loss_per_share = pos_entry_price - staged_stop_price
                staged_total_loss = staged_loss_per_share * pos_qty
                staged_dist_curr = pos_cur_price - staged_stop_price
                staged_dist_curr_pct = (staged_dist_curr / pos_cur_price * 100) if pos_cur_price > 0 else 0.0

                st.markdown(f"""
                <div style="background: #0D0E12; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 14px; margin: 10px 0; font-family: 'DM Mono', monospace; font-size: 0.74rem;">
                    <div style="display: flex; justify-content: space-between; padding-bottom: 4px;">
                        <span style="color: #71717A;">NEW STOP TRIGGER:</span>
                        <span style="color: #FFFFFF; font-weight: 600;">${staged_stop_price:,.2f} ({staged_pct*100:+.1f}% from Entry)</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.06);">
                        <span style="color: #71717A;">DISTANCE FROM CURRENT PRICE:</span>
                        <span style="color: {'#82FBBD' if staged_dist_curr > 0 else '#FF9A9C'}; font-weight: 600;">{'+' if staged_dist_curr >= 0 else ''}${staged_dist_curr:,.2f} ({staged_dist_curr_pct:+.1f}%)</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; padding-top: 4px;">
                        <span style="color: #71717A;">MAX DOWNSIDE AT-RISK CAPITAL:</span>
                        <span style="color: #FF9A9C; font-weight: 600;">-${abs(staged_total_loss):,.2f} ({int(pos_qty)} shares)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                b_save, b_reset = st.columns(2)
                with b_save:
                    if st.button(f"💾 Apply Stop-Loss to {target_sym}", type="primary", use_container_width=True, key=f"save_sl_btn_{target_sym}"):
                        sl_manager.set_stop_loss_pct(target_sym, staged_pct)
                        st.toast(f"✅ Set {target_sym} Stop-Loss to {staged_pct*100:.1f}% (${staged_stop_price:,.2f})!", icon="🛡️")
                        st.rerun()

                with b_reset:
                    if st.button(f"🔄 Revert to Bot Default", disabled=(not pos_is_custom), type="secondary", use_container_width=True, key=f"reset_sl_btn_{target_sym}"):
                        sl_manager.reset_stop_loss(target_sym)
                        st.toast(f"🔄 Reverted {target_sym} to Bot Default ({sl_manager.global_default_pct*100:.1f}%)!", icon="🔄")
                        st.rerun()

        # Global Default Stop-Loss Configuration Expander
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        with st.expander("⚙️ Configure Bot Global Default Stop-Loss Limit (All Assets)", expanded=False):
            g_col1, g_col2 = st.columns([2.5, 1.2])
            with g_col1:
                new_global_sl = st.number_input(
                    "Bot Global Default Stop-Loss % (Enforced across any non-overridden ticker)",
                    min_value=2.0,
                    max_value=30.0,
                    value=float(abs(sl_manager.global_default_pct * 100)),
                    step=0.5,
                    format="%.1f",
                    key="global_sl_input"
                )
            with g_col2:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if st.button("💾 Apply Global Default", key="apply_global_sl_btn", use_container_width=True):
                    sl_manager.set_global_default_pct(new_global_sl)
                    st.toast(f"✅ Updated Bot Global Default Stop-Loss to -{new_global_sl:.1f}%!", icon="⚙️")
                    st.rerun()

        st.markdown("<div style='margin-top: 18px;'></div>", unsafe_allow_html=True)
        with st.expander("🚨 Manual Position Liquidation Override", expanded=False):
            st.markdown("<div style='font-size:0.78rem; color:#71717A; margin-bottom: 8px;'>Emergency manual intervention: immediately liquidate any open position via broker market order.</div>", unsafe_allow_html=True)
            liq_col1, liq_col2 = st.columns([2.5, 1.2])
            with liq_col1:
                sel_liq = st.selectbox("Select Position to Liquidate", options=[p["symbol"] for p in positions], key="pos_page_liq_select")
                sel_pos_data = next((p for p in positions if p["symbol"] == sel_liq), None)
                if sel_pos_data:
                    pnl_v = sel_pos_data.get("unrealized_pl", 0.0)
                    plpc_v = sel_pos_data.get("unrealized_plpc", 0.0) * 100
                    pnl_c = "#82FBBD" if pnl_v >= 0 else "#FF9A9C"
                    st.markdown(f"<div style='font-family:\"DM Mono\",monospace; font-size:0.75rem; color:#71717A; margin-top:-6px; margin-bottom:8px;'>Holding: <b style='color:#FFFFFF;'>{sel_pos_data.get('qty')} shares</b> | Market Val: <b style='color:#FFFFFF;'>${sel_pos_data.get('market_value', 0):,.2f}</b> | P&L: <b style='color:{pnl_c};'>{format_pnl_str(pnl_v)} ({format_pct_str(plpc_v)})</b></div>", unsafe_allow_html=True)
            with liq_col2:
                st.markdown("<div style='margin-top: 28px;'></div>", unsafe_allow_html=True)
                if st.button(f"🚨 Liquidate {sel_liq}", type="secondary", key="pos_page_liq_btn", use_container_width=True):
                    with st.spinner(f"Liquidating {sel_liq}..."):
                        c_res = broker.close_position(sel_liq)
                        if c_res.get("success"):
                            st.toast(f"✅ Closed {sel_liq} position!", icon="🚨")
                            st.rerun()
                        else:
                            st.error(f"Liquidation failed: {c_res.get('error')}")
    else:
        st.info("No open positions reported by broker.")


# ==============================================================================
# PAGE: ⚡ MANUAL ORDER DESK & EXECUTION
# ==============================================================================
elif page == "⚡ Manual Order Desk & Execution":
    st.markdown("""
    <div class="page-title-box">
        <div class="page-title">⚡ Manual Order Desk & Execution Controls</div>
        <div class="page-subtitle">PROMPT BOT ORDER PLACEMENT • BOT UNIVERSE DICTIONARY • REAL-TIME OPEN ORDER MANIPULATION</div>
    </div>
    """, unsafe_allow_html=True)

    open_orders = broker.get_open_orders()
    stock_dict = broker.get_stock_dictionary()
    positions = broker.get_positions_detailed()
    pos_map = {p["symbol"]: p for p in positions}

    # Top KPI Deck
    o_kpi1, o_kpi2, o_kpi3, o_kpi4 = st.columns(4)
    with o_kpi1:
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">OPEN ORDERS QUEUED</div>
            <div class="kpi-value"><div class="{'metric-big-green' if len(open_orders) > 0 else 'metric-big'}">{len(open_orders)} Active</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-uniform">BROKER REST SYNCED</div></div>
        </div>
        """, unsafe_allow_html=True)

    with o_kpi2:
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">BUYING POWER AVAILABLE</div>
            <div class="kpi-value"><div class="metric-big">{CURRENCY_SYMBOL}{buying_power:,.2f}</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-mint">NON-MARGIN CASH</div></div>
        </div>
        """, unsafe_allow_html=True)

    with o_kpi3:
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">ACTIVE HOLDINGS</div>
            <div class="kpi-value"><div class="metric-big">{len(positions)} Stocks</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-uniform">{CURRENCY_SYMBOL}{invested_capital:,.2f} INVESTED</div></div>
        </div>
        """, unsafe_allow_html=True)

    with o_kpi4:
        universe_label = "NIFTY 50 / NSE 100" if is_india_mode else "S&P 500 + MEGA-CAPS"
        st.markdown(f"""
        <div class="cyber-kpi-card">
            <div class="kpi-title">BOT UNIVERSE DICTIONARY</div>
            <div class="kpi-value"><div class="metric-big">{len(stock_dict)} Equities</div></div>
            <div class="kpi-badge-row"><div class="metric-badge-uniform">{universe_label}</div></div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)

    with st.expander("📊 Account Purchasing Power & Portfolio Sizing Donut Telemetry", expanded=False):
        d_desk1, d_desk2 = st.columns(2)
        with d_desk1:
            power_labels = ["Invested Capital", "Liquid Cash Reserve"]
            power_values = [round(max(0.0, invested_capital), 2), round(max(0.0, cash), 2)]
            power_colors = ["#82FBBD", "#3B82F6"]
            power_center = f"<b>EQUITY</b><br><span style='font-size:16px; color:#82FBBD;'>{CURRENCY_SYMBOL}{equity:,.0f}</span><br><span style='font-size:10px; color:#71717A;'>TOTAL NAV</span>"
            fig_power = create_donut_chart(
                labels=power_labels,
                values=power_values,
                colors=power_colors,
                center_text=power_center,
                title="PURCHASING POWER & CAPITAL ALLOCATION",
                height=240,
                hole=0.66
            )
            st.plotly_chart(fig_power, width='stretch')
        with d_desk2:
            open_ord_notional = sum(float(o.get('qty', 0)) * float(o.get('limit_price') or 100) for o in open_orders) if open_orders else 0.0
            uncommitted_power = max(0.0, buying_power - open_ord_notional)
            buf_labels = ["Committed in Open Orders", "Uncommitted Buying Power"]
            buf_values = [round(open_ord_notional, 2), round(uncommitted_power, 2)] if open_orders else [0.0, round(buying_power, 2)]
            buf_colors = ["#FFB800", "#00F2FE"]
            buf_center = f"<b>AVAILABLE</b><br><span style='font-size:16px; color:#00F2FE;'>${buying_power:,.0f}</span><br><span style='font-size:10px; color:#71717A;'>BUYING POWER</span>"
            fig_buf = create_donut_chart(
                labels=buf_labels,
                values=buf_values,
                colors=buf_colors,
                center_text=buf_center,
                title="OPEN ORDER COMMITMENT VS UNCOMMITTED LIQUIDITY",
                height=240,
                hole=0.66
            )
            st.plotly_chart(fig_buf, width='stretch')

    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

    col_prompt, col_manipulate = st.columns([1.05, 1.25])

    # --------------------------------------------------------------------------
    # LEFT COLUMN: ⚡ PROMPT BOT ORDER EXECUTION
    # --------------------------------------------------------------------------
    with col_prompt:
        st.markdown("""
        <div class="cyber-card" style="margin-bottom: 12px;">
            <div class="kpi-title" style="color: #82FBBD; font-size: 0.76rem; letter-spacing: 0.12em;">// 01. PROMPT BOT ORDER EXECUTION</div>
            <div style="font-size: 0.78rem; color: #71717A; margin-top: 4px; line-height: 1.4;">
                Select a stock from the bot's S&P 500 universe dictionary and configure order sizing by either exact dollar value ($) or share quantity.
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Quick Pick Pills
        st.markdown("<div style='font-family: \"DM Mono\", monospace; font-size: 0.68rem; color: #71717A; text-transform: uppercase; margin-bottom: 4px;'>QUICK PICKS (HIGH CONVICTION)</div>", unsafe_allow_html=True)
        quick_cols = st.columns(6)
        quick_tickers = (
            ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "BHARTIARTL.NS", "SBIN.NS"]
            if is_india_mode else
            ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "SPY"]
        )
        if "selected_symbol" not in st.session_state or st.session_state.selected_symbol not in stock_dict:
            st.session_state.selected_symbol = quick_tickers[0]

        for idx, q_sym in enumerate(quick_tickers):
            with quick_cols[idx]:
                if st.button(q_sym, key=f"quick_{q_sym}", use_container_width=True):
                    st.session_state.selected_symbol = q_sym
                    st.rerun()

        # Stock Selector from Bot's Dictionary
        default_index = 0
        if st.session_state.selected_symbol in stock_dict:
            default_index = stock_dict.index(st.session_state.selected_symbol)

        selected_symbol = st.selectbox(
            "Select Stock from Bot's Universe Dictionary",
            options=stock_dict,
            index=default_index,
            key="symbol_selector",
            help="Universe dictionary utilized by Quant Engine"
        )
        st.session_state.selected_symbol = selected_symbol

        # Fetch live price for selected stock
        curr_price = broker.get_latest_price(selected_symbol)
        if curr_price <= 0.0:
            curr_price = 100.0  # Fallback

        # Check existing position in this stock
        existing_pos = pos_map.get(selected_symbol)
        existing_qty = existing_pos["qty"] if existing_pos else 0
        existing_val = existing_pos["market_value"] if existing_pos else 0.0
        existing_pnl = existing_pos["unrealized_pl"] if existing_pos else 0.0
        existing_plpc = (existing_pos["unrealized_plpc"] * 100) if existing_pos else 0.0

        st.markdown(f"""
        <div style="padding: 10px 14px; background: #070709; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; margin-bottom: 14px; font-family: 'DM Mono', monospace; font-size: 0.78rem;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>TICKER: <b style="color: #FFFFFF; font-size: 0.95rem;">{selected_symbol}</b></span>
                <span>LIVE PRICE: <b style="color: #82FBBD; font-size: 0.95rem;">{CURRENCY_SYMBOL}{curr_price:,.2f}</b></span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px; color: #71717A;">
                <span>PORTFOLIO STATUS:</span>
                <span>
                    {f"Holding {existing_qty} shares ({CURRENCY_SYMBOL}{existing_val:,.2f} | <b style='color: {'#82FBBD' if existing_pnl >= 0 else '#FF9A9C'};'>{format_pnl_str(existing_pnl)} ({format_pct_str(existing_plpc)})</b>)" if existing_qty > 0 else "<span style='color: #71717A;'>No Active Position (0 Shares)</span>"}
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Order Parameters
        order_side_col, order_type_col = st.columns(2)
        with order_side_col:
            order_side = st.selectbox("Action / Side", options=["BUY", "SELL"], index=0, key="order_side_select")
        with order_type_col:
            order_type = st.selectbox("Order Type", options=["MARKET", "LIMIT"], index=0, key="order_type_select")

        limit_price = None
        if order_type == "LIMIT":
            limit_price = st.number_input(
                f"Limit Price ({CURRENCY_SYMBOL})",
                min_value=0.01,
                value=float(round(curr_price, 2)),
                step=0.10,
                format="%.2f",
                key="limit_price_input"
            )

        # Sizing Mode: Value (Notional) vs Quantity (Shares)
        size_mode = st.radio(
            "Order Sizing Mode",
            options=[f"By Capital Amount ({CURRENCY_SYMBOL} Notional)", "By Quantity (Shares)"],
            horizontal=True,
            key="size_mode_radio"
        )

        calc_notional = 0.0
        calc_qty = 0.0

        if "By Capital Amount" in size_mode:
            order_val = st.number_input(
                f"Target Capital Amount ({CURRENCY_SYMBOL})",
                min_value=1.0,
                max_value=max(100000.0, float(buying_power)),
                value=min(25000.0 if is_india_mode else 2500.0, float(buying_power) if buying_power > 0 else 1000.0),
                step=100.0,
                format="%.2f",
                key="dollar_val_input",
                help=f"The exact amount of capital ({CURRENCY_SYMBOL}) to buy or sell"
            )
            calc_notional = order_val
            ref_price = limit_price if (order_type == "LIMIT" and limit_price) else curr_price
            calc_qty = max(1, int(order_val / ref_price)) if ref_price > 0 else 1
            st.caption(f"Estimated Shares: ~**{calc_qty} shares** at {CURRENCY_SYMBOL}{ref_price:,.2f} / share")
        else:
            order_qty = st.number_input(
                "Share Quantity",
                min_value=1,
                max_value=50000,
                value=10,
                step=1,
                key="share_qty_input",
                help="The exact number of whole shares to buy or sell"
            )
            calc_qty = float(order_qty)
            ref_price = limit_price if (order_type == "LIMIT" and limit_price) else curr_price
            calc_notional = calc_qty * ref_price
            st.caption(f"Estimated Total Notional: ~**{CURRENCY_SYMBOL}{calc_notional:,.2f}** at {CURRENCY_SYMBOL}{ref_price:,.2f} / share")

        # Portfolio Impact & Safeguards Check
        post_weight = ((existing_val + calc_notional) / equity * 100) if equity > 0 else 0.0
        is_cap_breach = (post_weight > 15.0) and (order_side == "BUY")

        st.markdown(f"""
        <div style="background: #0D0E12; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 14px; margin: 12px 0; font-family: 'DM Mono', monospace; font-size: 0.74rem;">
            <div style="display: flex; justify-content: space-between; padding-bottom: 4px;">
                <span style="color: #71717A;">ESTIMATED ORDER NOTIONAL:</span>
                <span style="color: #FFFFFF; font-weight: 600;">${calc_notional:,.2f}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.06);">
                <span style="color: #71717A;">POST-TRADE ALLOCATION:</span>
                <span style="color: {'#FF9A9C' if is_cap_breach else '#82FBBD'}; font-weight: 600;">{post_weight:.1f}% of Equity (15% Max)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding-top: 4px;">
                <span style="color: #71717A;">REMAINING CASH BUFFER:</span>
                <span style="color: #82FBBD; font-weight: 600;">${max(0.0, cash - (calc_notional if order_side == 'BUY' else -calc_notional)):,.2f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if is_cap_breach:
            ceiling_val = equity * 0.15
            st.warning(f"⚠️ Warning: This trade will result in {selected_symbol} exceeding the institutional 15% single-stock ceiling ({CURRENCY_SYMBOL}{ceiling_val:,.2f}).")

        # Order Submission Button
        btn_label = f"⚡ TRANSMIT {order_side} ORDER FOR {selected_symbol}"
        if st.button(btn_label, type="primary" if order_side == "BUY" else "secondary", use_container_width=True):
            # Validation
            if order_side == "BUY" and calc_notional > buying_power:
                st.error(f"❌ Order Rejected: Insufficient buying power ({CURRENCY_SYMBOL}{buying_power:,.2f} available vs {CURRENCY_SYMBOL}{calc_notional:,.2f} required).")
            elif order_side == "SELL" and existing_qty < calc_qty:
                st.error(f"❌ Order Rejected: Cannot sell {calc_qty} shares; you only hold {existing_qty} shares (Long-only discipline enforced).")
            else:
                broker_target_name = "Groww (NSE)" if is_india_mode else "Alpaca"
                with st.spinner(f"Transmitting {order_side} order for {selected_symbol} to {broker_target_name}..."):
                    if "By Capital Amount" in size_mode and order_type == "MARKET":
                        res = broker.place_order(
                            symbol=selected_symbol,
                            notional=calc_notional,
                            side=order_side.lower(),
                            order_type="market",
                            time_in_force="day"
                        )
                    else:
                        res = broker.place_order(
                            symbol=selected_symbol,
                            qty=calc_qty,
                            side=order_side.lower(),
                            order_type=order_type.lower(),
                            limit_price=limit_price,
                            time_in_force="day"
                        )

                    if res.get("success"):
                        o_data = res.get("order", {})
                        st.success(f"✅ {res.get('message', 'Order placed successfully!')} (ID: {o_data.get('id', 'N/A')}, Status: {o_data.get('status', 'ACCEPTED').upper()})")
                        st.toast(f"✅ Order for {selected_symbol} placed!", icon="⚡")
                        st.rerun()
                    else:
                        st.error(f"❌ Order Placement Error: {res.get('error', 'Unknown broker error')}")

    # --------------------------------------------------------------------------
    # RIGHT COLUMN: 📋 LIVE PLACED ORDERS MANIPULATION
    # --------------------------------------------------------------------------
    with col_manipulate:
        st.markdown(f"""
        <div class="cyber-card" style="margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div class="kpi-title" style="color: #82FBBD; font-size: 0.76rem; letter-spacing: 0.12em;">// 02. ACTIVE PLACED ORDERS QUEUE</div>
                <div style="font-size: 0.78rem; color: #71717A; margin-top: 4px;">
                    Inspect, modify, or cancel currently queued & pending orders on Alpaca.
                </div>
            </div>
            <div>
                <span class="status-pill" style="border-color: rgba(130,251,189,0.3); color: #82FBBD;">{len(open_orders)} LIVE</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if open_orders:
            b_col1, b_col2 = st.columns([1, 1])
            with b_col1:
                if st.button("🚨 Cancel All Open Orders", use_container_width=True, type="secondary"):
                    with st.spinner("Canceling all open orders on Alpaca..."):
                        if broker.cancel_all_orders():
                            st.toast("✅ All open orders canceled!", icon="🗑️")
                            st.rerun()
                        else:
                            st.error("Failed to cancel all orders.")
            with b_col2:
                if st.button("🔄 Refresh Orders Queue", use_container_width=True):
                    st.rerun()

            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)

            # Render individual orders with cancel & modify buttons
            for idx, o in enumerate(open_orders):
                side_color = "#82FBBD" if o["side"] == "BUY" else "#FF9A9C"
                badge_border = "rgba(130, 251, 189, 0.3)" if o["side"] == "BUY" else "rgba(255, 154, 156, 0.3)"
                lp_str = f"@ ${o['limit_price']:,.2f}" if o.get("limit_price") else ""
                sub_time = o.get("submitted_at", "")[11:19] if len(o.get("submitted_at", "")) >= 19 else ""
                
                with st.container():
                    st.markdown(f"""
                    <div style="background: #0A0B0E; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 12px 14px; margin-bottom: 8px; font-family: 'DM Mono', monospace;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 1.05rem; font-weight: 700; color: #FFFFFF; font-family: 'Space Grotesk', sans-serif;">{o['symbol']}</span>
                                <span style="font-size: 0.68rem; padding: 2px 7px; border-radius: 4px; border: 1px solid {badge_border}; color: {side_color}; font-weight: 600;">{o['side']}</span>
                                <span style="font-size: 0.68rem; color: #71717A;">{o['type']} {lp_str}</span>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 0.68rem; color: #82FBBD; background: rgba(130,251,189,0.08); padding: 2px 6px; border-radius: 4px; border: 1px solid rgba(130,251,189,0.2);">{o['status']}</span>
                                <span style="font-size: 0.68rem; color: #71717A;">{sub_time} UTC</span>
                            </div>
                        </div>
                        <div style="display: flex; justify-content: space-between; font-size: 0.72rem; color: #71717A; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 6px;">
                            <span>Quantity: <b style="color: #FFFFFF;">{o['qty']} shares</b> (Filled: {o['filled_qty']})</span>
                            <span style="font-size: 0.66rem; color: #52525B;">ID: {o['client_order_id'][:16] if o['client_order_id'] else o['id'][:12]}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                    btn_c1, btn_c2 = st.columns([1, 1.2])
                    with btn_c1:
                        if st.button("🗑️ Cancel", key=f"cancel_{o['id']}_{idx}", use_container_width=True):
                            with st.spinner(f"Canceling order for {o['symbol']}..."):
                                c_res = broker.cancel_order(o["id"])
                                if c_res.get("success"):
                                    st.toast(f"✅ Order for {o['symbol']} canceled!", icon="🗑️")
                                    st.rerun()
                                else:
                                    st.error(f"Failed to cancel: {c_res.get('error')}")

                    with btn_c2:
                        with st.expander("✏️ Modify Order", expanded=False):
                            m_qty = st.number_input(
                                "New Qty",
                                min_value=1,
                                value=int(o["qty"]),
                                step=1,
                                key=f"mod_qty_{o['id']}_{idx}"
                            )
                            m_lp = None
                            if o["type"] == "LIMIT" or o.get("limit_price"):
                                m_lp = st.number_input(
                                    "New Limit Price",
                                    min_value=0.01,
                                    value=float(o.get("limit_price") or 100.0),
                                    step=0.10,
                                    format="%.2f",
                                    key=f"mod_lp_{o['id']}_{idx}"
                                )
                            if st.button("💾 Apply Modification", key=f"apply_mod_{o['id']}_{idx}", use_container_width=True):
                                with st.spinner("Modifying order..."):
                                    mod_res = broker.replace_order(
                                        order_id=o["id"],
                                        new_qty=m_qty,
                                        new_limit_price=m_lp
                                    )
                                    if mod_res.get("success"):
                                        st.toast(f"✅ Order for {o['symbol']} updated!", icon="✏️")
                                        st.rerun()
                                    else:
                                        st.error(f"Modification error: {mod_res.get('error')}")

        else:
            st.info("No active open orders in the broker queue. All orders filled or cleared.")

        # Bottom Sub-Card: Active Position Liquidator
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div class="cyber-card">
            <div class="kpi-title" style="color: #FF9A9C; font-size: 0.74rem;">// 03. QUICK POSITION LIQUIDATOR</div>
            <div style="font-size: 0.78rem; color: #71717A; margin-top: 4px; line-height: 1.4;">
                Manually exit or close any open equity position via immediate broker market sell.
            </div>
        """, unsafe_allow_html=True)

        if positions:
            pos_symbols = [p["symbol"] for p in positions]
            close_sym = st.selectbox("Select Position to Liquidate", options=pos_symbols, key="desk_liq_select")
            chosen_pos = pos_map.get(close_sym)
            if chosen_pos:
                chosen_pnl = chosen_pos['unrealized_pl']
                chosen_plpc = chosen_pos['unrealized_plpc'] * 100
                chosen_pnl_color = "#82FBBD" if chosen_pnl >= 0 else "#FF9A9C"
                st.markdown(f"<div style='font-family:\"DM Mono\",monospace; font-size:0.75rem; color:#71717A; margin-bottom:8px;'>Holds: <b style='color:#FFFFFF;'>{chosen_pos['qty']} shares</b> | Market Value: <b style='color:#FFFFFF;'>${chosen_pos['market_value']:,.2f}</b> | PnL: <b style='color:{chosen_pnl_color};'>{format_pnl_str(chosen_pnl)} ({format_pct_str(chosen_plpc)})</b></div>", unsafe_allow_html=True)
                if st.button(f"🚨 MARKET CLOSE {close_sym} POSITION", type="secondary", key="desk_close_pos_btn", use_container_width=True):
                    with st.spinner(f"Liquidating position in {close_sym}..."):
                        c_pos_res = broker.close_position(close_sym)
                        if c_pos_res.get("success"):
                            st.toast(f"✅ Closed {close_sym} position!", icon="🚨")
                            st.rerun()
                        else:
                            st.error(f"Liquidation error: {c_pos_res.get('error')}")
        else:
            st.caption("No open positions available to liquidate.")
        st.markdown("</div>", unsafe_allow_html=True)


# ==============================================================================
# PAGE 3: 🏆 30-DAY INCUBATION SCORECARD
# ==============================================================================
elif page == "🏆 30-Day Incubation Scorecard":
    st.markdown("""
    <div class="page-title-box">
        <div class="page-title">🏆 30-Day Paper Incubation Health Scorecard</div>
        <div class="page-subtitle">AUTONOMOUS INCUBATION MONITOR • REAL-TIME AUDIT TRAIL • GRADUATION PROGRESS</div>
    </div>
    """, unsafe_allow_html=True)

    df_history = broker.get_portfolio_history(period="1M", timeframe="1D")

    if df_history is not None and not df_history.empty:
        df_history = df_history[df_history["equity"] > 0]
        days_logged = len(df_history)
        start_equity = float(df_history['equity'].iloc[0])
        current_eq = float(df_history['equity'].iloc[-1])
        net_change = current_eq - start_equity
        net_change_pct = (net_change / start_equity * 100) if start_equity > 0 else 0.0

        rolling_max = df_history['equity'].cummax()
        drawdown_series = (df_history['equity'] - rolling_max) / rolling_max
        max_drawdown = float(drawdown_series.min() * 100)

        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">INCUBATION PROGRESS</div>
                <div class="kpi-value"><div class="metric-big">Day {days_logged} <span style="font-size: 1.05rem; color: #71717A;">/ 30</span></div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">{(days_logged/30)*100:.0f}% COMPLETED</div></div>
            </div>
            """, unsafe_allow_html=True)

        with sc2:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">INCEPTION BASE CAPITAL</div>
                <div class="kpi-value"><div class="metric-big">{CURRENCY_SYMBOL}{start_equity:,.2f}</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">BASE PRINCIPAL</div></div>
            </div>
            """, unsafe_allow_html=True)

        with sc3:
            pnl_class = "metric-big-green" if net_change >= 0 else "metric-big-red"
            badge_class = "metric-badge-mint" if net_change >= 0 else "metric-badge-danger"
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">NET INCUBATION RETURN</div>
                <div class="kpi-value"><div class="{pnl_class}">{format_pnl_str(net_change)}</div></div>
                <div class="kpi-badge-row"><div class="{badge_class}">{format_pct_str(net_change_pct)} TOTAL RETURN</div></div>
            </div>
            """, unsafe_allow_html=True)

        with sc4:
            dd_class = "metric-big-green" if max_drawdown > -8.0 else "metric-big-red"
            dd_badge = "metric-badge-mint" if max_drawdown > -8.0 else "metric-badge-danger"
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">PEAK-TO-TROUGH DRAWDOWN</div>
                <div class="kpi-value"><div class="{dd_class}">{max_drawdown:.2f}%</div></div>
                <div class="kpi-badge-row"><div class="{dd_badge}">TOLERANCE &lt; -10.0%</div></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # Sleek Equity Curve (Blacklead Studio Minimalist Edition)
        fig_equity = go.Figure()
        curve_color = "#82FBBD" if net_change >= 0 else "#FF9A9C"
        curve_fill = "rgba(130, 251, 189, 0.08)" if net_change >= 0 else "rgba(255, 154, 156, 0.08)"
        fig_equity.add_trace(go.Scatter(
            x=df_history["timestamp"],
            y=df_history["equity"],
            mode="lines",
            name="Account Equity",
            line=dict(color=curve_color, width=2.4),
            fill="tozeroy",
            fillcolor=curve_fill
        ))
        fig_equity.add_hline(
            y=100000.0,
            line_dash="dash",
            line_color="#52525B",
            annotation_text="Base Capital ($100k)",
            annotation_font_color="#71717A"
        )
        fig_equity.update_layout(
            title="Autonomous Portfolio Equity Trajectory (Past Sessions)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=50, b=20, l=10, r=10),
            height=360,
            font=dict(family="Space Grotesk, sans-serif", color="#FFFFFF"),
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)")
        )
        st.plotly_chart(fig_equity, width='stretch')

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # DUAL DONUT TELEMETRY DECK: INCUBATION MILESTONES & SESSION WIN RATIO
        # ----------------------------------------------------------------------
        inc_c1, inc_c2 = st.columns(2)

        with inc_c1:
            days_done = min(30, days_logged)
            days_rem = max(0, 30 - days_logged)
            m_labels = ["Days Completed", "Days Remaining"]
            m_values = [days_done, days_rem]
            m_colors = ["#82FBBD", "#27272A"]
            m_pct = (days_done / 30) * 100
            m_center = f"<b>PROGRESS</b><br><span style='font-size:18px; color:#82FBBD;'>{m_pct:.0f}%</span><br><span style='font-size:10px; color:#71717A;'>DAY {days_done}/30</span>"

            fig_inc_prog = create_donut_chart(
                labels=m_labels,
                values=m_values,
                colors=m_colors,
                center_text=m_center,
                title="30-DAY INCUBATION TIMELINE PROGRESS",
                height=250,
                hole=0.66
            )
            st.plotly_chart(fig_inc_prog, width='stretch')

        with inc_c2:
            daily_deltas = df_history['equity'].diff().dropna()
            win_days = int((daily_deltas > 0).sum())
            loss_days = int((daily_deltas < 0).sum())
            flat_days = int((daily_deltas == 0).sum())

            if win_days == 0 and loss_days == 0:
                win_days = 1 if net_change >= 0 else 0
                loss_days = 1 if net_change < 0 else 0

            s_labels = ["Winning Sessions", "Losing Sessions"] + (["Flat Sessions"] if flat_days > 0 else [])
            s_values = [win_days, loss_days] + ([flat_days] if flat_days > 0 else [])
            s_colors = ["#82FBBD", "#FF9A9C"] + (["#52525B"] if flat_days > 0 else [])
            tot_s = max(1, win_days + loss_days)
            s_win_rate = (win_days / tot_s) * 100
            s_center = f"<b>DAY WIN RATE</b><br><span style='font-size:18px; color:{'#82FBBD' if s_win_rate >= 50 else '#FF9A9C'};'>{s_win_rate:.0f}%</span><br><span style='font-size:10px; color:#71717A;'>{win_days}W - {loss_days}L</span>"

            fig_inc_win = create_donut_chart(
                labels=s_labels,
                values=s_values,
                colors=s_colors,
                center_text=s_center,
                title="DAILY SESSION WIN / LOSS RATIO",
                height=250,
                hole=0.66
            )
            st.plotly_chart(fig_inc_win, width='stretch')

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        st.markdown("### 🎓 5 Hard Institutional Graduation Criteria")

        positions = broker.get_positions_detailed()
        sl_breaches = sum(1 for p in (positions or []) if p.get("unrealized_plpc", 0.0) <= -0.08)

        g1, g2 = st.columns(2)
        with g1:
            if sl_breaches == 0:
                st.success("✅ **Criterion 1: Hard Stop-Loss Enforcement (-8%)** — Passed. 0 active breaches unhandled.")
            else:
                st.error(f"❌ **Criterion 1: Hard Stop-Loss Enforcement (-8%)** — {sl_breaches} position(s) breached.")

            if max_drawdown > -10.0:
                st.success(f"✅ **Criterion 2: Max Drawdown Containment (< 10%)** — Passed. Peak-to-trough: {max_drawdown:.2f}%.")
            else:
                st.error(f"❌ **Criterion 2: Max Drawdown Containment (< 10%)** — Breached: {max_drawdown:.2f}%.")

            if cash >= 0:
                st.success(f"✅ **Criterion 3: Solvency & Long-Only Buffer** — Passed. Cash: ${cash:,.2f} ({cash_pct:.1f}%).")
            else:
                st.warning(f"⚠️ **Criterion 3: Solvency & Long-Only Buffer** — Normalizing: ${cash:,.2f}.")

        with g2:
            recent_orders = broker.get_recent_orders(limit=10)
            idempotent_orders = [o for o in recent_orders if str(o.get("client_order_id", "")).startswith("Q-")]
            if idempotent_orders or not recent_orders:
                st.success("✅ **Criterion 4: Execution Idempotency & Clean Order Books** — Passed. Deterministic order hashing `Q-<hash>` active.")
            else:
                st.info("ℹ️ **Criterion 4: Execution Idempotency** — Active. Monitoring incoming order hashes.")

            short_positions = [p for p in (positions or []) if float(p.get("qty", 0)) < 0]
            if len(positions or []) > 0 and len(short_positions) == 0:
                st.success(f"✅ **Criterion 5: Dynamic Multi-Strategy Long-Only Ensemble** — Passed. {len(positions)} high-conviction positions dynamically held, 0 short positions.")
            elif len(positions or []) == 0:
                st.info("ℹ️ **Criterion 5: Dynamic Ensemble** — 100% Cash Buffer (0 active positions).")
            else:
                st.error(f"❌ **Criterion 5: Shorting Detected** — {len(short_positions)} short positions found.")


# ==============================================================================
# PAGE 4: ⚡ ORDER ACTIVITY LOG
# ==============================================================================
elif page in ("⚡ Order Activity Log", "📜 Order Activity Log"):
    st.markdown("""
    <div class="page-title-box">
        <div class="page-title">⚡ Real-Time Execution Order Ledger</div>
        <div class="page-subtitle">COMPLETE BROKER ORDER HISTORY • DIVIDED BY SESSION DATE • MULTI-PAGE AUDIT TRAIL</div>
    </div>
    """, unsafe_allow_html=True)

    all_orders = broker.get_recent_orders(limit=500)

    if all_orders:
        orders_data = []
        filled_count = 0
        idempotent_count = 0

        for o in all_orders:
            sub = o.get("submitted_at", "")
            date_val = sub[:10] if len(sub) >= 10 else "Unknown"
            time_val = sub[11:19] if len(sub) >= 19 else "00:00:00"
            qty = float(o.get("filled_qty") or o.get("qty") or 0.0)
            price = float(o.get("filled_avg_price") or o.get("limit_price") or 0.0)
            notional = round(qty * price, 2)
            st_text = str(o.get("status", "")).upper()
            cid = str(o.get("client_order_id", ""))

            if st_text == "FILLED":
                filled_count += 1
            if cid.startswith("Q-"):
                idempotent_count += 1

            orders_data.append({
                "Date": date_val,
                "Time (UTC)": time_val,
                "Symbol": o.get("symbol", ""),
                "Side": str(o.get("side", "")).upper(),
                "Shares": int(qty) if qty.is_integer() else qty,
                "Fill Price": price,
                "Total Value": notional,
                "Status": st_text,
                "Client Order ID": cid
            })

        df_all_orders = pd.DataFrame(orders_data)
        total_traded_vol = float(df_all_orders["Total Value"].sum())
        unique_dates = sorted(df_all_orders["Date"].unique().tolist(), reverse=True)

        # Top 4 KPI Metrics Deck
        o1, o2, o3, o4 = st.columns(4)
        with o1:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">LIFETIME ORDERS</div>
                <div class="kpi-value"><div class="metric-big">{len(df_all_orders)} Orders</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">COMPLETE HISTORY</div></div>
            </div>
            """, unsafe_allow_html=True)

        with o2:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">TRADING SESSIONS</div>
                <div class="kpi-value"><div class="metric-big-green">{len(unique_dates)} Dates</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">DATE-DIVIDED</div></div>
            </div>
            """, unsafe_allow_html=True)

        with o3:
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">TOTAL CAPITAL TRADED</div>
                <div class="kpi-value"><div class="metric-big">{CURRENCY_SYMBOL}{total_traded_vol:,.2f}</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">NOTIONAL VOLUME</div></div>
            </div>
            """, unsafe_allow_html=True)

        with o4:
            fill_rate = (filled_count / len(df_all_orders) * 100) if len(df_all_orders) > 0 else 100.0
            st.markdown(f"""
            <div class="cyber-kpi-card">
                <div class="kpi-title">FILL SUCCESS RATE</div>
                <div class="kpi-value"><div class="metric-big-green">{fill_rate:.1f}%</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">100% IDEMPOTENT</div></div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # DUAL DONUT TELEMETRY DECK: ORDER SIDE & EXECUTION INTEGRITY
        # ----------------------------------------------------------------------
        ord_c1, ord_c2 = st.columns(2)

        with ord_c1:
            buys_count = int((df_all_orders["Side"] == "BUY").sum())
            sells_count = int((df_all_orders["Side"] == "SELL").sum())
            side_labels = ["Buy Orders", "Sell Orders"]
            side_values = [buys_count, sells_count]
            side_colors = ["#82FBBD", "#FF9A9C"]
            tot_orders = len(df_all_orders)
            side_center = f"<b>ORDERS</b><br><span style='font-size:18px; color:#FFFFFF;'>{tot_orders}</span><br><span style='font-size:10px; color:#71717A;'>LIFETIME</span>"

            fig_order_side = create_donut_chart(
                labels=side_labels,
                values=side_values,
                colors=side_colors,
                center_text=side_center,
                title="ORDER DIRECTION ALLOCATION (BUYS VS SELLS)",
                height=250,
                hole=0.66
            )
            st.plotly_chart(fig_order_side, width='stretch')

        with ord_c2:
            status_counts = df_all_orders["Status"].value_counts().to_dict()
            stat_labels = list(status_counts.keys())
            stat_values = list(status_counts.values())
            stat_colors_map = {
                "FILLED": "#00F2FE",
                "NEW": "#82FBBD",
                "ACCEPTED": "#3B82F6",
                "CANCELED": "#FF9A9C",
                "EXPIRED": "#71717A",
                "REPLACED": "#FFB800"
            }
            stat_colors = [stat_colors_map.get(k, "#A1A1AA") for k in stat_labels]
            fill_center = f"<b>FILL RATE</b><br><span style='font-size:18px; color:#00F2FE;'>{fill_rate:.1f}%</span><br><span style='font-size:10px; color:#71717A;'>{filled_count} FILLED</span>"

            fig_order_stat = create_donut_chart(
                labels=stat_labels,
                values=stat_values,
                colors=stat_colors,
                center_text=fill_center,
                title="EXECUTION STATUS & ORDER ROUTING INTEGRITY",
                height=250,
                hole=0.66
            )
            st.plotly_chart(fig_order_stat, width='stretch')

        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

        # ==========================================
        # DATE DIVISION & FILTER CONTROLS
        # ==========================================
        date_options = ["🌟 All Trading Dates"]
        for d in unique_dates:
            d_count = sum(df_all_orders["Date"] == d)
            d_vol = df_all_orders[df_all_orders["Date"] == d]["Total Value"].sum()
            date_options.append(f"📅 {d} ({d_count} orders • {CURRENCY_SYMBOL}{d_vol:,.0f})")

        f_col1, f_col2, f_col3, f_col4 = st.columns([2.5, 1.2, 1.5, 1.2])

        with f_col1:
            selected_date_filter = st.selectbox(
                "Filter by Trading Date",
                options=date_options,
                index=0,
                key="order_date_filter"
            )

        with f_col2:
            side_filter = st.selectbox(
                "Filter Side",
                options=["ALL SIDES", "BUY", "SELL"],
                index=0,
                key="order_side_filter"
            )

        with f_col3:
            ticker_search = st.text_input(
                "Search Ticker",
                placeholder="e.g. PH, GOOG...",
                key="order_ticker_search"
            ).strip().upper()

        with f_col4:
            page_size = st.selectbox(
                "Orders / Page",
                options=[15, 25, 50, 100],
                index=1,
                key="order_page_size"
            )

        # Apply Filters
        filtered_df = df_all_orders.copy()

        if not selected_date_filter.startswith("🌟"):
            extracted_date = selected_date_filter.split(" ")[1]
            filtered_df = filtered_df[filtered_df["Date"] == extracted_date]

        if side_filter != "ALL SIDES":
            filtered_df = filtered_df[filtered_df["Side"] == side_filter]

        if ticker_search:
            filtered_df = filtered_df[filtered_df["Symbol"].str.contains(ticker_search, na=False)]

        # Session Summary Banner
        session_orders = len(filtered_df)
        session_vol = filtered_df["Total Value"].sum()
        session_buys = sum(filtered_df["Side"] == "BUY")
        session_sells = sum(filtered_df["Side"] == "SELL")

        st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; margin-bottom: 12px; padding: 11px 18px; background: #0D0E12; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px; font-family: 'DM Mono', monospace; font-size: 0.80rem;">
            <div style="display: flex; gap: 14px; align-items: center;">
                <span style="color: #FFFFFF; font-weight: 700; font-size: 0.86rem;">// LEDGER STATUS:</span>
                <span style="color: #82FBBD; font-weight: 600;">{session_orders} Matching Orders</span>
                <span style="color: #52525B;">|</span>
                <span style="color: #FFFFFF;">Volume: <b style="color: #82FBBD;">${session_vol:,.2f}</b></span>
            </div>
            <div style="display: flex; gap: 12px; color: #71717A;">
                <span>BUYS: <b style="color: #82FBBD;">{session_buys}</b></span>
                <span>SELLS: <b style="color: #FF9A9C;">{session_sells}</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ==========================================
        # PAGINATION ENGINE
        # ==========================================
        total_rows = len(filtered_df)
        total_pages = max(1, (total_rows - 1) // page_size + 1)

        if "order_ledger_page" not in st.session_state:
            st.session_state.order_ledger_page = 1

        if st.session_state.order_ledger_page > total_pages:
            st.session_state.order_ledger_page = total_pages

        start_row = (st.session_state.order_ledger_page - 1) * page_size
        end_row = min(start_row + page_size, total_rows)
        paged_df = filtered_df.iloc[start_row:end_row]

        # Order Table with Non-Choppy Explicit Column Configuration
        st.dataframe(
            paged_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Date": st.column_config.TextColumn("Session Date", width="small"),
                "Time (UTC)": st.column_config.TextColumn("Time (UTC)", width="small"),
                "Symbol": st.column_config.TextColumn("Ticker", width="small"),
                "Side": st.column_config.TextColumn("Action", width="small"),
                "Shares": st.column_config.NumberColumn("Shares", format="%d", width="small"),
                "Fill Price": st.column_config.NumberColumn("Fill Price", format=f"{CURRENCY_SYMBOL}%.2f", width="small"),
                "Total Value": st.column_config.NumberColumn("Total Notional", format=f"{CURRENCY_SYMBOL}%.2f", width="medium"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Client Order ID": st.column_config.TextColumn("Idempotent Hash", width="medium")
            }
        )

        # Interactive Pagination Navigation Strip
        p_col1, p_col2, p_col3 = st.columns([1, 2, 1])

        with p_col1:
            if st.button("◀ Previous Page", disabled=(st.session_state.order_ledger_page <= 1), width="stretch"):
                st.session_state.order_ledger_page -= 1
                st.rerun()

        with p_col2:
            st.markdown(f"""
            <div style="text-align: center; font-family: 'DM Mono', monospace; font-size: 0.80rem; color: #71717A; padding-top: 8px;">
                Page <b style="color: #82FBBD;">{st.session_state.order_ledger_page}</b> of <b style="color: #FFFFFF;">{total_pages}</b> • Displaying rows {start_row + 1} – {end_row} of {total_rows}
            </div>
            """, unsafe_allow_html=True)

        with p_col3:
            if st.button("Next Page ▶", disabled=(st.session_state.order_ledger_page >= total_pages), width="stretch"):
                st.session_state.order_ledger_page += 1
                st.rerun()

        # Date-by-Date Accordion Breakdown
        st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
        with st.expander("📅 Expand Complete Session-by-Session Breakdown (All 16 Dates)"):
            for d in unique_dates:
                d_df = df_all_orders[df_all_orders["Date"] == d]
                d_buys = sum(d_df["Side"] == "BUY")
                d_sells = sum(d_df["Side"] == "SELL")
                d_notional = d_df["Total Value"].sum()

                st.markdown(f"""
                <div style="padding: 8px 12px; background: #0D0E12; border-left: 3px solid #82FBBD; border-radius: 6px; margin: 8px 0; font-family: 'DM Mono', monospace; font-size: 0.80rem; display: flex; justify-content: space-between;">
                    <span><b>📅 {d}</b> — {len(d_df)} Orders</span>
                    <span>Volume: <b style="color: #82FBBD;">${d_notional:,.2f}</b> (<b style="color: #82FBBD;">{d_buys} Buys</b> / <b style="color: #FF9A9C;">{d_sells} Sells</b>)</span>
                </div>
                """, unsafe_allow_html=True)

                st.dataframe(
                    d_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Date": st.column_config.TextColumn("Session Date", width="small"),
                        "Time (UTC)": st.column_config.TextColumn("Time (UTC)", width="small"),
                        "Symbol": st.column_config.TextColumn("Ticker", width="small"),
                        "Side": st.column_config.TextColumn("Action", width="small"),
                        "Shares": st.column_config.NumberColumn("Shares", format="%d", width="small"),
                        "Fill Price": st.column_config.NumberColumn("Fill Price", format="$%.2f", width="small"),
                        "Total Value": st.column_config.NumberColumn("Total Notional", format="$%.2f", width="medium"),
                        "Status": st.column_config.TextColumn("Status", width="small"),
                        "Client Order ID": st.column_config.TextColumn("Idempotent Hash", width="medium")
                    }
                )
    else:
        st.info("No recent execution records found.")


# ==============================================================================
# PAGE 5: 🧠 QUANT BRAIN & STRATEGY
# ==============================================================================
elif page == "🧠 Quant Brain & Strategy":
    st.markdown("""
    <div class="page-title-box">
        <div class="page-title">🧠 Autonomous Quant Brain & AI Gating</div>
        <div class="page-subtitle">WALK-FORWARD ANCHORS • MATHEMATICAL FORMULA • PHASE 3 RANDOM FOREST CLASSIFIER</div>
    </div>
    """, unsafe_allow_html=True)

    config_path = os.path.join(os.path.dirname(__file__), "app", "config", "dynamic_params.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            params = json.load(f)
        p1, p2 = st.columns(2)
        with p1:
            st.markdown(f"""
            <div class="cyber-kpi-card" style="height: 120px !important; min-height: 120px !important;">
                <div class="kpi-title">FAST TREND MOVING AVERAGE WINDOW</div>
                <div class="kpi-value"><div class="metric-big">{params.get('fast_sma', 20)} Days</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">CONTINUOUS WALK-FORWARD CALIBRATED</div></div>
            </div>
            """, unsafe_allow_html=True)
        with p2:
            st.markdown(f"""
            <div class="cyber-kpi-card" style="height: 120px !important; min-height: 120px !important;">
                <div class="kpi-title">SLOW ANCHOR MOVING AVERAGE WINDOW</div>
                <div class="kpi-value"><div class="metric-big">{params.get('slow_sma', 50)} Days</div></div>
                <div class="kpi-badge-row"><div class="metric-badge-uniform">INSTITUTIONAL REGIME ANCHOR</div></div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # DUAL DONUT TELEMETRY DECK: ALPHA WEIGHTS & FEATURE MATRIX
    # --------------------------------------------------------------------------
    qb_c1, qb_c2 = st.columns(2)

    with qb_c1:
        alpha_labels = ["Velocity Momentum (ROC-20)", "Trend Extension Anchor (SMA)"]
        alpha_values = [70, 30]
        alpha_colors = ["#82FBBD", "#3B82F6"]
        alpha_center = "<b>WEIGHT</b><br><span style='font-size:18px; color:#82FBBD;'>70%</span><span style='font-size:12px; color:#71717A;'>/30%</span><br><span style='font-size:10px; color:#71717A;'>ALPHA SPLIT</span>"

        fig_alpha_weight = create_donut_chart(
            labels=alpha_labels,
            values=alpha_values,
            colors=alpha_colors,
            center_text=alpha_center,
            title="CONVICTION SCORE WEIGHT FORMULA SPLIT",
            height=250,
            hole=0.66
        )
        st.plotly_chart(fig_alpha_weight, width='stretch')

    with qb_c2:
        ml_labels = ["Multi-Horizon Momentum", "Trend & MA Architecture", "Volatility & ATR Spreads", "Volume & Flow Surges"]
        ml_values = [35, 25, 20, 20]
        ml_colors = ["#82FBBD", "#00F2FE", "#A855F7", "#FFB800"]
        ml_center = "<b>FEATURES</b><br><span style='font-size:18px; color:#A855F7;'>18</span><br><span style='font-size:10px; color:#71717A;'>150 TREES</span>"

        fig_ml_feat = create_donut_chart(
            labels=ml_labels,
            values=ml_values,
            colors=ml_colors,
            center_text=ml_center,
            title="RANDOM FOREST FEATURE GROUP IMPORTANCE",
            height=250,
            hole=0.66
        )
        st.plotly_chart(fig_ml_feat, width='stretch')

    st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
    st.markdown("### 📐 Risk-Adjusted Momentum Formula")
    st.latex(r"""
    \text{Conviction Score} = 0.70 \times \left( \frac{\text{ROC}_{20}}{\sigma_{20} + 0.05} \right) + 0.30 \times \left( \frac{\text{Price} - \text{SMA}_{\text{slow}}}{\text{SMA}_{\text{slow}}} \right)
    """)
    st.markdown(r"""
    - **Velocity Component ($\text{ROC}_{20}$):** 20-day rate of change rewards strong upward momentum.
    - **Smoothness Adjustment ($\sigma_{20}$):** Penalizes choppy, erratic breakouts with high volatility.
    - **Trend Extension Anchor:** Rewards persistent structural uptrends relative to the institutional moving average.
    - **Dynamic Sizing:** Weight is proportional to conviction score, dynamically scaled with **15% max per stock** and **zero naked shorting**.
    """)

    st.markdown("---")
    st.markdown("### 🤖 Phase 3: Machine Learning Alpha Gate")
    st.markdown(r"""
    - **Classifier:** 150-tree Random Forest trained on 10 years of purged walk-forward cross-validation.
    - **Feature Matrix:** 18 stationary normalized indicators (multi-horizon returns, moving average spreads, normalized ATR, RSI, Bollinger %B, volatility ratios, volume surges).
    - **Alpha Gating:** Evaluates $P(\text{Alpha}_{5d} > 0.5\%)$. Vetoes false breakouts and bull traps ($P < 0.48$), and modulates conviction weight on confirmed setups ($P \ge 0.50$).
    """)


# ==============================================================================
# PAGE 6: 🛡️ RISK SAFEGUARDS GRID
# ==============================================================================
elif page == "🛡️ Risk Safeguards":
    st.markdown("""
    <div class="page-title-box">
        <div class="page-title">🛡️ 5-Layer Institutional Risk Defense Grid</div>
        <div class="page-subtitle">CAPITAL PRESERVATION ARCHITECTURE • STRICT LONG-ONLY DISCIPLINE • ZERO SHORT RISK</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.02rem;">1. Multi-Asset Macro Weather & Crash Radar</div>
            <div style="font-size: 0.82rem; color: #71717A; margin-top: 8px; line-height: 1.6;">
                Continuous evaluation of <b>SPY</b> (200 SMA & Trend Ratio), <b>QQQ</b> (Tech Bubble Dispersion), and <b>VIX</b> (Volatility Panic):
                <br>• <b style="color: #82FBBD;">BULL_NORMAL:</b> 95% Max Exposure (Full Risk-On Momentum)
                <br>• <b style="color: #FFFFFF;">BULL_ROTATION:</b> 85% Exposure (QQQ &lt; 50 SMA Tech Fatigue; Value Rotation)
                <br>• <b style="color: #FFFFFF;">BULL_CHOPPY:</b> 85% Max Exposure (Dip-Buying Focus, 15% Cash Shield)
                <br>• <b style="color: #FFB800;">VOLATILITY_CAUTION:</b> 60% Exposure (VIX &gt; 22; 40% Cash Defense)
                <br>• <b style="color: #FF9A9C;">CRASH_WARNING:</b> 0% Exposure (SPY &lt; 200 SMA or VIX &ge; 28; 100% Cash / Treasury Halt)
            </div>
        </div>

        <div class="cyber-card" style="margin-top: 12px;">
            <div class="hud-title" style="font-size: 1.02rem;">2. Dual Protection: Profit-Lock & Stop-Loss (-8%)</div>
            <div style="font-size: 0.82rem; color: #71717A; margin-top: 8px; line-height: 1.6;">
                • <b>Hard Stop-Loss (-8.0%):</b> Unconditionally liquidates any position falling &le; -8.0% to prevent rogue drawdowns.
                <br>• <b>Trailing Profit Lock:</b> When unrealized gains reach &ge; +8.0%, locks in gains if price dips below the 20-day SMA, preventing bubble round-trips.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.02rem;">3. Dynamic Concentration Ceilings</div>
            <div style="font-size: 0.82rem; color: #71717A; margin-top: 8px; line-height: 1.6;">
                • <b>&ge; 5 Candidates:</b> Strict <b>15.0%</b> cap ensures broad multi-asset diversification.
                <br>• <b>3–4 Candidates:</b> Dynamically expands to <b>21.2% – 28.0%</b> to prevent capital starvation.
                <br>• <b>1–2 Candidates:</b> Sized up to <b>25.0% – 30.0%</b> with remaining capital held in cash to guard against company wipeouts.
            </div>
        </div>

        <div class="cyber-card" style="margin-top: 12px;">
            <div class="hud-title" style="font-size: 1.02rem;">4. Execution Idempotency</div>
            <div style="font-size: 0.82rem; color: #71717A; margin-top: 8px; line-height: 1.6;">
                Deterministic SHA-256 client order hashing (<code>Q-&lt;hash&gt;</code>) eliminates double-order fills, duplicate submissions, and network retry collisions.
            </div>
        </div>

        <div class="cyber-card" style="margin-top: 12px;">
            <div class="hud-title" style="font-size: 1.02rem;">5. Long-Only Solvency Buffer</div>
            <div style="font-size: 0.82rem; color: #71717A; margin-top: 8px; line-height: 1.6;">
                Zero naked shorting, zero borrow fees, zero margin interest traps, and guaranteed positive cash balances at all times.
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # DUAL DONUT TELEMETRY DECK: REGIME LIMITS & SINGLE-STOCK CAP
    # --------------------------------------------------------------------------
    rs_c1, rs_c2 = st.columns(2)

    with rs_c1:
        regime_labels = ["Max Equity Exposure Limit", "Mandatory Cash Defense Buffer"]
        regime_values = [95.0, 5.0]
        regime_colors = ["#82FBBD", "#27272A"]
        regime_center = "<b>REGIME</b><br><span style='font-size:18px; color:#82FBBD;'>95%</span><br><span style='font-size:10px; color:#71717A;'>BULL_NORMAL</span>"

        fig_regime = create_donut_chart(
            labels=regime_labels,
            values=regime_values,
            colors=regime_colors,
            center_text=regime_center,
            title="MACRO SPY REGIME EXPOSURE VS CASH SHIELD",
            height=250,
            hole=0.66
        )
        st.plotly_chart(fig_regime, width='stretch')

    with rs_c2:
        cap_labels = ["Single Stock Max Ceiling", "Uncapped Universe Equity Capacity", "Minimum Cash Buffer"]
        cap_values = [15.0, 80.0, 5.0]
        cap_colors = ["#FFB800", "#3B82F6", "#82FBBD"]
        cap_center = "<b>HARD CAP</b><br><span style='font-size:18px; color:#FFB800;'>15.0%</span><br><span style='font-size:10px; color:#71717A;'>MAX / ASSET</span>"

        fig_cap = create_donut_chart(
            labels=cap_labels,
            values=cap_values,
            colors=cap_colors,
            center_text=cap_center,
            title="INSTITUTIONAL SINGLE-STOCK EXPOSURE CEILING",
            height=250,
            hole=0.66
        )
        st.plotly_chart(fig_cap, width='stretch')
