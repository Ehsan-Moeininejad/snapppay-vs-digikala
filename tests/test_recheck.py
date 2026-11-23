# -*- coding: utf-8 -*-
"""Recheck cases from the manual review of real matches (2026-11-23)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from recheck import recheck  # noqa: E402


def rc(title, dk_title, brand_fa="", brand_en="", merchant="", category="health"):
    return recheck({"title": title, "merchant": merchant, "category": category},
                   {"title": dk_title}, {"title_fa": dk_title, "title_en": "", "brand_fa": brand_fa, "brand_en": brand_en})


def test_different_brand_goes_to_review():
    r = rc("زینک پلاس 10 میلی گرم یوروویتال بسته 60 عددی",
           "کپسول زینک پلاس 10 میلی گرم استار ویت بسته 60 عددی", "استار ویت", "Star Vit")
    assert r["verdict"] == "review"


def test_same_brand_passes():
    r = rc("کپسول ففول اینترافارم 30 عددی", "کپسول ففول اینترافارم بسته 30 عددی", "اینترافارم", "Interpharm")
    assert r["verdict"] == "pass"


def test_kitten_vs_adult_fails():
    r = rc("غذای خشک بچه گربه روتیکا ۱۰ کیلوگرم", "غذای خشک گربه روتیکا مدل adult وزن 10 کیلوگرم", "روتیکا", "Rotika", category="pet")
    assert r["verdict"] == "fail"


def test_sensitive_vs_whitening_fails():
    r = rc("دهان‌شویه سفیدکننده پرودنتین 400 میل", "دهان شویه پرودنتین 361 مدل Sensitive حجم 400 میلی لیتر", "پرودنتین", "Prodentin")
    assert r["verdict"] == "fail"


def test_iphone8_vs_8plus_fails():
    r = rc("ماکت گوشی موبایل اپل مدل iPhone 8", "ماکت گوشی موبایل اپل مدل iphone 8 plus", "اپل", "Apple", category="digital")
    assert r["verdict"] == "fail"


def test_flavour_fails():
    r = rc("کنسرو غذای گربه دی پی اس پته با طعم گوشت خالص وزن 800 گرم",
           "کنسرو غذای گربه بالغ دی پی اس مدل پته طعم مرغ وزن ۸۰۰ گرم", "دی پی اس", "DPS", category="pet")
    assert r["verdict"] == "fail"


def test_two_tyres_vs_one_fails():
    r = rc("لاستیک خودرو کویر تایر مدل KB27 سایز 185/65R14 – دو حلقه",
           "لاستیک خودرو سواری چهار فصل کویر تایر مدل KB27 سایز 185/65R14 تیوبلس", "کویر تایر", "Kavir Tire", category="automotive")
    assert r["verdict"] == "fail"


def test_bundle_fails():
    r = rc("پلی‌استیشن 5 اسلیم دیجیتال",
           "کنسول بازی سونی مدل PlayStation 5 Slim Digital Edition ظرفیت 825 گیگابایت ریجن CFI-2116 اروپا به همراه دسته اضافی و پایه شارژر",
           "سونی", "Sony", category="digital")
    assert r["verdict"] == "fail"


def test_product_line_implies_brand():
    r = rc("گوشی iPhone 17 Pro Max ظرفیت 256 گیگ",
           "گوشی موبایل اپل مدل iPhone 17 Pro Max ZAA تک سیم کارت + eSim ظرفیت 256 گیگابایت و رم 12 گیگابایت", "اپل", "Apple", category="digital")
    assert r["verdict"] == "pass"


def test_vague_title_goes_to_review():
    r = rc("مدل 2635", "لنت ترمز جلو وایت لیون کد 2635 مناسب برای برلیانس 220 / 230", "وایت لیون", "White Lion", category="automotive")
    assert r["verdict"] == "review"


def test_model_code_overrides_missing_brand():
    r = rc("همزن دستی گوسونیک مدل GHM-839", "همزن گوسونیک مدل GHM-839", "گوسونیک", "Gosonic", category="home")
    assert r["verdict"] == "pass"


def test_seller_name_counts_as_brand():
    r = rc("مانتو زنانه مدل 216637", "مانتو زنانه سرژه مدل 216637", "سرژه", "Serjeh", merchant="سرژه", category="fashion")
    assert r["verdict"] == "pass"


def test_joined_word_is_not_a_variant():
    r = rc("کپسول فمی لاکت توپلاس زیست تخمیر - 30 عددی", "کپسول فمی لاکت تو پلاس زیست تخمیر بسته 30 عددی", "زیست تخمیر", "Zist Takhmir")
    assert r["verdict"] == "pass"


def test_hyphen_code_counts():
    r = rc("گردنبند نقره کوبیک QP-1310", "گردنبند نقره زنانه کوبیک مدل QP-1310", "کوبیک", "Cubic", category="gold")
    assert r["verdict"] == "pass"


def test_persian_iphone_is_apple():
    r = rc("گوشی آیفون 17 پرو مکس 256 گیگ سرمه‌ای",
           "گوشی موبایل اپل مدل iPhone 17 Pro Max ZAA تک سیم کارت + eSim ظرفیت 256 گیگابایت", "اپل", "Apple", category="digital")
    assert r["verdict"] == "pass"


def test_partial_and_fuzzy_brand():
    assert rc("کپسول زینک پلاس ب کمپلکس 10 میلی گرم 60 عددی دانا", "کپسول زینک پلاس ب کمپلکس داروسازی دانا 10 میلی‌گرم بسته 60 عددی",
              "داروسازی دانا", "Dana")["verdict"] == "pass"
    from recheck import brand_status
    assert brand_status("پاوراستیشن 700 وات پاورولوژی", "پاورولوجی", "Powerology") == "ok"


def test_flavour_difference_still_fails():
    r = rc("کنسرو غذای سگ دی پی اس پته با طعم گوشت مرغ و بوقلمون و کدو وزن 800 گرم",
           "کنسرو غذای سگ دی پی اس مدل پته طعم مرغ، گوساله و بوقلمون وزن ۸۰۰ گرم", "دی پی اس", "DPS", category="pet")
    assert r["verdict"] == "fail"


def test_unspecified_model_goes_to_review():
    r = rc("ماشین ظرفشویی 14 نفره دوو", "ماشین ظرفشویی 14 نفره دوو مدل DW-160W", "دوو", "Daewoo", category="home")
    assert r["verdict"] == "review"


def test_unknown_size_goes_to_review():
    r = rc("ماگ استنلی Quencher", "تراول ماگ استنلی مدل Quencher Tumbler H2.0 کد 30oz گنجایش 0.89 لیتر", "استنلی", "Stanley", category="sports")
    assert r["verdict"] == "review"


def test_spaced_code_and_units():
    assert rc("چای‌ساز ایستاده GTS 071 میگل", "چای ساز روی هم میگل مدل GTS-071", "میگل", "Migel", category="home")["verdict"] == "pass"
    assert rc("پودر کراتین 300 گرمی دوبیس", "پودر کراتین مونو هیدرات میکرونایز دوبیس - 300 گرم", "دوبیس", "Dobis")["verdict"] == "pass"


def test_numeric_dk_model_needs_snapp_model():
    r = rc("سرویس قابلمه استیل 8 پارچه", "سرویس قابلمه استیل ۸ پارچه مدل 9900", "", "", category="home")
    assert r["verdict"] == "review"


def test_gender_conflict_fails():
    r = rc("شلوار اسلش دخترانه جين وست كد", "شلوار اسلش مردانه جين وست كد 24152002", "جین وست", "Jean West",
           merchant="جین وست", category="fashion")
    assert r["verdict"] == "fail"


def test_dk_multipack_fails():
    r = rc("کپسول گرناهیر پریمیوم آدریان", "قرص گرناهیر پریمیوم آدریان 3 بسته 30 عددی", "آدریان", "Adrian")
    assert r["verdict"] == "fail"


def test_generic_no_brand_goes_to_review():
    r = rc("عینک آفتابی دخترانه قلبی", "عینک آفتابی دخترانه مدل قلبی", "متفرقه", "Miscellaneous", category="fashion")
    assert r["verdict"] == "review"


def test_no_brand_with_shared_code_passes():
    r = rc("حوله سفری هپی کمپ کد 46805", "حوله سفری هپی کمپ کد 46805", "متفرقه", "Miscellaneous", category="sports")
    assert r["verdict"] == "pass"


def test_kitten_equals_bache():
    r = rc("غذای خشک بچه گربه روتیکا ۱۰ کیلوگرم", "غذای خشک بچه گربه روتیکا مدل kitten وزن 10 کیلوگرم", "روتیکا", "Rotika", category="pet")
    assert r["verdict"] == "pass"
