# -*- coding: utf-8 -*-
"""Current price on the seller's own product page (SnappPay landing items).

The landing feed is a snapshot; the seller's page shows what a buyer pays right now.
Most Iranian shops publish schema.org Product JSON-LD (WooCommerce, custom stores):
    {"@type": "Product", "offers": {"price": 94990000, "priceCurrency": "IRR", "availability": ".../InStock"}}

Unit trap: many shops label Toman prices as "IRR" (e.g. Technolife 899000 "IRR" for an
899,000-Toman cable). So the currency field is ignored and the reading (x or x/10) closest
to the landing price is taken; a reading more than 3x away from it is rejected.
"""
from __future__ import annotations

import json
import math
import re

_LD = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_META = re.compile(r'<meta[^>]+(?:property|name)=["\'](?:product|og):price:amount["\'][^>]+content=["\']([\d.,]+)["\']'
                   r'|<meta[^>]+content=["\']([\d.,]+)["\'][^>]+(?:property|name)=["\'](?:product|og):price:amount["\']', re.I)


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = re.sub(r"[^\d.]", "", str(v).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
    try:
        x = float(s)
    except ValueError:
        return None
    return x if x > 0 else None


def _products(obj):
    if isinstance(obj, list):
        for o in obj:
            yield from _products(o)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" in types or "ProductGroup" in types:
            yield obj
        for k in ("@graph", "hasVariant", "mainEntity", "itemListElement"):
            if k in obj:
                yield from _products(obj[k])


def _offers(prod: dict):
    o = prod.get("offers")
    stack = o if isinstance(o, list) else [o]
    while stack:
        x = stack.pop(0)
        if isinstance(x, dict):
            yield x
            if isinstance(x.get("offers"), list):
                stack.extend(x["offers"])


def parse_page(html: str) -> dict:
    """Raw readings from a product page: candidate prices and stock state."""
    prices: list[float] = []
    stock = ""
    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block.strip(), strict=False)
        except ValueError:
            continue
        for prod in _products(data):
            for off in _offers(prod):
                for k in ("price", "lowPrice"):
                    x = _num(off.get(k))
                    if x:
                        prices.append(x)
                av = str(off.get("availability") or "")
                if "OutOfStock" in av or "SoldOut" in av:
                    stock = stock or "out"
                elif "InStock" in av or "LimitedAvailability" in av:
                    stock = "in"
    if not prices:
        for a, b in _META.findall(html or ""):
            x = _num(a or b)
            if x:
                prices.append(x)
    return {"prices": prices, "stock": stock}


def pick_price(prices: list[float], ref: float | None) -> int | None:
    """Toman price closest to the landing price, reading each value as Toman or Rial."""
    if not prices:
        return None
    if not ref:
        return int(min(prices) / 10)  # no reference: assume Rial (schema.org default)
    best, dist = None, math.inf
    for p in prices:
        for v in (p, p / 10):
            d = abs(math.log(v / ref))
            if d < dist:
                best, dist = v, d
    return int(round(best)) if dist <= math.log(3) else None


def page_price(html: str, ref: float | None) -> dict:
    raw = parse_page(html)
    price = pick_price(raw["prices"], ref)
    if price:
        status = "ok"
    elif raw["stock"] == "out":
        status = "out_of_stock"
    elif raw["prices"]:
        status = "mismatch"   # a price exists but is far from the landing one (other variant/page)
    else:
        status = "no_price"
    return {"price": price, "stock": raw["stock"], "status": status}
