# -*- coding: utf-8 -*-
"""Current price on the seller's own product page (SnappPay landing items).

The landing feed is a snapshot; the seller's page shows what a buyer pays right now.
Most Iranian shops publish schema.org Product JSON-LD (WooCommerce, custom stores):
    {"@type": "Product", "offers": {"price": 94990000, "priceCurrency": "IRR", "availability": ".../InStock"}}

Unit trap: many shops label Toman prices as "IRR" (e.g. Technolife 899000 "IRR" for an
899,000-Toman cable). So the currency field is ignored and the reading (x or x/10) closest
to the landing price is taken. A reading more than 35% away is rejected ("mismatch"), and a
page listing several variants at different prices (AggregateOffer lowPrice/highPrice) only
counts when one variant equals the landing price; otherwise the status is "variants".
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
    """Raw readings from a product page: explicit prices, aggregate (variant) range, stock."""
    prices: list[float] = []
    variants = False
    stock = ""
    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block.strip(), strict=False)
        except ValueError:
            continue
        for prod in _products(data):
            for off in _offers(prod):
                x = _num(off.get("price"))
                if x:
                    prices.append(x)
                lo, hi = _num(off.get("lowPrice")), _num(off.get("highPrice"))
                if lo:
                    prices.append(lo)
                count = _num(off.get("offerCount")) or 1
                if lo and hi and hi / lo > 1.02 and count > 1:
                    variants = True   # e.g. perfume sold in 10/30/50 ml: lowPrice is the smallest one
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
    distinct = sorted(set(prices))
    if len(distinct) > 1 and distinct[-1] / distinct[0] > 1.02 and not variants:
        # several different explicit offers on one page (colours/sizes) unless they are just Toman/Rial twins
        variants = not all(abs(math.log(distinct[-1] / d) - math.log(10)) < 0.01 or d == distinct[-1] for d in distinct)
    return {"prices": prices, "stock": stock, "variants": variants}


MAX_MOVE = 1.35  # a "current price" more than 35% away from the landing price is treated as a different item/variant


def _readings(prices: list[float]):
    for p in prices:
        yield p
        yield p / 10


def pick_price(prices: list[float], ref: float | None, variants: bool = False) -> tuple[int | None, str]:
    """(Toman price, status). Each value is read as Toman or Rial; the reading closest to the landing price wins."""
    if not prices:
        return None, "no_price"
    if not ref:
        return int(min(prices) / 10), "ok"
    best = min(_readings(prices), key=lambda v: abs(math.log(v / ref)))
    dist = abs(math.log(best / ref))
    if variants:
        # with several variants only an exact hit on the landing price tells us anything
        return (int(round(best)), "ok") if dist <= math.log(1.01) else (None, "variants")
    if dist > math.log(MAX_MOVE):
        return None, "mismatch"
    return int(round(best)), "ok"


def page_price(html: str, ref: float | None) -> dict:
    raw = parse_page(html)
    price, status = pick_price(raw["prices"], ref, raw["variants"])
    if not price and raw["stock"] == "out":
        status = "out_of_stock"
    return {"price": price, "stock": raw["stock"], "status": status}
