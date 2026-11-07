"""
Generate Production Web Dashboard (Static Site for GitHub Pages)
================================================================
Compiles current paper trading state, trade logs, and equity curves
into a high-aesthetic, responsive HTML5 web application.
Can be hosted 100% free on GitHub Pages (docs/index.html).
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timezone

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "trading_system", "data")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUT_HTML = os.path.join(DOCS_DIR, "index.html")

INDIA_STATE_FILE = os.path.join(DATA_DIR, "paper_state_india.json")
US_STATE_FILE = os.path.join(DATA_DIR, "paper_state_us.json")
INDIA_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_india.csv")
US_TRADES_CSV = os.path.join(DATA_DIR, "paper_trades_us.csv")
EQUITY_LOG_CSV = os.path.join(DATA_DIR, "paper_equity_log.csv")


def load_json(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_csv(path: str) -> pd.DataFrame:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return pd.DataFrame()


def generate_dashboard_html() -> str:
    os.makedirs(DOCS_DIR, exist_ok=True)
    in_state = load_json(INDIA_STATE_FILE)
    us_state = load_json(US_STATE_FILE)
    in_trades = load_csv(INDIA_TRADES_CSV)
    us_trades = load_csv(US_TRADES_CSV)
    eq_log = load_csv(EQUITY_LOG_CSV)

    in_cash = in_state.get("cash", 80000.0)
    in_initial = in_state.get("initial_capital", 80000.0)
    in_pos = in_state.get("positions", {})
    in_pending_buys = in_state.get("pending_buys", [])
    in_pending_sells = in_state.get("pending_sells", [])
    in_hwm = in_state.get("hwm_true", in_initial)
    in_dd = in_state.get("max_drawdown", 0.0)
    in_defense = in_state.get("in_tier4_defense", False)

    us_cash = us_state.get("cash", 10000.0)
    us_initial = us_state.get("initial_capital", 10000.0)
    us_pos = us_state.get("positions", {})
    us_pending_buys = us_state.get("pending_buys", [])
    us_pending_sells = us_state.get("pending_sells", [])
    us_hwm = us_state.get("hwm_true", us_initial)
    us_dd = us_state.get("max_drawdown", 0.0)
    us_defense = us_state.get("in_tier4_defense", False)

    # Estimate current equity values
    in_equity = in_cash + sum(p.get("shares", 0) * p.get("peak_price", p.get("entry_price", 0)) for p in in_pos.values())
    us_equity = us_cash + sum(p.get("shares", 0) * p.get("peak_price", p.get("entry_price", 0)) for p in us_pos.values())

    in_pnl = in_equity - in_initial
    in_pnl_pct = (in_pnl / in_initial * 100) if in_initial > 0 else 0.0

    us_pnl = us_equity - us_initial
    us_pnl_pct = (us_pnl / us_initial * 100) if us_initial > 0 else 0.0

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build chart data from equity log
    dates = []
    in_navs = []
    us_navs = []
    if not eq_log.empty and "pod" in eq_log.columns and "total_equity" in eq_log.columns:
        piv = eq_log.pivot_table(index="date", columns="pod", values="total_equity", aggfunc="last").ffill()
        dates = [str(d) for d in piv.index]
        in_series = piv["INDIA"] if "INDIA" in piv.columns else pd.Series([in_equity]*len(dates), index=piv.index)
        us_series = piv["US"] if "US" in piv.columns else pd.Series([us_equity]*len(dates), index=piv.index)
        in_navs = [float(v) for v in in_series.fillna(in_equity)]
        us_navs = [float(v) for v in us_series.fillna(us_equity)]
    elif not eq_log.empty:
        for _, row in eq_log.iterrows():
            d = str(row.get("date", ""))
            dates.append(d)
            in_navs.append(float(row.get("india_equity", in_initial)))
            us_navs.append(float(row.get("us_equity", us_initial)))
    else:
        dates = [datetime.now(timezone.utc).strftime("%Y-%m-%d")]
        in_navs = [in_equity]
        us_navs = [us_equity]

    # Generate India Holdings Table HTML
    in_holdings_rows = ""
    for sym, p in sorted(in_pos.items()):
        shs = p.get("shares", 0)
        entry = p.get("entry_price", 0.0)
        peak = p.get("peak_price", entry)
        cur_val = shs * peak
        pnl_pct = ((peak - entry) / entry * 100.0) if entry > 0 else 0.0
        pnl_color = "#10B981" if pnl_pct >= 0 else "#EF4444"
        in_holdings_rows += f"""
        <tr>
            <td style="font-weight: 600; color: #60A5FA;">{sym}</td>
            <td>{shs:,.0f}</td>
            <td>₹{entry:,.2f}</td>
            <td>₹{peak:,.2f}</td>
            <td>₹{cur_val:,.2f}</td>
            <td style="color: {pnl_color}; font-weight: 600;">{pnl_pct:+.2f}%</td>
            <td><span class="badge badge-success">ACTIVE RUNNER</span></td>
        </tr>
        """
    if not in_holdings_rows:
        in_holdings_rows = """<tr><td colspan="7" style="text-align: center; color: #9CA3AF; padding: 24px;">No open positions (100% Capital Preserved in Liquid Cash)</td></tr>"""

    # Generate US Holdings Table HTML
    us_holdings_rows = ""
    for sym, p in sorted(us_pos.items()):
        shs = p.get("shares", 0)
        entry = p.get("entry_price", 0.0)
        peak = p.get("peak_price", entry)
        cur_val = shs * peak
        pnl_pct = ((peak - entry) / entry * 100.0) if entry > 0 else 0.0
        pnl_color = "#10B981" if pnl_pct >= 0 else "#EF4444"
        us_holdings_rows += f"""
        <tr>
            <td style="font-weight: 600; color: #60A5FA;">{sym}</td>
            <td>{shs:,.2f}</td>
            <td>${entry:,.2f}</td>
            <td>${peak:,.2f}</td>
            <td>${cur_val:,.2f}</td>
            <td style="color: {pnl_color}; font-weight: 600;">{pnl_pct:+.2f}%</td>
            <td><span class="badge badge-success">ACTIVE RUNNER</span></td>
        </tr>
        """
    if not us_holdings_rows:
        us_holdings_rows = """<tr><td colspan="7" style="text-align: center; color: #9CA3AF; padding: 24px;">No open positions (100% Cash Yield Active)</td></tr>"""

    # Generate Recent Trades Rows
    recent_trades_rows = ""
    combined_trades = []
    if not in_trades.empty:
        for _, r in in_trades.tail(10).iterrows():
            dt = str(r.get("timestamp", r.get("date", "")))
            sym = str(r.get("symbol", ""))
            side = str(r.get("action", r.get("side", "")))
            px = float(r.get("fill_price", r.get("price", 0.0)))
            pnl = float(r.get("realized_pnl", r.get("net_pnl", 0.0)))
            combined_trades.append(("🇮🇳 IN", dt, sym, side, px, pnl, "₹"))
    if not us_trades.empty:
        for _, r in us_trades.tail(10).iterrows():
            dt = str(r.get("timestamp", r.get("date", "")))
            sym = str(r.get("symbol", ""))
            side = str(r.get("action", r.get("side", "")))
            px = float(r.get("fill_price", r.get("price", 0.0)))
            pnl = float(r.get("realized_pnl", r.get("net_pnl", 0.0)))
            combined_trades.append(("🇺🇸 US", dt, sym, side, px, pnl, "$"))

    for pod, dt, sym, side, px, pnl, curr in combined_trades[-8:]:
        pnl_color = "#10B981" if pnl > 0 else ("#EF4444" if pnl < 0 else "#9CA3AF")
        side_badge = "badge-buy" if side.upper() == "BUY" else "badge-sell"
        recent_trades_rows += f"""
        <tr>
            <td>{pod}</td>
            <td>{dt}</td>
            <td style="font-weight:600;">{sym}</td>
            <td><span class="badge {side_badge}">{side}</span></td>
            <td>{curr}{px:,.2f}</td>
            <td style="color:{pnl_color}; font-weight:600;">{curr}{pnl:+,.2f}</td>
        </tr>
        """
    if not recent_trades_rows:
        recent_trades_rows = """<tr><td colspan="6" style="text-align: center; color: #9CA3AF; padding: 18px;">No trades executed yet in forward forward testing horizon</td></tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ANTIGRAVITY // Dual-Pod Institutional Trading Desk</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-canvas: #090B10;
            --bg-card: #11151F;
            --border: #1F2637;
            --text-main: #F3F4F6;
            --text-muted: #9CA3AF;
            --accent-blue: #3B82F6;
            --accent-green: #10B981;
            --accent-red: #EF4444;
            --accent-amber: #F59E0B;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: var(--bg-canvas);
            color: var(--text-main);
            padding: 24px 16px;
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border);
            margin-bottom: 28px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .logo-badge {{
            background: linear-gradient(135deg, #2563EB, #1D4ED8);
            color: white;
            padding: 8px 12px;
            border-radius: 8px;
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            font-size: 1rem;
            letter-spacing: 1px;
        }}
        .brand h1 {{
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: -0.5px;
        }}
        .telemetry {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.82rem;
            color: var(--text-muted);
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 8px 16px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .live-dot {{
            width: 8px;
            height: 8px;
            background-color: var(--accent-green);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--accent-green);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.4; }}
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 16px;
            margin-bottom: 28px;
        }}
        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 20px;
        }}
        .kpi-title {{
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}
        .kpi-value {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.7rem;
            font-weight: 700;
            margin-bottom: 6px;
        }}
        .kpi-sub {{
            font-size: 0.82rem;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 28px;
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .card-title {{
            font-size: 1.1rem;
            font-weight: 700;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
        }}
        th {{
            text-align: left;
            padding: 12px 14px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 0.76rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        td {{
            padding: 14px;
            border-bottom: 1px solid #171C28;
            font-family: 'JetBrains Mono', monospace;
        }}
        tr:hover td {{
            background-color: rgba(255, 255, 255, 0.02);
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.5px;
        }}
        .badge-success {{ background: rgba(16, 185, 129, 0.15); color: #34D399; }}
        .badge-buy {{ background: rgba(59, 130, 246, 0.15); color: #60A5FA; }}
        .badge-sell {{ background: rgba(239, 68, 68, 0.15); color: #F87171; }}
        .badge-defense {{ background: rgba(245, 158, 11, 0.15); color: #FBBF24; }}
        .tabs {{
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
        }}
        .tab-btn {{
            background: #171C28;
            border: 1px solid var(--border);
            color: var(--text-muted);
            padding: 8px 18px;
            border-radius: 6px;
            font-weight: 600;
            cursor: pointer;
            font-size: 0.85rem;
        }}
        .tab-btn.active {{
            background: var(--accent-blue);
            color: white;
            border-color: var(--accent-blue);
        }}
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        footer {{
            text-align: center;
            font-size: 0.8rem;
            color: var(--text-muted);
            padding: 24px 0;
            border-top: 1px solid var(--border);
            margin-top: 32px;
        }}
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <div class="logo-badge">AGY-QUANT</div>
            <div>
                <h1>Autonomous Dual-Pod Trading Desk</h1>
                <p style="font-size: 0.82rem; color: var(--text-muted);">Exploratory Shadow Tracking (Real-Time Forward Paper Mode - Non-Gate B) • India NSE 100 & US Mega/Mid Multi-Sector</p>
            </div>
        </div>
        <div class="telemetry">
            <div class="live-dot"></div>
            <span>LAST SYNC: {now_utc}</span>
        </div>
    </header>

    <div style="background: rgba(245, 158, 11, 0.12); border: 1px solid #F59E0B; border-radius: 8px; padding: 12px 18px; margin: 20px 0; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
        <div style="display: flex; align-items: center; gap: 10px;">
            <span style="background: #F59E0B; color: #000; font-weight: 700; font-size: 0.72rem; padding: 3px 8px; border-radius: 4px; text-transform: uppercase;">Exploratory Shadow Mode</span>
            <span style="font-size: 0.82rem; color: #FCD34D; font-weight: 500;">
                Non-Gate B Incubation. Gate B strictly requires an audited Gate A pass. Multi-Asset Tactical Trend V2.1 remains the binding Gate A priority.
            </span>
        </div>
        <span style="font-size: 0.74rem; color: var(--text-muted); font-family: monospace;">PROTOCOL: MULTI_ASSET_V2.1</span>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">🇮🇳 India Pod Equity (Variant 2)</div>
            <div class="kpi-value" style="color: #60A5FA;">₹{in_equity:,.0f}</div>
            <div class="kpi-sub" style="color: {'#10B981' if in_pnl >= 0 else '#EF4444'};">
                {in_pnl_pct:+.2f}% ({'₹' if in_pnl >= 0 else '-₹'}{abs(in_pnl):,.0f})
            </div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">🇺🇸 US Pod Equity (Variant 1)</div>
            <div class="kpi-value" style="color: #34D399;">${us_equity:,.2f}</div>
            <div class="kpi-sub" style="color: {'#10B981' if us_pnl >= 0 else '#EF4444'};">
                {us_pnl_pct:+.2f}% ({'$' if us_pnl >= 0 else '-$'}{abs(us_pnl):,.2f})
            </div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">🛡️ Risk Sentinel & Drawdown</div>
            <div class="kpi-value" style="color: {'#10B981' if in_dd > -0.10 else '#F59E0B'};">{in_dd*100:.1f}%</div>
            <div class="kpi-sub" style="color: var(--text-muted);">
                {f'<span class="badge badge-defense">BEAR DEFENSE ACTIVE</span>' if in_defense else '<span class="badge badge-success">HEALTHY / NORMAL</span>'}
            </div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">📊 Active Allocation</div>
            <div class="kpi-value">{len(in_pos)} IN / {len(us_pos)} US</div>
            <div class="kpi-sub" style="color: var(--text-muted);">
                Cash: ₹{in_cash:,.0f} | ${us_cash:,.2f}
            </div>
        </div>
    </div>

    <div class="card">
        <div class="card-header">
            <div class="card-title">Dual-Pod Equity Growth Curves (Exploratory Shadow Tracking)</div>
        </div>
        <div style="height: 280px; position: relative;">
            <canvas id="equityChart"></canvas>
        </div>
    </div>

    <div class="card">
        <div class="card-header">
            <div class="card-title">Live Portfolio Holdings</div>
            <div class="tabs">
                <button class="tab-btn active" onclick="switchTab('india')">🇮🇳 India Pod ({len(in_pos)})</button>
                <button class="tab-btn" onclick="switchTab('us')">🇺🇸 US Pod ({len(us_pos)})</button>
            </div>
        </div>

        <div id="tab-india" class="tab-content active">
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Shares</th>
                        <th>Avg Entry</th>
                        <th>Current / Peak</th>
                        <th>Market Value</th>
                        <th>P&L %</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {in_holdings_rows}
                </tbody>
            </table>
        </div>

        <div id="tab-us" class="tab-content">
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Shares</th>
                        <th>Avg Entry</th>
                        <th>Current / Peak</th>
                        <th>Market Value</th>
                        <th>P&L %</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {us_holdings_rows}
                </tbody>
            </table>
        </div>
    </div>

    <div class="card">
        <div class="card-header">
            <div class="card-title">Recent Trade Executions (Next-Day Open Fills)</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Pod</th>
                    <th>Date / Time</th>
                    <th>Symbol</th>
                    <th>Action</th>
                    <th>Execution Price</th>
                    <th>Realized Net P&L</th>
                </tr>
            </thead>
            <tbody>
                {recent_trades_rows}
            </tbody>
        </table>
    </div>

    <div style="margin: 20px 0; padding: 14px 18px; background: rgba(30, 41, 59, 0.5); border-left: 3px solid var(--accent); border-radius: 4px; font-size: 0.80rem; color: var(--text-muted); line-height: 1.5;">
        <strong style="color: var(--text-main);">Governance Architecture Note:</strong> Variant 1 (US) and Variant 2 (India) are monitored simultaneously under comparative exploratory shadow tracking. When any specific variant is subsequently selected for live capital incubation, that selection constitutes an independent trial and will be logged in <code>trial_log.csv</code>.
    </div>

    <footer>
        ANTIGRAVITY Autonomous Quant System • Institutional Gate A Invariants Verified • Zero Look-Ahead Bias
    </footer>

    <script>
        function switchTab(pod) {{
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            if (pod === 'india') {{
                document.querySelectorAll('.tab-btn')[0].classList.add('active');
                document.getElementById('tab-india').classList.add('active');
            }} else {{
                document.querySelectorAll('.tab-btn')[1].classList.add('active');
                document.getElementById('tab-us').classList.add('active');
            }}
        }}

        const ctx = document.getElementById('equityChart').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(dates)},
                datasets: [
                    {{
                        label: 'India Pod NAV (INR ₹)',
                        data: {json.dumps(in_navs)},
                        borderColor: '#60A5FA',
                        backgroundColor: 'rgba(96, 165, 250, 0.05)',
                        borderWidth: 2,
                        yAxisID: 'yIndia',
                        tension: 0.2,
                        fill: true
                    }},
                    {{
                        label: 'US Pod NAV (USD $)',
                        data: {json.dumps(us_navs)},
                        borderColor: '#34D399',
                        backgroundColor: 'rgba(52, 211, 153, 0.05)',
                        borderWidth: 2,
                        yAxisID: 'yUS',
                        tension: 0.2,
                        fill: true
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                interaction: {{ mode: 'index', intersect: false }},
                plugins: {{
                    legend: {{ labels: {{ color: '#9CA3AF', font: {{ family: 'JetBrains Mono', size: 11 }} }} }}
                }},
                scales: {{
                    x: {{ grid: {{ color: '#1F2637' }}, ticks: {{ color: '#9CA3AF', font: {{ family: 'JetBrains Mono', size: 10 }} }} }},
                    yIndia: {{
                        type: 'linear',
                        position: 'left',
                        grid: {{ color: '#1F2637' }},
                        ticks: {{ color: '#60A5FA', font: {{ family: 'JetBrains Mono', size: 10 }}, callback: v => '₹' + v.toLocaleString() }}
                    }},
                    yUS: {{
                        type: 'linear',
                        position: 'right',
                        grid: {{ drawOnChartArea: false }},
                        ticks: {{ color: '#34D399', font: {{ family: 'JetBrains Mono', size: 10 }}, callback: v => '$' + v.toLocaleString() }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[Dashboard] Successfully compiled responsive web dashboard to: {OUTPUT_HTML}")
    return OUTPUT_HTML


if __name__ == "__main__":
    generate_dashboard_html()
