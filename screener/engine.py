import math
from typing import Dict, Any
from screener.constants import (
    MAX_HARAM_BUSINESS_REVENUE_PCT,
    MAX_IMPERMISSIBLE_INCOME_PCT,
    MAX_DEBT_TO_ASSETS_PCT,
    MIN_ILLIQUID_ASSETS_PCT,
    MAX_NON_COMPLIANT_INV_PCT
)

def evaluate_all_criteria(
    market_cap: float,
    financials: Dict[str, float],
    audit_data: Dict[str, float]
) -> Dict[str, Any]:
    total_assets = financials.get("total_assets", 0.0) or 0.0
    total_revenue = financials.get("total_revenue", 0.0) or 0.0
    total_liabilities = financials.get("total_liabilities", 0.0) or 0.0

    # Guard: If fundamental financial data is missing, zero, or NaN
    if (
        math.isnan(total_assets) or math.isnan(total_revenue) or
        total_assets <= 0 or total_revenue <= 0
    ):
        return {
            "is_compliant": False,
            "error": "Incomplete Statements: Total Assets or Revenue not available",
            "results": {
                "Criteria 1: Core Business": {"metric": "N/A", "threshold": f"< {MAX_HARAM_BUSINESS_REVENUE_PCT}%", "status": False},
                "Criteria 2: Impermissible Income": {"metric": "N/A", "threshold": f"< {MAX_IMPERMISSIBLE_INCOME_PCT}%", "status": False},
                "Criteria 3: Debt / Assets": {"metric": "N/A", "threshold": f"< {MAX_DEBT_TO_ASSETS_PCT}%", "status": False},
                "Criteria 4: Illiquid / Assets": {"metric": "N/A", "threshold": f">= {MIN_ILLIQUID_ASSETS_PCT}%", "status": False},
                "Criteria 5: Net Liquid < MCap": {"metric": "N/A", "threshold": "Net Liquid < MCap", "status": False},
                "Criteria 6: Non-Compliant Inv": {"metric": "N/A", "threshold": f"< {MAX_NON_COMPLIANT_INV_PCT}%", "status": False},
            }
        }

    # 1. Core Business Activity (< 5%)
    haram_rev = audit_data.get("haram_business_revenue", 0.0) or 0.0
    c1_ratio = (haram_rev / total_revenue) * 100
    c1_pass = c1_ratio < MAX_HARAM_BUSINESS_REVENUE_PCT

    # 2. Impermissible Income (< 5%)
    imp_income = audit_data.get("impermissible_interest_income", 0.0) or financials.get("impermissible_interest_income", 0.0) or 0.0
    c2_ratio = (imp_income / total_revenue) * 100
    c2_pass = c2_ratio < MAX_IMPERMISSIBLE_INCOME_PCT

    # 3. Interest-Bearing Debt / Total Assets (< 33%)
    debt = financials.get("interest_bearing_debt", 0.0) or 0.0
    c3_ratio = (debt / total_assets) * 100
    c3_pass = c3_ratio < MAX_DEBT_TO_ASSETS_PCT

    # 4. Illiquid Assets / Total Assets (>= 20%)
    illiquid = financials.get("illiquid_assets", 0.0) or 0.0
    c4_ratio = (illiquid / total_assets) * 100
    c4_pass = c4_ratio >= MIN_ILLIQUID_ASSETS_PCT

    # 5. Net Liquid Asset < Market Capitalization
    liquid = financials.get("liquid_assets", 0.0) or 0.0
    net_liquid_assets = liquid - total_liabilities
    c5_pass = net_liquid_assets < market_cap

    # 6. Non-Compliant Investments / Total Assets (< 33%)
    non_comp_inv = audit_data.get("non_compliant_investments", 0.0) or financials.get("non_compliant_investments", 0.0) or 0.0
    c6_ratio = (non_comp_inv / total_assets) * 100
    c6_pass = c6_ratio < MAX_NON_COMPLIANT_INV_PCT

    overall_compliant = all([c1_pass, c2_pass, c3_pass, c4_pass, c5_pass, c6_pass])

    return {
        "is_compliant": overall_compliant,
        "results": {
            "Criteria 1: Core Business": {
                "metric": f"{c1_ratio:.2f}%",
                "threshold": f"< {MAX_HARAM_BUSINESS_REVENUE_PCT}%",
                "status": c1_pass
            },
            "Criteria 2: Impermissible Income": {
                "metric": f"{c2_ratio:.2f}% (₹{imp_income:,.0f} Cr)",
                "threshold": f"< {MAX_IMPERMISSIBLE_INCOME_PCT}%",
                "status": c2_pass
            },
            "Criteria 3: Debt / Assets": {
                "metric": f"{c3_ratio:.2f}%",
                "threshold": f"< {MAX_DEBT_TO_ASSETS_PCT}%",
                "status": c3_pass
            },
            "Criteria 4: Illiquid / Assets": {
                "metric": f"{c4_ratio:.2f}%",
                "threshold": f">= {MIN_ILLIQUID_ASSETS_PCT}%",
                "status": c4_pass
            },
            "Criteria 5: Net Liquid < MCap": {
                "metric": f"Net Liq: ₹{net_liquid_assets:,.0f} Cr | MCap: ₹{market_cap:,.0f} Cr",
                "threshold": "Net Liquid < MCap",
                "status": c5_pass
            },
            "Criteria 6: Non-Compliant Inv": {
                "metric": f"{c6_ratio:.2f}% (₹{non_comp_inv:,.0f} Cr)",
                "threshold": f"< {MAX_NON_COMPLIANT_INV_PCT}%",
                "status": c6_pass
            }
        }
    }