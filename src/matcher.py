# -*- coding: utf-8 -*-
"""Title normalisation and SnappPay -> Digikala product matching.

Pure functions, no network. Used by crawler.py and by the tests.
"""
from __future__ import annotations

import re

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_CHAR_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه", "أ": "ا", "إ": "ا", "آ": "ا",
    "‌": " ", "‏": " ", "‎": " ", "ـ": "",
})

# Words that say nothing about *which* product it is.
STOPWORDS = {
    "مدل", "کد", "سری", "طرح", "نوع", "رنگ", "سایز", "اندازه", "ظرفیت", "حجم", "وزن",
    "بسته", "عددی", "عدد", "مجموعه", "به", "با", "و", "از", "برای", "همراه", "در",
    "مناسب", "حاوی", "اصل", "اورجینال", "original", "new", "جدید", "-", "–", "+",
    "the", "for", "and", "with", "of", "model", "code",
}

# If one of these appears in the Digikala title but NOT in the SnappPay title,
# the Digikala item is very likely an accessory of the product (a sticker for a
# PS5, a case for a phone ...) - the classic false match.
ACCESSORY_WORDS = {
    "برچسب", "استیکر", "قاب", "کاور", "گلس", "محافظ", "کیف", "پایه", "هولدر", "شارژر",
    "کابل", "دسته", "لوازم", "یدک", "روکش", "جاکلیدی", "پوستر", "اسکین", "بند",
    "ماکت", "اسباب", "فیلتر", "سری", "کارتریج", "باتری",
}

# Applied to BOTH titles so either spelling meets the other.
UNIT_ALIASES = {
    "گیگ": "گیگابایت", "gb": "گیگابایت", "g": "گرم", "میل": "میلی", "ml": "میلی",
    "tb": "ترابایت", "ترا": "ترابایت", "mah": "میلی",
    # Persian transliterations of brand / model words -> latin
    "ایفون": "iphone", "اپل": "apple", "پرو": "pro", "مکس": "max", "پلاس": "plus",
    "اولترا": "ultra", "مینی": "mini", "اسلیم": "slim", "دیجیتال": "digital",
    "سامسونگ": "samsung", "گلکسی": "galaxy", "شیائومی": "xiaomi", "ردمی": "redmi",
    "پوکو": "poco", "ایرپاد": "airpods", "ایرپادز": "airpods", "واچ": "watch",
    "ایپد": "ipad", "مک": "mac", "بوک": "book", "نوکیا": "nokia", "هواوی": "huawei",
    "سونی": "sony", "پلیاستیشن": "playstation", "دوال": "dual", "سنس": "sense",
    "ث": "c", "ای": "e",
}
_PHRASES = [  # multi-word spellings, collapsed before tokenising
    ("پلی استیشن", "playstation"), ("جی بی ال", "jbl"), ("ال جی", "lg"),
    ("مک بوک", "macbook"), ("ایر پاد", "airpods"), ("دوال سنس", "dualsense"),
    ("ps5", "playstation 5"), ("ps4", "playstation 4"), ("پلی استیشن5", "playstation 5"),
]


def normalize(text: str) -> str:
    t = (text or "").translate(_FA_DIGITS).translate(_CHAR_MAP).lower()
    t = re.sub(r"(\d)[,٬](\d{3})", r"\1\2", t)          # 20,000 -> 20000
    t = re.sub(r"[^\w\s.]", " ", t)                        # punctuation -> space
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)              # keep 3.5, drop other dots
    t = re.sub(r"\s+", " ", t).strip()
    for a, b in _PHRASES:
        t = re.sub(rf"(?<!\S){re.escape(a)}(?!\S)", b, t)
    return t


def tokens(text: str) -> list[str]:
    out = []
    for tok in normalize(text).split():
        tok = UNIT_ALIASES.get(tok, tok)
        if tok in STOPWORDS or (len(tok) < 2 and not tok.isdigit() and not "a" <= tok <= "z"):
            continue
        out.append(tok)
    return out


_NUM_WORDS = {"یک": "1", "دو": "2", "سه": "3", "چهار": "4", "پنج": "5", "شش": "6",
              "هفت": "7", "هشت": "8", "نه": "9", "ده": "10", "دوازده": "12"}
_UNITS = [  # (regex on normalised text, canonical unit) - longest first
    (r"میلی ?لیتر", "ml"), (r"میلی ?گرم", "mg"), (r"میکرو ?گرم", "mcg"),
    (r"میلی ?امپر(?: ?ساعت)?", "mah"), (r"میلی|میل", "ml"),
    (r"کیلو ?گرم|کیلویی|کیلو", "kg"), (r"گرمی|گرم", "g"),
    (r"لیتری|لیتر", "l"), (r"گیگابایت|گیگ", "gb"), (r"ترابایت", "tb"), (r"اینچ", "inch"),
    (r"سانتی ?متر|سانت", "cm"), (r"مثقال(?:ی)?", "mesghal"),
    (r"عددی|عدد|حلقه|جفت|تکه", "pcs"),
]
_UNIT_RE = re.compile(
    r"(?<![\w.])(\d+(?:\.\d+)?|" + "|".join(_NUM_WORDS) + r") ?(" +
    "|".join(f"(?:{u})" for u, _ in _UNITS) + r")(?!\w)")


_TO_BASE = {"g": ("w", 1.0), "kg": ("w", 1000.0), "mesghal": ("w", 4.608),
            "ml": ("v", 1.0), "l": ("v", 1000.0)}


def quantities(text: str) -> dict[str, set[str]]:
    """{'g': {'300'}, 'pcs': {'2'}} - sizes and pack counts found in a title."""
    out: dict[str, set[str]] = {}
    for num, unit in _UNIT_RE.findall(normalize(text)):
        num = _NUM_WORDS.get(num, num)
        for pat, canon in _UNITS:
            if re.fullmatch(pat, unit):
                out.setdefault(canon, set()).add(num.rstrip("0").rstrip(".") if "." in num else num)
                break
    return out


def _families(q: dict[str, set[str]]) -> dict[str, list[float]]:
    """Weights in grams, volumes in ml - so 1 مثقال (4.6 g) never equals 1 g."""
    fam: dict[str, list[float]] = {}
    for unit, nums in q.items():
        if unit in _TO_BASE:
            f, k = _TO_BASE[unit]
            fam.setdefault(f, []).extend(float(n) * k for n in nums)
    return fam


_BUNDLE_RE = re.compile(r"(?<!\S)(ست|پک|همراه)(?!\S)")


def quantity_conflict(snapp_title: str, dk_title: str) -> bool:
    """Same unit, different numbers (300 g vs 500 g, 2 rings vs 4 rings, 1 مثقال vs 1 g),
    Digikala sells a small multipack (2-12) while SnappPay names no pack size, or the
    Digikala item is a bundle/set ("ست", "به همراه ...") that the SnappPay one is not."""
    s, d = quantities(snapp_title), quantities(dk_title)
    for unit in (s.keys() & d.keys()) - set(_TO_BASE):
        if not s[unit] & d[unit]:
            return True
    sf, df = _families(s), _families(d)
    for f in sf.keys() & df.keys():
        if not any(abs(a - b) <= 0.03 * max(a, b) for a in sf[f] for b in df[f]):
            return True
    if "pcs" in d and "pcs" not in s:
        if any(n.isdigit() and 2 <= int(n) <= 12 for n in d["pcs"]):
            return True
    if _BUNDLE_RE.search(normalize(dk_title)) and not _BUNDLE_RE.search(normalize(snapp_title)):
        return True
    return False


# Brand names alone don't identify a product ("پاوربانک شیائومی" is not one model).
BRAND_WORDS = {"apple", "samsung", "xiaomi", "huawei", "sony", "nokia", "jbl", "lg",
               "philips", "bosch", "anker", "baseus", "honor", "lenovo", "asus", "hp"}


def is_model_token(tok: str) -> bool:
    """Tokens that pin down an exact model: numbers and latin words (not brand names)."""
    if tok in BRAND_WORDS:
        return False
    return bool(re.search(r"\d", tok)) or bool(re.fullmatch(r"[a-z]{2,}", tok))


def build_query(title: str, max_tokens: int = 9) -> str:
    """Short search query: drop marketing tails after a comma / parenthesis."""
    head = re.sub(r"\([^)]*\)", " ", title)       # drop "(...)"
    head = re.split(r"[،]", head)[0]                 # drop marketing tail
    # Light clean-up only: Digikala's own search handles Persian spelling
    # variants (آ/ا, ی/ي) better than our aggressive normalisation would.
    head = head.translate(_FA_DIGITS).replace("\u200c", " ")
    head = re.sub(r"[^\w\s.\-]", " ", head)
    toks = [t for t in head.split() if t not in {"مدل", "کد", "-", "–"}]
    return " ".join(toks[:max_tokens])


def build_fallback_query(title: str) -> str | None:
    """Second, narrower search for products the first query missed: the product word
    plus its model codes (e.g. "همزن BS-368TS"). None when there is no model code."""
    words = build_query(title, max_tokens=20).split()
    models = [w for w in words if len(w) >= 3 and re.search(r"[A-Za-z]", w) and re.search(r"\d", w)]
    if not words or not models:
        return None
    q = " ".join([words[0]] + models[:2])
    return q if q != build_query(title) else None


def score(snapp_title: str, dk_title: str) -> dict:
    s_toks = tokens(snapp_title)
    d_toks = set(tokens(dk_title))
    if not s_toks:
        return {"score": 0.0, "model_ok": False, "accessory": False, "recall": 0.0,
                "model_hits": 0, "n_tokens": 0, "qty_conflict": False}

    def weight(t: str) -> float:
        return 2.0 if is_model_token(t) else 1.0

    total = sum(weight(t) for t in s_toks)
    hit = sum(weight(t) for t in s_toks if t in d_toks)
    recall = hit / total

    # Precision side: how much of the Digikala title is "extra" stuff.
    s_set = set(s_toks)
    extra = [t for t in d_toks if t not in s_set]
    precision = 1 - min(len(extra) / max(len(d_toks), 1), 1)

    s_models = {t for t in s_toks if is_model_token(t)}
    d_models = {t for t in d_toks if is_model_token(t)}
    model_ok = s_models <= d_models if s_models else True

    accessory = bool((d_toks & ACCESSORY_WORDS) - s_set)

    model_hits = len(s_models & d_models)
    qty_conflict = quantity_conflict(snapp_title, dk_title)

    sc = 0.75 * recall + 0.25 * precision
    if not model_ok:
        sc -= 0.20
    if accessory:
        sc -= 0.35
    if qty_conflict:
        sc -= 0.25
    n_words = len(tokens(snapp_title.replace("\u200c", "")))
    return {"score": round(max(sc, 0.0), 3), "model_ok": model_ok, "accessory": accessory,
            "recall": round(recall, 3), "model_hits": model_hits, "n_tokens": n_words,
            "qty_conflict": qty_conflict}


def price_plausible(dk_price: float, snapp_price: float, snapp_before: float | None) -> bool:
    """Reject matches whose price is in a different universe (accessory/bundle)."""
    if not dk_price or not snapp_price:
        return False
    ref_hi = max(snapp_before or 0, snapp_price)
    return snapp_price * 0.35 <= dk_price <= ref_hi * 2.5


def _confidence(b: dict, strict: bool) -> str:
    clean = b["model_ok"] and b["price_ok"] and not b["accessory"] and not b["qty_conflict"]
    # A title must be specific enough to name ONE product: a shared model number /
    # latin model word, or enough descriptive words. "کفش ورزشی مردانه" is not.
    specific_hi = b["model_hits"] >= 1 or (not strict and b["n_tokens"] >= 5 and b["recall"] >= 0.9)
    specific_md = b["model_hits"] >= 1 or (not strict and b["n_tokens"] >= 4)
    if clean and specific_hi and b["score"] >= 0.72:
        return "high"
    if clean and specific_md and b["score"] >= 0.6 and b["recall"] >= 0.75:
        return "medium"
    return "low"


def rank_candidates(snapp_title: str, snapp_price: float, snapp_before: float | None,
                    candidates: list[dict], strict: bool = False) -> list[dict]:
    """All candidates scored, best first (ties within 0.02 -> cheaper first), each with
    its own confidence. Used by the recheck step to fall back to the next candidate."""
    out, seen = [], set()
    for c in candidates:
        if not c.get("price") or c.get("id") in seen:
            continue
        seen.add(c.get("id"))
        sc = score(snapp_title, c["title"])
        if not price_plausible(c["price"], snapp_price, snapp_before):
            sc["score"] = round(sc["score"] - 0.25, 3)
            sc["price_ok"] = False
        else:
            sc["price_ok"] = True
        b = {**c, **sc}
        b["confidence"] = _confidence(b, strict)
        out.append(b)
    out.sort(key=lambda b: (-round(b["score"] / 0.02), b["price"]))
    return out


def best_match(snapp_title: str, snapp_price: float, snapp_before: float | None,
               candidates: list[dict], strict: bool = False) -> dict | None:
    """candidates: dicts with id, title, price (Toman). Returns best with confidence.

    strict=True (gold & jewellery, priced by weight): a shared model number is required.
    """
    best = None
    for b in rank_candidates(snapp_title, snapp_price, snapp_before, candidates, strict):
        better = best is None or b["score"] > best["score"] + 0.02 or (
            abs(b["score"] - best["score"]) <= 0.02 and b["price"] < best["price"])
        if better:
            best = b
    return best
