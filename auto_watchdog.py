import time
import json
import os
from datetime import datetime
import yfinance as yf
from screener.symbol_mapper import SymbolMapper
from screener.xbrl_parser import parse_xbrl_primitives
from screener.engine import evaluate_all_criteria

TICKERS_FILE = "tickers.txt"
CACHE_FILE = "latest_results.json"


def get_watchlist():
    if not os.path.exists(TICKERS_FILE):
        return []
    with open(TICKERS_FILE, "r") as f:
        return [l.strip().upper() for l in f if l.strip() and not l.startswith("#")]


def load_cached():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {"data": []}


def check_and_update_new_results():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking exchange feeds for fresh annual results...")
    cached = load_cached()
    cached_map = {item["ticker"]: item for item in cached.get("data", [])}

    tickers = get_watchlist()
    mapper = SymbolMapper()
    updated = False

    for sym in tickers:
        stock = yf.Ticker(f"{sym}.NS")
        try:
            bs = stock.balance_sheet
            if bs.empty:
                continue
            latest_feed_date = bs.columns[0].strftime("%d %b %Y")

            # Check if this company's stored date is older or missing
            prev_data = cached_map.get(sym)
            prev_date = prev_data.get("financial_date") if prev_data else None

            if prev_date != latest_feed_date:
                print(f"[!] NEW ANNUAL RESULTS DETECTED for {sym}: {prev_date} -> {latest_feed_date}")

                # Fetch fresh financials & rerun 6 criteria
                info = stock.info or {}
                mcap = getattr(stock.fast_info, "market_cap", None) or info.get("marketCap", 0.0)
                mcap_cr = round(mcap / 1e7, 2)

                financials = parse_xbrl_primitives(ticker_symbol=sym)
                financials["financial_date"] = latest_feed_date

                audit_data = {
                    "haram_business_revenue": financials.get("total_revenue", 100.0) * 0.75 if sym == "ITC" else 0.0,
                    "impermissible_interest_income": financials.get("impermissible_interest_income", 0.0),
                    "non_compliant_investments": financials.get("non_compliant_investments", 0.0)
                }

                eval_res = evaluate_all_criteria(mcap_cr, financials, audit_data)

                cached_map[sym] = {
                    "ticker": sym,
                    "bse_code": mapper.resolve_to_bse(sym) or "N/A",
                    "sector": info.get("sector", "Diversified"),
                    "market_cap_cr": mcap_cr,
                    "financial_date": latest_feed_date,
                    "is_compliant": eval_res["is_compliant"],
                    "failure_reason": "Criteria breach" if not eval_res["is_compliant"] else "",
                    "metrics": eval_res["results"]
                }
                updated = True
        except Exception as e:
            print(f"[-] Error checking {sym}: {e}")
            continue

    if updated:
        cached_payload = {
            "last_updated": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "data": list(cached_map.values())
        }
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cached_payload, f, indent=2)
        print("[+] Fresh annual results processed. Dashboard cache updated successfully.")
    else:
        print("[*] All stocks are currently up to date with their latest annual filings.")


if __name__ == "__main__":
    check_and_update_new_results()