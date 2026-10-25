import yfinance as yf


def get_market_cap_inr_crores(ticker_symbol: str) -> float:
    """
    Retrieves real-time market capitalization in ₹ Crores.
    """
    clean_ticker = ticker_symbol.upper().replace(".NS", "").strip()
    ticker = yf.Ticker(f"{clean_ticker}.NS")

    fast_info = ticker.fast_info
    mcap = getattr(fast_info, "market_cap", None)

    if not mcap:
        info = ticker.info
        mcap = info.get("marketCap", 0.0)

    return round(mcap / 1e7, 2)  # Convert to ₹ Crores