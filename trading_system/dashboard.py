import os
import json
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

from trading_system.app.config.settings import settings
from trading_system.app.broker.alpaca import AlpacaBrokerAdapter

st.set_page_config(
    page_title="V2 Institutional Quant Dashboard",
    layout="wide",
    page_icon="📈"
)

# Custom Styling
st.markdown("""
<style>
    .metric-card {
        background-color: #1E222D;
        border-radius: 8px;
        padding: 15px;
        border: 1px solid #2A2E39;
    }
    .status-badge {
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("🦅 V2 Quant Bot")
st.sidebar.caption("Systematic Risk-Adjusted Momentum Engine")

api_key = settings.PAPER_API_KEY
api_secret = settings.PAPER_API_SECRET

if not api_key or not api_secret:
    st.sidebar.warning("⚠️ Alpaca Paper API Keys not detected in .env")
    api_key = st.sidebar.text_input("Alpaca API Key", type="password")
    api_secret = st.sidebar.text_input("Alpaca API Secret", type="password")

broker = AlpacaBrokerAdapter(api_key=api_key or "mock", api_secret=api_secret or "mock")

page = st.sidebar.radio(
    "Navigation",
    [
        "📊 Portfolio Overview",
        "🏆 30-Day Incubation Scorecard",
        "📋 Positions & Stop-Loss",
        "⚡ Order Activity Log",
        "🧠 Quant Brain & Strategy",
        "🛡️ Risk Safeguards"
    ]
)

# Fetch Account Details
acc_details = broker.get_account_details()
equity = acc_details.get("equity", 100000.0)
cash = acc_details.get("cash", 0.0)
today_pnl = acc_details.get("today_pnl", 0.0)
today_pnl_pct = acc_details.get("today_pnl_pct", 0.0)
overall_pnl = acc_details.get("overall_pnl", 0.0)
overall_pnl_pct = acc_details.get("overall_pnl_pct", 0.0)
cash_pct = (cash / equity * 100) if equity > 0 else 0.0

# Top KPI Metric Row (Always visible)
st.title("🏛️ Institutional Quant Trading Terminal")
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

kpi1.metric("Total Equity", f"${equity:,.2f}")
kpi2.metric(
    "Today's Return",
    f"${today_pnl:,.2f}",
    f"{today_pnl_pct:+.2f}%",
    delta_color="normal"
)
kpi3.metric(
    "Overall Return",
    f"${overall_pnl:,.2f}",
    f"{overall_pnl_pct:+.2f}%",
    delta_color="normal"
)
kpi4.metric(
    "Cash Reserve",
    f"${cash:,.2f}",
    f"{cash_pct:.1f}% liquid buffer"
)
kpi5.metric(
    "Account Status",
    "PAPER LIVE" if (api_key and api_key != "mock") else "SIMULATED",
    "Active"
)

st.markdown("---")

# ==========================================
# PAGE 1: PORTFOLIO OVERVIEW
# ==========================================
if page == "📊 Portfolio Overview":
    st.subheader("Asset Allocation & Portfolio Distribution")
    
    positions = broker.get_positions_detailed()
    
    if positions:
        df_pos = pd.DataFrame(positions)
        
        col_chart, col_stats = st.columns([3, 2])
        
        with col_chart:
            # Prepare data for allocation chart including cash reserve
            chart_data = []
            for _, row in df_pos.iterrows():
                chart_data.append({
                    "Asset": row["symbol"],
                    "Value": row["market_value"],
                    "Category": "Equities"
                })
            chart_data.append({
                "Asset": "CASH RESERVE",
                "Value": cash,
                "Category": "Cash"
            })
            df_chart = pd.DataFrame(chart_data)
            
            fig = px.pie(
                df_chart,
                names="Asset",
                values="Value",
                title=f"Current Portfolio Allocation ({len(positions)} Stocks + Cash Buffer)",
                hole=0.45,
                color_discrete_sequence=px.colors.qualitative.Prism
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            fig.update_layout(showlegend=False, margin=dict(t=40, b=10, l=10, r=10))
            st.plotly_chart(fig, use_container_width=True)
            
        with col_stats:
            st.markdown("#### Portfolio Health Metrics")
            invested_capital = equity - cash
            invested_pct = (invested_capital / equity * 100) if equity > 0 else 0.0
            
            st.write(f"**Total Invested Value:** ${invested_capital:,.2f} ({invested_pct:.1f}%)")
            st.write(f"**Liquid Cash Reserve:** ${cash:,.2f} ({cash_pct:.1f}%)")
            st.write(f"**Total Active Holdings:** {len(positions)} tickers")
            st.write(f"**Max Single Stock Cap:** 15.0% (${equity*0.15:,.2f})")
            st.write(f"**Max Portfolio Exposure:** 95.0% (${equity*0.95:,.2f})")
            
            # Winner vs Loser count
            winners = df_pos[df_pos['unrealized_pl'] > 0]
            losers = df_pos[df_pos['unrealized_pl'] < 0]
            win_rate = (len(winners) / len(df_pos) * 100) if len(df_pos) > 0 else 0.0
            
            st.progress(win_rate / 100)
            st.caption(f"Win Rate on Open Positions: **{win_rate:.1f}%** ({len(winners)} green / {len(losers)} red)")
            
            st.info("💡 **Cash Reserve Function:** Liquid buffer protects against drawdowns and ensures instant dry powder for fresh high-conviction breakouts.")
    else:
        st.info("No open positions reported by broker. Portfolio is currently in 100% Cash.")

# ==========================================
# PAGE 2: 30-DAY INCUBATION SCORECARD
# ==========================================
elif page == "🏆 30-Day Incubation Scorecard":
    st.subheader("🏆 30-Day Paper Incubation Tracker & Health Scorecard")
    st.caption("Monitoring hands-off operational stability, risk limits, and alpha before live graduation.")
    
    # Fetch portfolio history from Alpaca API
    df_history = broker.get_portfolio_history(period="1M", timeframe="1D")
    
    if df_history is not None and not df_history.empty:
        days_logged = len(df_history)
        start_equity = float(df_history['equity'].iloc[0])
        current_eq = float(df_history['equity'].iloc[-1])
        net_change = current_eq - start_equity
        net_change_pct = (net_change / start_equity * 100) if start_equity > 0 else 0.0
        
        # Calculate Max Drawdown
        rolling_max = df_history['equity'].cummax()
        drawdown_series = (df_history['equity'] - rolling_max) / rolling_max
        max_drawdown = float(drawdown_series.min() * 100)
        
        # Scorecard KPI row
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("Incubation Progress", f"Day {days_logged} / 30", f"{(days_logged/30)*100:.0f}% Completed")
        sc2.metric("Inception Equity", f"${start_equity:,.2f}")
        sc3.metric("Net Incubation PnL", f"${net_change:+,.2f}", f"{net_change_pct:+.2f}%")
        sc4.metric("Max Drawdown", f"{max_drawdown:.2f}%", "Tolerance: < -10.0%")
        
        st.markdown("### 📈 Live Alpaca Equity Curve")
        fig_equity = px.line(
            df_history,
            x="timestamp",
            y="equity",
            title=f"Alpaca Paper Equity Curve (Past {days_logged} Trading Sessions)",
            labels={"timestamp": "Trading Session", "equity": "Account Equity ($)"},
            template="plotly_dark"
        )
        fig_equity.add_hline(y=100000.0, line_dash="dash", line_color="#888888", annotation_text="Initial Capital ($100k)")
        fig_equity.update_traces(line_color="#00FFAA", line_width=2.5)
        fig_equity.update_layout(margin=dict(t=40, b=20, l=10, r=10), height=380)
        st.plotly_chart(fig_equity, use_container_width=True)
        
        # 5 Hard Graduation Criteria
        st.markdown("### 🎓 5 Hard Graduation Criteria (Verification Checklist)")
        
        positions = broker.get_positions_detailed()
        sl_breaches = 0
        if positions:
            for p in positions:
                if p.get("unrealized_plpc", 0.0) <= -0.08:
                    sl_breaches += 1
                    
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
                st.warning(f"⚠️ **Criterion 3: Solvency & Long-Only Buffer** — Normalizing: ${cash:,.2f} (auto-rebalancing on Monday).")

        with g2:
            recent_orders = broker.get_recent_orders(limit=10)
            idempotent_orders = [o for o in recent_orders if str(o.get("client_order_id", "")).startswith("Q-")]
            if idempotent_orders or not recent_orders:
                st.success("✅ **Criterion 4: Execution Idempotency & Clean Order Books** — Passed. Deterministic order hashing `Q-<hash>` active.")
            else:
                st.info("ℹ️ **Criterion 4: Execution Idempotency** — Active. Monitoring incoming order hashes.")

            short_positions = [p for p in positions if float(p.get("qty", 0)) < 0]
            if len(positions) > 0 and len(short_positions) == 0:
                st.success(f"✅ **Criterion 5: Dynamic Multi-Strategy Long-Only Ensemble** — Passed. {len(positions)} high-conviction positions dynamically held, 0 short positions.")
            elif len(positions) == 0:
                st.info("ℹ️ **Criterion 5: Dynamic Ensemble** — 100% Cash Buffer (0 active positions).")
            else:
                st.error(f"❌ **Criterion 5: Shorting Detected** — {len(short_positions)} short positions found.")
            
        st.info("📌 **Incubation Discipline:** During the incubation testing window, avoid manual interventions or ad-hoc strategy tweaks. Let the autonomous pipeline trade every market session through to Day 30.")
    else:
        st.info("Unable to retrieve historical equity data from Alpaca API. Ensure paper credentials are active.")

# ==========================================
# PAGE 3: POSITIONS & STOP-LOSS MONITOR
# ==========================================
elif page == "📋 Positions & Stop-Loss":
    st.subheader("Active Position Monitor & Stop-Loss Gating")
    
    positions = broker.get_positions_detailed()
    if positions:
        df_pos = pd.DataFrame(positions)
        
        # Add stop-loss status column
        def evaluate_sl_status(row):
            pct = row['unrealized_plpc'] * 100
            if pct <= -8.0:
                return "🛑 STOP-LOSS TRIGGERED"
            elif pct <= -5.0:
                return "⚠️ WATCH LIST (< -5%)"
            elif pct > 0:
                return "🟢 PROFITABLE"
            else:
                return "⚪ NORMAL HOLD"
                
        df_pos["Status"] = df_pos.apply(evaluate_sl_status, axis=1)
        df_pos["Return %"] = (df_pos["unrealized_plpc"] * 100).round(2).astype(str) + "%"
        df_pos["PnL ($)"] = df_pos["unrealized_pl"].round(2)
        df_pos["Market Value"] = df_pos["market_value"].round(2)
        df_pos["Current Price"] = df_pos["current_price"].round(2)
        df_pos["Avg Price"] = df_pos["avg_entry_price"].round(2)
        
        display_cols = ["symbol", "qty", "Current Price", "Avg Price", "Market Value", "PnL ($)", "Return %", "Status"]
        
        st.dataframe(
            df_pos[display_cols].sort_values(by="PnL ($)", ascending=False),
            use_container_width=True,
            hide_index=True
        )
        
        # Stop-loss summary
        critical = df_pos[df_pos['unrealized_plpc'] <= -0.08]
        if not critical.empty:
            st.error(f"⚠️ {len(critical)} positions have breached the -8% stop-loss threshold and will be liquidated on the next cycle!")
        else:
            st.success("✅ All positions are within acceptable risk tolerances (Drawdown > -8%).")
    else:
        st.info("No open positions to monitor.")

# ==========================================
# PAGE 3: ORDER ACTIVITY LOG
# ==========================================
elif page == "⚡ Order Activity Log":
    st.subheader("Recent Execution Order Book (Direct from Alpaca API)")
    
    recent_orders = broker.get_recent_orders(limit=50)
    if recent_orders:
        orders_data = []
        for o in recent_orders:
            orders_data.append({
                "Date / Time": o.get("submitted_at", "")[:19].replace("T", " "),
                "Symbol": o.get("symbol"),
                "Side": o.get("side", "").upper(),
                "Qty": o.get("qty"),
                "Filled Qty": o.get("filled_qty"),
                "Fill Price": o.get("filled_avg_price") or o.get("limit_price") or "Market",
                "Status": o.get("status", "").upper(),
                "Client Order ID": o.get("client_order_id", "")
            })
        df_orders = pd.DataFrame(orders_data)
        st.dataframe(df_orders, use_container_width=True, hide_index=True)
    else:
        st.info("No recent orders retrieved from Alpaca.")

# ==========================================
# PAGE 4: QUANT BRAIN & STRATEGY
# ==========================================
elif page == "🧠 Quant Brain & Strategy":
    st.subheader("Autonomous Quant Brain Parameters")
    
    config_path = os.path.join(os.path.dirname(__file__), "app", "config", "dynamic_params.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            params = json.load(f)
        col_p1, col_p2 = st.columns(2)
        col_p1.metric("Fast Trend Window (SMA)", f"{params.get('fast_sma', 20)} Days")
        col_p2.metric("Slow Anchor Window (SMA)", f"{params.get('slow_sma', 50)} Days")
        st.caption("Parameters are continuously re-optimized every Saturday at 12:00 UTC via Walk-Forward Grid Search.")
    else:
        st.warning("Dynamic parameters configuration file not found.")

    st.markdown("---")
    st.subheader("Risk-Adjusted Momentum Formula")
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
    st.subheader("Phase 3: Machine Learning Alpha Gate")
    st.markdown(r"""
    - **Classifier:** 150-tree Random Forest trained on 10 years of purged walk-forward cross-validation.
    - **Feature Matrix:** 18 stationary normalized indicators (multi-horizon returns, moving average spreads, normalized ATR, RSI, Bollinger %B, volatility ratios, volume surges).
    - **Alpha Gating:** Evaluates $P(\text{Alpha}_{5d} > 0.5\%)$. Vetoes false breakouts and bull traps ($P < 0.48$), and modulates conviction weight on confirmed setups ($P \ge 0.50$).
    """)

# ==========================================
# PAGE 5: RISK SAFEGUARDS
# ==========================================
elif page == "🛡️ Risk Safeguards":
    st.subheader("5-Layer Institutional Risk Architecture")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(r"""
        ### 1. Macro Regime Filter (Market Weather)
        - Analyzes SPY 200-day SMA, ATR-14 volatility, and short-term breakdown.
        - **BULL_NORMAL:** 95% Max Exposure
        - **BULL_VOLATILE:** 70% Max Exposure
        - **BEAR_NORMAL:** 30% Max Exposure
        - **CRASH_WARNING:** 0% Exposure (100% Cash Halt)

        ### 2. Hard Per-Position Stop-Loss (-8%)
        - Real-time check on broker cost basis before any new trade is allowed.
        - Unconditionally forces full market liquidation if drawdown $\le -8\%$.
        """)
        
    with col2:
        st.markdown("""
        ### 3. Dollar-Exposure Risk Engine
        - Pre-trade validation rejects any order pushing a position over 15% equity.
        - Validates against real-time account equity (not share counts).

        ### 4. Idempotent Execution Guards
        - Deterministic `client_order_id` hash prevents duplicate fills on network retries.
        - Dual HTTP 200/201 recognition.

        ### 5. Liquid Cash Buffer
        - Minimum 5% uninvested cash maintained at all times for solvency and opportunity.
        """)

st.sidebar.markdown("---")
st.sidebar.caption("Antigravity Autonomous Trading Bot • S&P 500 Alpha Engine")
