"""Checks that never trust the AI: same rules as SafeTell's st_norm_text / st_numbers."""
from __future__ import annotations
import re
from decimal import Decimal

_TR = str.maketrans({'‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', ' ': ' '})


def norm_text(t: str | None) -> str:
    return re.sub(r'\s+', ' ', (t or '').translate(_TR).lower()).strip()


def numbers(t: str | None) -> set[str]:
    out = set()
    for m in re.findall(r'(\d[\d,]*(?:\.\d+)?)', t or ''):
        v = m.replace(',', '')
        if re.fullmatch(r'\d+(\.\d+)?', v):
            d = Decimal(v).normalize()
            out.add(format(d, 'f'))
    return out


def quote_verified(quote: str | None, paragraph_text: str) -> bool:
    q = norm_text(quote)
    return bool(q) and q in norm_text(paragraph_text)


def unmatched_numbers(requirement_text: str, paragraph_text: str) -> list[str]:
    return sorted(numbers(requirement_text) - numbers(paragraph_text))
