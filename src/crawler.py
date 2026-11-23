#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SnappPay Black Friday  vs  Digikala  -  price comparison crawler
================================================================

1. Reads SnappPay's two Black Friday feeds (plain JSON files the landing pages load):
     https://snapppay.ir/blackfriday/data/products.json   (~700 merchant products)
     https://snapppay.ir/timetable/products.json          (~400 timed deals: online / in-store / live)
2. Searches every product on Digikala (discovery search API) and picks the best
   matching product with a confidence level (high / medium / low).
3. Compares prices and writes:
     data/latest.json, data/latest.csv     full row-level result
     data/summary_history.csv             one line per run (trend)
     docs/index.html                      dark, Persian report (GitHub Pages ready)

All prices are Toman. Digikala's API returns Rial -> divided by 10.
No LLM, no browser: one HTTP request per SnappPay product.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

sys.path.insert(0, str(Path(__file__).parent))
from matcher import best_match, build_fallback_query, build_query, rank_candidates  # noqa: E402
from recheck import recheck  # noqa: E402
from report import render_report  # noqa: E402

# ----------------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------------
SNAPP_LANDING = "https://snapppay.ir/blackfriday/data/products.json"
SNAPP_TIMETABLE = "https://snapppay.ir/timetable/products.json"
DK_SEARCH = "https://api.digikala.com/discovery/api/v2/search?page=1&q={q}"
DK_PRODUCT_URL = "https://www.digikala.com/product/dkp-{id}/"
DK_PRODUCT_API = "https://api.digikala.com/product/v1/products/{id}/"
RECHECK_TOP = 3          # how many first-pass candidates the recheck may try, best first

WORKERS = int(os.environ.get("DK_WORKERS", "4"))       # parallel Digikala searches
DELAY = float(os.environ.get("DK_DELAY", "0.3"))         # seconds between requests per worker
TIMEOUT = 20
RETRIES = 3
CANDIDATES_PER_SEARCH = 15
EQUAL_BAND_PCT = 1.0          # |diff| <= 1%  -> "equal"
LIMIT = int(os.environ.get("LIMIT", "0"))  # >0 = only first N products (testing)

TZ = ZoneInfo("Asia/Tehran")
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DOCS = ROOT / "docs"
for d in (DATA, DOCS):
    d.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fa-IR,fa;q=0.9,en;q=0.8",
}

# SnappPay timetable category ids that differ from the landing ones
CATEGORY_LABELS = {
    "digital": "کالای دیجیتال", "gold": "طلا و نقره", "fashion": "مد و پوشاک",
    "home": "خانه و آشپزخانه", "beauty": "آرایشی و بهداشتی", "hb": "آرایشی و بهداشتی",
    "health": "سلامت", "pet": "حیوانات خانگی", "automotive": "خودرو و ابزار",
    "books": "فرهنگ و هنر", "consumables": "کالای مصرفی", "sports": "ورزش و سفر",
    # extra ids used only by the timetable feed
    "sport": "ورزش و سفر", "kitchen": "خانه و آشپزخانه", "grocery": "کالای مصرفی",
    "children": "کودک و اسباب‌بازی", "tools": "خودرو و ابزار", "tourism": "سفر و گردشگری",
    "education": "آموزش", "services": "خدمات", "others": "سایر",
}
# Timetable feed uses its own category ids -> fold them into the landing ones
CATEGORY_CANON = {"hb": "beauty", "sport": "sports", "kitchen": "home", "grocery": "consumables",
                  "tools": "automotive"}
CHANNEL_LABELS = {"landing": "لندینگ (فروشگاه‌ها)", "online": "آنلاین (اپ اسنپ‌پی)",
                  "store": "حضوری", "social": "لایو / سوشال"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
log = logging.getLogger("snapp-vs-dk")


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------
def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


# Optional fallback: route requests through the Cloudflare Worker in cloudflare/worker.js
# (set repository secrets DK_PROXY_URL and DK_PROXY_KEY). Empty = fetch directly.
PROXY_URL = os.environ.get("DK_PROXY_URL", "").rstrip("/")
PROXY_KEY = os.environ.get("DK_PROXY_KEY", "")


def get_json(s: requests.Session, url: str) -> dict | list:
    last = None
    for attempt in range(1, RETRIES + 1):
        try:
            if PROXY_URL:
                r = s.get(f"{PROXY_URL}/fetch", params={"url": url},
                          headers={"x-proxy-key": PROXY_KEY}, timeout=TIMEOUT * 2)
            else:
                # Digikala's CDN answers the first hit with a 307 + cookie; the Session
                # keeps that cookie across the redirect, which is all it needs.
                r = s.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code in (403, 404):
                break
        except (requests.RequestException, ValueError) as e:
            last = repr(e)
        time.sleep(1.5 * attempt)
    raise RuntimeError(f"{url} -> {last}")


# ----------------------------------------------------------------------------
# SNAPPPAY
# ----------------------------------------------------------------------------
def live_window(times: list[dict]) -> tuple[str, str]:
    """Return (status, Tehran-time text) for the current / next live slot."""
    now = time.time()
    fmt = lambda ts: datetime.fromtimestamp(ts, TZ).strftime("%m/%d %H:%M")  # noqa: E731
    for t in sorted(times or [], key=lambda x: x["from"]):
        if t["from"] <= now <= t["to"]:
            return "live", f"تا {fmt(t['to'])}"
        if t["from"] > now:
            return "upcoming", fmt(t["from"])
    return ("ended", "") if times else ("always", "")


def load_snapppay(s: requests.Session) -> list[dict]:
    items: list[dict] = []

    landing = get_json(s, SNAPP_LANDING)
    for p in landing.get("products", []):
        if not p.get("t") or not p.get("p"):
            continue
        items.append({
            "snapp_id": p["i"], "channel": "landing", "title": p["t"].strip(),
            "merchant": p.get("m") or "", "category": p.get("c") or "",
            "snapp_price": int(p["p"]), "snapp_before": int(p.get("o") or 0) or None,
            "snapp_discount": p.get("d"), "cashback_pct": p.get("cb") or 0,
            "snapp_url": p.get("u") or "", "img": p.get("img") or "",
            "live_status": "always", "live_text": "",
        })
    log.info("SnappPay landing: %d products", len(items))

    tt = get_json(s, SNAPP_TIMETABLE)
    n0 = len(items)
    for p in tt:
        if p.get("type") == "voucher" or not p.get("title") or not p.get("price"):
            continue
        status, text = live_window(p.get("liveTimes") or [])
        img = p.get("img") or ""
        items.append({
            "snapp_id": p["id"], "channel": p.get("type") or "online", "title": p["title"].strip(),
            "merchant": p.get("merchant") or ", ".join(p.get("tags") or []),
            "category": CATEGORY_CANON.get(p.get("category") or "", p.get("category") or ""),
            "snapp_price": int(p["price"]), "snapp_before": int(p.get("prePrice") or 0) or None,
            "snapp_discount": p.get("discount"), "cashback_pct": 0,
            "snapp_url": "https://snapppay.ir/timetable/",
            "img": f"https://snapppay.ir/timetable{img}" if img.startswith("/") else img,
            "live_status": status, "live_text": text, "is_range": bool(p.get("isRange")),
        })
    log.info("SnappPay timetable: %d deals (vouchers skipped)", len(items) - n0)
    return items


# ----------------------------------------------------------------------------
# DIGIKALA
# ----------------------------------------------------------------------------
def dk_search(s: requests.Session, query: str) -> list[dict]:
    j = get_json(s, DK_SEARCH.format(q=quote(query)))
    out, seen = [], set()
    for w in (j.get("data") or {}).get("widgets") or []:
        for inner in (w.get("data") or {}).get("widgets") or []:
            if inner.get("type") != "product":
                continue
            p = inner.get("data") or {}
            price = ((p.get("default_variant") or {}).get("price") or {})
            sp = price.get("selling_price") or 0
            if not p.get("id") or p["id"] in seen or p.get("status") != "marketable" or not sp:
                continue
            seen.add(p["id"])
            out.append({
                "id": p["id"], "title": (p.get("title_fa") or "").strip(),
                "price": sp // 10, "rrp": (price.get("rrp_price") or sp) // 10,
                "dk_discount": price.get("discount_percent") or 0,
                "is_incredible": bool(price.get("is_incredible")),
                "dk_category": (p.get("data_layer") or {}).get("item_category2") or "",
                "brand": (p.get("data_layer") or {}).get("brand") or "",
            })
            if len(out) >= CANDIDATES_PER_SEARCH:
                return out
    return out


def preflight(s: requests.Session) -> None:
    """Fail fast with a clear message when Digikala blocks this runner's IP."""
    try:
        dk_search(s, "گوشی موبایل")
    except Exception as e:  # noqa: BLE001
        log.error("Digikala search API is NOT reachable from this machine: %s", e)
        log.error("If this keeps failing on GitHub, deploy cloudflare/worker.js and set the "
                  "DK_PROXY_URL / DK_PROXY_KEY secrets - see README section 4.")
        sys.exit(3)


_local = threading.local()

# Brand / full titles per Digikala product id. Kept between runs (data/dk_products_cache.json)
# because they do not change; prices always come from the live search result.
PRODUCT_CACHE_FILE = DATA / "dk_products_cache.json"
try:
    PRODUCT_CACHE: dict[str, dict] = json.loads(PRODUCT_CACHE_FILE.read_text("utf-8"))
except (OSError, ValueError):
    PRODUCT_CACHE = {}
_cache_lock = threading.Lock()


def dk_product(s: requests.Session, pid: int) -> dict | None:
    """Read the Digikala product itself: brand (fa/en), full Persian/English titles, category."""
    key = str(pid)
    with _cache_lock:
        if key in PRODUCT_CACHE:
            return PRODUCT_CACHE[key]
    try:
        j = get_json(s, DK_PRODUCT_API.format(id=pid))
    except Exception:  # noqa: BLE001 - recheck still runs on search data alone
        return None
    p = (j.get("data") or {}).get("product") or {}
    if not p:
        return None
    d = {"title_fa": (p.get("title_fa") or "").strip(), "title_en": (p.get("title_en") or "").strip(),
         "brand_fa": (p.get("brand") or {}).get("title_fa") or "",
         "brand_en": (p.get("brand") or {}).get("title_en") or "",
         "category": (p.get("category") or {}).get("title_fa") or ""}
    with _cache_lock:
        PRODUCT_CACHE[key] = d
    return d


def compare_one(item: dict) -> dict:
    if not hasattr(_local, "s"):
        _local.s = session()          # one HTTP session per worker thread
    s = _local.s
    q = build_query(item["title"])
    row = {**item, "query": q, "match": None, "error": ""}
    try:
        strict = item["category"] == "gold"
        cands, cands2 = dk_search(s, q), []
        m = best_match(item["title"], item["snapp_price"], item["snapp_before"], cands, strict=strict)
        # Not surely found -> one more, narrower search on the model code before giving up.
        fq = build_fallback_query(item["title"]) if (not m or m["confidence"] == "low") else None
        if fq:
            time.sleep(DELAY)
            cands2 = dk_search(s, fq)
            m2 = best_match(item["title"], item["snapp_price"], item["snapp_before"], cands + cands2, strict=strict)
            if m2 and (not m or m2["score"] > m["score"]):
                m = m2
                row["query"] = f"{q} | {fq}"
        row["match"] = m

        # ---- Recheck: read the Digikala product(s) and verify brand, variant, flavour,
        # pack. If the best candidate fails, the next-best candidates get the same check.
        if m and m["confidence"] in ("high", "medium"):
            ranked = [c for c in rank_candidates(item["title"], item["snapp_price"], item["snapp_before"],
                                                 cands + (cands2 if fq else []), strict=strict)
                      if c["confidence"] in ("high", "medium")][:RECHECK_TOP]
            chosen, notes = None, []
            for c in ranked:
                rc = recheck(item, c, dk_product(s, c["id"]))
                if rc["verdict"] == "fail":
                    notes.append(f"رد شد ({c['title'][:40]}): " + "؛ ".join(rc["reasons"]))
                    continue
                c = {**c, "title": rc["dk_title_full"] or c["title"]}
                if rc["verdict"] == "review":
                    c["confidence"] = "medium"
                chosen = c
                notes = rc["reasons"] + notes
                break
            if chosen:
                row["match"] = chosen
            else:   # every candidate failed the recheck -> no trustworthy match
                row["match"] = {**m, "confidence": "low"}
            row["recheck"] = " | ".join(notes)
    except Exception as e:  # noqa: BLE001
        row["error"] = str(e)[:200]
    time.sleep(DELAY)
    return row


NOT_FOUND_BELOW = 0.45   # best candidate scored below this -> "not on Digikala"
DK_STATUS_LABELS = {"matched": "تطبیق قطعی", "review": "نیازمند بررسی",
                    "uncertain": "نامشخص (معادل قطعی پیدا نشد)",
                    "not_found": "در دیجی‌کالا پیدا نشد"}


def enrich(row: dict) -> dict:
    m = row.pop("match")
    row["confidence"] = m["confidence"] if m else "none"
    row["match_score"] = m["score"] if m else 0
    # Where the product stands on Digikala. "not_found" = the search returned nothing
    # close; "uncertain" = there are candidates but none is surely the same product
    # (generic titles, other sizes/brands). Only high/medium rows get Digikala prices.
    if m and m["confidence"] == "high":
        row["dk_status"] = "matched"
    elif m and m["confidence"] == "medium":
        row["dk_status"] = "review"
    elif not m or m["score"] < NOT_FOUND_BELOW:
        row["dk_status"] = "not_found"
    else:
        row["dk_status"] = "uncertain"
    if m and m["confidence"] in ("high", "medium"):
        dk, sp = m["price"], row["snapp_price"]
        diff = (dk - sp) / sp * 100
        eff = round(sp * (1 - (row["cashback_pct"] or 0) / 100))
        row.update({
            "dk_id": m["id"], "dk_title": m["title"], "dk_price": dk, "dk_rrp": m["rrp"],
            "dk_discount": m["dk_discount"], "dk_is_incredible": m["is_incredible"],
            "dk_url": DK_PRODUCT_URL.format(id=m["id"]),
            "diff_toman": dk - sp, "diff_pct": round(diff, 1),
            "snapp_effective": eff, "diff_pct_vs_effective": round((dk - eff) / eff * 100, 1),
            "verdict": ("equal" if abs(diff) <= EQUAL_BAND_PCT else
                        "dk_cheaper" if diff < 0 else "snapp_cheaper"),
        })
    return row


# ----------------------------------------------------------------------------
# OUTPUT
# ----------------------------------------------------------------------------
CSV_COLS = ["dk_status", "recheck", "confidence", "verdict", "diff_pct", "diff_toman", "channel", "category", "merchant",
            "title", "snapp_price", "snapp_before", "snapp_discount", "cashback_pct",
            "snapp_effective", "diff_pct_vs_effective", "dk_title", "dk_price", "dk_rrp",
            "dk_discount", "dk_is_incredible", "dk_id", "dk_url", "snapp_url", "live_status",
            "live_text", "match_score", "snapp_id", "query", "error"]


def summarize(rows: list[dict], started: datetime) -> dict:
    # Headline numbers use HIGH-confidence matches only. A manual check of real data
    # (2026-11-23) found ~95% of high matches correct but only ~55% of medium ones,
    # so medium rows are shown in the report as "needs review" and kept out of stats.
    matched = [r for r in rows if r["confidence"] == "high"]
    diffs = [r["diff_pct"] for r in matched]
    count = lambda v: sum(1 for r in matched if r["verdict"] == v)  # noqa: E731
    by_cat: dict[str, list[float]] = {}
    by_channel: dict[str, list[float]] = {}
    for r in matched:
        by_cat.setdefault(r["category"], []).append(r["diff_pct"])
        by_channel.setdefault(r["channel"], []).append(r["diff_pct"])
    return {
        "run_at": started.strftime("%Y-%m-%d %H:%M"),
        "snapp_items": len(rows),
        "searched_ok": sum(1 for r in rows if not r["error"]),
        "matched": len(matched),
        "matched_high": len(matched),
        "matched_medium": sum(1 for r in rows if r["confidence"] == "medium"),
        "not_found": sum(1 for r in rows if r.get("dk_status") == "not_found"),
        "uncertain": sum(1 for r in rows if r.get("dk_status") == "uncertain"),
        "landing_items": sum(1 for r in rows if r["channel"] == "landing"),
        "dk_cheaper": count("dk_cheaper"), "equal": count("equal"),
        "snapp_cheaper": count("snapp_cheaper"),
        "median_diff_pct": round(statistics.median(diffs), 1) if diffs else None,
        "mean_diff_pct": round(statistics.mean(diffs), 1) if diffs else None,
        "by_category": {
            k: {"n": len(v), "median": round(statistics.median(v), 1),
                "dk_cheaper": sum(1 for x in v if x < -EQUAL_BAND_PCT)}
            for k, v in sorted(by_cat.items(), key=lambda kv: -len(kv[1]))
        },
        "by_channel": {
            k: {"n": len(v), "median": round(statistics.median(v), 1),
                "dk_cheaper": sum(1 for x in v if x < -EQUAL_BAND_PCT)}
            for k, v in sorted(by_channel.items(), key=lambda kv: -len(kv[1]))
        },
    }


XLSX_COLS = [  # (header, key) - Persian headers, Latin digits
    ("وضعیت در دیجی‌کالا", "dk_status_fa"), ("نتیجه‌ی بازبینی (Recheck)", "recheck"), ("محصول اسنپ‌پی", "title"), ("فروشنده", "merchant"),
    ("نوع آفر", "channel_fa"), ("دسته‌بندی", "category_fa"), ("قیمت اسنپ‌پی (تومان)", "snapp_price"),
    ("قیمت قبل اسنپ‌پی", "snapp_before"), ("کش‌بک اسنپ‌پی %", "cashback_pct"),
    ("قیمت اسنپ‌پی پس از کش‌بک", "snapp_effective"), ("محصول دیجی‌کالا", "dk_title"),
    ("قیمت دیجی‌کالا (تومان)", "dk_price"), ("قیمت قبل دیجی‌کالا", "dk_rrp"),
    ("تخفیف دیجی‌کالا %", "dk_discount"), ("شگفت‌انگیز", "dk_incredible_fa"),
    ("اختلاف (تومان)", "diff_toman"), ("اختلاف %", "diff_pct"),
    ("اختلاف % پس از کش‌بک", "diff_pct_vs_effective"), ("نتیجه", "verdict_fa"),
    ("وضعیت پخش", "live_fa"), ("زمان", "live_text"), ("لینک اسنپ‌پی", "snapp_url"),
    ("لینک دیجی‌کالا", "dk_url"),
]
VERDICT_FA = {"dk_cheaper": "دیجی‌کالا ارزان‌تر", "equal": "برابر", "snapp_cheaper": "اسنپ‌پی ارزان‌تر"}
LIVE_FA = {"live": "در حال پخش", "upcoming": "نوبت بعد", "ended": "تمام‌شده"}


def write_xlsx(rows: list[dict], summary: dict) -> None:
    """data/report.xlsx - summary + full list + Digikala-cheaper + not-on-Digikala sheets."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        log.warning("openpyxl not installed - skipping report.xlsx")
        return

    def flat(r: dict) -> list:
        x = {**r, "dk_status_fa": DK_STATUS_LABELS.get(r.get("dk_status"), ""),
             "channel_fa": CHANNEL_LABELS.get(r["channel"], r["channel"]),
             "category_fa": CATEGORY_LABELS.get(r["category"], r["category"]),
             "dk_incredible_fa": "بله" if r.get("dk_is_incredible") else "",
             "verdict_fa": VERDICT_FA.get(r.get("verdict"), ""),
             "live_fa": LIVE_FA.get(r.get("live_status"), "")}
        return [x.get(k) for _, k in XLSX_COLS]

    wb = Workbook()
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="1F6FEB")

    def sheet(title: str, data: list[dict], first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.sheet_view.rightToLeft = True
        ws.append([h for h, _ in XLSX_COLS])
        for c in ws[1]:
            c.font, c.fill = head, fill
        for r in data:
            ws.append(flat(r))
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col, w in zip("ABCDEFGHIJKLMNOPQRSTUVW", [22, 40, 45, 18, 18, 16, 14, 14, 10, 14, 45, 14, 14, 10, 9, 14, 9, 12, 16, 12, 14, 35, 35]):
            ws.column_dimensions[col].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                    c.number_format = "#,##0.0" if isinstance(c.value, float) else "#,##0"

    order = {"matched": 0, "review": 1, "uncertain": 2, "not_found": 3}
    all_rows = sorted(rows, key=lambda r: (order.get(r.get("dk_status"), 9), -(r.get("diff_pct") or 0)))
    high = [r for r in rows if r["confidence"] == "high"]
    sheet("همه‌ی تخفیف‌های اسنپ‌پی", all_rows, first=True)
    sheet("دیجی‌کالا ارزان‌تر", sorted([r for r in high if r.get("verdict") == "dk_cheaper"], key=lambda r: r["diff_pct"]))
    sheet("اسنپ‌پی ارزان‌تر", sorted([r for r in high if r.get("verdict") == "snapp_cheaper"], key=lambda r: -r["diff_pct"]))
    sheet("در دیجی‌کالا پیدا نشد", [r for r in rows if r.get("dk_status") == "not_found"])

    ws = wb.create_sheet("خلاصه", 0)
    ws.sheet_view.rightToLeft = True
    for k, label in [("run_at", "آخرین اجرا (تهران)"), ("snapp_items", "کل تخفیف‌های اسنپ‌پی"),
                     ("landing_items", "تخفیف‌های لندینگ"), ("matched", "تطبیق قطعی روی دیجی‌کالا"),
                     ("matched_medium", "نیازمند بررسی"), ("uncertain", "نامشخص"),
                     ("not_found", "در دیجی‌کالا پیدا نشد"), ("dk_cheaper", "دیجی‌کالا ارزان‌تر"),
                     ("equal", "برابر"), ("snapp_cheaper", "اسنپ‌پی ارزان‌تر"),
                     ("median_diff_pct", "میانه اختلاف % (مثبت = دیجی‌کالا گران‌تر)")]:
        ws.append([label, summary.get(k)])
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 18
    wb.save(DATA / "report.xlsx")


def write_outputs(rows: list[dict], summary: dict) -> None:
    PRODUCT_CACHE_FILE.write_text(json.dumps(PRODUCT_CACHE, ensure_ascii=False), "utf-8")
    (DATA / "latest.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")
    with open(DATA / "latest.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS, extrasaction="ignore")
        w.writeheader()
        order = {"high": 0, "medium": 1, "low": 2, "none": 3}
        for r in sorted(rows, key=lambda r: (order[r["confidence"]], -(r.get("diff_pct") or 0))):
            w.writerow(r)
    hist = DATA / "summary_history.csv"
    keys = ["run_at", "snapp_items", "searched_ok", "matched", "matched_medium", "dk_cheaper",
            "equal", "snapp_cheaper", "median_diff_pct", "mean_diff_pct"]
    new = not hist.exists()
    with open(hist, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(summary)
    write_xlsx(rows, summary)
    history = list(csv.DictReader(open(hist, encoding="utf-8")))
    font = ROOT / "assets" / "Vazirmatn.woff2"
    html = render_report(rows, summary, history[-40:], CATEGORY_LABELS, CHANNEL_LABELS,
                         font.read_bytes() if font.exists() else None)
    (DOCS / "index.html").write_text(html, "utf-8")


def main() -> int:
    started = datetime.now(TZ)
    s = session()
    try:
        items = load_snapppay(s)
    except Exception as e:  # noqa: BLE001
        log.error("Could not read SnappPay feeds: %s", e)
        return 2
    if not items:
        log.error("SnappPay feeds returned no products")
        return 2
    if LIMIT:
        items = items[:LIMIT]

    preflight(s)
    log.info("Searching %d products on Digikala with %d workers ...", len(items), WORKERS)
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for i, row in enumerate(ex.map(compare_one, items), 1):
            rows.append(enrich(row))
            if i % 50 == 0:
                log.info("  %d / %d", i, len(items))

    errors = sum(1 for r in rows if r["error"])
    if errors > len(rows) * 0.5:
        log.error("%d of %d Digikala searches failed - keeping previous report", errors, len(rows))
        return 4

    summary = summarize(rows, started)
    write_outputs(rows, summary)
    log.info("Done: %s", json.dumps({k: v for k, v in summary.items() if not k.startswith("by_")},
                                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
