from __future__ import annotations

from decimal import Decimal


_UNICODE_TO_LATIN1 = {
    "\u2014": "-",
    "\u2013": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2022": "-",
    "\u2026": "...",
    "\u00a0": " ",
    "\u200b": "",
    "\ufeff": "",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2015": "--",
    "\u2039": "<",
    "\u203a": ">",
    "\u00ab": "<<",
    "\u00bb": ">>",
    "\u2032": "'",
    "\u2033": '"',
    "\u00b7": "-",
    "\u2212": "-",
    "\u00d7": "x",
    "\u00f7": "/",
}

_PT_BR_CHAR_MAP = {
    "\u00e7": "c",
    "\u00c7": "C",
    "\u00e3": "a",
    "\u00c3": "A",
    "\u00f5": "o",
    "\u00d5": "O",
    "\u00e1": "a",
    "\u00c1": "A",
    "\u00e0": "a",
    "\u00c0": "A",
    "\u00e2": "a",
    "\u00c2": "A",
    "\u00e9": "e",
    "\u00c9": "E",
    "\u00ea": "e",
    "\u00ca": "E",
    "\u00ed": "i",
    "\u00cd": "I",
    "\u00f3": "o",
    "\u00d3": "O",
    "\u00f4": "o",
    "\u00d4": "O",
    "\u00fa": "u",
    "\u00da": "U",
    "\u00fc": "u",
    "\u00dc": "U",
    "\u00f1": "n",
    "\u00d1": "N",
}


def format_brl(value: Decimal) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_percent(value: Decimal) -> str:
    return f"{value * Decimal('100'):.2f}%".replace(".", ",")


def sanitize_for_latin1(text: str) -> str:
    result = text
    for unicode_char, replacement in _UNICODE_TO_LATIN1.items():
        result = result.replace(unicode_char, replacement)
    for pt_br_char, ascii_char in _PT_BR_CHAR_MAP.items():
        result = result.replace(pt_br_char, ascii_char)
    import unicodedata
    normalized = unicodedata.normalize("NFKD", result)
    return "".join(
        char for char in normalized
        if ord(char) < 128 or unicodedata.category(char) != "Mn"
    ).strip()
