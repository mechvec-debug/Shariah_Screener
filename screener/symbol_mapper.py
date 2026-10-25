import json
import os
from typing import Optional

DEFAULT_MAP = {
    "RELIANCE": "500325",
    "TCS": "532540",
    "INFY": "500209",
    "HDFCBANK": "500180",
    "ICICIBANK": "532174",
    "ITC": "500875",
    "LT": "500510",
    "HINDUNILVR": "500696",
    "BHARTIARTL": "532454",
    "SBIN": "500112"
}

class SymbolMapper:
    def __init__(self, mapping_path: str = "nse_bse_mapping.json"):
        self.mapping_path = mapping_path
        self.mapping = DEFAULT_MAP.copy()
        if os.path.exists(mapping_path):
            with open(mapping_path, "r", encoding="utf-8") as f:
                self.mapping.update(json.load(f))

    def resolve_to_bse(self, symbol: str) -> Optional[str]:
        clean_symbol = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
        return self.mapping.get(clean_symbol)