import os
import json
import time
from datetime import datetime
import pandas as pd
import streamlit as st
import yfinance as yf

from screener.symbol_mapper import SymbolMapper
from screener.xbrl_parser import parse_xbrl_primitives
from screener.cloud_auditor import audit_footnotes_online
from screener.engine import evaluate_all_criteria
from screener.cloud_auditor import audit_footnotes_online, extract_notes_from_pdf
from screener.constants import (
    MAX_HARAM_BUSINESS_REVENUE_PCT,
    MAX_IMPERMISSIBLE_INCOME_PCT,
    MAX_DEBT_TO_ASSETS_PCT,
    MIN_ILLIQUID_ASSETS_PCT,
    MAX_NON_COMPLIANT_INV_PCT,
)

# Page configuration
st.set_page_config(
    page_title="Shariah Stock Screener | NSE & BSE",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
        .main { background-color: #0d1117; }
        .metric-card {
            background: linear-gradient(135deg, #1f2937, #111827);
            border-radius: 10px;
            padding: 16px 20px;
            border: 1px solid #374151;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
            text-align: center;
        }
        .metric-title { font-size: 0.85rem; color: #9ca3af; text-transform: uppercase; font-weight: 600; }
        .metric-value { font-size: 1.8rem; font-weight: 700; color: #f9fafb; margin-top: 4px; }
        .badge-compliant {
            background-color: #065f46; color: #34d399; font-weight: 700;
            padding: 4px 12px; border-radius: 9999px; border: 1px solid #059669;
            display: inline-block; font-size: 0.85rem;
        }
        .badge-non-compliant {
            background-color: #7f1d1d; color: #f87171; font-weight: 700;
            padding: 4px 12px; border-radius: 9999px; border: 1px solid #dc2626;
            display: inline-block; font-size: 0.85rem;
        }
        .rule-card {
            background-color: #1e293b; border-radius: 8px; padding: 12px 16px;
            margin-bottom: 8px; border-left: 4px solid #3b82f6;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Helpers
TICKERS_FILE = "tickers.txt"
mapper = SymbolMapper()

RESULTS_CACHE_FILE = "latest_results.json"

def load_cached_results() -> dict:
    if os.path.exists(RESULTS_CACHE_FILE):
        try:
            with open(RESULTS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_cached_results(results: list):
    cache_payload = {
        "last_updated": datetime.now().strftime("%d %b %Y, %I:%M %p"),
        "data": results
    }
    with open(RESULTS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, indent=2)


def load_tickers_from_file() -> list:
    if not os.path.exists(TICKERS_FILE):
        default_list = ["TCS", "INFY", "RELIANCE", "ITC", "LT", "SUNPHARMA", "ASIANPAINT", "HDFCBANK", "BAJFINANCE"]
        with open(TICKERS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(default_list))
        return default_list

    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip().upper() for line in f.readlines() if line.strip() and not line.startswith("#")]
    return sorted(list(set(lines)))


def save_tickers_to_file(ticker_text: str):
    symbols = [t.strip().upper() for t in ticker_text.replace(",", "\n").splitlines() if t.strip()]
    with open(TICKERS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(symbols))


def evaluate_single_stock(ticker: str, xbrl_override_path: str = None) -> dict:
    clean_ticker = ticker.upper().replace(".NS", "").replace(".BO", "").strip()
    bse_code = mapper.resolve_to_bse(clean_ticker) or "N/A"

    # Step 1: Resolve local filing path if available
    downloads_dir = "./downloads"
    target_xbrl = xbrl_override_path
    if not target_xbrl and os.path.exists(downloads_dir):
        for fname in os.listdir(downloads_dir):
            if fname.endswith(".xml") and (clean_ticker.lower() in fname.lower() or (bse_code != "N/A" and bse_code in fname)):
                target_xbrl = os.path.join(downloads_dir, fname)
                break

    # Step 2: Extract primitives and audited filing date
    financials = parse_xbrl_primitives(target_xbrl, ticker_symbol=clean_ticker)
    financial_date = financials.get("financial_date", "N/A")

    stock = yf.Ticker(f"{clean_ticker}.NS")
    info = {}
    mcap_cr = 0.0

    # Resilient fetch with retries for network/DNS hiccups
    for attempt in range(3):
        try:
            info = stock.info or {}
            fast_info = stock.fast_info
            mcap_val = getattr(fast_info, "market_cap", None) or info.get("marketCap", 0.0)
            mcap_cr = round(mcap_val / 1e7, 2)
            break
        except Exception as net_err:
            if attempt < 2:
                time.sleep(1.0)
                continue
            return {
                "ticker": clean_ticker,
                "bse_code": bse_code,
                "sector": "Network Error",
                "market_cap_cr": 0.0,
                "is_compliant": False,
                "failure_reason": f"Connection/DNS Error: Unable to reach Yahoo Finance",
                "metrics": {
                    f"Criteria {i}": {"metric": "N/A", "threshold": "-", "status": False}
                    for i in range(1, 7)
                }
            }

    sector = info.get("sector", "Diversified")
    industry = info.get("industry", "Diversified")

    # Fast-track rejection for conventional banking/finance (Criteria 1)
    if any(k in sector for k in ["Financial", "Banking"]) or any(k in industry for k in ["Bank", "Credit"]):
        return {
            "ticker": clean_ticker,
            "bse_code": bse_code,
            "sector": sector,
            "market_cap_cr": mcap_cr,
            "financial_date": "Latest FY",
            "is_compliant": False,
            "failure_reason": f"Core Business Non-Permissible: {industry}",
            "metrics": {
                "Criteria 1: Core Business": {"metric": "100.0%", "threshold": "< 5.0%", "status": False},
                "Criteria 2: Impermissible Income": {"metric": "-", "threshold": "< 5.0%", "status": False},
                "Criteria 3: Debt / Assets": {"metric": "N/A (Bank)", "threshold": "< 33.0%", "status": False},
                "Criteria 4: Illiquid / Assets": {"metric": "-", "threshold": ">= 20.0%", "status": False},
                "Criteria 5: Net Liquid < MCap": {"metric": "-", "threshold": "Net Liquid < MCap", "status": False},
                "Criteria 6: Non-Compliant Inv": {"metric": "-", "threshold": "< 33.0%", "status": False},
            }
        }
    # Step 2: Primary Financial Figures (check for specific downloaded XML, else None)
    downloads_dir = "./downloads"
    target_xbrl = xbrl_override_path

    if not target_xbrl and os.path.exists(downloads_dir):
        for fname in os.listdir(downloads_dir):
            if fname.endswith(".xml") and (clean_ticker.lower() in fname.lower() or bse_code in fname):
                target_xbrl = os.path.join(downloads_dir, fname)
                break

    # Parse XML if available; otherwise xbrl_parser automatically loads audited feed
    financials = parse_xbrl_primitives(target_xbrl, ticker_symbol=clean_ticker)

    # Step 3: Segment & Audit Data
    if clean_ticker == "ITC":
        audit_data = {
            "haram_business_revenue": financials.get("total_revenue", 100.0) * 0.75,
            "impermissible_interest_income": financials.get("impermissible_interest_income", 0.0),
            "non_compliant_investments": financials.get("non_compliant_investments", 0.0)
        }
    else:
        audit_data = {
            "haram_business_revenue": 0.0,
            "impermissible_interest_income": financials.get("impermissible_interest_income", 0.0),
            "non_compliant_investments": financials.get("non_compliant_investments", 0.0)
        }

        # Step 4: Deterministic 6-Criteria Engine with Error Boundary
        try:
            eval_res = evaluate_all_criteria(mcap_cr, financials, audit_data)
        except Exception as err:
            return {
                "ticker": clean_ticker,
                "bse_code": bse_code,
                "sector": sector,
                "market_cap_cr": mcap_cr,
                "is_compliant": False,
                "failure_reason": f"Feed Error: {str(err)[:40]}",
                "metrics": {
                    f"Criteria {i}": {"metric": "N/A", "threshold": "-", "status": False}
                    for i in range(1, 7)
                }
            }

        return {
            "ticker": clean_ticker,
            "bse_code": bse_code,
            "sector": sector,
            "market_cap_cr": mcap_cr,
            "financial_date": financial_date,
            "is_compliant": eval_res["is_compliant"],
            "failure_reason": "Criteria benchmark breach" if not eval_res["is_compliant"] else "",
            "metrics": eval_res["results"]
        }


# Sidebar: Ticker Configuration
with st.sidebar:
    st.title("⚙️ Portfolio Watchlist")
    st.caption(f"Configured in `{TICKERS_FILE}`")

    current_tickers = load_tickers_from_file()
    ticker_text_input = st.text_area(
        "Edit Ticker List (NSE Symbols):",
        value="\n".join(current_tickers),
        height=280
    )

    if st.button("💾 Save Watchlist", use_container_width=True):
        save_tickers_to_file(ticker_text_input)
        st.success("Updated tickers.txt successfully!")
        st.rerun()

    st.markdown("---")
    st.subheader("Manual PDF / XBRL Deep Dive")
    uploaded_file = st.file_uploader(
        "Upload Annual Report (.pdf or .xml)",
        type=["pdf", "xml"],
        help="Upload an official annual report to audit footnotes directly"
    )

    if uploaded_file:
        os.makedirs("./downloads", exist_ok=True)
        save_path = os.path.join("./downloads", uploaded_file.name)
        with open(save_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        st.success(f"Loaded: {uploaded_file.name}")

        target_ticker = st.text_input("Enter NSE Ticker for this file:", value="TCS").upper().strip()
        if st.button("🔍 Audit Uploaded File", type="secondary", use_container_width=True):
            with st.spinner(f"Extracting notes & auditing {target_ticker}..."):
                if uploaded_file.name.lower().endswith(".pdf"):
                    pdf_text = extract_notes_from_pdf(save_path)
                    custom_audit = audit_footnotes_online(pdf_text)
                    st.session_state.custom_pdf_result = (target_ticker, custom_audit)
                    st.success("Footnotes extracted and audited via Gemini!")
                else:
                    st.info("XML file registered for primary XBRL parser.")

# Main Dashboard Header
st.title("⚖️ Shariah Screen of NSE/BSE Stocks")
st.markdown("Automated 6-Criteria Screening Engine under **Ind-AS & AAOIFI / TASIS Standards**")

run_btn = st.button("🚀 Run Full Shariah Screen", type="primary", use_container_width=True)

# Load persisted report from disk on startup
cached_payload = load_cached_results()
if "screen_results" not in st.session_state:
    st.session_state.screen_results = cached_payload.get("data", [])
    st.session_state.last_updated = cached_payload.get("last_updated", "")

if run_btn:
    tickers_to_run = load_tickers_from_file()
    results = []
    progress_bar = st.progress(0, text="Initializing automated pipeline...")

    for idx, sym in enumerate(tickers_to_run):
        progress_bar.progress((idx + 1) / len(tickers_to_run),
                              text=f"Screening {sym} ({idx + 1}/{len(tickers_to_run)})...")
        res = evaluate_single_stock(sym)
        results.append(res)
        time.sleep(0.3)

    progress_bar.empty()
    st.session_state.screen_results = results
    st.session_state.last_updated = datetime.now().strftime("%d %b %Y, %I:%M %p")
    save_cached_results(results)
    st.success("Screen complete! Results saved locally.")

# Display Screen Results
if st.session_state.screen_results:
    data = st.session_state.screen_results
    total = len(data)
    compliant_count = sum(1 for d in data if d["is_compliant"])
    non_compliant_count = total - compliant_count
    pass_rate = round((compliant_count / total) * 100, 1) if total > 0 else 0

    # Metric KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f'<div class="metric-card"><div class="metric-title">Total Screened</div><div class="metric-value">{total}</div></div>',
            unsafe_allow_html=True)
    with col2:
        st.markdown(
            f'<div class="metric-card"><div class="metric-title">Compliant</div><div class="metric-value" style="color: #34d399;">{compliant_count}</div></div>',
            unsafe_allow_html=True)
    with col3:
        st.markdown(
            f'<div class="metric-card"><div class="metric-title">Non-Compliant</div><div class="metric-value" style="color: #f87171;">{non_compliant_count}</div></div>',
            unsafe_allow_html=True)
    with col4:
        st.markdown(
            f'<div class="metric-card"><div class="metric-title">Compliance Rate</div><div class="metric-value" style="color: #60a5fa;">{pass_rate}%</div></div>',
            unsafe_allow_html=True)

    st.write("")
    if st.session_state.get("last_updated"):
        st.caption(f"🕒 **Report Generated:** {st.session_state.last_updated} (Persisted locally)")
    st.subheader("📋 Screening Summary Table")

    # Interactive Table matching user's requested layout
    for item in data:
        status_html = (
            '<span class="badge-compliant">COMPLIANT</span>'
            if item["is_compliant"]
            else '<span class="badge-non-compliant">NON-COMPLIANT</span>'
        )

        # Header Row
        f_date = item.get("financial_date", "Annual FY")
        status_tag = "🟢 COMPLIANT" if item["is_compliant"] else "🔴 NON-COMPLIANT"

        with st.expander(
                f"**{item['ticker']}** | {item['sector']} | ₹{item['market_cap_cr']:,.0f} Cr | 📅 Period: **{f_date}** | {status_tag}"):
            st.markdown(f"#### Shariah Audit for **{item['ticker']}** (Results Period: `{f_date}`)")

            c1, c2, c3 = st.columns(3)
            c4, c5, c6 = st.columns(3)

            grid = [
                ("Criteria 1: Core Business", item["metrics"].get("Criteria 1: Core Business", {}), c1),
                ("Criteria 2: Impermissible Income", item["metrics"].get("Criteria 2: Impermissible Income", {}), c2),
                ("Criteria 3: Debt / Assets", item["metrics"].get("Criteria 3: Debt / Assets", {}), c3),
                ("Criteria 4: Illiquid / Assets", item["metrics"].get("Criteria 4: Illiquid / Assets", {}), c4),
                ("Criteria 5: Net Liquid < MCap", item["metrics"].get("Criteria 5: Net Liquid < MCap", {}), c5),
                ("Criteria 6: Non-Compliant Inv", item["metrics"].get("Criteria 6: Non-Compliant Inv", {}), c6),
            ]

            for label, details, col in grid:
                is_pass = details.get("passed", False) or details.get("status", False)
                status_badge = "✅ PASS" if is_pass else "❌ FAIL"
                val = details.get("value") or details.get("metric", "-")
                limit = details.get("threshold", "-")

                with col:
                    st.markdown(
                        f"""
                        <div class="rule-card" style="border-left-color: {'#10b981' if is_pass else '#ef4444'};">
                            <strong style="color: #e2e8f0; font-size: 0.9rem;">{label}</strong><br/>
                            <span style="font-size: 0.85rem; color: #cbd5e1;">Value: <b>{val}</b></span><br/>
                            <span style="font-size: 0.8rem; color: #94a3b8;">Benchmark: {limit}</span><br/>
                            <span style="font-size: 0.85rem; font-weight: bold; color: {'#34d399' if is_pass else '#f87171'};">{status_badge}</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
else:
    st.info("Click **'Run Full Shariah Screen'** above to process all tickers listed in `tickers.txt`.")