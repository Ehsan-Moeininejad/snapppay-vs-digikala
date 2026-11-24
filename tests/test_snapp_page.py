# -*- coding: utf-8 -*-
"""Seller-page price extraction, with the shapes seen on real shops (2026-11-24)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from snapp_page import page_price  # noqa: E402


def ld(obj: str) -> str:
    return f'<html><head><script type="application/ld+json">{obj}</script></head></html>'


def test_petabad_rial():
    # 94,990,000 IRR = 9,499,000 Toman (landing price 9,499,000)
    html = ld('{"@type":"Product","offers":{"@type":"Offer","priceCurrency":"IRR","price":"94990000",'
              '"availability":"https://schema.org/InStock"}}')
    assert page_price(html, 9499000) == {"price": 9499000, "stock": "in", "status": "ok"}


def test_technolife_toman_labelled_irr():
    # AggregateOffer, "IRR" but really Toman: 899,000 for a 970,920-Toman landing price
    html = ld('{"@type":"Product","offers":{"@type":"AggregateOffer","priceCurrency":"IRR","highPrice":970931,'
              '"lowPrice":899000,"offers":[{"price":899000,"availability":"https://schema.org/InStock"}]}}')
    r = page_price(html, 970920)
    assert r["price"] in (899000, 970931) and r["status"] == "ok"


def test_jeanswest_graph():
    html = ld('{"@graph":[{"@type":"WebPage"},{"@type":"Product","offers":{"price":26997000,"priceCurrency":"IRR",'
              '"availability":"https://schema.org/InStock"}}]}')
    assert page_price(html, 2699700)["price"] == 2699700


def test_out_of_stock_without_price():
    html = ld('{"@type":"Product","offers":{"@type":"Offer","availability":"https://schema.org/OutOfStock"}}')
    assert page_price(html, 390000) == {"price": None, "stock": "out", "status": "out_of_stock"}


def test_meta_fallback():
    html = '<meta property="product:price:amount" content="1500000"><meta property="product:price:currency" content="IRR">'
    assert page_price(html, 150000)["price"] == 150000


def test_far_price_rejected():
    html = ld('{"@type":"Product","offers":{"price":50000}}')
    assert page_price(html, 9000000)["status"] == "mismatch"


def test_no_data():
    assert page_price("<html>nothing</html>", 100000)["status"] == "no_price"
