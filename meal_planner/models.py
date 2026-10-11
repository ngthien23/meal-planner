CURRENCY_SYMBOLS: dict[str, str] = {
    "EUR": "€",
    "USD": "$",
    "GBP": "£",
    "VND": "₫",
    "CAD": "CA$",
    "AUD": "A$",
    "JPY": "¥",
    "CHF": "CHF",
}

def get_currency_symbol(currency_code: str) -> str:
    """Returns the visual currency symbol for a currency code (e.g. EUR -> €)."""
    return CURRENCY_SYMBOLS.get((currency_code or "").upper().strip(), currency_code)
