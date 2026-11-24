# -*- coding: utf-8 -*-
"""Self-contained dark Persian HTML report (Vazirmatn embedded, Latin digits).

Structure (marketing / product view):
  1. Key findings in plain sentences, landing and timed deals kept apart
  2. Headline tiles per offer type + match coverage
  3. Changes since the previous run (30-minute cadence)
  4. Timed deals live now / next, with Digikala price
  5. Action lists: where Digikala is more expensive / cheaper (landing)
  6. Category and merchant breakdowns, trend
  7. Full filterable, sortable table with SnappPay and Digikala links + Excel export
  8. Method notes
"""
from __future__ import annotations

import base64
import html
import json

STATUS_LABEL = {"matched": "تطبیق قطعی", "review": "نیازمند بررسی",
                "uncertain": "نامشخص", "not_found": "در دیجی‌کالا پیدا نشد"}
CONF_LABEL = {"high": "بالا", "medium": "متوسط", "low": "ضعیف", "none": "بدون نتیجه"}
VERDICT_LABEL = {"dk_cheaper": "دیجی‌کالا ارزان‌تر", "equal": "برابر",
                 "snapp_cheaper": "اسنپ‌پی ارزان‌تر"}
LIVE_LABEL = {"live": "در حال پخش", "upcoming": "نوبت بعد", "ended": "تمام‌شده"}
GROUP_LABEL = {"landing": "لندینگ بلک فرایدی (قیمت فروشگاه‌ها)",
               "timed": "آفرهای زمان‌دار تقویم (آنلاین، حضوری، لایو)"}

esc = html.escape


def _n(v) -> str:
    return "—" if v is None else f"{int(round(v)):,}"


def _pct(v) -> str:
    return "—" if v is None else f'<span dir="ltr">{v:+.1f}%</span>'


def _signed(v) -> str:
    return "—" if v is None else f'<span dir="ltr">{"+" if v > 0 else ""}{int(round(v)):,}</span>'


def _cls(v) -> str:
    if v is None:
        return ""
    return "pos" if v > 1 else "neg" if v < -1 else ""


def _phrase(m) -> str:
    """Median gap in words: product teams read 'Digikala 4.5% cheaper' faster than '-4.5%'."""
    if m is None:
        return "—"
    if m < -1:
        return f"دیجی‌کالا {abs(m):.1f}% ارزان‌تر"
    if m > 1:
        return f"دیجی‌کالا {m:.1f}% گران‌تر"
    return "تقریباً برابر"


def _share(part, whole) -> int:
    return round(part / whole * 100) if whole else 0


def _links(snapp_url: str, channel: str, dk_link: str, matched: bool) -> str:
    s_label = "صفحه‌ی کالا (اسنپ‌پی) ↗" if channel == "landing" else "تقویم اسنپ‌پی ↗"
    d_label = "صفحه‌ی کالا (دیجی‌کالا) ↗" if matched else "جستجو در دیجی‌کالا ↗"
    out = []
    if snapp_url:
        out.append(f"<a class='lk s' href='{esc(snapp_url)}' target='_blank' rel='noopener'>{s_label}</a>")
    if dk_link:
        out.append(f"<a class='lk d' href='{esc(dk_link)}' target='_blank' rel='noopener'>{d_label}</a>")
    return f"<div class='lks'>{''.join(out)}</div>"


def _spark(values: list[float], color: str) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return '<span class="muted">پس از چند اجرا نمایش داده می‌شود</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    w, h = 260, 44
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / rng * (h - 6) - 3:.1f}"
                   for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="direction:ltr">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/></svg>'
            f'<div class="muted" dir="ltr" style="text-align:right">{vals[0]:.1f} → {vals[-1]:.1f}</div>')


def _item_table(items, channel_labels, show_live=False) -> str:
    head = ("<tr><th>محصول</th>" + ("<th>زمان پخش</th>" if show_live else "") +
            "<th>اسنپ‌پی</th><th>دیجی‌کالا</th><th>اختلاف تومان</th><th>اختلاف</th></tr>")
    body = []
    for r in items:
        live = ""
        if show_live:
            live = (f"<td><span class='tag {'on' if r.get('live_status') == 'live' else ''}'>"
                    f"{LIVE_LABEL.get(r.get('live_status'), '')}</span>"
                    f"<div class='muted'>{esc(r.get('live_text') or '')}</div></td>")
        flag = "<span class='tag warn'>اختلاف غیرعادی، قیمت چک شود</span>" if r.get("outlier") else ""
        body.append(
            "<tr>"
            f"<td>{esc(r['title'][:80])}{flag}"
            f"<div class='muted'>{esc((r['merchant'] or '—')[:40])} · {esc(channel_labels.get(r['channel'], r['channel']))}</div>"
            f"{_links(r['snapp_url'], r['channel'], r.get('dk_link') or r.get('dk_url', ''), True)}</td>"
            f"{live}<td>{_n(r['snapp_price'])}</td>"
            f"<td>{_n(r['dk_price'])}{'<span class=tag>شگفت‌انگیز</span>' if r.get('dk_is_incredible') else ''}</td>"
            f"<td class='{_cls(r['diff_pct'])}'>{_signed(r.get('diff_toman'))}</td>"
            f"<td class='{_cls(r['diff_pct'])}'>{_pct(r['diff_pct'])}</td></tr>")
    cols = 6 if show_live else 5
    rows = "".join(body) or f"<tr><td colspan='{cols}' class='muted'>موردی یافت نشد</td></tr>"
    return f"<div class='tw'><table><thead>{head}</thead><tbody>{rows}</tbody></table></div>"


def _breakdown_table(data: dict, labels: dict, first_col: str, limit: int | None = None) -> str:
    rows = []
    for k, v in list(data.items())[:limit]:
        n = v["n"]
        rows.append(
            f"<tr><td>{esc(labels.get(k, k or '—'))}</td><td>{v['total']}</td>"
            f"<td>{n} <span class='muted'>({_share(n, v['total'])}%)</span></td>"
            f"<td class='{_cls(v['median'])}'>{_phrase(v['median'])}</td>"
            f"<td><span class='neg'>{_share(v['dk_cheaper'], n)}%</span> / "
            f"<span class='pos'>{_share(v['snapp_cheaper'], n)}%</span></td></tr>")
    body = "".join(rows) or "<tr><td colspan=5 class=muted>—</td></tr>"
    return (f"<div class='tw'><table><thead><tr><th>{first_col}</th><th>تخفیف‌های اسنپ‌پی</th>"
            "<th>تطبیق قطعی (پوشش)</th><th>میانه‌ی اختلاف</th><th>دیجی‌کالا ارزان‌تر / گران‌تر</th>"
            f"</tr></thead><tbody>{body}</tbody></table></div>")


def _group_tiles(g: dict, label: str) -> str:
    n = g["n"]
    return f"""<div class="grp"><div class="gh">{label}</div><div class="grid">
<div class="tile"><span class="muted">تخفیف‌های اسنپ‌پی</span><b>{g['total']:,}</b></div>
<div class="tile"><span class="muted">تطبیق قطعی روی دیجی‌کالا</span><b>{n:,}</b><span class="muted">پوشش {_share(n, g['total'])}% · +{g['review']} نیازمند بررسی</span></div>
<div class="tile"><span class="muted">دیجی‌کالا ارزان‌تر</span><b class="neg">{_share(g['dk_cheaper'], n)}%</b><span class="muted">{g['dk_cheaper']} کالا</span></div>
<div class="tile"><span class="muted">اسنپ‌پی ارزان‌تر</span><b class="pos">{_share(g['snapp_cheaper'], n)}%</b><span class="muted">{g['snapp_cheaper']} کالا · برابر: {g['equal']}</span></div>
<div class="tile"><span class="muted">میانه‌ی اختلاف قیمت</span><b class="{_cls(g['median'])}" style="font-size:19px">{_phrase(g['median'])}</b><span class="muted">نیمی از کالاها اختلاف کمتری دارند</span></div>
</div></div>"""


def _insights(summary, rows, cat_labels) -> str:
    gl, gt = summary["groups"]["landing"], summary["groups"]["timed"]
    out = []
    if gl["n"]:
        out.append(
            f"<b>لندینگ بلک فرایدی:</b> از {gl['total']:,} تخفیف، {gl['n']} کالا با اطمینان بالا روی دیجی‌کالا پیدا شد. "
            f"دیجی‌کالا در {_share(gl['dk_cheaper'], gl['n'])}% این کالاها ارزان‌تر و در {_share(gl['snapp_cheaper'], gl['n'])}% گران‌تر است؛ "
            f"میانه: {_phrase(gl['median'])}.")
    if gt["n"]:
        out.append(
            f"<b>آفرهای زمان‌دار:</b> اسنپ‌پی در {_share(gt['snapp_cheaper'], gt['n'])}% از {gt['n']} کالای تطبیق‌شده ارزان‌تر است "
            f"(میانه: {_phrase(gt['median'])}). این آفرها موجودی محدود و ساعت مشخص دارند؛ اثرشان بیشتر روی ادراک قیمت است تا فروش واقعی.")
    total = summary["snapp_items"]
    out.append(
        f"<b>پوشش:</b> فقط {_share(summary['matched'], total)}% از کل تخفیف‌ها معادل قطعی در دیجی‌کالا دارد. "
        f"{summary.get('not_found', 0):,} کالا در دیجی‌کالا پیدا نشد (بیشتر برند اختصاصی فروشنده، پوشاک و طلا) "
        f"و {summary.get('uncertain', 0):,} کالا فقط مشابه دارد.")
    cats = [(k, v) for k, v in summary.get("by_category_full", {}).items() if v["n"] >= 4 and v["median"] is not None]
    if cats:
        worst = max(cats, key=lambda kv: kv[1]["median"])
        best = min(cats, key=lambda kv: kv[1]["median"])
        out.append(
            f"<b>دسته‌ها (لندینگ):</b> بیشترین عقب‌ماندگی قیمتی دیجی‌کالا در «{esc(cat_labels.get(worst[0], worst[0]))}» "
            f"({_phrase(worst[1]['median'])}، {worst[1]['n']} کالا) و بهترین وضعیت در «{esc(cat_labels.get(best[0], best[0]))}» "
            f"({_phrase(best[1]['median'])}، {best[1]['n']} کالا).")
    mer = [(k, v) for k, v in summary.get("by_merchant", {}).items() if v["n"] >= 3 and v["median"] is not None]
    if mer:
        top = max(mer, key=lambda kv: kv[1]["median"])
        if top[1]["median"] > 1:
            out.append(
                f"<b>فروشنده‌ها (لندینگ):</b> «{esc(top[0])}» با {top[1]['n']} کالای مشترک بیشترین فاصله‌ی قیمتی را با دیجی‌کالا دارد "
                f"({_phrase(top[1]['median'])}).")
    if summary.get("outliers"):
        out.append(f"<b>کنترل کیفیت:</b> {summary['outliers']} تطبیق اختلاف بیش از 100% دارند و با برچسب «قیمت چک شود» مشخص شده‌اند "
                   "(معمولاً قیمت یک فروشنده‌ی گران در دیجی‌کالا یا نسخه‌ی متفاوت).")
    return "".join(f"<li>{x}</li>" for x in out)


def _changes(summary, channel_labels) -> str:
    ch = summary.get("changes") or {}
    if not ch:
        return "<div class='muted'>از اجرای بعدی، تغییرات نسبت به اجرای قبل اینجا نمایش داده می‌شود.</div>"
    rows = []
    for m in ch.get("price_moves", [])[:25]:
        what = []
        if m["snapp_old"] and m["snapp_new"] and m["snapp_old"] != m["snapp_new"]:
            what.append(f"اسنپ‌پی: {_n(m['snapp_old'])} → {_n(m['snapp_new'])}")
        if m["dk_old"] and m["dk_new"] and m["dk_old"] != m["dk_new"]:
            what.append(f"دیجی‌کالا: {_n(m['dk_old'])} → {_n(m['dk_new'])}")
        rows.append(
            f"<tr><td>{esc(m['title'][:80])}<div class='muted'>{esc((m['merchant'] or '—')[:40])} · "
            f"{esc(channel_labels.get(m['channel'], m['channel']))}</div>"
            f"{_links(m['snapp_url'], m['channel'], m['dk_url'], True)}</td>"
            f"<td>{'<br>'.join(what)}</td>"
            f"<td class='{_cls(m['diff_old'])}'>{_pct(m['diff_old'])}</td>"
            f"<td class='{_cls(m['diff_new'])}'>{_pct(m['diff_new'])}</td></tr>")
    table = ("<div class='tw'><table><thead><tr><th>محصول</th><th>تغییر قیمت (تومان)</th><th>اختلاف قبلی</th><th>اختلاف فعلی</th></tr></thead>"
             f"<tbody>{''.join(rows) or '<tr><td colspan=4 class=muted>قیمت هیچ کالای تطبیق‌شده‌ای تغییر نکرده است</td></tr>'}</tbody></table></div>")
    return (f"<div class='grid' style='margin-bottom:12px'>"
            f"<div class='tile'><span class='muted'>اجرای قبلی</span><b style='font-size:17px' dir='ltr'>{esc(ch.get('prev_run_at') or '—')}</b></div>"
            f"<div class='tile'><span class='muted'>تخفیف جدید در اسنپ‌پی</span><b>{ch.get('new_offers', 0)}</b></div>"
            f"<div class='tile'><span class='muted'>تخفیف حذف‌شده</span><b>{ch.get('ended_offers', 0)}</b></div>"
            f"<div class='tile'><span class='muted'>تغییر قیمت روی کالاهای تطبیق‌شده</span><b>{len(ch.get('price_moves', []))}</b></div>"
            f"</div>{table}")


CSS = """
:root{--bg:#0d1117;--card:#161b22;--card2:#1c222b;--line:#30363d;--tx:#e6edf3;--mu:#8b949e;--pos:#f87171;--neg:#34d399;--ac:#60a5fa;--warn:#fbbf24}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font-family:Vazirmatn,Tahoma,sans-serif;font-size:14px;line-height:1.75}
.wrap{max-width:1240px;margin:auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:32px 0 10px;border-right:3px solid var(--ac);padding-right:8px}.sub{color:var(--mu);font-size:12.5px;margin:-6px 0 10px}
.muted{color:var(--mu);font-size:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}.tile b{display:block;font-size:24px}
.grp{background:#11161d;border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px}.gh{font-weight:700;margin:0 4px 10px}
.key{background:#10203a;border:1px solid #1f3b63;border-radius:12px;padding:14px 18px}.key ul{margin:0;padding-inline-start:18px}.key li{margin:4px 0}
.tw{overflow-x:auto;border-radius:10px}
table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--line);border-radius:10px}
th,td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}
th{color:#c9d1d9;font-weight:600;background:var(--card2);position:sticky;top:0;z-index:5;box-shadow:0 2px 0 var(--line);white-space:nowrap}
th.s{cursor:pointer}th.s:after{content:" ⇅";color:var(--mu);font-size:11px}th.s.asc:after{content:" ▲";color:var(--ac)}th.s.desc:after{content:" ▼";color:var(--ac)}
a{color:var(--ac);text-decoration:none}.pos{color:var(--pos)}.neg{color:var(--neg)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:960px){.two{grid-template-columns:1fr}}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;align-items:center}
select,input{background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-family:inherit}
.tag{display:inline-block;font-size:11px;padding:0 7px;border-radius:6px;background:#1f2937;color:var(--mu);margin-inline-start:6px;white-space:nowrap}
.tag.on{background:#0f3d2b;color:var(--neg)}.tag.warn{background:#3b2f0b;color:var(--warn)}
.lks{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}.lk{font-size:11.5px;padding:1px 8px;border-radius:999px;border:1px solid var(--line);white-space:nowrap}
.lk.s{color:#c4b5fd;border-color:#4c3d7a}.lk.d{color:#fda4af;border-color:#7a3d4c}.lk:hover{background:#1f2630}
.btn{background:#1f6feb;color:#fff;border:0;border-radius:8px;padding:7px 12px;font-family:inherit;cursor:pointer}.btn:hover{background:#388bfd}.btn:disabled{opacity:.5;cursor:wait}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}.chip{background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:999px;padding:5px 14px;font-family:inherit;cursor:pointer}
.chip b{font-weight:700;margin-inline-start:6px}.chip.on{border-color:var(--ac);background:#132338}.chip.g b{color:var(--neg)}.chip.r b{color:var(--pos)}
.fresh{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;background:#1f2937;margin-inline-start:6px}
.fresh.ok{background:#0f3d2b;color:var(--neg)}.fresh.late{background:#3b2f0b;color:var(--warn)}.fresh.old{background:#3d1214;color:var(--pos)}
.note li{margin-bottom:5px}
"""


def render_report(rows, summary, history, cat_labels, channel_labels, font_bytes) -> str:
    font_css = ""
    if font_bytes:
        b64 = base64.b64encode(font_bytes).decode()
        font_css = (f"@font-face{{font-family:'Vazirmatn';src:url(data:font/woff2;base64,{b64}) "
                    f"format('woff2');font-weight:100 900;font-display:swap}}")

    high = [r for r in rows if r["confidence"] == "high"]
    landing_hi = [r for r in high if r["channel"] == "landing"]
    dk_expensive = sorted([r for r in landing_hi if r["verdict"] == "snapp_cheaper"], key=lambda r: -r["diff_pct"])[:15]
    dk_cheap = sorted([r for r in landing_hi if r["verdict"] == "dk_cheaper"], key=lambda r: r["diff_pct"])[:15]
    timed_all = sorted([r for r in high if r["channel"] != "landing" and r.get("live_status") in ("live", "upcoming")],
                       key=lambda r: (r.get("live_status") != "live", -r["diff_pct"]))
    timed_now = timed_all[:25]
    live_all = sum(1 for r in rows if r.get("live_status") == "live")

    groups = summary["groups"]
    tiles = _group_tiles(groups["landing"], GROUP_LABEL["landing"]) + _group_tiles(groups["timed"], GROUP_LABEL["timed"])

    table_data = [{
        "t": r["title"], "m": r["merchant"], "ch": r["channel"], "c": r["category"],
        "sp": r["snapp_price"], "sb": r["snapp_before"], "cb": r["cashback_pct"],
        "su": r["snapp_url"], "conf": r["confidence"], "v": r.get("verdict", ""),
        "dt": r.get("dk_title", ""), "dp": r.get("dk_price"), "du": r.get("dk_url", ""),
        "dl": r.get("dk_link") or r.get("dk_url", ""),
        "d": r.get("diff_pct"), "inc": r.get("dk_is_incredible", False),
        "ls": r.get("live_status", ""), "lt": r.get("live_text", ""),
        "st": r.get("dk_status", ""), "rc": r.get("recheck", ""),
        "eff": r.get("snapp_effective"), "de": r.get("diff_pct_vs_effective"),
        "dr": r.get("dk_rrp"), "dd": r.get("dk_discount"), "dt2": r.get("diff_toman"),
        "o": bool(r.get("outlier")),
    } for r in rows]

    hist_l = [h for h in history if h.get("landing_median") not in (None, "")]
    trend_median = _spark([float(h["median_diff_pct"]) if h.get("median_diff_pct") else None for h in history], "#60a5fa")
    trend_share = _spark([int(h["dk_cheaper"]) / max(int(h["matched"]), 1) * 100 for h in history if h.get("matched")], "#34d399")
    trend_land = _spark([float(h["landing_median"]) for h in hist_l], "#c4b5fd")

    js_consts = (
        f"const D={json.dumps(table_data, ensure_ascii=False)};\n"
        f"const SL={json.dumps(STATUS_LABEL, ensure_ascii=False)},CH={json.dumps(channel_labels, ensure_ascii=False)},"
        f"LS={json.dumps(LIVE_LABEL, ensure_ascii=False)},CAT={json.dumps(cat_labels, ensure_ascii=False)},"
        f"VL={json.dumps(VERDICT_LABEL, ensure_ascii=False)},RUN={json.dumps(summary['run_at'])};\n"
        f"const SUM={json.dumps([['آخرین اجرا (تهران)', summary['run_at']], ['کل تخفیف‌های اسنپ‌پی', summary['snapp_items']], ['تطبیق قطعی روی دیجی‌کالا', summary['matched']], ['نیازمند بررسی', summary.get('matched_medium', 0)], ['نامشخص', summary.get('uncertain', 0)], ['در دیجی‌کالا پیدا نشد', summary.get('not_found', 0)], ['لندینگ - تطبیق قطعی', groups['landing']['n']], ['لندینگ - دیجی‌کالا ارزان‌تر', groups['landing']['dk_cheaper']], ['لندینگ - اسنپ‌پی ارزان‌تر', groups['landing']['snapp_cheaper']], ['لندینگ - میانه اختلاف %', groups['landing']['median']], ['زمان‌دار - تطبیق قطعی', groups['timed']['n']], ['زمان‌دار - دیجی‌کالا ارزان‌تر', groups['timed']['dk_cheaper']], ['زمان‌دار - اسنپ‌پی ارزان‌تر', groups['timed']['snapp_cheaper']], ['زمان‌دار - میانه اختلاف %', groups['timed']['median']]], ensure_ascii=False)};\n")

    ch_opts = "".join(f'<option value="{k}">{esc(v)}</option>' for k, v in channel_labels.items())
    cat_opts = "".join(f'<option value="{k}">{esc(v)}</option>' for k, v in cat_labels.items() if k != "hb")

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>مقایسه قیمت بلک فرایدی اسنپ‌پی و دیجی‌کالا</title>
<style>{font_css}{CSS}</style></head><body><div class="wrap">
<h1>مقایسه قیمت تخفیف‌های بلک فرایدی اسنپ‌پی با دیجی‌کالا</h1>
<div class="muted">SnappPay Black Friday vs Digikala · آخرین اجرا: <span dir="ltr">{summary['run_at']}</span> تهران<span id="fresh" class="fresh"></span>
· به‌روزرسانی خودکار هر 30 دقیقه (دقیقه‌های 07 و 37) · مبالغ به تومان، قیمت کامل کالا (نه مبلغ قسط)</div>

<h2>جمع‌بندی (Key findings)</h2>
<div class="key"><ul>{_insights(summary, rows, cat_labels)}</ul></div>

<h2>شاخص‌های اصلی (Headline)</h2>
<div class="sub">آمار فقط از تطبیق‌های قطعی محاسبه می‌شود؛ لندینگ و آفرهای زمان‌دار جدا آمده‌اند چون منطق قیمت‌گذاری متفاوتی دارند.</div>
{tiles}

<h2>تغییرات از اجرای قبل (Changes since last run)</h2>
{_changes(summary, channel_labels)}

<h2>آفرهای زمان‌دار: در حال پخش و نوبت بعد (Timed deals)</h2>
<div class="sub">{live_all} آفر زمان‌دار در لحظه‌ی اجرا فعال است؛ {len(timed_all)} آفرِ در حال پخش یا نوبت بعد معادل قطعی در دیجی‌کالا دارد{" (25 مورد اول، مرتب: در حال پخش، سپس بیشترین اختلاف)" if len(timed_all) > 25 else ""}.</div>
{_item_table(timed_now, channel_labels, show_live=True)}

<div class="two">
<div><h2>اولویت اقدام: دیجی‌کالا گران‌تر (لندینگ)</h2>
<div class="sub">بیشترین فاصله‌ی قیمتی به ضرر دیجی‌کالا روی کالاهای یکسان؛ نامزد بررسی قیمت یا کمپین.</div>
{_item_table(dk_expensive, channel_labels)}</div>
<div><h2>مزیت قیمتی دیجی‌کالا (لندینگ)</h2>
<div class="sub">کالاهایی که دیجی‌کالا با بیشترین فاصله ارزان‌تر است؛ قابل استفاده در پیام‌های مقایسه‌ای.</div>
{_item_table(dk_cheap, channel_labels)}</div>
</div>

<h2>تفکیک دسته‌بندی، لندینگ (By category)</h2>
<div class="sub">فقط کالاهای لندینگ؛ آفرهای زمان‌دار به‌خاطر قیمت فلش جداگانه در جدول بالا آمده‌اند.</div>
{_breakdown_table(summary.get('by_category_full', {}), cat_labels, 'دسته‌بندی')}

<h2>فروشنده‌های لندینگ اسنپ‌پی با کالای مشترک (By merchant)</h2>
<div class="sub">فروشنده‌های لندینگ که دست‌کم 2 کالای مشترک با دیجی‌کالا دارند؛ مرتب بر اساس تعداد کالای مشترک.</div>
{_breakdown_table(summary.get('by_merchant', {}), {}, 'فروشنده', 20)}

<h2>روند در اجراهای اخیر (Trend)</h2>
<div class="grid">
<div class="tile"><span class="muted">میانه‌ی اختلاف قیمت، لندینگ (%)</span><br>{trend_land}</div>
<div class="tile"><span class="muted">میانه‌ی اختلاف قیمت، همه (%)</span><br>{trend_median}</div>
<div class="tile"><span class="muted">سهم کالاهایی که دیجی‌کالا ارزان‌تر است، همه (%)</span><br>{trend_share}</div>
</div>

<h2>همه‌ی تخفیف‌های اسنپ‌پی (All SnappPay offers)</h2>
<div class="filters" id="xl">
<button class="btn" data-x="all">دانلود اکسل: همه (Excel – All)</button>
<button class="btn" data-x="dk">دانلود اکسل: دیجی‌کالا ارزان‌تر (Digikala cheaper)</button>
<button class="btn" data-x="sn">دانلود اکسل: دیجی‌کالا گران‌تر (Digikala pricier)</button>
<button class="btn" data-x="nf">دانلود اکسل: در دیجی‌کالا پیدا نشد (Not on Digikala)</button>
<button class="btn" data-x="view">دانلود اکسل: نمای فعلی (Current view)</button>
<span class="muted" id="xlmsg"></span>
</div>
<div class="filters">
<input id="q" placeholder="جستجو در عنوان یا فروشنده" size="28">
<select id="fconf"><option value="">وضعیت در دیجی‌کالا: همه</option><option value="matched">تطبیق قطعی (مبنای آمار)</option><option value="review">نیازمند بررسی</option><option value="uncertain">نامشخص</option><option value="not_found">در دیجی‌کالا پیدا نشد</option></select>
<select id="fch"><option value="">نوع آفر: همه</option>{ch_opts}</select>
<select id="fc"><option value="">دسته‌بندی: همه</option>{cat_opts}</select>
<span class="muted" id="cnt"></span>
</div>
<div class="chips" id="vchips"></div>
<div class="sub">شمارش دکمه‌ها شامل تطبیق‌های «نیازمند بررسی» هم هست؛ برای عددهای هم‌خوان با شاخص‌های اصلی، وضعیت را روی «تطبیق قطعی» بگذارید.</div>
<div class="tw"><table><thead><tr>
<th class="s" data-k="t">محصول اسنپ‌پی</th><th class="s" data-k="sp">قیمت اسنپ‌پی</th><th class="s" data-k="dt">محصول دیجی‌کالا</th>
<th class="s" data-k="dp">قیمت دیجی‌کالا</th><th class="s" data-k="dt2">اختلاف تومان</th><th class="s" data-k="d">اختلاف</th><th class="s" data-k="st">وضعیت در دیجی‌کالا</th>
</tr></thead><tbody id="tb"></tbody></table></div>

<h2>روش و ملاحظات (Method)</h2>
<ul class="note muted">
<li>منبع اسنپ‌پی: فید لندینگ بلک فرایدی (قیمت فروشگاه‌های طرف قرارداد) و فید تقویم تخفیف‌ها (آفرهای زمان‌دار آنلاین، حضوری و لایو؛ وچرها حذف شده‌اند). منبع دیجی‌کالا: جستجو و صفحه‌ی محصول دیجی‌کالا در لحظه‌ی اجرا؛ قیمت دیجی‌کالا قیمت فروشنده‌ی پیش‌فرض (buy box) است.</li>
<li>لینک‌ها: «صفحه‌ی کالا (اسنپ‌پی)» برای کالاهای لندینگ به صفحه‌ی کالا در سایت فروشنده می‌رود. آفرهای تقویم در فید اسنپ‌پی صفحه‌ی اختصاصی ندارند و به تقویم تخفیف‌ها لینک می‌شوند. «صفحه‌ی کالا (دیجی‌کالا)» برای کالاهای تطبیق‌شده و «جستجو در دیجی‌کالا» برای بقیه، تا بررسی دستی ممکن باشد.</li>
<li>هر محصول اسنپ‌پی با عنوانش در جستجوی دیجی‌کالا جستجو و بهترین نتیجه با امتیاز شباهت عنوان، تطابق مدل/عدد، تطابق حجم و تعداد بسته و منطقی‌بودن قیمت انتخاب شده است.</li>
<li>همه‌ی آمار این صفحه فقط بر پایه‌ی تطبیق‌های «اطمینان بالا» است (مدل یا کد مشترک و مشخصات یکسان؛ در بررسی دستی حدود 95% درست). تطبیق‌های «متوسط» در بررسی دستی حدود نیمی برند یا محصول متفاوت داشتند و فقط در جدول برای بررسی آمده‌اند.</li>
<li>قیمت اسنپ‌پی همیشه قیمت کامل کالاست، نه مبلغ یک قسط: روی کارت‌های لندینگ «4 قسط» برابر یک‌چهارم همین قیمت است (مثلاً 970,920 تومان = 4 قسط 242,730) و در تقویم تخفیف‌ها فقط قیمت کامل نمایش داده می‌شود.</li>
<li>بازبینی (Recheck): برای هر تطبیق، صفحه‌ی محصول دیجی‌کالا (برند فارسی و انگلیسی، عنوان کامل) خوانده و دوباره مقایسه می‌شود. تفاوت نسخه (Pro، Plus، NC، OLED، دوقلو)، طعم، جنسیت یا گروه سنی (بچه‌گربه و بالغ، زنانه و مردانه)، حجم یا تعداد بسته، و فروش همراه با لوازم اضافه باعث رد تطبیق می‌شود. نبودن برند دیجی‌کالا در عنوان اسنپ‌پی، نبودن مدل یا حجم در عنوان اسنپ‌پی، یا عنوان خیلی کلی، تطبیق را به «نیازمند بررسی» می‌برد. اگر بهترین نتیجه رد شود، دو نتیجه‌ی بعدی هم بازبینی می‌شوند. دلیل هر تصمیم زیر ستون وضعیت آمده است.</li>
<li>«در دیجی‌کالا پیدا نشد» یعنی همین محصول (همین مدل، برند یا حجم) در نتایج دیجی‌کالا نبود؛ برای کالاهای دارای کد مدل یک جستجوی دوم فقط با کد مدل هم انجام می‌شود. در بررسی نمونه‌ای، بیشتر این موارد کالای برند اختصاصی فروشنده (مثل جین‌وست، کوبیک)، مدل‌هایی که دیجی‌کالا ندارد یا عنوان‌های عمومی بودند؛ یعنی دیجی‌کالا معمولاً کالای مشابه دارد، ولی همان کالا را نه. «نامشخص» یعنی کالای مشابه هست ولی هیچ‌کدام قطعاً همان محصول (همان برند، مدل یا حجم) نیست. هر دو گروه بدون قیمت دیجی‌کالا نمایش داده می‌شوند.</li>
<li>عنوان‌های عمومی بدون برند یا مدل (مثل «کفش ورزشی مردانه») و طلا و جواهر بدون کد مدل، عمداً تطبیق داده نمی‌شوند.</li>
<li>اختلاف = (قیمت دیجی‌کالا − قیمت اسنپ‌پی) ÷ قیمت اسنپ‌پی. مثبت یعنی دیجی‌کالا گران‌تر. اختلاف کمتر از 1% «برابر» حساب می‌شود. اختلاف بیش از 100% با برچسب «قیمت چک شود» مشخص می‌شود؛ این موارد در آمار می‌مانند ولی چون از میانه استفاده می‌شود، اثر کمی روی آن دارند.</li>
<li>«تغییرات از اجرای قبل»: تخفیف‌های تازه یا حذف‌شده‌ی اسنپ‌پی و تغییر قیمت بیش از 1% روی کالاهای تطبیق‌شده (هر دو طرف)، نسبت به اجرای 30 دقیقه قبل.</li>
<li>کش‌بک اسنپ‌پی در قیمت اصلی لحاظ نشده و در اکسل (ستون «قیمت اسنپ‌پی پس از کش‌بک») آمده است.</li>
<li>بخش زیادی از محصولات لندینگ اسنپ‌پی کالای فروشگاه‌های کوچک یا بی‌برند است و معادل دقیقی در دیجی‌کالا ندارد؛ نرخ تطبیق پایین در این دسته‌ها طبیعی است.</li>
<li>آفرهای تقویم اسنپ‌پی زمان‌دار و با موجودی محدود (گاهی ۱ عدد) هستند؛ ستون وضعیت، زمان پخش بعدی را نشان می‌دهد.</li>
<li>«قیمت قبل از تخفیف» اسنپ‌پی در بسیاری موارد چند برابر قیمت بازار است؛ مقایسه فقط روی قیمت نهایی انجام شده است.</li>
</ul>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script>
{js_consts}{JS}
</script></body></html>"""


JS = r"""
const $=id=>document.getElementById(id);
const f=n=>n==null?"—":Math.round(n).toLocaleString("en-US"),e=s=>(s||"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const sg=n=>n==null?"—":(n>0?"+":"")+Math.round(n).toLocaleString("en-US");
const SO={matched:0,review:1,uncertain:2,not_found:3};
// freshness badge: Tehran is UTC+03:30
(function(){const t=Date.parse(RUN.replace(" ","T")+":00+03:30");const m=Math.round((Date.now()-t)/60000);const el=$("fresh");if(isNaN(m))return;
const txt=m<60?m+" دقیقه پیش":Math.floor(m/60)+" ساعت و "+(m%60)+" دقیقه پیش";el.textContent=txt;el.className="fresh "+(m<=45?"ok":m<=90?"late":"old");
if(m>90)el.textContent+=" · گزارش به‌روز نیست";})();
const links=x=>`<div class="lks">${x.su?`<a class="lk s" href="${e(x.su)}" target="_blank" rel="noopener">${x.ch==="landing"?"صفحه‌ی کالا (اسنپ‌پی) ↗":"تقویم اسنپ‌پی ↗"}</a>`:""}${x.dl?`<a class="lk d" href="${e(x.dl)}" target="_blank" rel="noopener">${x.du?"صفحه‌ی کالا (دیجی‌کالا) ↗":"جستجو در دیجی‌کالا ↗"}</a>`:""}</div>`;
const VCH=[["","همه",""],["dk_cheaper","دیجی‌کالا ارزان‌تر","g"],["snapp_cheaper","دیجی‌کالا گران‌تر","r"],["equal","برابر",""],["none","بدون داده (بدون معادل قطعی)",""]];
let fv="",sortK=null,sortDir=1;
document.addEventListener("click",ev=>{const b=ev.target.closest(".chip");if(b){fv=b.dataset.v;draw();return;}
const h=ev.target.closest("th.s");if(h){const k=h.dataset.k;if(sortK===k)sortDir=-sortDir;else{sortK=k;sortDir=(k==="t"||k==="dt"||k==="st")?1:-1;}
document.querySelectorAll("th.s").forEach(t=>t.classList.remove("asc","desc"));h.classList.add(sortDir>0?"asc":"desc");draw();}});
const vk=x=>x.v||"none";
function cmp(a,b){if(!sortK)return (SO[a.st]??9)-(SO[b.st]??9)||(b.d??-999)-(a.d??-999);
let x=a[sortK],y=b[sortK];if(sortK==="st"){x=SO[x]??9;y=SO[y]??9;}
if(x==null||x==="")return 1;if(y==null||y==="")return -1;return (typeof x==="string"?x.localeCompare(y,"fa"):x-y)*sortDir;}
function draw(){const q=$("q").value.trim(),cf=$("fconf").value,ch=$("fch").value,c=$("fc").value;
const base=D.filter(x=>(!cf||x.st===cf)&&(!ch||x.ch===ch)&&(!c||x.c===c||(c==="beauty"&&x.c==="hb"))&&(!q||(x.t+" "+x.m).includes(q)));
const cntv={"":base.length};base.forEach(x=>cntv[vk(x)]=(cntv[vk(x)]||0)+1);
$("vchips").innerHTML=VCH.map(([k,l,cls])=>`<button class="chip ${cls} ${fv===k?"on":""}" data-v="${k}">${l}<b>${(cntv[k]||0).toLocaleString("en-US")}</b></button>`).join("");
const r=base.filter(x=>!fv||vk(x)===fv).sort(cmp);
window.__view=r;$("cnt").textContent=r.length.toLocaleString("en-US")+" ردیف";
$("tb").innerHTML=r.slice(0,1500).map(x=>`<tr><td>${e(x.t)}${x.o?`<span class="tag warn">قیمت چک شود</span>`:""}<div class="muted">${e(x.m)} · ${CH[x.ch]||x.ch}${x.ls&&LS[x.ls]?`<span class="tag ${x.ls==="live"?"on":""}">${LS[x.ls]} ${e(x.lt)}</span>`:""}</div>${links(x)}</td>
<td>${f(x.sp)}${x.cb?`<div class="muted">کش‌بک ${x.cb}%</div>`:""}</td><td>${x.dt?e(x.dt):"—"}${x.inc?`<span class="tag">شگفت‌انگیز</span>`:""}</td>
<td>${f(x.dp)}</td><td class="${x.d>1?"pos":x.d<-1?"neg":""}" dir="ltr" style="text-align:right">${sg(x.dt2)}</td>
<td class="${x.d>1?"pos":x.d<-1?"neg":""}" dir="ltr" style="text-align:right">${x.d==null?"—":(x.d>0?"+":"")+x.d.toFixed(1)+"%"}</td>
<td>${SL[x.st]||""}${x.rc?`<div class="muted" style="max-width:260px">${e(x.rc)}</div>`:""}</td></tr>`).join("");}
["q","fconf","fch","fc"].forEach(i=>$(i).addEventListener("input",draw));draw();
const toRow=x=>({"وضعیت در دیجی‌کالا":SL[x.st]||"","نتیجه‌ی بازبینی (Recheck)":x.rc||"","محصول اسنپ‌پی":x.t,"فروشنده":x.m,"نوع آفر":CH[x.ch]||x.ch,"دسته‌بندی":CAT[x.c]||x.c,
"قیمت اسنپ‌پی (تومان)":x.sp,"قیمت قبل اسنپ‌پی":x.sb,"کش‌بک اسنپ‌پی %":x.cb,"قیمت اسنپ‌پی پس از کش‌بک":x.eff,
"محصول دیجی‌کالا":x.dt,"قیمت دیجی‌کالا (تومان)":x.dp,"قیمت قبل دیجی‌کالا":x.dr,"تخفیف دیجی‌کالا %":x.dd,"شگفت‌انگیز":x.inc?"بله":"",
"اختلاف (تومان)":x.dt2,"اختلاف %":x.d,"اختلاف % پس از کش‌بک":x.de,"نتیجه":VL[x.v]||"","قیمت چک شود":x.o?"بله":"",
"وضعیت پخش":LS[x.ls]||"","زمان":x.lt,"لینک اسنپ‌پی":x.su,"لینک دیجی‌کالا (کالا یا جستجو)":x.dl});
function sheet(rows){const ws=XLSX.utils.json_to_sheet(rows.map(toRow));ws["!cols"]=[18,40,40,16,16,16,14,14,10,14,40,14,14,10,8,14,9,12,16,10,12,14,40,40].map(w=>({wch:w}));
rows.forEach((x,i)=>{const R=i+1;[[22,x.su],[23,x.dl]].forEach(([C,u])=>{const a=XLSX.utils.encode_cell({r:R,c:C});if(u&&ws[a])ws[a].l={Target:u};});});return ws;}
function book(sheets){const wb=XLSX.utils.book_new();wb.Workbook={Views:[{RTL:true}]};
XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(SUM),"خلاصه");for(const [n,r] of sheets)XLSX.utils.book_append_sheet(wb,sheet(r),n);return wb;}
const high=D.filter(x=>x.conf==="high");
const byStatus=[...D].sort((a,b)=>(SO[a.st]??9)-(SO[b.st]??9)||(b.d??-999)-(a.d??-999));
const dkC=()=>high.filter(x=>x.v==="dk_cheaper").sort((a,b)=>a.d-b.d),snC=()=>high.filter(x=>x.v==="snapp_cheaper").sort((a,b)=>b.d-a.d);
const SETS={all:()=>[["همه‌ی تخفیف‌های اسنپ‌پی",byStatus],["دیجی‌کالا ارزان‌تر",dkC()],["دیجی‌کالا گران‌تر",snC()],["در دیجی‌کالا پیدا نشد",D.filter(x=>x.st==="not_found")]],
dk:()=>[["دیجی‌کالا ارزان‌تر",dkC()]],sn:()=>[["دیجی‌کالا گران‌تر",snC()]],
nf:()=>[["در دیجی‌کالا پیدا نشد",D.filter(x=>x.st==="not_found")]],view:()=>[["نمای فعلی",window.__view||[]]]};
const NAMES={all:"snapppay-vs-digikala-all",dk:"digikala-cheaper",sn:"digikala-pricier",nf:"not-on-digikala",view:"snapppay-vs-digikala-view"};
async function exportXl(k,btn){const msg=$("xlmsg");if(typeof XLSX==="undefined"){msg.textContent="کتابخانه‌ی اکسل بارگذاری نشد";return;}
btn.disabled=true;try{const wb=book(SETS[k]());const buf=XLSX.write(wb,{bookType:"xlsx",type:"array"});const name=NAMES[k]+"-"+RUN.replace(/[ :]/g,"-")+".xlsx";
let dl=null;try{dl=window.claude&&await window.claude.use("downloads");}catch(_){}
if(dl){await dl.save({filename:name,data:new Blob([buf])});msg.textContent="";}
else{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([buf],{type:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}));a.download=name;document.body.appendChild(a);a.click();a.remove();}}
catch(err){msg.textContent=(err&&err.code==="declined")?"":"دانلود انجام نشد";}finally{btn.disabled=false;}}
document.querySelectorAll("#xl .btn").forEach(b=>b.addEventListener("click",()=>exportXl(b.dataset.x,b)));
"""
