import os
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from screener.symbol_mapper import SymbolMapper
from screener.market_data import get_market_cap_inr_crores
from screener.downloader import fetch_latest_xbrl
from screener.xbrl_parser import parse_xbrl_primitives
from screener.cloud_auditor import audit_footnotes_online
from screener.engine import evaluate_all_criteria

console = Console()


def run():
    parser = argparse.ArgumentParser(description="Terminal Shariah Screener (Ind-AS)")
    parser.add_argument("--ticker", required=True, help="NSE Ticker (e.g., TCS, INFY, RELIANCE)")
    parser.add_argument("--xbrl", required=False, help="Direct path to an Ind-AS XBRL XML file (optional)")
    parser.add_argument("--notes_file", required=False, help="Path to plain text extract of footnotes (optional)")
    args = parser.parse_args()

    ticker = args.ticker.upper().strip()
    console.print(f"[bold cyan][*] Resolving BSE code for {ticker}...[/bold cyan]")

    mapper = SymbolMapper()
    bse_code = mapper.resolve_to_bse(ticker)
    if not bse_code:
        console.print(f"[bold red][-] Could not resolve BSE Scrip Code for {ticker}.[/bold red]")
        return

    console.print(f"[green][+] Mapped {ticker} -> BSE: {bse_code}[/green]")

    # 1. Market Cap
    console.print("[bold cyan][*] Fetching live Market Cap...[/bold cyan]")
    mcap = get_market_cap_inr_crores(ticker)
    console.print(f"[green][+] Market Cap: ₹{mcap:,.2f} Cr[/green]")

    # 2. Get XBRL filing (via local file or automated BSE download)
    if args.xbrl and os.path.exists(args.xbrl):
        xbrl_path = args.xbrl
        console.print(f"[green][+] Using local XBRL: {xbrl_path}[/green]")
    else:
        console.print("[bold cyan][*] Fetching latest XBRL filing from BSE...[/bold cyan]")
        xbrl_path = fetch_latest_xbrl(bse_code)
        if not xbrl_path:
            console.print("[bold red][-] Failed to locate/download XBRL from BSE.[/bold red]")
            return
        console.print(f"[green][+] Downloaded: {xbrl_path}[/green]")

    # 3. Parse XBRL
    console.print("[bold cyan][*] Parsing primary Ind-AS financial tags...[/bold cyan]")
    financials = parse_xbrl_primitives(xbrl_path, ticker_symbol=ticker)

    # 4. Footnote Audit (online LLM)
    notes_content = ""
    if args.notes_file and os.path.exists(args.notes_file):
        with open(args.notes_file, "r", encoding="utf-8") as f:
            notes_content = f.read()
    else:
        notes_content = "Interest income on fixed deposits: INR 0. No non-permissible segment revenue."

    console.print("[bold cyan][*] Running online footnote audit...[/bold cyan]")
    audit_data = audit_footnotes_online(notes_content)

    # 5. Evaluate All 6 Criteria
    results = evaluate_all_criteria(mcap, financials, audit_data)

    # Display Results
    table = Table(title=f"Shariah Compliance Screen: {ticker} (BSE: {bse_code})")
    table.add_column("Rule", style="white", justify="left")
    table.add_column("Computed Value", justify="center")
    table.add_column("Benchmark", justify="center")
    table.add_column("Status", justify="center")

    for rule, data in results["results"].items():
        status_str = "[green]PASS[/green]" if data["status"] else "[red]FAIL[/red]"
        table.add_row(rule, data["metric"], data["threshold"], status_str)

    console.print(table)

    verdict = (
        "[bold green]VERDICT: SHARIAH COMPLIANT[/bold green]"
        if results["is_compliant"]
        else "[bold red]VERDICT: NON-COMPLIANT[/bold red]"
    )
    console.print(Panel(verdict, expand=False))


if __name__ == "__main__":
    run()