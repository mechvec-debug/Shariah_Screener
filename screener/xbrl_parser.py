import os
from lxml import etree
from typing import Dict, Any
from datetime import datetime
import pandas as pd
import yfinance as yf
from screener.constants import IND_AS_TAGS

# Extended tags
INVESTMENT_TAGS = [
    "CurrentInvestments", "InvestmentsCurrent",
    "OtherShortTermInvestments", "FinancialAssetsCurrent",
    "OtherCurrentFinancialAssets"
]
INTEREST_INCOME_TAGS = [
    "InterestIncome", "InterestIncomeFromBankDeposits",
    "InterestIncomeOthers", "OtherIncomeInterest"
]


def parse_xbrl_primitives(xml_path: str = None, ticker_symbol: str = "") -> Dict[str, Any]:
    data = {"financial_date": "Unknown"}

    # 1. Parse local XML if available
    if xml_path and os.path.exists(xml_path):
        try:
            tree = etree.parse(xml_path)
            root = tree.getroot()

            # Extract Filing / Period End Date from XBRL contexts
            date_nodes = root.xpath("//*[local-name()='endDate' or local-name()='instant']")
            if date_nodes:
                raw_date = (date_nodes[-1].text or "").strip()
                try:
                    dt = datetime.strptime(raw_date, "%Y-%m-%d")
                    data["financial_date"] = dt.strftime("%d %b %Y")
                except ValueError:
                    data["financial_date"] = raw_date

            # Extract base tags
            for metric, tags in IND_AS_TAGS.items():
                for tag in tags:
                    nodes = root.xpath(
                        f"//*[translate(local-name(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{tag.lower()}']"
                    )
                    if nodes:
                        for node in reversed(nodes):
                            txt = (node.text or "").strip()
                            try:
                                val = float(txt)
                                data[metric] = val / 1e7 if val > 1e7 else val
                                break
                            except ValueError:
                                continue
                        if metric in data:
                            break
                data.setdefault(metric, 0.0)

            # C6: Non-compliant investments
            for tag in INVESTMENT_TAGS:
                nodes = root.xpath(
                    f"//*[translate(local-name(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{tag.lower()}']")
                if nodes:
                    for node in reversed(nodes):
                        txt = (node.text or "").strip()
                        try:
                            val = float(txt)
                            data["non_compliant_investments"] = val / 1e7 if val > 1e7 else val
                            break
                        except ValueError:
                            continue
                    if "non_compliant_investments" in data:
                        break
            data.setdefault("non_compliant_investments", 0.0)

            # C2: Interest Income
            for tag in INTEREST_INCOME_TAGS:
                nodes = root.xpath(
                    f"//*[translate(local-name(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{tag.lower()}']")
                if nodes:
                    for node in reversed(nodes):
                        txt = (node.text or "").strip()
                        try:
                            val = float(txt)
                            data["impermissible_interest_income"] = val / 1e7 if val > 1e7 else val
                            break
                        except ValueError:
                            continue
                    if "impermissible_interest_income" in data:
                        break
            data.setdefault("impermissible_interest_income", 0.0)

            # Primitives aggregation
            data["illiquid_assets"] = (
                    data.get("ppe", 0.0) + data.get("cwip", 0.0) +
                    data.get("investment_property", 0.0) + data.get("intangible", 0.0) +
                    data.get("inventories", 0.0)
            )
            data["liquid_assets"] = (
                    data.get("cash_equivalents", 0.0) + data.get("bank_balances", 0.0) +
                    data.get("trade_receivables", 0.0) + data.get("other_current_financial_assets", 0.0)
            )
            data["interest_bearing_debt"] = (
                    data.get("current_borrowings", 0.0) + data.get("non_current_borrowings", 0.0)
            )
        except Exception as e:
            print(f"[!] XML parse notice: {e}. Falling back to market feed.")

    # 2. Audited statements fallback & date extraction
    if (data.get("total_assets", 0.0) == 0.0 or data.get("financial_date") == "Unknown") and ticker_symbol:
        clean_ticker = ticker_symbol.upper().replace(".NS", "").strip()
        stock = yf.Ticker(f"{clean_ticker}.NS")

        try:
            bs = stock.balance_sheet
            pnl = stock.financials

            # Extract latest audited date from column header
            if not bs.empty:
                latest_col = bs.columns[0]
                try:
                    data["financial_date"] = pd.to_datetime(latest_col).strftime("%d %b %Y")
                except Exception:
                    data["financial_date"] = str(latest_col)[:10]

            if not bs.empty and "Total Assets" in bs.index and data.get("total_assets", 0.0) == 0.0:
                data["total_assets"] = float(bs.loc["Total Assets"].iloc[0]) / 1e7
            if not pnl.empty and "Total Revenue" in pnl.index and data.get("total_revenue", 0.0) == 0.0:
                data["total_revenue"] = float(pnl.loc["Total Revenue"].iloc[0]) / 1e7
            if "Cash Cash Equivalents And Short Term Investments" in bs.index and data.get("liquid_assets", 0.0) == 0.0:
                data["liquid_assets"] = float(bs.loc["Cash Cash Equivalents And Short Term Investments"].iloc[0]) / 1e7
            if "Total Debt" in bs.index and data.get("interest_bearing_debt", 0.0) == 0.0:
                data["interest_bearing_debt"] = float(bs.loc["Total Debt"].iloc[0]) / 1e7

            if data.get("total_liabilities", 0.0) == 0.0:
                for liab_key in ["Total Liabilities Net Minority Interest",
                                 "Total Non Current Liabilities Net Minority Interest"]:
                    if liab_key in bs.index:
                        data["total_liabilities"] = float(bs.loc[liab_key].iloc[0]) / 1e7
                        break

            # C4 Illiquid
            if data.get("illiquid_assets", 0.0) == 0.0:
                illiquid_total = 0.0
                for item in ["Net PPE", "Goodwill And Other Intangible Assets", "Goodwill", "Other Intangible Assets",
                             "Leases", "Inventory"]:
                    if item in bs.index:
                        try:
                            val = float(bs.loc[item].iloc[0])
                            if val > 0: illiquid_total += val
                        except (ValueError, TypeError):
                            pass
                data["illiquid_assets"] = illiquid_total / 1e7

            # C6 Non-compliant investments
            if data.get("non_compliant_investments", 0.0) == 0.0:
                inv_total = 0.0
                for inv_key in ["Other Short Term Investments", "Investments In Other Financial Assets",
                                "Financial Assets", "Available For Sale Securities"]:
                    if inv_key in bs.index:
                        try:
                            val = float(bs.loc[inv_key].iloc[0])
                            if val > 0: inv_total += val
                        except (ValueError, TypeError):
                            pass
                data["non_compliant_investments"] = inv_total / 1e7

            # C2 Interest income
            if data.get("impermissible_interest_income", 0.0) == 0.0 and not pnl.empty:
                interest_val = 0.0
                for int_key in ["Interest Income Non Operating", "Interest Income",
                                "Net Non Operating Interest Income Expense"]:
                    if int_key in pnl.index:
                        try:
                            val = float(pnl.loc[int_key].iloc[0])
                            if val > 0:
                                interest_val = val
                                break
                        except (ValueError, TypeError):
                            pass
                data["impermissible_interest_income"] = interest_val / 1e7

        except Exception as err:
            print(f"[-] Audited feed extraction error for {ticker_symbol}: {err}")

    return data