import os
import json
import time
import argparse
from typing import Dict, List, Any
import yfinance as yf
from rich.console import Console
from rich.table import Table

from screener.constants import (
    MAX_DEBT_TO_ASSETS_PCT,
    MIN_ILLIQUID_ASSETS_PCT
)

console = Console()

DEFAULT_WATCHLIST = [
    "TCS", "INFY", "RELIANCE", "HDFCBANK",
    "ITC", "LT", "TATAMOTORS", "SUNPHARMA",
    "BAJFINANCE", "ASIANPAINT"
]


def run_stage1_screen(ticker_symbol: str) -> Dict[str, Any]:
    clean_ticker = ticker_symbol.upper().replace(".NS", "").strip()
    stock = yf.Ticker(f"{clean_ticker}.NS")

    result = {
        "ticker": clean_ticker,
        "sector": "Unknown",
        "passed": False,
        "reason": "",
        "metrics": {}
    }

    try:
        info = stock.info
        fast_info = stock.fast_info

        # 1. Sector Check (Criteria 1: Instant filter for conventional financial institutions)
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        result["sector"] = sector

        if "Financial" in sector or "Bank" in industry or "Credit" in industry:
            result["reason"] = f"Failed C1: Financial/Banking Sector ({industry})"
            return result

        # Fetch Market Cap (₹ Cr)
        mcap = getattr(fast_info, "market_cap", None) or info.get("marketCap", 0.0)
        mcap_cr = mcap / 1e7

        # Balance Sheet Data
        bs = stock.balance_sheet
        if bs.empty or "Total Assets" not in bs.index:
            result["reason"] = "Incomplete balance sheet data on feed"
            return result

        total_assets = float(bs.loc["Total Assets"].iloc[0]) / 1e7
        if total_assets <= 0:
            result["reason"] = "Total Assets <= 0"
            return result

        # Debt (Criteria 3)
        total_debt = float(bs.loc["Total Debt"].iloc[0]) / 1e7 if "Total Debt" in bs.index else 0.0
        debt_ratio = (total_debt / total_assets) * 100
        c3_pass = debt_ratio < MAX_DEBT_TO_ASSETS_PCT

        # Illiquid Assets (Criteria 4)
        illiquid_total = 0.0
        for tag in ["Net PPE", "Goodwill And Other Intangible Assets", "Goodwill", "Other Intangible Assets", "Leases",
                    "Inventory"]:
            if tag in bs.index:
                val = float(bs.loc[tag].iloc[0])
                if val > 0:
                    illiquid_total += val
        illiquid_ratio = ((illiquid_total / 1e7) / total_assets) * 100
        c4_pass = illiquid_ratio >= MIN_ILLIQUID_ASSETS_PCT

        # Liquid Assets vs Market Cap (Criteria 5)
        cash_rec = 0.0
        for tag in ["Cash Cash Equivalents And Short Term Investments", "Receivables"]:
            if tag in bs.index:
                val = float(bs.loc[tag].iloc[0])
                if val > 0:
                    cash_rec += val
        liquid_cr = cash_rec / 1e7

        total_liab = 0.0
        for tag in ["Total Liabilities Net Minority Interest", "Total Non Current Liabilities Net Minority Interest"]:
            if tag in bs.index:
                total_liab = float(bs.loc[tag].iloc[0]) / 1e7
                break

        net_liquid = liquid_cr - total_liab
        c5_pass = net_liquid < mcap_cr

        # Aggregate Result
        result["metrics"] = {
            "Debt_Ratio": f"{debt_ratio:.1f}% (<{MAX_DEBT_TO_ASSETS_PCT}%)",
            "Illiquid_Ratio": f"{illiquid_ratio:.1f}% (>={MIN_ILLIQUID_ASSETS_PCT}%)",
            "Net_Liquid_vs_MCap": f"₹{net_liquid:.0f}Cr < ₹{mcap_cr:.0f}Cr"
        }

        if c3_pass and c4_pass and c5_pass:
            result["passed"] = True
        else:
            failures = []
            if not c3_pass: failures.append(f"High Debt ({debt_ratio:.1f}%)")
            if not c4_pass: failures.append(f"Low Illiquid Assets ({illiquid_ratio:.1f}%)")
            if not c5_pass: failures.append("Net Liquid >= MCap")
            result["reason"] = ", ".join(failures)

    except Exception as e:
        result["reason"] = f"Error: {str(e)[:40]}"

    return result


def batch_screen(tickers: List[str], output_file: str = "stage1_candidates.json"):
    console.print(f"[bold cyan][*] Running Stage 1 Quantitative Filter on {len(tickers)} stocks...[/bold cyan]\n")

    passed_stocks = []

    table = Table(title="Stage 1: Quantitative Batch Screening")
    table.add_column("Ticker", style="bold white", justify="left")
    table.add_column("Sector", justify="left")
    table.add_column("Debt / Assets (<33%)", justify="center")
    table.add_column("Illiquid / Assets (>=20%)", justify="center")
    table.add_column("Stage 1 Status", justify="center")
    table.add_column("Elimination Reason / Notes", justify="left")

    for ticker in tickers:
        data = run_stage1_screen(ticker)
        time.sleep(0.5)  # Safe delay between API calls

        if data["passed"]:
            status_str = "[bold green]PASS[/bold green]"
            passed_stocks.append(data["ticker"])
            table.add_row(
                data["ticker"],
                data["sector"][:18],
                data["metrics"].get("Debt_Ratio", "-"),
                data["metrics"].get("Illiquid_Ratio", "-"),
                status_str,
                "[green]Eligible for Stage 2 Audit[/green]"
            )
        else:
            status_str = "[bold red]FAIL[/bold red]"
            table.add_row(
                data["ticker"],
                data["sector"][:18],
                data["metrics"].get("Debt_Ratio", "-"),
                data["metrics"].get("Illiquid_Ratio", "-"),
                status_str,
                f"[dim red]{data['reason']}[/dim red]"
            )

    console.print(table)

    # Save qualifying candidates for Stage 2
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(passed_stocks, f, indent=2)

    console.print(f"\n[bold green][+] {len(passed_stocks)}/{len(tickers)} stocks passed Stage 1.[/bold green]")
    console.print(f"[cyan][*] Qualified candidates saved to: [bold]{output_file}[/bold][/cyan]")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 1 Batch Screener")
    parser.add_argument("--tickers", nargs="+", help="List of NSE tickers (e.g. TCS INFY RELIANCE)")
    args = parser.parse_args()

    ticker_pool = args.tickers if args.tickers else DEFAULT_WATCHLIST
    batch_screen(ticker_pool)