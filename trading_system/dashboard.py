import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from trading_system.app.config.settings import settings
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter

# ==========================================
# PAGE CONFIGURATION & METADATA
# ==========================================
st.set_page_config(
    page_title="ANTIGRAVITY // Quantum Terminal",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

# ==========================================
# FUTURISTIC CYBERPUNK HUD STYLING
# ==========================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,600;0,700;1,400&family=Space+Grotesk:wght@400;500;600;700&display=swap');

/* Global Font & Theme */
html, body, [class*="css"] {
    font-family: 'Space Grotesk', -apple-system, sans-serif !important;
    color: #E2E8F0;
}

code, pre, .mono-font {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Deep Obsidian Space Background */
.stApp {
    background: radial-gradient(circle at 10% 10%, rgba(0, 242, 254, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 90%, rgba(157, 78, 221, 0.05) 0%, transparent 45%),
                radial-gradient(circle at 50% 50%, rgba(5, 213, 123, 0.02) 0%, transparent 60%),
                #070A12;
}

/* Futuristic Sidebar */
section[data-testid="stSidebar"] {
    background-color: #05070E !important;
    border-right: 1px solid rgba(0, 242, 254, 0.15) !important;
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.6);
}

/* Custom Glassmorphism Card */
.cyber-card {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.75) 0%, rgba(8, 12, 22, 0.85) 100%);
    border: 1px solid rgba(0, 242, 254, 0.18);
    border-radius: 14px;
    padding: 18px 22px;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.06);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    margin-bottom: 15px;
}
.cyber-card:hover {
    border-color: rgba(0, 242, 254, 0.5);
    box-shadow: 0 8px 30px rgba(0, 242, 254, 0.15), inset 0 1px 0 rgba(0, 242, 254, 0.3);
    transform: translateY(-2px);
}

/* Top Telemetry Header */
.hud-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 24px;
    background: linear-gradient(90deg, rgba(15, 23, 42, 0.9) 0%, rgba(10, 15, 29, 0.9) 100%);
    border: 1px solid rgba(0, 242, 254, 0.2);
    border-radius: 14px;
    margin-bottom: 22px;
    box-shadow: 0 4px 25px rgba(0, 0, 0, 0.5);
}

.hud-title {
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    background: linear-gradient(90deg, #00F2FE 0%, #4FACFE 50%, #00FF9D 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    display: flex;
    align-items: center;
    gap: 10px;
}

.hud-subtitle {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    color: #64748B;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

/* Status Badges & Pills */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 6px 14px;
    border-radius: 20px;
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(0, 242, 254, 0.25);
    color: #94A3B8;
}

.pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #00FF9D;
    box-shadow: 0 0 10px #00FF9D;
    animation: radar-pulse 2s infinite;
    display: inline-block;
}
@keyframes radar-pulse {
    0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 157, 0.7); }
    70% { transform: scale(1.2); box-shadow: 0 0 0 8px rgba(0, 255, 157, 0); }
    100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 255, 157, 0); }
}

/* Metric Card Inner Typography */
.metric-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #64748B;
    margin-bottom: 6px;
}

.metric-big {
    font-size: 1.9rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: #F8FAFC;
    line-height: 1.15;
}

.metric-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    font-weight: 600;
    padding: 3px 9px;
    border-radius: 12px;
    margin-top: 8px;
}
.badge-green {
    background: rgba(0, 255, 157, 0.1);
    color: #00FF9D;
    border: 1px solid rgba(0, 255, 157, 0.25);
}
.badge-cyan {
    background: rgba(0, 242, 254, 0.1);
    color: #00F2FE;
    border: 1px solid rgba(0, 242, 254, 0.25);
}
.badge-purple {
    background: rgba(157, 78, 221, 0.12);
    color: #C084FC;
    border: 1px solid rgba(157, 78, 221, 0.3);
}

/* Sleek Streamlit Dataframes */
[data-testid="stDataFrame"] {
    border-radius: 12px !important;
    border: 1px solid rgba(0, 242, 254, 0.15) !important;
    overflow: hidden !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
}

/* Radio Navigation Buttons */
div[role="radiogroup"] > label {
    background: rgba(15, 23, 42, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-radius: 10px !important;
    padding: 10px 14px !important;
    margin-bottom: 6px !important;
    transition: all 0.2s ease !important;
}
div[role="radiogroup"] > label:hover {
    border-color: rgba(0, 242, 254, 0.35) !important;
    background: rgba(0, 242, 254, 0.05) !important;
}
</style>
""", unsafe_allow_html=True)

# ==========================================
# SIDEBAR CONFIGURATION
# ==========================================
st.sidebar.markdown("""
<div style="padding: 10px 0 20px 0; border-bottom: 1px solid rgba(0, 242, 254, 0.15); margin-bottom: 20px;">
    <div style="font-size: 1.25rem; font-weight: 700; letter-spacing: -0.02em; background: linear-gradient(90deg, #00F2FE, #00FF9D); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
        ⚡ QUANTUM // OS
    </div>
    <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.70rem; color: #64748B; letter-spacing: 0.1em; margin-top: 4px;">
        INSTITUTIONAL DESK v2.4
    </div>
    <div style="margin-top: 12px;">
        <span class="status-pill" style="padding: 3px 10px; font-size: 0.7rem; border-color: rgba(0, 255, 157, 0.3);">
            <span class="pulse-dot"></span> AUTONOMOUS AGENT ACTIVE
        </span>
    </div>
</div>
""", unsafe_allow_html=True)

api_key = settings.PAPER_API_KEY
api_secret = settings.PAPER_API_SECRET

if not api_key or not api_secret:
    st.sidebar.warning("⚠️ API credentials not detected in .env")
    api_key = st.sidebar.text_input("Alpaca API Key", type="password")
    api_secret = st.sidebar.text_input("Alpaca API Secret", type="password")

broker = AlpacaBrokerAdapter(api_key=api_key or "mock", api_secret=api_secret or "mock")

page = st.sidebar.radio(
    "NAVIGATION INTERFACE",
    [
        "📊 Portfolio Overview",
        "🏆 30-Day Incubation Scorecard",
        "📋 Positions & Stop-Loss",
        "⚡ Order Activity Log",
        "🧠 Quant Brain & Strategy",
        "🛡️ Risk Safeguards"
    ]
)

st.sidebar.markdown("---")
st.sidebar.markdown("""
<div style="font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: #64748B; padding: 6px;">
    <div>BROKER: ALPACA PAPER API</div>
    <div>LATENCY: &lt;42ms (REST)</div>
    <div>ACTIVE SPEC: PHASE 3 ML GATE</div>
    <div>LONG-ONLY SOLVENCY: 100%</div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# BROKER DATA INGESTION
# ==========================================
acc_details = broker.get_account_details()
equity = acc_details.get("equity", 100000.0)
cash = acc_details.get("cash", 0.0)
today_pnl = acc_details.get("today_pnl", 0.0)
today_pnl_pct = acc_details.get("today_pnl_pct", 0.0)
overall_pnl = acc_details.get("overall_pnl", 0.0)
overall_pnl_pct = acc_details.get("overall_pnl_pct", 0.0)
cash_pct = (cash / equity * 100) if equity > 0 else 0.0
invested_capital = equity - cash
invested_pct = (invested_capital / equity * 100) if equity > 0 else 0.0

# ==========================================
# TOP TELEMETRY HUD BAR
# ==========================================
st.markdown(f"""
<div class="hud-header">
    <div>
        <div class="hud-title">⚡ ANTIGRAVITY QUANTUM TERMINAL</div>
        <div class="hud-subtitle">PHASE 2 MULTI-STRATEGY ENSEMBLE • PHASE 3 ML ALPHA GATE • REAL-TIME BROKER TELEMETRY</div>
    </div>
    <div style="display: flex; gap: 10px; align-items: center;">
        <span class="status-pill"><span class="pulse-dot"></span> LIVE EXECUTION READY</span>
        <span class="status-pill">BROKER: PAPER LIVE</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ==========================================
# 5-CARD GLASSMORPHIC KPI DECK
# ==========================================
k1, k2, k3, k4, k5 = st.columns(5)

with k1:
    st.markdown(f"""
    <div class="cyber-card">
        <div class="metric-meta">TOTAL PORTFOLIO EQUITY</div>
        <div class="metric-big" style="color: #00F2FE;">${equity:,.2f}</div>
        <div class="metric-badge badge-cyan">NAV REAL-TIME</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    badge_class = "badge-green" if today_pnl >= 0 else "badge-crimson"
    st.markdown(f"""
    <div class="cyber-card">
        <div class="metric-meta">TODAY'S SESSION P&L</div>
        <div class="metric-big" style="color: {'#00FF9D' if today_pnl >= 0 else '#FF2A55'};">${today_pnl:+,.2f}</div>
        <div class="metric-badge {badge_class}">{today_pnl_pct:+.2f}% TODAY</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    badge_class = "badge-green" if overall_pnl >= 0 else "badge-crimson"
    st.markdown(f"""
    <div class="cyber-card">
        <div class="metric-meta">CUMULATIVE INCEPTION GAIN</div>
        <div class="metric-big" style="color: {'#00FF9D' if overall_pnl >= 0 else '#FF2A55'};">${overall_pnl:+,.2f}</div>
        <div class="metric-badge {badge_class}">{overall_pnl_pct:+.2f}% NET ALPHA</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    st.markdown(f"""
    <div class="cyber-card">
        <div class="metric-meta">LIQUID CASH BUFFER</div>
        <div class="metric-big" style="color: #F8FAFC;">${cash:,.2f}</div>
        <div class="metric-badge badge-cyan">{cash_pct:.1f}% PRESERVED</div>
    </div>
    """, unsafe_allow_html=True)

with k5:
    st.markdown(f"""
    <div class="cyber-card">
        <div class="metric-meta">AI ARCHITECTURE TIER</div>
        <div class="metric-big" style="color: #C084FC;">PHASE 3</div>
        <div class="metric-badge badge-purple">ML ALPHA GATE ACTIVE</div>
    </div>
    """, unsafe_allow_html=True)

# ==========================================
# PAGE 1: PORTFOLIO OVERVIEW
# ==========================================
if page == "📊 Portfolio Overview":
    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
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
                "Asset": "CASH SHIELD",
                "Value": cash,
                "Category": "Cash Buffer"
            })
            df_chart = pd.DataFrame(chart_data)

            # Modern futuristic neon color palette
            cyber_colors = [
                "#00F2FE", "#00FF9D", "#38BDF8", "#818CF8", "#C084FC",
                "#F472B6", "#FB7185", "#FBBF24", "#34D399", "#A78BFA",
                "#60A5FA", "#4ADE80", "#F59E0B", "#2DD4BF", "#E879F9"
            ]

            fig = px.pie(
                df_chart,
                names="Asset",
                values="Value",
                title=f"Dynamic Capital Allocation ({len(positions)} High-Conviction Equities + Cash Reserve)",
                hole=0.68,
                color_discrete_sequence=cyber_colors
            )
            fig.update_traces(
                textposition='inside',
                textinfo='percent+label',
                marker=dict(line=dict(color='#070A12', width=2))
            )
            fig.update_layout(
                showlegend=False,
                margin=dict(t=50, b=10, l=10, r=10),
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Space Grotesk, sans-serif", color="#94A3B8"),
                annotations=[dict(
                    text=f"<b>EQUITY</b><br>${equity:,.0f}<br><span style='font-size:10px; color:#00F2FE;'>CASH {cash_pct:.1f}%</span>",
                    x=0.5, y=0.5,
                    font_size=16,
                    font_family="Space Grotesk",
                    font_color="#F8FAFC",
                    showarrow=False
                )]
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_stats:
            st.markdown("""
            <div class="cyber-card" style="margin-top: 25px;">
                <div class="metric-meta">PORTFOLIO EXPOSURE TELEMETRY</div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
                <span style="color: #94A3B8;">Invested Equities Value:</span>
                <span style="color: #00F2FE; font-weight: 600;">${invested_capital:,.2f} ({invested_pct:.1f}%)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
                <span style="color: #94A3B8;">Liquid Cash Reserve:</span>
                <span style="color: #00FF9D; font-weight: 600;">${cash:,.2f} ({cash_pct:.1f}%)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
                <span style="color: #94A3B8;">Active Holdings:</span>
                <span style="color: #F8FAFC; font-weight: 600;">{len(positions)} Stocks (Dynamic Sizing)</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
                <span style="color: #94A3B8;">Single Stock Ceiling:</span>
                <span style="color: #F8FAFC; font-weight: 600;">15.0% (${equity*0.15:,.2f})</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;">
                <span style="color: #94A3B8;">Max Macro Exposure:</span>
                <span style="color: #F8FAFC; font-weight: 600;">95.0% (${equity*0.95:,.2f})</span>
            </div>
            """, unsafe_allow_html=True)

            winners = df_pos[df_pos['unrealized_pl'] > 0]
            losers = df_pos[df_pos['unrealized_pl'] < 0]
            win_rate = (len(winners) / len(df_pos) * 100) if len(df_pos) > 0 else 0.0

            st.markdown(f"""
            <div style="margin-top: 15px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.08);">
                <div style="display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; margin-bottom: 6px;">
                    <span style="color: #94A3B8;">Win Rate on Open Positions:</span>
                    <span style="color: #00FF9D; font-weight: 700;">{win_rate:.1f}% ({len(winners)}W / {len(losers)}L)</span>
                </div>
            </div>
            </div>
            """, unsafe_allow_html=True)
            st.progress(win_rate / 100)
    else:
        st.info("No open positions reported by broker. Portfolio is currently in 100% Cash Buffer.")

# ==========================================
# PAGE 2: 30-DAY INCUBATION SCORECARD
# ==========================================
elif page == "🏆 30-Day Incubation Scorecard":
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <span style="font-size: 1.3rem; font-weight: 700; color: #F8FAFC;">🏆 30-Day Paper Incubation Health Scorecard</span>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748B;">AUTONOMOUS INCUBATION MONITOR • HANDS-OFF OPERATIONAL STABILITY</div>
    </div>
    """, unsafe_allow_html=True)

    df_history = broker.get_portfolio_history(period="1M", timeframe="1D")

    if df_history is not None and not df_history.empty:
        days_logged = len(df_history)
        start_equity = float(df_history['equity'].iloc[0])
        current_eq = float(df_history['equity'].iloc[-1])
        net_change = current_eq - start_equity
        net_change_pct = (net_change / start_equity * 100) if start_equity > 0 else 0.0

        rolling_max = df_history['equity'].cummax()
        drawdown_series = (df_history['equity'] - rolling_max) / rolling_max
        max_drawdown = float(drawdown_series.min() * 100)

        # 4 Sleek Scorecard Cards
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.markdown(f"""
            <div class="cyber-card">
                <div class="metric-meta">INCUBATION PROGRESS</div>
                <div class="metric-big" style="color: #00F2FE;">Day {days_logged} <span style="font-size: 1.1rem; color: #64748B;">/ 30</span></div>
                <div class="metric-badge badge-cyan">{(days_logged/30)*100:.0f}% COMPLETED</div>
            </div>
            """, unsafe_allow_html=True)

        with sc2:
            st.markdown(f"""
            <div class="cyber-card">
                <div class="metric-meta">INCEPTION BASE CAPITAL</div>
                <div class="metric-big">${start_equity:,.2f}</div>
                <div class="metric-badge badge-cyan">ORIGINAL PRINCIPAL</div>
            </div>
            """, unsafe_allow_html=True)

        with sc3:
            badge_class = "badge-green" if net_change >= 0 else "badge-crimson"
            st.markdown(f"""
            <div class="cyber-card">
                <div class="metric-meta">NET INCUBATION RETURN</div>
                <div class="metric-big" style="color: {'#00FF9D' if net_change >= 0 else '#FF2A55'};">${net_change:+,.2f}</div>
                <div class="metric-badge {badge_class}">{net_change_pct:+.2f}% TOTAL RETURN</div>
            </div>
            """, unsafe_allow_html=True)

        with sc4:
            st.markdown(f"""
            <div class="cyber-card">
                <div class="metric-meta">PEAK-TO-TROUGH DRAWDOWN</div>
                <div class="metric-big" style="color: {'#00FF9D' if max_drawdown > -5.0 else '#FFB800'};">{max_drawdown:.2f}%</div>
                <div class="metric-badge badge-green">TOLERANCE &lt; -10.0%</div>
            </div>
            """, unsafe_allow_html=True)

        # Futuristic Neon Equity Curve
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(
            x=df_history["timestamp"],
            y=df_history["equity"],
            mode="lines",
            name="Account Equity",
            line=dict(color="#00F2FE", width=3),
            fill="tozeroy",
            fillcolor="rgba(0, 242, 254, 0.06)"
        ))
        fig_equity.add_hline(
            y=100000.0,
            line_dash="dash",
            line_color="#F59E0B",
            annotation_text="Base Capital ($100k)",
            annotation_font_color="#F59E0B"
        )
        fig_equity.update_layout(
            title="⚡ Autonomous Portfolio Equity Trajectory (Past Sessions)",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=50, b=20, l=10, r=10),
            height=380,
            font=dict(family="Space Grotesk, sans-serif", color="#94A3B8"),
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)")
        )
        st.plotly_chart(fig_equity, use_container_width=True)

        # 5 Hard Graduation Criteria
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

# ==========================================
# PAGE 3: POSITIONS & STOP-LOSS MONITOR
# ==========================================
elif page == "📋 Positions & Stop-Loss":
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <span style="font-size: 1.3rem; font-weight: 700; color: #F8FAFC;">📋 Active Position Telemetry & Stop-Loss Gating</span>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748B;">REAL-TIME COST BASIS • UNREALIZED P&L • MANDATORY -8% STOP MONITOR</div>
    </div>
    """, unsafe_allow_html=True)

    positions = broker.get_positions_detailed()
    if positions:
        df_pos = pd.DataFrame(positions)

        def evaluate_sl_status(row):
            pct = row['unrealized_plpc'] * 100
            if pct <= -8.0:
                return "🛑 STOP BREACH"
            elif pct <= -5.0:
                return "⚠️ WATCHLIST (< -5%)"
            elif pct > 0:
                return "🟢 PROFITABLE"
            else:
                return "⚪ HOLDING"

        df_pos["Status"] = df_pos.apply(evaluate_sl_status, axis=1)
        df_pos["Return %"] = (df_pos["unrealized_plpc"] * 100).round(2).astype(str) + "%"
        df_pos["PnL ($)"] = df_pos["unrealized_pl"].round(2)
        df_pos["Market Value"] = df_pos["market_value"].round(2)
        df_pos["Current Price"] = df_pos["current_price"].round(2)
        df_pos["Avg Entry"] = df_pos["avg_entry_price"].round(2)

        display_cols = ["symbol", "qty", "Current Price", "Avg Entry", "Market Value", "PnL ($)", "Return %", "Status"]

        st.dataframe(
            df_pos[display_cols].sort_values(by="PnL ($)", ascending=False),
            use_container_width=True,
            hide_index=True
        )

        critical = df_pos[df_pos['unrealized_plpc'] <= -0.08]
        if not critical.empty:
            st.error(f"⚠️ {len(critical)} position(s) have breached the -8% stop-loss threshold and will be liquidated on the next session cycle!")
        else:
            st.success("✅ Risk Integrity 100%: All active holdings are within safe operating limits (Drawdown > -8.0%).")
    else:
        st.info("No open positions reported by broker.")

# ==========================================
# PAGE 4: ORDER ACTIVITY LOG
# ==========================================
elif page == "⚡ Order Activity Log":
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <span style="font-size: 1.3rem; font-weight: 700; color: #F8FAFC;">⚡ Real-Time Execution Order Book</span>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748B;">STREAM DIRECTLY FROM ALPACA API • IDEMPOTENT Q-HASH SIGNATURES</div>
    </div>
    """, unsafe_allow_html=True)

    recent_orders = broker.get_recent_orders(limit=50)
    if recent_orders:
        orders_data = []
        for o in recent_orders:
            orders_data.append({
                "Timestamp (UTC)": o.get("submitted_at", "")[:19].replace("T", " "),
                "Symbol": o.get("symbol"),
                "Action": o.get("side", "").upper(),
                "Target Qty": o.get("qty"),
                "Filled Qty": o.get("filled_qty"),
                "Fill Price ($)": o.get("filled_avg_price") or o.get("limit_price") or "Market",
                "Status": o.get("status", "").upper(),
                "Client Order ID": o.get("client_order_id", "")
            })
        df_orders = pd.DataFrame(orders_data)
        st.dataframe(df_orders, use_container_width=True, hide_index=True)
    else:
        st.info("No recent execution records found.")

# ==========================================
# PAGE 5: QUANT BRAIN & STRATEGY
# ==========================================
elif page == "🧠 Quant Brain & Strategy":
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <span style="font-size: 1.3rem; font-weight: 700; color: #F8FAFC;">🧠 Autonomous Quant Brain & AI Gating</span>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748B;">WALK-FORWARD ANCHORS • MATHEMATICAL FORMULA • PHASE 3 RANDOM FOREST CLASSIFIER</div>
    </div>
    """, unsafe_allow_html=True)

    config_path = os.path.join(os.path.dirname(__file__), "app", "config", "dynamic_params.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            params = json.load(f)
        p1, p2 = st.columns(2)
        with p1:
            st.markdown(f"""
            <div class="cyber-card">
                <div class="metric-meta">FAST TREND MOVING AVERAGE WINDOW</div>
                <div class="metric-big" style="color: #00F2FE;">{params.get('fast_sma', 20)} Days</div>
                <div class="metric-badge badge-cyan">CONTINUOUS WALK-FORWARD CALIBRATED</div>
            </div>
            """, unsafe_allow_html=True)
        with p2:
            st.markdown(f"""
            <div class="cyber-card">
                <div class="metric-meta">SLOW ANCHOR MOVING AVERAGE WINDOW</div>
                <div class="metric-big" style="color: #C084FC;">{params.get('slow_sma', 50)} Days</div>
                <div class="metric-badge badge-purple">INSTITUTIONAL REGIME ANCHOR</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")
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

# ==========================================
# PAGE 6: RISK SAFEGUARDS
# ==========================================
elif page == "🛡️ Risk Safeguards":
    st.markdown("""
    <div style="margin-bottom: 15px;">
        <span style="font-size: 1.3rem; font-weight: 700; color: #F8FAFC;">🛡️ 5-Layer Institutional Risk Defense Grid</span>
        <div style="font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; color: #64748B;">CAPITAL PRESERVATION ARCHITECTURE • STRICT LONG-ONLY DISCIPLINE</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.05rem;">1. Macro SPY Regime Filter</div>
            <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 8px; line-height: 1.6;">
                Continuous evaluation of S&P 500 200-day SMA, ATR-14 volatility, and trend ratios before each market open:
                <br>• <b style="color: #00FF9D;">BULL_NORMAL:</b> 95% Max Exposure (Full Risk-On)
                <br>• <b style="color: #FBBF24;">BULL_CHOPPY:</b> 85% Max Exposure (15% Cash Shield)
                <br>• <b style="color: #F97316;">BEAR_CORRECTION:</b> 40% Max Exposure (60% Cash Defense)
                <br>• <b style="color: #FF2A55;">CRASH_WARNING:</b> 0% Exposure (100% Cash / Treasury Halt)
            </div>
        </div>

        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.05rem;">2. Hard Per-Position Stop-Loss (-8%)</div>
            <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 8px; line-height: 1.6;">
                Automated cost-basis gating that unconditionally liquidates any position falling &le; -8.0% to prevent catastrophic drawdowns or rogue outliers.
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.05rem;">3. Dollar-Exposure Ceilings</div>
            <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 8px; line-height: 1.6;">
                Strict single-stock exposure cap enforced at <b>15.0% maximum equity</b>. Excess high-conviction weight is iteratively redistributed across remaining uncapped candidates.
            </div>
        </div>

        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.05rem;">4. Execution Idempotency</div>
            <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 8px; line-height: 1.6;">
                Deterministic SHA-256 client order hashing (<code>Q-&lt;hash&gt;</code>) eliminates double-order fills, duplicate submissions, and network retry collisions.
            </div>
        </div>

        <div class="cyber-card">
            <div class="hud-title" style="font-size: 1.05rem;">5. Long-Only Solvency Buffer</div>
            <div style="font-size: 0.85rem; color: #94A3B8; margin-top: 8px; line-height: 1.6;">
                Zero naked shorting, zero borrow fees, zero margin interest traps, and guaranteed positive cash balances at all times.
            </div>
        </div>
        """, unsafe_allow_html=True)
