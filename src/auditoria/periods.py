from __future__ import annotations

import datetime
import re
import unicodedata


_MONTH_ALIASES = {
    "jan": 1,
    "janeiro": 1,
    "fev": 2,
    "fevereiro": 2,
    "mar": 3,
    "marco": 3,
    "abr": 4,
    "abril": 4,
    "mai": 5,
    "maio": 5,
    "jun": 6,
    "junho": 6,
    "jul": 7,
    "julho": 7,
    "ago": 8,
    "agosto": 8,
    "set": 9,
    "setembro": 9,
    "out": 10,
    "outubro": 10,
    "nov": 11,
    "novembro": 11,
    "dez": 12,
    "dezembro": 12,
}

_ORDINAL_QUARTERS = {
    "primeiro": 1,
    "segundo": 2,
    "terceiro": 3,
    "quarto": 4,
}


def infer_year_quarter(periodo: str) -> tuple[int, int]:
    text = str(periodo or "")
    normalized = _normalize_period_text(text)

    year_match = re.search(r"(?:19|20)\d{2}", text)
    year = int(year_match.group(0)) if year_match else datetime.datetime.now().year

    quarter_match = re.search(r"\b(?:T|Q)\s*([1-4])\b", normalized)
    if not quarter_match:
        quarter_match = re.search(r"\b([1-4])\s*(?:T|TRI|TRIM|TRIMESTRE)\b", normalized)
    if not quarter_match:
        quarter_match = re.search(r"\b(?:TRI|TRIM|TRIMESTRE)\s*([1-4])\b", normalized)
    if quarter_match:
        return year, int(quarter_match.group(1))

    normalized_lower = normalized.lower()
    for ordinal, quarter in _ORDINAL_QUARTERS.items():
        if re.search(rf"\b{ordinal}\s+trimestre\b", normalized_lower):
            return year, quarter

    dates = re.findall(r"(\d{2})/(\d{2})/((?:19|20)\d{2})", text)
    if dates:
        month = int(dates[-1][1])
        return int(dates[-1][2]), ((month - 1) // 3) + 1

    months = [
        month
        for token in re.findall(r"\b[a-z]{3,9}\b", normalized_lower)
        for month in [_MONTH_ALIASES.get(token)]
        if month is not None
    ]
    if months:
        return year, ((months[-1] - 1) // 3) + 1

    return year, 0


def _normalize_period_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().replace("º", "O").replace("°", "O")
    text = re.sub(r"([1-4])O\s+TRIM", r"\1 TRIM", text)
    text = re.sub(r"([TQ])([1-4])", r"\1 \2", text)
    text = re.sub(r"([1-4])([TQ])", r"\1 \2", text)
    text = re.sub(r"[^A-Z0-9/]+", " ", text)
    return " ".join(text.split())
