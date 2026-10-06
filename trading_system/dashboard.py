import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import text
from app.common.database import engine

st.set_page_config(page_title="V2 Quant Dashboard", layout="wide", page_icon="📈")

st.title("V2 Institutional Engine Dashboard")
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Live Overview", "Research & Validation", "Order Book & Risk Log"])

@st.cache_data(ttl=5)
def load_data(query):
    with engine.connect() as conn:
        return pd.read_sql_query(query, conn)

if page == "Live Overview":
    st.header("Live / Paper Trading Status")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Performance Snapshots")
        try:
            df_perf = load_data("SELECT timestamp, equity, realized_pnl, drawdown FROM performance_snapshots ORDER BY timestamp ASC")
            if not df_perf.empty:
                fig = px.line(df_perf, x="timestamp", y="equity", title="Equity Curve")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No performance data yet.")
        except Exception as e:
            st.error(f"Error loading performance: {e}")

    with col2:
        st.subheader("Active Positions")
        try:
            df_pos = load_data("SELECT symbol, quantity, average_price, updated_at FROM positions WHERE quantity != 0")
            if not df_pos.empty:
                st.dataframe(df_pos, use_container_width=True)
            else:
                st.info("No open positions.")
        except Exception as e:
            st.error(f"Error loading positions: {e}")

elif page == "Research & Validation":
    st.header("Experiment Registry & Strategy Candidates")
    
    st.subheader("Strategy Registry")
    try:
        df_strat = load_data("SELECT strategy_id, name, status, created_at FROM strategies ORDER BY created_at DESC")
        st.dataframe(df_strat, use_container_width=True)
    except Exception as e:
        st.error(f"Error loading strategies: {e}")
        
    st.subheader("Recent Experiments (Walk-Forward / Holdout)")
    try:
        df_exp = load_data("SELECT experiment_id, strategy_id, dataset_version, timestamp FROM experiments ORDER BY timestamp DESC LIMIT 20")
        st.dataframe(df_exp, use_container_width=True)
    except Exception as e:
        st.error(f"Error loading experiments: {e}")

elif page == "Order Book & Risk Log":
    st.header("Order Execution & Risk Constraints")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Recent Orders")
        try:
            df_orders = load_data("SELECT client_order_id, symbol, side, quantity, price, status, created_at FROM orders ORDER BY created_at DESC LIMIT 50")
            st.dataframe(df_orders, use_container_width=True)
        except Exception as e:
            st.error(f"Error loading orders: {e}")
            
    with col2:
        st.subheader("Risk Engine Interventions")
        try:
            df_risk = load_data("SELECT timestamp, event_type, symbol, action_taken, description FROM risk_events ORDER BY timestamp DESC LIMIT 50")
            if not df_risk.empty:
                st.dataframe(df_risk, use_container_width=True)
            else:
                st.success("No recent risk interventions.")
        except Exception as e:
            st.error(f"Error loading risk events: {e}")
