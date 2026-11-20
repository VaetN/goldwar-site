"""Готовит копию site/ для GitHub Pages: сайт открывается из подпапки /goldwar-site/.
Пути от корня (/static/..., /npc/...) получают префикс, во все страницы добавляется noindex."""
import os, re, sys
src, dst, pre = sys.argv[1], sys.argv[2], sys.argv[3].rstrip("/")
path = re.compile(r'(["\'(])/(?=[A-Za-z0-9_.%-])')
for root, _, files in os.walk(src):
    for fn in files:
        a = os.path.join(root, fn); b = os.path.join(dst, os.path.relpath(a, src))
        os.makedirs(os.path.dirname(b), exist_ok=True)
        ext = fn.rsplit(".", 1)[-1]
        if ext in ("html", "css", "js", "json"):
            t = open(a, encoding="utf-8").read()
            t = path.sub(lambda m: m.group(1) + pre + "/", t)
            if ext == "html":
                t = t.replace('href="/"', f'href="{pre}/"').replace("href='/'", f"href='{pre}/'")
                t = re.sub(r'<meta name="robots"[^>]*>', "", t)
                t = t.replace("<head>", '<head><meta name="robots" content="noindex, nofollow">', 1)
            open(b, "w", encoding="utf-8").write(t)
        elif fn != ".htaccess":
            with open(a, "rb") as f, open(b, "wb") as g: g.write(f.read())
