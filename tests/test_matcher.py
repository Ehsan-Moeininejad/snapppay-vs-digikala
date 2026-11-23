# -*- coding: utf-8 -*-
"""Cases taken from real SnappPay / Digikala data (2026-11-23). Run: python -m pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from matcher import best_match  # noqa: E402


def c(title, price, i=0):
    return {"id": i, "title": title, "price": price}


def test_ps5_ignores_sticker_and_matches_console():
    m = best_match("پلی‌استیشن 5 اسلیم دیجیتال", 90_000_000, 190_000_000, [
        c("برچسب کنسول بازی پلی استیشن5 اسلیم دیجیتال توییجین وموییجین مدل space 02 مجموعه6 عددی", 800_000, 1),
        c("کنسول بازی سونی مدل PlayStation 5 Slim Digital Edition ظرفیت 825 گیگابایت ریجن CFI-2116 اروپا", 205_000_000, 2),
        c("کنسول بازی سونی مدل PlayStation 5 Slim ظرفیت 1 ترابایت ریجن CFI-2116 اروپا", 202_999_000, 3),
    ])
    assert m["id"] == 2 and m["confidence"] in ("high", "medium")


def test_iphone_persian_title():
    m = best_match("گوشی آیفون 17 پرو مکس 256 گیگ سرمه‌ای", 406_000_000, 583_000_000, [
        c("گوشی موبایل سامسونگ مدل Galaxy S25 FE دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت", 183_066_400, 1),
        c("گوشی موبایل اپل مدل iPhone 17 Pro Max ZAA تک سیم کارت + eSim ظرفیت 256 گیگابایت و رم 12 گیگابایت", 529_999_000, 2),
        c("گوشی موبایل اپل مدل iPhone 17 Pro Max ZAA تک سیم کارت + eSim ظرفیت 512 گیگابایت و رم 12 گیگابایت", 660_930_000, 3),
    ])
    assert m["id"] == 2 and m["confidence"] in ("high", "medium")


def test_wrong_model_is_not_confident():
    # SnappPay sells S24 FE, Digikala only shows S25 FE -> must not be a match
    m = best_match("گوشی Galaxy S24 FE ظرفیت 256 گیگ", 108_000_000, 180_000_000, [
        c("گوشی موبایل سامسونگ مدل Galaxy S25 FE دو سیم کارت ظرفیت 256 گیگابایت و رم 8 گیگابایت", 183_066_400),
        c("محافظ صفحه نمایش شهر گلس مدل SUPRDS مناسب برای گوشی موبایل سامسونگ Galaxy S24 FE 5G", 297_000),
    ])
    assert m["confidence"] == "low"


def test_only_accessory_available():
    m = best_match("گوشی Redmi A7 Pro ظرفیت 128 گیگ", 21_962_500, 43_925_000, [
        c("محافظ صفحه نمایش لایونکس مدل SUPERDNL مناسب برای گوشی موبایل شیائومی Redmi A7 Pro 4G / 5G", 400_000),
        c("گوشی موبایل شیائومی مدل Redmi A3 Pro دو سیم کارت ظرفیت 128 گیگابایت و رم 4 گیگابایت", 49_999_000),
    ])
    assert m["confidence"] == "low"


def test_same_product_exact_title():
    m = best_match("چمدان مونزا مدل 7070 سایز بزرگ ارتفاع 75 سانتی متر", 9_083_025, 28_360_500, [
        c("ست چهار عددی چمدان مدل فشن FSN7070 VIP NEW", 28_999_000, 1),
        c("چمدان مونزا مدل 7070 سایز بزرگ ارتفاع 75 سانتی متر", 25_900_000, 2),
    ])
    assert m["id"] == 2 and m["confidence"] == "high"


def test_vitamin_c_persian_letter():
    m = best_match("قرص ویتامین C 1000 میلی گرم یوروویتال بسته 60 عدد", 223_900, 814_000, [
        c("قرص زینک پلاس پابا یوروویتال بسته 60 عددی", 590_000, 1),
        c("قرص ویتامین ث 1000 یورویتال بسته 60 عددی", 278_000, 2),
    ])
    assert m["id"] == 2 and m["confidence"] in ("high", "medium")


def test_six_pack_vs_single_pack_rejected_by_price():
    m = best_match("پک 6 عددی قرص کروم 200 میلی گرم یوروویتال بسته 60 عددی", 690_998, 2_574_000, [
        c("قرص کروم 200 میکروگرم یوروویتال بسته 60 عددی", 90_000),
    ])
    assert m["confidence"] == "low"


def test_airpods_picks_base_variant_on_tie():
    m = best_match("هدفون اپل AirPods 4", 15_000_000, 30_000_000, [
        c("هدفون بلوتوثی اپل مدل AirPods 4 دارای نویز کنسلینگ، درگاه شارژ USB-Type-C و شارژ بی سیم", 34_000_000, 1),
        c("هدفون بلوتوثی اپل مدل AirPods 4 فاقد قابلیت نویز کنسلینگ، درگاه شارژ USB Type-C، شارژ بی سیم", 26_167_800, 2),
        c("هدفون بلوتوثی وونک مدل Light_3", 1_849_990, 3),
    ])
    assert m["id"] in (1, 2) and m["confidence"] in ("high", "medium")


def test_tyre_size_and_pack():
    m = best_match("لاستیک خودرو کویر تایر مدل KB27 سایز 185/65R14 – دو حلقه", 11_000_000, 55_000_000, [
        c("لاستیک خودرو سواری چهار فصل کویر تایر مدل KB27 سایز 185/65R14 تیوبلس", 11_900_000, 1),
        c("لاستیک خودرو کویر تایر مدل KB27 سایز 185/65R15 - یک حلقه", 9_506_000, 2),
    ])
    assert m["id"] == 1


def test_generic_title_is_not_a_match():
    m = best_match("کفش ورزشی مردانه", 2_000_000, 5_000_000, [c("کفش ورزشی مردانه روویکس مدل 1064", 1_900_000)])
    assert m["confidence"] == "low"


def test_tyre_two_vs_four_rings():
    m = best_match("لاستیک خودرو کویر تایر مدل KB27 سایز 185/65R14 – دو حلقه", 11_000_000, 55_000_000, [
        c("لاستیک خودرو کویر تایر مدل KB27 سایز 185/65R14 - چهار حلقه", 43_500_000),
    ])
    assert m["confidence"] == "low"


def test_multipack_vs_single():
    m = best_match("قهوه فوری گلد گرمی", 900_000, 1_500_000, [c("قهوه فوری گلد گرمی - 300 گرم بسته 2 عددی", 1_760_000)])
    assert m["confidence"] == "low"


def test_same_pill_count_ok():
    m = best_match("قرص کرومیوم 200 میکروگرم نورم لایف 60 عددی", 76_800, 429_000, [
        c("قرص کرومیوم 200 نورم لایف بسته 60 عددی", 165_000)])
    assert m["confidence"] in ("high", "medium")


def test_gold_requires_model_number():
    m = best_match("گردنبند طلا لویی ویتون", 20_000_000, 30_000_000,
                   [c("آویز گردنبند طلا 18 عیار زنانه ماوی گالری مدل لویی ویتون رز", 12_000_000)], strict=True)
    assert m["confidence"] == "low"


def test_mesghal_is_not_gram():
    m = best_match("زعفران سرگل قائنات – 1 مثقالی – خاتم", 1_770_000, 2_490_000,
                   [c("زعفران سرگل قائنات - 1 گرم", 700_000)])
    assert m["confidence"] == "low"


def test_brand_only_title_is_not_a_match():
    m = best_match("پاوربانک شیائومی", 6_300_000, 9_000_000,
                   [c("پاوربانک 18 وات شیائومی مدل Redmi ظرفیت 20000 میلی‌آمپرساعت", 3_499_000)])
    assert m["confidence"] == "low"


def test_bundle_is_not_single_item():
    m = best_match("تی‌شرت چاپ‌دار مردانه", 1_000_000, 1_500_000,
                   [c("ست تی‌شرت آستین کوتاه و شلوارک راحتی مردانه مدل چاپ دار", 590_000)])
    assert m["confidence"] == "low"
    m = best_match("پلی‌استیشن 5 اسلیم دیجیتال", 90_000_000, 190_000_000, [
        c("کنسول بازی سونی مدل PlayStation 5 Slim Digital Edition ظرفیت 825 گیگابایت به همراه دسته اضافی و پایه شارژر", 220_000_000)])
    assert m["confidence"] == "low"


def test_fallback_query_uses_model_code():
    from matcher import build_fallback_query
    assert build_fallback_query("همزن بوش برقی مدل BOSCH BS-368TS") == "همزن BS-368TS"
    assert build_fallback_query("کت لینن زنانه فروزان") is None
