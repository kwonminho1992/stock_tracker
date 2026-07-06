"""Small HTML scrapers for macro indicators not covered by FRED/Yahoo.

These are intentionally narrow and best-effort. If a page layout changes, callers
fall back to the existing link-only cards instead of failing the whole update.
"""
from __future__ import annotations

import html
import re
import urllib.request
from typing import Dict, Optional


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; market-disparity-tracker/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def _meta_description(page: str) -> str:
    m = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        page,
        flags=re.IGNORECASE,
    )
    return html.unescape(m.group(1)) if m else page


def _last_update(page: str) -> Optional[str]:
    m = re.search(r"LastUpdate\s*=\s*'(\d{8})", page)
    if not m:
        return None
    raw = m.group(1)
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def fetch_tradingeconomics(item: Dict) -> Optional[Dict]:
    page = _fetch_html(item["url"])
    desc = _meta_description(page)
    parser = item.get("parser")

    patterns = {
        "te_last_recorded_percent": r"last recorded at\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*percent",
        "te_ppi_change_percent": r"Producer Prices in Taiwan\s+(?:increased|decreased)\s+([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*percent",
        "te_money_level": r"increased to\s*([-+]?\d+(?:,\d{3})*(?:\.\d+)?)\s*JPY Billion",
    }
    pattern = patterns.get(parser)
    if not pattern:
        return None

    m = re.search(pattern, desc, flags=re.IGNORECASE)
    if not m:
        return None

    return {
        "value": _num(m.group(1)),
        "asof": _last_update(page),
        "source_text": desc,
    }
