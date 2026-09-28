"""Suggest which checklist items are life-critical, from the customer's own list.
Key-word overlap, not whole-phrase matching (whole-phrase matching found 0 of 9 on the
Brightwater form). Suggestions only: a person confirms every one."""
from __future__ import annotations
import re

STOP = set('a an and at the in of on to for with by from over under no not all any be is are has have place use '
           'during after before per ft feet inch in. min minutes than or its it this that each every'.split())
YES = {'yes', 'y', 'true', '1', 'x', 'critical', 'lc', '✓', '✔'}


def keywords(s: str) -> set[str]:
    return {re.sub(r's$', '', w) for w in re.findall(r'[a-z]+', s.lower()) if w not in STOP and len(w) > 2}


def match(item_text: str, life_critical: list[str]) -> str | None:
    it = keywords(item_text)
    best, best_n = None, 0
    for lc in life_critical:
        k = keywords(lc)
        n = len(k & it)
        if n >= 2 or (k and len(k) <= 2 and n == len(k)):
            if n > best_n:
                best, best_n = lc, n
    return best


def suggestions(items: list[dict], life_critical: list[str]) -> list[dict]:
    """items: {text, critical?}. Returns one row per item that their column or the list flags."""
    out = []
    for i, it in enumerate(items):
        col = str(it.get('critical') or '').strip()
        says = col.lower() in YES
        m = match(it['text'], life_critical)
        if says or m:
            out.append({'index': i, 'text': it['text'], 'their_column': col, 'column_says_critical': says,
                        'list_match': m, 'disagree': says != bool(m)})
    return out
