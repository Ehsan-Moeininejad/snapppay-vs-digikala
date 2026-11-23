// Fallback proxy for the SnappPay vs Digikala crawler (only needed if Digikala
// stops answering GitHub's servers directly).
//
// Deploy: dash.cloudflare.com -> Workers & Pages -> Create -> "Hello World" worker ->
// Edit code -> paste this file -> Deploy. Then Settings -> Variables -> add a
// secret named PROXY_KEY (any long random text). In the GitHub repo add the
// secrets DK_PROXY_URL (the worker URL, e.g. https://dk-proxy.<you>.workers.dev)
// and DK_PROXY_KEY (same text as PROXY_KEY).
//
// Tested 2026-11-23 from Cloudflare London: Digikala search API answers once the
// CDN's cookie challenge (307 + Set-Cookie) is followed, which this code does.

const ALLOWED = ["api.digikala.com", "snapppay.ir"];
const HEADERS = {
  "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  "accept": "application/json",
  "accept-language": "fa-IR,fa;q=0.9,en;q=0.8",
};

export default {
  async fetch(request, env) {
    const u = new URL(request.url);
    if (u.pathname !== "/fetch") return new Response("ok", { status: 200 });
    if (!env.PROXY_KEY || request.headers.get("x-proxy-key") !== env.PROXY_KEY) {
      return new Response("forbidden", { status: 403 });
    }
    let target;
    try { target = new URL(u.searchParams.get("url") || ""); } catch { return new Response("bad url", { status: 400 }); }
    if (target.protocol !== "https:" || !ALLOWED.includes(target.hostname)) {
      return new Response("host not allowed", { status: 400 });
    }

    const jar = {};
    let url = target.toString();
    let r;
    for (let i = 0; i < 6; i++) {
      const cookie = Object.entries(jar).map(([k, v]) => `${k}=${v}`).join("; ");
      r = await fetch(url, { headers: { ...HEADERS, cookie }, redirect: "manual" });
      for (const c of r.headers.getSetCookie ? r.headers.getSetCookie() : []) {
        const pair = c.split(";")[0];
        const k = pair.split("=")[0];
        jar[k] = pair.slice(k.length + 1);
      }
      if (r.status >= 300 && r.status < 400 && r.headers.get("location")) {
        url = new URL(r.headers.get("location"), url).toString();
        continue;
      }
      break;
    }
    return new Response(r.body, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") || "application/json" },
    });
  },
};
