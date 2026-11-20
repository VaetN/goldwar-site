"""Полный SEO/GEO-обход локальной сборки dist/ (как видит бот: исходный HTML)."""
import os, re, json, sys, collections
from bs4 import BeautifulSoup
from urllib.parse import urlparse

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
BASE = "https://goldwar.net"
pages = {}
for root, _, files in os.walk(D):
    for f in files:
        if f.endswith(".html"):
            p = "/" + os.path.relpath(os.path.join(root, f), D).replace("index.html", "")
            pages[p] = os.path.join(root, f)

files_all = set()
for root, _, files in os.walk(D):
    for f in files:
        files_all.add("/" + os.path.relpath(os.path.join(root, f), D))

def exists(href):
    u = urlparse(href); p = u.path
    if p.endswith("/"): return p in pages
    return p in files_all

sm = open(os.path.join(D, "sitemap.xml")).read()
sm_urls = set(re.findall(r"<loc>([^<]+)</loc>", sm))
rows = []; inlinks = collections.Counter(); broken = collections.Counter()
for p, fp in pages.items():
    h = open(fp, encoding="utf-8").read()
    s = BeautifulSoup(h, "html.parser")
    t = s.title.get_text(strip=True) if s.title else ""
    dm = s.find("meta", attrs={"name": "description"}); d = dm.get("content", "") if dm else ""
    can = s.find("link", rel="canonical"); can = can.get("href") if can else None
    rob = s.find("meta", attrs={"name": "robots"}); rob = rob.get("content", "") if rob else ""
    h1 = [x.get_text(" ", strip=True) for x in s.find_all("h1")]
    ld = []; bad = 0
    for tag in s.find_all("script", type="application/ld+json"):
        try:
            j = json.loads(tag.string or "")
            for i in (j.get("@graph", [j]) if isinstance(j, dict) else j):
                ld.append(i.get("@type"))
        except Exception: bad += 1
    og = all(s.find("meta", property=k) for k in ("og:title", "og:description", "og:image", "og:url", "og:type", "og:locale"))
    imgs = s.find_all("img"); noalt = [i.get("src") for i in imgs if i.get("alt") is None]
    links = [a.get("href") for a in s.find_all("a") if a.get("href", "").startswith("/")]
    for l in set(links):
        if exists(l): inlinks[urlparse(l).path] += 1
        else: broken[l] += 1
    main = s.find("main") or s
    for x in main(["script", "style", "noscript", "nav", "footer", "header"]): x.decompose()
    words = len(main.get_text(" ", strip=True).split())
    text = s.get_text(" ", strip=True)
    rows.append(dict(p=p, t=t, tl=len(t), d=d, dl=len(d), h1=h1, can=can, rob=rob, ld=ld, ldbad=bad, og=og,
                     noalt=len(noalt), words=words, em=(t + d + text).count("—"), insm=(BASE + p) in sm_urls,
                     ni="noindex" in rob))

idx = [r for r in rows if not r["ni"] and (r["can"] in (None, BASE + r["p"]))]
def cnt(cond): return sum(1 for r in idx if cond(r))
dup_t = [k for k, v in collections.Counter(r["t"] for r in idx).items() if v > 1]
dup_d = [k for k, v in collections.Counter(r["d"] for r in idx).items() if v > 1]
sect = collections.Counter(r["p"].split("/")[1] or "home" for r in rows)
rep = {
    "pages": len(rows), "indexable": len(idx), "noindex": sum(r["ni"] for r in rows),
    "canon_other": sum(1 for r in rows if r["can"] and r["can"] != BASE + r["p"]),
    "no_canonical": [r["p"] for r in rows if not r["can"]][:5],
    "sections": dict(sect),
    "title_gt60": cnt(lambda r: r["tl"] > 60), "title_lt30": cnt(lambda r: r["tl"] < 30),
    "desc_missing": cnt(lambda r: not r["d"]), "desc_gt160": cnt(lambda r: r["dl"] > 160), "desc_lt110": cnt(lambda r: 0 < r["dl"] < 110),
    "h1_not1": [r["p"] for r in rows if len(r["h1"]) != 1][:10],
    "dup_titles": len(dup_t), "dup_desc": len(dup_d), "dup_desc_ex": dup_d[:3],
    "no_og": cnt(lambda r: not r["og"]), "ld_bad": sum(r["ldbad"] for r in rows),
    "img_noalt_pages": cnt(lambda r: r["noalt"] > 0), "em_dash": cnt(lambda r: r["em"] > 0),
    "thin_lt80": cnt(lambda r: r["words"] < 80),
    "idx_not_in_sitemap": [r["p"] for r in idx if not r["insm"]][:10], "idx_not_in_sitemap_n": cnt(lambda r: not r["insm"]),
    "sitemap_not_indexable": len([u for u in sm_urls if u[len(BASE):] not in {r["p"] for r in idx}]),
    "broken_links": broken.most_common(10), "orphans": [r["p"] for r in idx if inlinks[r["p"]] == 0][:15],
    "orphans_n": sum(1 for r in idx if inlinks[r["p"]] == 0),
    "ld_types": collections.Counter(t if isinstance(t, str) else "/".join(t) for r in rows for t in r["ld"]).most_common(),
}
per_sec = collections.defaultdict(lambda: collections.Counter())
for r in idx:
    k = r["p"].split("/")[1] or "home"
    per_sec[k]["n"] += 1; per_sec[k]["tgt60"] += r["tl"] > 60; per_sec[k]["dgt160"] += r["dl"] > 160
    per_sec[k]["dlt110"] += 0 < r["dl"] < 110; per_sec[k]["thin"] += r["words"] < 80
rep["per_section"] = {k: dict(v) for k, v in per_sec.items()}
json.dump({"rep": rep, "rows": rows}, open("/tmp/seoaudit.json", "w"), ensure_ascii=False)
print(json.dumps(rep, ensure_ascii=False, indent=1))
