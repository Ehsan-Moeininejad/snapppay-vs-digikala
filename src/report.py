# -*- coding: utf-8 -*-
"""Self-contained dark Persian HTML report (Vazirmatn embedded, Latin digits)."""
from __future__ import annotations

import base64
import html
import json

STATUS_LABEL = {"matched": "تطبیق قطعی", "review": "نیازمند بررسی",
                "uncertain": "نامشخص", "not_found": "در دیجی‌کالا پیدا نشد"}
CONF_LABEL = {"high": "بالا", "medium": "متوسط", "low": "ضعیف", "none": "بدون نتیجه"}
VERDICT_LABEL = {"dk_cheaper": "دیجی‌کالا ارزان‌تر", "equal": "برابر",
                 "snapp_cheaper": "اسنپ‌پی ارزان‌تر"}


def _n(v) -> str:
    return "—" if v is None else f"{int(v):,}"


def _pct(v) -> str:
    return "—" if v is None else f'<span dir="ltr">{v:+.1f}%</span>'


def _spark(values: list[float], color: str) -> str:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return '<span class="muted">پس از چند اجرا نمایش داده می‌شود</span>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    w, h = 220, 40
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - (v - lo) / rng * (h - 6) - 3:.1f}"
                   for i, v in enumerate(vals))
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="direction:ltr">'
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/></svg>')


def render_report(rows, summary, history, cat_labels, channel_labels, font_bytes) -> str:
    esc = html.escape
    matched = [r for r in rows if r["confidence"] == "high"]
    m = len(matched) or 1
    share = lambda k: round(summary[k] / m * 100)  # noqa: E731

    font_css = ""
    if font_bytes:
        b64 = base64.b64encode(font_bytes).decode()
        font_css = (f"@font-face{{font-family:'Vazirmatn';src:url(data:font/woff2;base64,{b64}) "
                    f"format('woff2');font-weight:100 900;font-display:swap}}")

    # --- category table
    cat_rows = []
    for c, v in summary["by_category"].items():
        cls = "neg" if v["median"] < -1 else "pos" if v["median"] > 1 else ""
        cat_rows.append(
            f"<tr><td>{esc(cat_labels.get(c, c or '—'))}</td><td>{v['n']}</td>"
            f"<td class='{cls}'>{_pct(v['median'])}</td>"
            f"<td>{round(v['dk_cheaper'] / v['n'] * 100)}%</td></tr>")

    def item_rows(items):
        out = []
        for r in items:
            out.append(
                "<tr>"
                f"<td><a href='{esc(r['snapp_url'])}' target='_blank'>{esc(r['title'][:70])}</a>"
                f"<div class='muted'>{esc(r['merchant'][:40])} · {esc(channel_labels.get(r['channel'], r['channel']))}</div></td>"
                f"<td>{_n(r['snapp_price'])}</td>"
                f"<td><a href='{esc(r['dk_url'])}' target='_blank'>{_n(r['dk_price'])}</a></td>"
                f"<td class='{'pos' if r['diff_pct'] > 0 else 'neg'}'>{_pct(r['diff_pct'])}</td>"
                f"<td>{CONF_LABEL[r['confidence']]}</td></tr>")
        return "".join(out) or "<tr><td colspan='5' class='muted'>موردی یافت نشد</td></tr>"

    dk_expensive = sorted([r for r in matched if r["verdict"] == "snapp_cheaper"],
                          key=lambda r: -r["diff_pct"])[:15]
    dk_cheap = sorted([r for r in matched if r["verdict"] == "dk_cheaper"],
                      key=lambda r: r["diff_pct"])[:10]

    live = [r for r in rows if r.get("live_status") == "live"]
    live_matched = sorted([r for r in live if r["confidence"] == "high"], key=lambda r: -r["diff_pct"])

    ch_rows = []
    for c, v in summary.get("by_channel", {}).items():
        cls = "neg" if v["median"] < -1 else "pos" if v["median"] > 1 else ""
        ch_rows.append(
            f"<tr><td>{esc(channel_labels.get(c, c))}</td><td>{v['n']}</td>"
            f"<td class='{cls}'>{_pct(v['median'])}</td>"
            f"<td>{round(v['dk_cheaper'] / v['n'] * 100)}%</td></tr>")

    # data for the interactive table (all rows with any candidate)
    table_data = [{
        "t": r["title"], "m": r["merchant"], "ch": r["channel"], "c": r["category"],
        "sp": r["snapp_price"], "sb": r["snapp_before"], "cb": r["cashback_pct"],
        "su": r["snapp_url"], "conf": r["confidence"], "v": r.get("verdict", ""),
        "dt": r.get("dk_title", ""), "dp": r.get("dk_price"), "du": r.get("dk_url", ""),
        "d": r.get("diff_pct"), "inc": r.get("dk_is_incredible", False),
        "ls": r.get("live_status", ""), "lt": r.get("live_text", ""),
        "st": r.get("dk_status", ""), "rc": r.get("recheck", ""),
        "eff": r.get("snapp_effective"), "de": r.get("diff_pct_vs_effective"),
        "dr": r.get("dk_rrp"), "dd": r.get("dk_discount"), "dt2": r.get("diff_toman"),
    } for r in rows]

    trend_median = _spark([float(h["median_diff_pct"]) if h.get("median_diff_pct") else None
                           for h in history], "#60a5fa")
    trend_share = _spark([int(h["dk_cheaper"]) / max(int(h["matched"]), 1) * 100
                          for h in history if h.get("matched")], "#34d399")

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>مقایسه قیمت بلک فرایدی اسنپ‌پی و دیجی‌کالا</title>
<style>
{font_css}
:root{{--bg:#0d1117;--card:#161b22;--line:#30363d;--tx:#e6edf3;--mu:#8b949e;--pos:#f87171;--neg:#34d399;--ac:#60a5fa}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--tx);font-family:Vazirmatn,Tahoma,sans-serif;font-size:14px;line-height:1.7}}
.wrap{{max-width:1200px;margin:auto;padding:24px 16px}}h1{{font-size:22px;margin:0 0 4px}}h2{{font-size:17px;margin:28px 0 10px;border-right:3px solid var(--ac);padding-right:8px}}
.muted{{color:var(--mu);font-size:12px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}}.tile b{{display:block;font-size:24px}}
table{{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--line);border-radius:10px}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}}th{{color:#c9d1d9;font-weight:600;background:#1c222b;position:sticky;top:0;z-index:5;box-shadow:0 2px 0 var(--line)}}
thead th:first-child{{border-top-right-radius:10px}}thead th:last-child{{border-top-left-radius:10px}}
a{{color:var(--ac);text-decoration:none}}.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}@media(max-width:900px){{.two{{grid-template-columns:1fr}}}}
.filters{{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}}select,input{{background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-family:inherit}}
.tag{{display:inline-block;font-size:11px;padding:0 6px;border-radius:6px;background:#1f2937;color:var(--mu);margin-inline-start:4px}}
.btn{{background:#1f6feb;color:#fff;border:0;border-radius:8px;padding:7px 12px;font-family:inherit;cursor:pointer}}.btn:hover{{background:#388bfd}}.btn:disabled{{opacity:.5;cursor:wait}}
.scroll{{border-radius:10px}}
.chips{{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px}}.chip{{background:var(--card);color:var(--tx);border:1px solid var(--line);border-radius:999px;padding:5px 14px;font-family:inherit;cursor:pointer}}
.chip b{{font-weight:700;margin-inline-start:6px}}.chip.on{{border-color:var(--ac);background:#132338}}.chip.g b{{color:var(--neg)}}.chip.r b{{color:var(--pos)}}.note li{{margin-bottom:4px}}
</style></head><body><div class="wrap">
<h1>مقایسه قیمت محصولات بلک فرایدی اسنپ‌پی با دیجی‌کالا</h1>
<div class="muted">SnappPay Black Friday vs Digikala · آخرین اجرا: {summary['run_at']} (تهران) · مبالغ به تومان · منبع: لندینگ بلک فرایدی و تقویم تخفیف‌های اسنپ‌پی</div>

<h2>خلاصه</h2>
<div class="grid">
<div class="tile"><span class="muted">محصولات اسنپ‌پی</span><b>{summary['snapp_items']:,}</b></div>
<div class="tile"><span class="muted">تطبیق قطعی روی دیجی‌کالا (اطمینان بالا)</span><b>{summary['matched']:,}</b><span class="muted">+{summary.get('matched_medium', 0)} مورد نیازمند بررسی</span></div>
<div class="tile"><span class="muted">دیجی‌کالا ارزان‌تر</span><b class="neg" dir="ltr" style="text-align:right">{share('dk_cheaper')}%</b><span class="muted">{summary['dk_cheaper']} مورد</span></div>
<div class="tile"><span class="muted">در دیجی‌کالا پیدا نشد</span><b>{summary.get('not_found', 0):,}</b><span class="muted">+{summary.get('uncertain', 0):,} مورد نامشخص (بدون معادل قطعی)</span></div>
<div class="tile"><span class="muted">اسنپ‌پی ارزان‌تر</span><b class="pos" dir="ltr" style="text-align:right">{share('snapp_cheaper')}%</b><span class="muted">{summary['snapp_cheaper']} مورد</span></div>
<div class="tile"><span class="muted">میانه اختلاف قیمت دیجی‌کالا</span><b class="{'pos' if (summary['median_diff_pct'] or 0) > 0 else 'neg'}">{_pct(summary['median_diff_pct'])}</b><span class="muted">مثبت = دیجی‌کالا گران‌تر</span></div>
</div>

<h2>آفرهای در حال پخش همین الان (Live now)</h2>
<div class="muted" style="margin-bottom:8px">{len(live)} آفر زمان‌دار اسنپ‌پی در لحظه‌ی اجرا فعال است؛ {len(live_matched)} مورد با اطمینان بالا روی دیجی‌کالا پیدا شد.</div>
<table><thead><tr><th>محصول اسنپ‌پی</th><th>اسنپ‌پی</th><th>دیجی‌کالا</th><th>اختلاف</th><th>اطمینان</th></tr></thead><tbody>{item_rows(live_matched[:20])}</tbody></table>

<h2>روند در اجراهای اخیر</h2>
<div class="two"><div class="tile"><span class="muted">میانه اختلاف قیمت (%)</span><br>{trend_median}</div>
<div class="tile"><span class="muted">سهم محصولاتی که دیجی‌کالا ارزان‌تر است (%)</span><br>{trend_share}</div></div>

<div class="two">
<div><h2>تفکیک دسته‌بندی</h2>
<table><thead><tr><th>دسته‌بندی</th><th>تعداد</th><th>میانه اختلاف</th><th>دیجی‌کالا ارزان‌تر</th></tr></thead><tbody>{''.join(cat_rows) or "<tr><td colspan=4 class=muted>—</td></tr>"}</tbody></table></div>
<div><h2>تفکیک نوع آفر اسنپ‌پی</h2>
<table><thead><tr><th>کانال</th><th>تعداد</th><th>میانه اختلاف</th><th>دیجی‌کالا ارزان‌تر</th></tr></thead><tbody>{''.join(ch_rows) or "<tr><td colspan=4 class=muted>—</td></tr>"}</tbody></table></div>
</div>

<div class="two">
<div><h2>بیشترین شکاف به ضرر دیجی‌کالا</h2>
<table><thead><tr><th>محصول اسنپ‌پی</th><th>اسنپ‌پی</th><th>دیجی‌کالا</th><th>اختلاف</th><th>اطمینان</th></tr></thead><tbody>{item_rows(dk_expensive)}</tbody></table></div>
<div><h2>محصولاتی که دیجی‌کالا ارزان‌تر است</h2>
<table><thead><tr><th>محصول اسنپ‌پی</th><th>اسنپ‌پی</th><th>دیجی‌کالا</th><th>اختلاف</th><th>اطمینان</th></tr></thead><tbody>{item_rows(dk_cheap)}</tbody></table></div>
</div>

<h2>همه‌ی تخفیف‌های اسنپ‌پی (All SnappPay offers)</h2>
<div class="filters" id="xl">
<button class="btn" data-x="all">دانلود اکسل: همه‌ی تخفیف‌های اسنپ‌پی (Excel – All)</button>
<button class="btn" data-x="dk">دانلود اکسل: دیجی‌کالا ارزان‌تر (Excel – Digikala cheaper)</button>
<button class="btn" data-x="nf">دانلود اکسل: در دیجی‌کالا پیدا نشد (Excel – Not on Digikala)</button>
<button class="btn" data-x="view">دانلود اکسل: نمای فیلترشده (Excel – Current view)</button>
<span class="muted" id="xlmsg"></span>
</div>
<div class="filters">
<input id="q" placeholder="جستجو در عنوان یا فروشنده" size="28">
<select id="fconf"><option value="">وضعیت در دیجی‌کالا: همه</option><option value="matched">تطبیق قطعی (مبنای آمار)</option><option value="review">نیازمند بررسی</option><option value="uncertain">نامشخص</option><option value="not_found">در دیجی‌کالا پیدا نشد</option></select>
<select id="fv"><option value="">قیمت دیجی‌کالا: همه</option><option value="dk_cheaper">دیجی‌کالا قیمت بهتر (ارزان‌تر)</option><option value="snapp_cheaper">دیجی‌کالا قیمت بدتر (گران‌تر)</option><option value="equal">برابر (اختلاف کمتر از 1%)</option><option value="none">بدون داده (بدون معادل در دیجی‌کالا)</option></select>
<select id="fch"><option value="">همه کانال‌ها</option>{''.join(f'<option value="{k}">{v}</option>' for k, v in channel_labels.items())}</select>
<select id="fc"><option value="">همه دسته‌ها</option>{''.join(f'<option value="{k}">{v}</option>' for k, v in cat_labels.items() if k != 'hb')}</select>
<span class="muted" id="cnt"></span>
</div>
<div class="chips" id="vchips"></div>
<div class="scroll"><table><thead><tr><th>محصول اسنپ‌پی</th><th>قیمت اسنپ‌پی</th><th>محصول دیجی‌کالا</th><th>قیمت دیجی‌کالا</th><th>اختلاف</th><th>وضعیت در دیجی‌کالا</th></tr></thead><tbody id="tb"></tbody></table></div>

<h2>روش و ملاحظات</h2>
<ul class="note muted">
<li>هر محصول اسنپ‌پی با عنوانش در جستجوی دیجی‌کالا جستجو و بهترین نتیجه با امتیاز شباهت عنوان، تطابق مدل/عدد، تطابق حجم و تعداد بسته و منطقی‌بودن قیمت انتخاب شده است.</li>
<li>همه‌ی آمار این صفحه فقط بر پایه‌ی تطبیق‌های «اطمینان بالا» است (مدل یا کد مشترک و مشخصات یکسان؛ در بررسی دستی حدود 95% درست). تطبیق‌های «متوسط» در بررسی دستی حدود نیمی برند یا محصول متفاوت داشتند و فقط در جدول برای بررسی آمده‌اند.</li>
<li>قیمت اسنپ‌پی همیشه قیمت کامل کالاست، نه مبلغ یک قسط: روی کارت‌های لندینگ «4 قسط» برابر یک‌چهارم همین قیمت است (مثلاً 970,920 تومان = 4 قسط 242,730) و در تقویم تخفیف‌ها فقط قیمت کامل نمایش داده می‌شود.</li>
<li>بازبینی (Recheck): برای هر تطبیق، صفحه‌ی محصول دیجی‌کالا (برند فارسی و انگلیسی، عنوان کامل) خوانده و دوباره مقایسه می‌شود. تفاوت نسخه (Pro، Plus، NC، OLED، دوقلو)، طعم، جنسیت یا گروه سنی (بچه‌گربه و بالغ، زنانه و مردانه)، حجم یا تعداد بسته، و فروش همراه با لوازم اضافه باعث رد تطبیق می‌شود. نبودن برند دیجی‌کالا در عنوان اسنپ‌پی، نبودن مدل یا حجم در عنوان اسنپ‌پی، یا عنوان خیلی کلی، تطبیق را به «نیازمند بررسی» می‌برد. اگر بهترین نتیجه رد شود، دو نتیجه‌ی بعدی هم بازبینی می‌شوند. دلیل هر تصمیم زیر ستون وضعیت آمده است.</li>
<li>«در دیجی‌کالا پیدا نشد» یعنی همین محصول (همین مدل، برند یا حجم) در نتایج دیجی‌کالا نبود؛ برای کالاهای دارای کد مدل یک جستجوی دوم فقط با کد مدل هم انجام می‌شود. در بررسی نمونه‌ای، بیشتر این موارد کالای برند اختصاصی فروشنده (مثل جین‌وست، کوبیک)، مدل‌هایی که دیجی‌کالا ندارد یا عنوان‌های عمومی بودند؛ یعنی دیجی‌کالا معمولاً کالای مشابه دارد، ولی همان کالا را نه. «نامشخص» یعنی کالای مشابه هست ولی هیچ‌کدام قطعاً همان محصول (همان برند، مدل یا حجم) نیست. هر دو گروه بدون قیمت دیجی‌کالا نمایش داده می‌شوند.</li>
<li>عنوان‌های عمومی بدون برند یا مدل (مثل «کفش ورزشی مردانه») و طلا و جواهر بدون کد مدل، عمداً تطبیق داده نمی‌شوند.</li>
<li>اختلاف = (قیمت دیجی‌کالا − قیمت اسنپ‌پی) ÷ قیمت اسنپ‌پی. مثبت یعنی دیجی‌کالا گران‌تر.</li>
<li>کش‌بک اسنپ‌پی در قیمت اصلی لحاظ نشده و فقط در فایل CSV (ستون snapp_effective) آمده است.</li>
<li>بخش زیادی از محصولات لندینگ اسنپ‌پی کالای فروشگاه‌های کوچک یا بی‌برند است و معادل دقیقی در دیجی‌کالا ندارد؛ نرخ تطبیق پایین در این دسته‌ها طبیعی است.</li>
<li>آفرهای تقویم اسنپ‌پی زمان‌دار و با موجودی محدود (گاهی ۱ عدد) هستند؛ ستون وضعیت، زمان پخش بعدی را نشان می‌دهد.</li>
<li>«قیمت قبل از تخفیف» اسنپ‌پی در بسیاری موارد چند برابر قیمت بازار است؛ مقایسه فقط روی قیمت نهایی انجام شده است.</li>
</ul>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
<script>
const D={json.dumps(table_data, ensure_ascii=False)};
const CL={json.dumps(CONF_LABEL, ensure_ascii=False)},SL={json.dumps(STATUS_LABEL, ensure_ascii=False)},SO={{matched:0,review:1,uncertain:2,not_found:3}},CH={json.dumps(channel_labels, ensure_ascii=False)},LS={{live:"در حال پخش",upcoming:"نوبت بعد",ended:"تمام‌شده"}};
const f=n=>n==null?"—":Math.round(n).toLocaleString("en-US"),e=s=>(s||"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
const VCH=[["","همه",""],["dk_cheaper","دیجی‌کالا بهتر","g"],["snapp_cheaper","دیجی‌کالا بدتر","r"],["equal","برابر",""],["none","بدون داده",""]];
document.addEventListener("click",ev=>{{const b=ev.target.closest(".chip");if(!b)return;fv.value=b.dataset.v;draw();}});
function draw(){{const q=document.getElementById("q").value.trim(),cf=fconf.value,v=fv.value,ch=fch.value,c=fc.value;
const base=D.filter(x=>(!cf||x.st===cf)&&(!ch||x.ch===ch)&&(!c||x.c===c||(c==="beauty"&&x.c==="hb"))&&(!q||(x.t+x.m).includes(q)));
const vk=x=>x.v||"none";
const cntv={{"":base.length}};base.forEach(x=>cntv[vk(x)]=(cntv[vk(x)]||0)+1);
vchips.innerHTML=VCH.map(([k,l,cls])=>`<button class="chip ${{cls}} ${{v===k?"on":""}}" data-v="${{k}}">${{l}}<b>${{(cntv[k]||0).toLocaleString("en-US")}}</b></button>`).join("");
const r=base.filter(x=>!v||vk(x)===v)
.sort(v==="dk_cheaper"?(a,b)=>(SO[a.st]??9)-(SO[b.st]??9)||a.d-b.d:(a,b)=>(SO[a.st]??9)-(SO[b.st]??9)||(b.d??-999)-(a.d??-999));
window.__view=r; cnt.textContent=r.length+" ردیف";
tb.innerHTML=r.slice(0,1500).map(x=>`<tr><td><a href="${{e(x.su)}}" target="_blank">${{e(x.t)}}</a><div class="muted">${{e(x.m)}} · ${{CH[x.ch]||x.ch}}${{x.ls&&LS[x.ls]?`<span class="tag">${{LS[x.ls]}} ${{e(x.lt)}}</span>`:""}}</div></td>
<td>${{f(x.sp)}}${{x.cb?`<div class="muted">کش‌بک ${{x.cb}}%</div>`:""}}</td><td>${{x.du?`<a href="${{e(x.du)}}" target="_blank">${{e(x.dt)}}</a>`:"—"}}${{x.inc?`<span class="tag">شگفت‌انگیز</span>`:""}}</td>
<td>${{f(x.dp)}}</td><td class="${{x.d>1?"pos":x.d<-1?"neg":""}}" dir="ltr" style="text-align:right">${{x.d==null?"—":(x.d>0?"+":"")+x.d.toFixed(1)+"%"}}</td><td>${{SL[x.st]||""}}${{x.rc?`<div class="muted" style="max-width:260px">${{e(x.rc)}}</div>`:""}}</td></tr>`).join("");}}
["q","fconf","fv","fch","fc"].forEach(i=>document.getElementById(i).addEventListener("input",draw));draw();
const CAT={json.dumps(cat_labels, ensure_ascii=False)},VL={json.dumps(VERDICT_LABEL, ensure_ascii=False)},RUN={json.dumps(summary["run_at"])};
const toRow=x=>({{"وضعیت در دیجی‌کالا":SL[x.st]||"","نتیجه‌ی بازبینی (Recheck)":x.rc||"","محصول اسنپ‌پی":x.t,"فروشنده":x.m,"نوع آفر":CH[x.ch]||x.ch,"دسته‌بندی":CAT[x.c]||x.c,
"قیمت اسنپ‌پی (تومان)":x.sp,"قیمت قبل اسنپ‌پی":x.sb,"کش‌بک اسنپ‌پی %":x.cb,"قیمت اسنپ‌پی پس از کش‌بک":x.eff,
"محصول دیجی‌کالا":x.dt,"قیمت دیجی‌کالا (تومان)":x.dp,"قیمت قبل دیجی‌کالا":x.dr,"تخفیف دیجی‌کالا %":x.dd,"شگفت‌انگیز":x.inc?"بله":"",
"اختلاف (تومان)":x.dt2,"اختلاف %":x.d,"اختلاف % پس از کش‌بک":x.de,"نتیجه":VL[x.v]||"",
"وضعیت پخش":LS[x.ls]||"","زمان":x.lt,"لینک اسنپ‌پی":x.su,"لینک دیجی‌کالا":x.du}});
function sheet(rows){{const ws=XLSX.utils.json_to_sheet(rows.map(toRow));ws["!cols"]=[20,40,40,16,16,16,14,14,10,14,40,14,14,10,8,14,9,12,16,12,14,30,30].map(w=>({{wch:w}}));return ws;}}
function book(sheets){{const wb=XLSX.utils.book_new();wb.Workbook={{Views:[{{RTL:true}}]}};
const sum=[["آخرین اجرا",RUN],["کل تخفیف‌های اسنپ‌پی",{summary["snapp_items"]}],["تطبیق قطعی روی دیجی‌کالا",{summary["matched"]}],["در دیجی‌کالا پیدا نشد",{summary.get("not_found", 0)}],["نامشخص",{summary.get("uncertain", 0)}],["دیجی‌کالا ارزان‌تر",{summary["dk_cheaper"]}],["برابر",{summary["equal"]}],["اسنپ‌پی ارزان‌تر",{summary["snapp_cheaper"]}],["میانه اختلاف %",{json.dumps(summary["median_diff_pct"])}]];
XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(sum),"خلاصه");for(const [n,r] of sheets)XLSX.utils.book_append_sheet(wb,sheet(r),n);return wb;}}
const high=D.filter(x=>x.conf==="high");
const byStatus=[...D].sort((a,b)=>(SO[a.st]??9)-(SO[b.st]??9)||(b.d??-999)-(a.d??-999));
const SETS={{all:()=>[["همه‌ی تخفیف‌های اسنپ‌پی",byStatus],["دیجی‌کالا ارزان‌تر",high.filter(x=>x.v==="dk_cheaper").sort((a,b)=>a.d-b.d)],["اسنپ‌پی ارزان‌تر",high.filter(x=>x.v==="snapp_cheaper").sort((a,b)=>b.d-a.d)],["در دیجی‌کالا پیدا نشد",D.filter(x=>x.st==="not_found")]],
dk:()=>[["دیجی‌کالا ارزان‌تر",high.filter(x=>x.v==="dk_cheaper").sort((a,b)=>a.d-b.d)]],
nf:()=>[["در دیجی‌کالا پیدا نشد",D.filter(x=>x.st==="not_found")]],
view:()=>[["نمای فیلترشده",window.__view||[]]]}};
const NAMES={{all:"snapppay-vs-digikala-all",dk:"digikala-cheaper",nf:"not-on-digikala",view:"snapppay-vs-digikala-filtered"}};
async function exportXl(k,btn){{const msg=document.getElementById("xlmsg");if(typeof XLSX==="undefined"){{msg.textContent="کتابخانه‌ی اکسل بارگذاری نشد";return;}}
btn.disabled=true;try{{const wb=book(SETS[k]());const buf=XLSX.write(wb,{{bookType:"xlsx",type:"array"}});const name=NAMES[k]+"-"+RUN.replace(/[ :]/g,"-")+".xlsx";
let dl=null;try{{dl=window.claude&&await window.claude.use("downloads");}}catch(e){{}}
if(dl){{await dl.save({{filename:name,data:new Blob([buf])}});msg.textContent="";}}
else{{const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([buf],{{type:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}}));a.download=name;document.body.appendChild(a);a.click();a.remove();}}}}
catch(e){{msg.textContent=(e&&e.code==="declined")?"":"دانلود انجام نشد";}}finally{{btn.disabled=false;}}}}
document.querySelectorAll("#xl .btn").forEach(b=>b.addEventListener("click",()=>exportXl(b.dataset.x,b)));
</script></body></html>"""
