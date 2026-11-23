# -*- coding: utf-8 -*-
"""Second-pass verification ("recheck") of a SnappPay -> Digikala match.

The first pass (matcher.best_match) only compares search-result titles. The recheck
reads the Digikala product itself (brand in Persian/English, full title, category)
and rejects or downgrades matches that a person would reject:

  hard fail (-> not a match):  different variant (Pro vs non-Pro, kitten vs adult,
                               Sensitive vs whitening), different flavour, bundle vs
                               single item, different size / pack count
  soft fail (-> "needs review"): Digikala's brand does not appear in the SnappPay
                               title or seller, title too vague to name one product

Pure functions; the HTTP fetch of the product lives in crawler.py.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from matcher import _FA_DIGITS, UNIT_ALIASES, normalize, quantities, quantity_conflict, tokens

# Product-line words that imply a brand even when the brand name is absent.
LINE_BRAND = {
    "iphone": "apple", "ipad": "apple", "airpods": "apple", "macbook": "apple", "imac": "apple",
    "galaxy": "samsung", "redmi": "xiaomi", "poco": "xiaomi", "playstation": "sony",
    "dualsense": "sony", "ps5": "sony", "ps4": "sony", "nespresso": "delonghi",
}
BRAND_SYNONYMS = {  # Persian brand name -> latin, both directions are checked
    "اپل": "apple", "سامسونگ": "samsung", "شیائومی": "xiaomi", "سونی": "sony",
    "جی بی ال": "jbl", "ال جی": "lg", "فیلیپس": "philips", "بوش": "bosch",
    "انکر": "anker", "باسئوس": "baseus", "بیسوس": "baseus", "دلونگی": "delonghi",
    "هواوی": "huawei", "نوکیا": "nokia", "لنوو": "lenovo", "ایسوس": "asus",
}
NO_BRAND = {"", "متفرقه", "miscellaneous", "other", "نامشخص", "generic"}
# Words inside brand names that do not identify the brand on their own.
BRAND_FILLER = {"داروسازی", "شرکت", "گروه", "صنایع", "گالری", "پروفیشینال", "professional",
                "group", "co", "company", "industries", "پخش", "تولیدی", "برند", "home", "هوم"}

# Words that name a variant: present on one side only -> different product.
VARIANT_WORDS = {
    "pro", "max", "plus", "ultra", "mini", "lite", "fe", "nc", "anc", "edge", "air",
    "بچه", "kitten", "توله", "puppy", "junior", "بالغ", "adult", "senior",
    "sensitive", "سفیدکننده", "دوقلو", "ساید", "اولد", "oled", "qled",
}
_FLAVOUR_RE = re.compile(r"(?:طعم|رایحه)\s+((?:\S+\s*){1,5})")
_FLAVOUR_STOP = {"و", "با", "حجم", "وزن", "مدل", "بسته", "مناسب", "گرم", "میلی", "لیتر"}


def _nospace(text: str) -> str:
    return re.sub(r"\s+", "", normalize(text))


def brand_status(snapp_text: str, brand_fa: str, brand_en: str, dk_title: str = "") -> str:
    """'ok' | 'unknown' (Digikala item has no real brand) | 'missing'."""
    bfa, ben = (brand_fa or "").strip(), (brand_en or "").strip().lower()
    if normalize(bfa) in NO_BRAND and ben in NO_BRAND:
        return "unknown"
    hay = _nospace(snapp_text)
    cands = {c for c in (_nospace(bfa), _nospace(ben)) if len(c) >= 2}
    syn = BRAND_SYNONYMS.get(normalize(bfa))
    if syn:
        cands.add(syn)
    if any(c in hay for c in cands):
        return "ok"
    toks = set(tokens(snapp_text)) | set(normalize(snapp_text).split())
    for line, brand in LINE_BRAND.items():
        if line in toks and brand in cands | {ben}:
            return "ok"
    # A distinctive word of the brand is enough ("فیدار" for "فیدار پاتیرا", "دانا" for
    # "داروسازی دانا"); near-identical spelling too ("پاورولوژی" ~ "پاورولوجی").
    # A brand word that is also an ordinary word of the product title ("قهوه" in the
    # brand "قهوه بار" of "دانه قهوه ... قهوه بار") does not identify the brand.
    rest = normalize(dk_title).replace(normalize(bfa), " ") if bfa else normalize(dk_title)
    rest_words = set(rest.split())
    words = [w for w in normalize(f"{bfa} {ben}").split()
             if len(w) >= 3 and w not in BRAND_FILLER and w not in rest_words]
    for w in words:
        if w in toks:
            return "ok"
        if len(w) >= 5 and any(len(t) >= 5 and SequenceMatcher(None, w, t).ratio() >= 0.8 for t in toks):
            return "ok"
    return "missing"


def _flavours(text: str) -> set[str]:
    out: set[str] = set()
    for m in _FLAVOUR_RE.finditer(normalize(text)):
        for w in m.group(1).split():
            if w in _FLAVOUR_STOP or w.isdigit():
                break
            out.add(w)
    return out


_ALIAS_BACK: dict[str, set[str]] = {}
for _fa, _lat in UNIT_ALIASES.items():
    _ALIAS_BACK.setdefault(_lat, set()).add(_fa)


# Same meaning, different language: compared as one word.
VARIANT_CANON = {"kitten": "بچه", "puppy": "بچه", "توله": "بچه", "junior": "بچه",
                 "adult": "بالغ", "oled": "اولد"}


def variant_conflict(snapp_title: str, dk_title: str) -> list[str]:
    canon = lambda ws: {VARIANT_CANON.get(w, w) for w in ws}  # noqa: E731
    s, d = canon(tokens(snapp_title)), canon(tokens(dk_title))
    ns, nd = _nospace(snapp_title), _nospace(dk_title)
    out = []
    for w in sorted((s ^ d) & VARIANT_WORDS):
        other = nd if w in s else ns
        forms = {w} | _ALIAS_BACK.get(w, set())
        # "توپلاس" (one word) still contains "پلاس": not a different variant
        if any(f in other for f in forms if len(f) >= 3):
            continue
        out.append(w)
    return out


def flavour_conflict(snapp_title: str, dk_title: str) -> bool:
    a, b = _flavours(snapp_title), _flavours(dk_title)
    return bool(a and b and a != b)


_CODE_RE = re.compile(r"[a-z0-9]+(?:[-_/][a-z0-9]+)*")


def _join_spaced(text: str) -> str:
    """'GTS 071' -> 'gts071' so a code written with a space is still a code."""
    t = text.translate(_FA_DIGITS).lower()
    return re.sub(r"\b([a-z]{2,4})\s+(\d{2,5})\b", r"\1\2", t)


def strong_model_code(snapp_title: str, dk_title: str) -> bool:
    """A shared code like BS-368TS, A3949, GHM-839, QP-0510 identifies one product."""
    d = re.sub(r"[\s\-_/]", "", dk_title.translate(_FA_DIGITS).lower())
    for w in _CODE_RE.findall(_join_spaced(snapp_title)):
        w2 = re.sub(r"[\-_/]", "", w)
        if len(w2) >= 4 and re.search(r"[a-z]", w2) and re.search(r"\d", w2) and w2 in d:
            return True
    return False


def recheck(item: dict, cand: dict, detail: dict | None) -> dict:
    """item: SnappPay row; cand: matcher result; detail: Digikala product data or None.

    Returns {"verdict": "pass"|"review"|"fail", "reasons": [...], "dk_title_full": str,
             "brand_fa": str, "brand_en": str}
    """
    title_fa = (detail or {}).get("title_fa") or cand.get("title", "")
    title_en = (detail or {}).get("title_en") or ""
    brand_fa = (detail or {}).get("brand_fa") or cand.get("brand", "") or ""
    brand_en = (detail or {}).get("brand_en") or ""
    dk_full = f"{title_fa} {title_en}".strip()
    st = item["title"]
    reasons: list[str] = []
    hard = False

    vc = variant_conflict(st, title_fa)
    if vc:
        reasons.append("مدل/نسخه متفاوت: " + "، ".join(vc))
        hard = True
    if flavour_conflict(st, title_fa):
        reasons.append("طعم یا رایحه متفاوت")
        hard = True
    if quantity_conflict(st, dk_full):
        reasons.append("حجم، وزن، تعداد یا بسته‌بندی متفاوت")
        hard = True
    sq, dq = _pcs(st), _pcs(title_fa)
    if sq and sq > 1 and not dq:
        reasons.append(f"اسنپ‌پی بسته‌ی {sq} عددی است، دیجی‌کالا تکی")
        hard = True
    if dq and dq > 1 and not sq:
        reasons.append(f"دیجی‌کالا بسته‌ی {dq} عددی است، اسنپ‌پی تکی")
        hard = True
    ga, gb = _genders(st), _genders(title_fa)
    if ga and gb and not (ga & gb):
        reasons.append("جنسیت/گروه سنی متفاوت: " + "، ".join(sorted(ga)) + " ≠ " + "، ".join(sorted(gb)))
        hard = True

    code = strong_model_code(st, dk_full)
    bs = brand_status(f"{st} {item.get('merchant', '')}", brand_fa, brand_en, title_fa)
    soft = False
    if bs == "missing" and not code:
        reasons.append(f"برند دیجی‌کالا ({brand_fa or brand_en}) در عنوان اسنپ‌پی نیست")
        soft = True
    elif bs == "unknown" and not code and not shared_model_tokens(st, dk_full):
        reasons.append("کالای دیجی‌کالا برند مشخص ندارد و کد یا شماره‌ی مدل مشترکی هم نیست")
        soft = True
    dk_models = _codes(title_fa) + re.findall(r"(?:مدل|کد)\s+(\d{3,6})\b", normalize(title_fa))
    snapp_nums = set(re.findall(r"\d+", normalize(st)))
    dk_models = [m for m in dk_models if m not in snapp_nums]
    if not code and not _codes(st) and dk_models:
        reasons.append("دیجی‌کالا مدل مشخص دارد (" + dk_models[0].upper() + ") ولی عنوان اسنپ‌پی مدل ندارد")
        soft = True
    sf, df = set(quantities(st)), set(quantities(dk_full))
    size_units = {"g", "kg", "mesghal", "ml", "l", "inch", "gb", "tb", "mah"}
    if not code and (df & size_units) and not (sf & size_units):
        reasons.append("حجم/وزن/ظرفیت در عنوان اسنپ‌پی نیامده و قابل تطبیق نیست")
        soft = True
    missing = distinctive_missing(st, dk_full, brand_fa)
    if missing and not code:
        reasons.append("کلمه‌ی کلیدی اسنپ‌پی در عنوان دیجی‌کالا نیست: " + "، ".join(missing[:3]))
        soft = True
    n_words = len(tokens(st.replace("‌", "")))
    if n_words < 3 and not code:
        reasons.append("عنوان اسنپ‌پی برای تشخیص یک محصول مشخص کافی نیست")
        soft = True
    if item.get("category") == "gold" and not code:
        reasons.append("طلا و جواهر بدون کد مدل؛ قیمت به وزن بستگی دارد")
        soft = True

    verdict = "fail" if hard else ("review" if soft else "pass")
    return {"verdict": verdict, "reasons": reasons, "dk_title_full": title_fa,
            "brand_fa": brand_fa, "brand_en": brand_en}


# Ordinary words that may be absent from the other title without meaning a different
# product: colours, marketing words, generic product nouns.
GENERIC_WORDS = set("""
مشکی سفید سرمه سرمه‌ای سرمه ای بنفش آبی ابی قرمز سبز زرد نارنجی صورتی طوسی خاکستری نقره‌ای نقره ای طلایی کرم قهوه‌ای
قهوه ای رنگ اصلی اصل استاندارد مدرن بدون فاقد دارای میکروگرم مثقال مثقالی کیلویی گرمی لیتری
سرویس قابلمه تابه استیل چاقو ظرف ظروف لباس پوشاک کیف کفش ساعت گوشواره گردنبند دستبند انگشتر آویز زنجیر اورجینال original جدید ویژه هدیه کادویی ارسال رندوم سایز بزرگ کوچک متوسط عدد عددی تعداد
گوشی موبایل هوشمند اسمارت بلوتوثی بلوتوث بی‌سیم بیسیم وات لیتری لیتر کیلویی کیلوگرم گرمی گرم میل میلی سانتی متری متر
دستی برقی شارژی ایستاده رومیزی زمینی دیواری توکار آموزشی اموزشی خانگی حرفه‌ای حرفه ای پرتابل قابل حمل زنانه مردانه
بچگانه دخترانه پسرانه یونیسکس برند مدل کد طرح سری ست مجموعه بسته پک جفت حلقه پارچه نفره فوت اینچ ظرفیت گیگ گیگابایت
ترابایت حجم وزن کپسول قرص شربت ساشه سافت ژل پودر دانه مکمل غذای خشک کنسرو با برای مناسب همراه و از به در
""".split())


def distinctive_missing(snapp_title: str, dk_full: str, brand_fa: str = "") -> list[str]:
    """Persian product-name words of the SnappPay title (4+ letters) that the Digikala
    title lacks, e.g. "هیرویت" vs "کورکومکس" under the same brand."""
    hay = _nospace(f"{dk_full} {brand_fa}")
    out = []
    for w in normalize(snapp_title).split():
        if len(w) < 4 or w in GENERIC_WORDS or re.search(r"[a-z0-9]", w):
            continue
        if w in hay or any(f in hay for f in _ALIAS_BACK.get(w, ())):
            continue
        dk_words = normalize(f"{dk_full} {brand_fa}").split()
        # spelling variants ("ویواتیون" ~ "ویواتون") and run-together words ("کلدحجم")
        if any(len(x) >= 4 and SequenceMatcher(None, w, x).ratio() >= 0.8 for x in dk_words):
            continue
        if any(len(x) >= 3 and (w.startswith(x) or w.endswith(x)) and len(x) >= len(w) * 0.5 for x in dk_words):
            continue
        lat = UNIT_ALIASES.get(w)
        if lat and lat in hay:
            continue
        out.append(w)
    return out


def _codes(text: str) -> list[str]:
    """Model codes: letters+digits, 4+ chars once '-', '/' are removed (DW-160W, PB3018ZM)."""
    out = []
    for w in _CODE_RE.findall(_join_spaced(text)):
        w2 = re.sub(r"[\-_/]", "", w)
        if len(w2) >= 4 and re.search(r"[a-z]", w2) and re.search(r"\d", w2):
            out.append(w)
    return out


def shared_distinctive(snapp_title: str, dk_full: str) -> list[str]:
    """Non-generic words (4+ letters) that both titles contain: a product name in common."""
    d = set(normalize(dk_full).split())
    return [w for w in normalize(snapp_title).split()
            if len(w) >= 4 and w not in GENERIC_WORDS and not w.isdigit() and w in d]


GENDER_WORDS = {"زنانه": "زن", "مردانه": "مرد", "دخترانه": "دختر", "پسرانه": "پسر",
                "بچگانه": "کودک", "نوزادی": "نوزاد"}


def _genders(text: str) -> set[str]:
    words = set(normalize(text).split())
    out = {v for k, v in GENDER_WORDS.items() if k in words}
    if "یونیسکس" in words or "unisex" in words:
        out |= {"زن", "مرد"}
    return out


def shared_model_tokens(snapp_title: str, dk_full: str) -> list[str]:
    """Latin model words or 3+ digit numbers present in both titles (46805, toyoset, plus)."""
    d = set(tokens(dk_full))
    return [t for t in tokens(snapp_title) if t in d and
            ((re.fullmatch(r"[a-z]{3,}", t) and t not in LINE_BRAND) or re.fullmatch(r"\d{3,}", t))]


_PCS_RE = re.compile(r"(\d+|دو|سه|چهار|پنج|شش|ده|دوازده)\s?(?:حلقه|عددی|عدد|جفت|تایی)")
_NUM = {"دو": 2, "سه": 3, "چهار": 4, "پنج": 5, "شش": 6, "ده": 10, "دوازده": 12}


def _pcs(text: str) -> int | None:
    """Pack count for small packs only (2-12); pill counts like '60 عددی' are ignored.
    Also "3 بسته 30 عددی" (three packs of 30)."""
    t = normalize(text)
    m = re.search(r"(\d+|دو|سه|چهار|پنج|شش)\s?بسته(?:\s|$)", t)
    if m:
        n = _NUM.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else 0)
        if 2 <= n <= 12:
            return n
    for m in _PCS_RE.finditer(t):
        n = _NUM.get(m.group(1)) or (int(m.group(1)) if m.group(1).isdigit() else None)
        if n and 2 <= n <= 12:
            return n
    return None
