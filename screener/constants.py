"""
Non-negotiable Shariah screening benchmarks under Ind-AS.
"""

# Thresholds
MAX_HARAM_BUSINESS_REVENUE_PCT = 5.0      # Criteria 1
MAX_IMPERMISSIBLE_INCOME_PCT = 5.0        # Criteria 2: (Non-permissible Income / Total Revenue) %
MAX_DEBT_TO_ASSETS_PCT = 33.0             # Criteria 3: (Interest-bearing Debt / Total Assets) %
MIN_ILLIQUID_ASSETS_PCT = 20.0            # Criteria 4: (Illiquid Assets / Total Assets) % >= 20%
MAX_NON_COMPLIANT_INV_PCT = 33.0          # Criteria 6: (Non-compliant Investments / Total Assets) %

# Criteria 5 rule: (Liquid Assets - Total Liabilities) MUST be less than Market Capitalization

# Standard MCA Ind-AS XBRL Tags
IND_AS_TAGS = {
    "total_assets": ["Assets", "TotalAssets"],
    "total_liabilities": ["EquityAndLiabilities", "TotalEquityAndLiabilities", "Liabilities"],
    "ppe": ["PropertyPlantAndEquipment", "TangibleAssets"],
    "cwip": ["CapitalWorkInProgress"],
    "investment_property": ["InvestmentProperty"],
    "intangible": ["IntangibleAssets", "OtherIntangibleAssets"],
    "inventories": ["Inventories"],
    "cash_equivalents": ["CashAndCashEquivalents"],
    "bank_balances": ["OtherBalancesWithBanks", "BankBalancesOtherThanCashAndCashEquivalents"],
    "trade_receivables": ["TradeReceivablesCurrent", "CurrentTradeReceivables"],
    "other_current_financial_assets": ["OtherCurrentFinancialAssets"],
    "current_borrowings": ["BorrowingsCurrent", "CurrentBorrowings"],
    "non_current_borrowings": ["BorrowingsNonCurrent", "NonCurrentBorrowings"],
    "total_revenue": ["RevenueFromOperations", "Income"]
}