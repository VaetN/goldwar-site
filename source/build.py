#!/usr/bin/env python3
"""Генератор сайта Goldwar: главная + база знаний Interlude.
Данные: открытый набор lineage2-api (MIT), позже заменяются файлами сервера Goldwar."""
import json, os, re, shutil, math, html, datetime, collections
from jinja2 import Environment, FileSystemLoader
from PIL import Image, ImageFilter
import ru

SRC = os.environ.get("L2API") or (os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor/l2api")
       if os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor/l2api")) else "/home/claude/src/l2api")
DATA = f"{SRC}/data/generated/interlude"
ICONS = f"{SRC}/public/icons"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "dist")
ASSETS = os.path.join(HERE, "assets")          # материалы заказчика (лого, видео, сундук)
BASE = "https://goldwar.net"
TODAY = datetime.date.today()
MONTHS = ["января","февраля","марта","апреля","мая","июня","июля","августа","сентября","октября","ноября","декабря"]

def load(n): return json.load(open(f"{DATA}/{n}.json"))
items = load("items"); npcs = load("npcs"); skills = load("skills"); classes = load("classes")
drops = load("drops"); spawns = load("spawns"); zones = load("huntingzones"); quests = load("quests")
qnames = load("questname"); recipes = load("recipes"); sets = load("armor-sets"); buylists = load("buylists")
regions = load("regions")

ITEM = {i["id"]: i for i in items}
NPC = {n["id"]: n for n in npcs}
SKILL = {}
for s in skills: SKILL.setdefault(s["id"], {})[s["level"]] = s
CLS = {c["id"]: c for c in classes}

# ---------- утилиты ----------
NB = "\u00a0"
def fmt(n):
    if n is None: return "–"
    if isinstance(n, float):
        n = round(n, 2) if n < 100 else round(n)
        if isinstance(n, float) and n.is_integer(): n = int(n)
    s = f"{n:,}".replace(",", NB)
    return s.replace(".", ",")
def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().replace("'", "")).strip("-")
    return s or "x"
def esc(s): return html.escape(str(s), quote=True)
def pct(raw):
    p = raw / 10000
    if p >= 100: return "100%"
    if p >= 0.01: return (f"{p:.2f}".rstrip("0").rstrip(".") + "%").replace(".", ",")
    return f"1/{fmt(round(100 / p))}"
def plural(n, a, b, c):
    n = abs(n) % 100
    if 10 < n < 20: return c
    n %= 10
    return a if n == 1 else b if 2 <= n <= 4 else c
def clip_title(main, brand=" | Goldwar", limit=60):
    t = main + brand
    return t if len(t) <= limit else main

USED_ICONS = set()
ICON_OK = set(os.listdir(ICONS))
CUSTOM_ICONS = os.path.join(HERE, "assets/icons")   # свои иконки сервера (Goldwar Weapon и др.)
if os.path.isdir(CUSTOM_ICONS): ICON_OK |= set(os.listdir(CUSTOM_ICONS))
FALLBACK = "etc_question_mark_i00.png" if "etc_question_mark_i00.png" in ICON_OK else "etc_coins_gold_i00.png"
def icon(f):
    if not f or f not in ICON_OK: f = FALLBACK
    USED_ICONS.add(f)
    return f[:-4] + ".webp"

# ---------- регионы и зоны ----------
G = regions["grid"]; RNAME = {r["id"]: r["name"] for r in regions["regions"]}
def region_of(x, y):
    rx = (x >> 15) + G["originX"]; ry = (y >> 15) + G["originY"]
    if 0 <= rx < G["width"] and 0 <= ry < G["height"]:
        i = G["cells"][ry * G["width"] + rx]
        if i >= 0:
            n = RNAME.get(i); return ru.REGION_RU.get(n, n)
    return None
def zone_of(x, y):
    best, bd = None, 10000 ** 2
    for z in zones:
        d = (z["x"] - x) ** 2 + (z["y"] - y) ** 2
        if d < bd: best, bd = z, d
    return best

MOB_TYPES = {"Monster", "RaidBoss", "GrandBoss"}
mobs = [n for n in npcs if n["npcType"] in MOB_TYPES and (n.get("level") or 0) > 0]
MOB = {n["id"]: n for n in mobs}
SP_BY = collections.defaultdict(list)
for s in spawns:
    if s["npcId"] in MOB: SP_BY[s["npcId"]].append(s)
MOB_ZONE, ZONE_MOBS, MOB_REGION = {}, collections.defaultdict(set), {}
for nid, lst in SP_BY.items():
    zc, rc = collections.Counter(), collections.Counter()
    for s in lst[:60]:
        z = zone_of(s["x"], s["y"])
        if z: zc[z["id"]] += 1
        r = region_of(s["x"], s["y"])
        if r: rc[r] += 1
    if zc:
        zid = zc.most_common(1)[0][0]; MOB_ZONE[nid] = zid; ZONE_MOBS[zid].add(nid)
    if rc: MOB_REGION[nid] = rc.most_common(1)[0][0]
ZONE = {z["id"]: z for z in zones}

# ---------- данные сервера Goldwar (их npcs.xml: только NPC с включённым дропом) ----------
import xml.etree.ElementTree as ET
GW_FILE = os.path.join(HERE, "data/npcs.xml")
GW, GW_NAMES = {}, {}
def _dd(lst):
    seen = {}
    for r in lst:
        k = (r[0], r[1], r[2])
        if k not in seen or r[3] > seen[k][3]: seen[k] = r
    return sorted(seen.values(), key=lambda r: -r[3])
if os.path.exists(GW_FILE):
    for n in ET.parse(GW_FILE).getroot().findall("npc"):
        GW_NAMES[int(n.get("id"))] = n.get("name")
        st = {x.get("name"): x.get("val") for x in n.findall("set")}
        dr = n.find("drops")
        if dr is None or st.get("type") not in ("Monster", "RaidBoss", "GrandBoss"): continue
        reg, sp = [], []
        for c in dr.findall("category"):
            for d in c.findall("drop"):
                row = (int(d.get("itemid")), int(d.get("min")), int(d.get("max")), int(d.get("chance")))
                (sp if int(c.get("id")) == -1 else reg).append(row)
        ai = n.find("ai")
        f = lambda k: float(st.get(k) or 0)
        GW[int(n.get("id"))] = {"id": int(n.get("id")), "name": n.get("name"), "title": n.get("title") or "", "type": st["type"],
            "level": int(st["level"]), "hp": f("hp"), "mp": f("mp"), "pAtk": f("pAtk"), "pDef": f("pDef"), "mAtk": f("mAtk"), "mDef": f("mDef"),
            "exp": int(f("exp")), "sp": int(f("sp")), "aggro": ai is not None and int(ai.get("aggro") or 0) > 0,
            "drop": _dd(reg), "spoil": _dd(sp), "minions": [(int(m.get("id")), int(m.get("min")), int(m.get("max"))) for m in n.findall("minions/minion")]}
GW_SPAWN = collections.defaultdict(list)
for s_ in spawns:
    if s_["npcId"] in GW: GW_SPAWN[s_["npcId"]].append(s_)
_std_by_name = {}
for n_ in npcs:
    if n_["npcType"] in ("RaidBoss", "GrandBoss", "Monster"): _std_by_name.setdefault(n_["name"], n_["id"])
def gw_custom(nid): return nid >= 50000
def gw_where(nid):
    sp_ = GW_SPAWN.get(nid)
    if not sp_ and gw_custom(nid): return None, None
    if not sp_:
        alt = _std_by_name.get(GW[nid]["name"])
        sp_ = [x for x in spawns if x["npcId"] == alt][:20] if alt else []
    if not sp_: return None, None
    z = zone_of(sp_[0]["x"], sp_[0]["y"]); r = region_of(sp_[0]["x"], sp_[0]["y"])
    return (z["name"] if z else None), r
GW_ITEM = collections.defaultdict(list)
for nid_, g_ in GW.items():
    for r in g_["drop"]: GW_ITEM[r[0]].append((nid_, r, False))
    for r in g_["spoil"]: GW_ITEM[r[0]].append((nid_, r, True))

# ---------- дроп ----------
DROP = {}; DROPPED_BY = collections.defaultdict(list); SPOILED_BY = collections.defaultdict(list)
for d in drops:
    if d["npcId"] not in MOB: continue
    reg, sp = [], []
    for c in d["categories"]:
        for e in c["drops"]:
            row = (e["itemId"], e.get("min"), e.get("max"), e.get("chance") or 0)
            (sp if c["categoryId"] == -1 else reg).append(row)
            (SPOILED_BY if c["categoryId"] == -1 else DROPPED_BY)[e["itemId"]].append((d["npcId"], row))
    def _dd(lst):
        seen = {}
        for r in lst:
            k = (r[0], r[1], r[2])
            if k not in seen or r[3] > seen[k][3]: seen[k] = r
        return sorted(seen.values(), key=lambda r: -r[3])
    DROP[d["npcId"]] = (_dd(reg), _dd(sp))

# публикуем только монстров, у которых есть спавн или дроп
MOB = {k: v for k, v in MOB.items() if k in SP_BY or any(DROP.get(k, ([], []))) }
mobs = [n for n in mobs if n["id"] in MOB]
_mg = collections.defaultdict(list)
for n in mobs: _mg[(n["name"], n["level"])].append(n["id"])
MPRIMARY = {}
for _k, _ids in _mg.items():
    _p = max(_ids, key=lambda x: (len(SP_BY.get(x, [])) > 0, len(DROP.get(x, ([], []))[0]) + len(DROP.get(x, ([], []))[1]), -x))
    for _x in _ids: MPRIMARY[_x] = _p

# рецепты, магазины, сеты
RECIPE_FOR = {r["productItemId"]: r for r in recipes}
RECIPE_BY_ITEM = {r["recipeItemId"]: r for r in recipes}
USED_IN = collections.defaultdict(list)
for r in recipes:
    for g in r["ingredients"]: USED_IN[g["itemId"]].append(r)
SOLD = collections.defaultdict(list)
for b in buylists:
    for p in b["products"]: SOLD[p["itemId"]].append((b["npcId"], p.get("price")))
SET_OF = {}
for st in sets:
    for k, v in st["pieces"].items():
        if v: SET_OF[v] = st
QUEST_REWARD = collections.defaultdict(list)
for q in quests:
    for it in (q.get("rewards") or {}).get("items") or []: QUEST_REWARD[it["itemId"]].append(q)

# какие предметы публикуем отдельными страницами
PUB = set()
for i in items:
    if i["type"] in ("weapon", "armor"): PUB.add(i["id"])
    elif i.get("etcItemType") != "quest" and (i["id"] in DROPPED_BY or i["id"] in SPOILED_BY or i["id"] in RECIPE_FOR
            or i["id"] in RECIPE_BY_ITEM or i["id"] in USED_IN or i["id"] in SOLD or i["id"] in QUEST_REWARD):
        PUB.add(i["id"])
_byname = collections.defaultdict(list)
for _i in PUB: _byname[ITEM[_i]["name"]].append(_i)
PRIMARY = {}
for _n, _ids in _byname.items():
    _p = max(_ids, key=lambda x: (len(DROPPED_BY.get(x, [])) + len(SPOILED_BY.get(x, [])) + (5 if x in RECIPE_FOR else 0) + (3 if x in SET_OF else 0), -x))
    for _x in _ids: PRIMARY[_x] = _p
def iurl(iid): return f"/wiki/item/{iid}-{slug(ITEM[iid]['name'])}/" if iid in PUB else None
def murl(nid): return f"/wiki/monster/{nid}-{slug(NPC[nid]['name'])}/" if nid in MOB else None
def zurl(zid): return f"/wiki/zone/{zid}-{slug(ZONE[zid]['name'])}/"
def curl(cid): return f"/wiki/classes/{slug(CLS[cid]['name'])}/"
def qurl(qid): return f"/wiki/quest/{qid}-{slug(QBY[qid]['name'])}/"
QBY = {q["id"]: q for q in quests}

def gbadge(g):
    return f'<span class="grade g-{g}">{ru.GRADE_RU.get(g, g).upper() if g != "none" else "–"}</span>'

def item_kind(i):
    if i["type"] == "weapon":
        if i["bodypart"] == "lhand" or i.get("weaponType") == "NONE": return "Щит"
        return ru.WEAPON_RU.get(i.get("weaponType"), "Оружие")
    if i["type"] == "armor":
        bp = i["bodypart"]
        if bp in ("hairall", "hair", "face", "dhair", "alldress"): return "Аксессуар"
        if bp in ("wolf", "hatchling", "strider", "babypet"): return "Снаряжение питомца"
        k = ru.BODY_RU.get(bp, "Броня")
        at = ru.ARMOR_TYPE_RU.get(i.get("armorType") or "", "")
        return f"{k}" + (f", {at.lower()}" if at and bp not in ("rear;lear", "neck", "rfinger;lfinger", "lhand") else "")
    return ru.ETC_RU.get(i.get("etcItemType"), "Прочее")

def item_cell(iid, extra=""):
    i = ITEM.get(iid)
    if not i: return f"#{iid}"
    u = iurl(iid); ic = icon(i.get("iconFile"))
    g = f' {gbadge(i["grade"])}' if i["grade"] != "none" else ""
    inner = f'<img src="/static/i/{ic}" alt="" width="32" height="32" loading="lazy"><span>{esc(i["name"])}{g}{("<small>"+extra+"</small>") if extra else ""}</span>'
    return f'<a class="it" href="{u}" data-i="{iid}">{inner}</a>' if u else f'<span class="it">{inner}</span>'
def npc_cell(nid, extra=""):
    n = NPC.get(nid)
    if not n: return f"#{nid}"
    u = murl(nid)
    lbl = esc(n["name"]) + (f'<small>{extra}</small>' if extra else "")
    return f'<a class="it" href="{u}"><span>{lbl}</span></a>' if u else f'<span class="it"><span>{lbl}</span></span>'

def table(head, rows, cls=""):
    th = "".join(f'<th{" class=r" if h.endswith(">") else ""}>{h.rstrip(">")}</th>' for h in head)
    body = "".join("<tr>" + "".join(f'<td{" class=r" if head[k].endswith(">") else ""}>{c}</td>' for k, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<table class="tbl {cls}"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'

def qty(mn, mx):
    if mn is None and mx is None: return "1"
    if mn == mx or mx is None: return fmt(mn)
    return f"{fmt(mn)}–{fmt(mx)}"

def bc_ld(bc):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": k + 1, "name": n, **({"item": BASE + u} if u else {})} for k, (n, u) in enumerate(bc)]}
def faq_ld(faq):
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}

# ---------- шаблоны ----------
env = Environment(loader=FileSystemLoader(os.path.join(HERE, "templates")), autoescape=True)
SOC_ICON = {
 "tg": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M21.4 4.3 2.9 11.4c-1 .4-1 1.6 0 1.9l4.6 1.4 1.8 5.4c.2.7 1.1.9 1.6.4l2.6-2.4 4.8 3.5c.6.4 1.4.1 1.6-.6L22.9 5.6c.2-1-.6-1.7-1.5-1.3ZM9.8 14.4l-.5 3.3-1.2-3.8 9.5-6-7.8 6.5Z"/></svg>',
 "ds": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19.6 5.3A16.4 16.4 0 0 0 15.5 4l-.5 1a15 15 0 0 0-6 0l-.5-1a16.4 16.4 0 0 0-4.1 1.3C1.8 9.2 1.1 13 1.4 16.8a16.6 16.6 0 0 0 5 2.5l1.1-1.7a10.5 10.5 0 0 1-1.7-.8l.4-.3a11.8 11.8 0 0 0 11.6 0l.4.3-1.7.8 1.1 1.7a16.5 16.5 0 0 0 5-2.5c.4-4.4-.7-8.2-3-11.5ZM8.7 14.5c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Zm6.6 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2Z"/></svg>',
 "tt": '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16.6 3h-3.2v12.3a2.8 2.8 0 1 1-2-2.7V9.3a6 6 0 1 0 5.2 6V9a7.6 7.6 0 0 0 4.4 1.4V7.2a4.4 4.4 0 0 1-4.4-4.2Z"/></svg>',
 "ig": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r=".8" fill="currentColor"/></svg>',
}
SITE = {
    "base": BASE, "v": TODAY.strftime("%Y%m%d"), "year": TODAY.year,
    "updated_ru": f"{TODAY.day} {MONTHS[TODAY.month-1]} {TODAY.year}",
    "acp_register": "https://acp.goldwar.net/register/", "acp_login": "https://acp.goldwar.net/login/",
    "tg_event": "https://t.me/qr_qwery", "ds_event": "https://discord.gg/67VF8SUYj",
    "has_logo": os.path.exists(f"{ASSETS}/logoGold.png"), "has_video": os.path.exists(f"{ASSETS}/hero.mp4") or os.path.exists(f"{ASSETS}/video.mp4"), "has_heroimg": os.path.exists(f"{ASSETS}/hero.jpg"),
    "has_wikiart": os.path.exists(f"{ASSETS}/wiki.jpg"), "has_wikivideo": os.path.exists(f"{ASSETS}/wiki.mp4"), "has_raidart": os.path.exists(f"{ASSETS}/raid.jpg"),
    "has_races": all(os.path.exists(f"{ASSETS}/race-{r}.jpg") for r in ("human", "elf", "dark-elf", "orc", "dwarf")),
    "has_chest": os.path.exists(f"{ASSETS}/chest.jpg") or os.path.exists(f"{ASSETS}/sunduk.png"), "has_coin": os.path.exists(f"{ASSETS}/goldcoin.png"),
    "menu": [
        {"key": "home", "title": "Главная", "href": "/"},
        {"key": "bosses", "title": "Рейд-боссы", "href": "/bosses/"},
        {"key": "epic", "title": "Эпик-боссы", "href": "/epic/"},
        {"key": "drop", "title": "Дроп", "href": "/drop/"},
        {"key": "files", "title": "Файлы", "href": "/files/"},
        {"key": "support", "title": "Поддержка", "href": "/support/"},
    ],
    "wiki_menu": [
        {"key": "home", "title": "Обзор", "href": "/wiki/"},
        {"key": "classes", "title": "Классы", "href": "/wiki/classes/"},
        {"key": "items", "title": "Предметы", "href": "/wiki/items/"},
        {"key": "monsters", "title": "Монстры", "href": "/wiki/monsters/"},
        {"key": "raid", "title": "Рейд-боссы", "href": "/wiki/raid-bosses/"},
        {"key": "zones", "title": "Зоны охоты", "href": "/wiki/zones/"},
        {"key": "quests", "title": "Квесты", "href": "/wiki/quests/"},
        {"key": "sets", "title": "Сеты", "href": "/wiki/items/sets/"},
    ],
    "socials": [
        {"title": "Telegram-канал", "href": "https://t.me/GoldwarChannel", "icon": SOC_ICON["tg"]},
        {"title": "Чат в Telegram", "href": "https://t.me/GoldwarChat", "icon": SOC_ICON["tg"]},
        {"title": "Discord", "href": "https://discord.gg/QmESSAQJM", "icon": SOC_ICON["ds"]},
        {"title": "TikTok", "href": "https://www.tiktok.com/@goldwar_official", "icon": SOC_ICON["tt"]},
        {"title": "Instagram", "href": "https://www.instagram.com/goldwar.net_l2", "icon": SOC_ICON["ig"]},
    ],
}
PAGES = []
SEARCH = []
ARTS = {n: os.path.exists(f"{ASSETS}/{n}.jpg") for n in ("wiki", "raid", "items", "monsters", "zones", "quests")}
def auto_art(path, ctx):
    if "art" in ctx: return ctx["art"]
    sec = ctx.get("wsec")
    want = {"raid": "raid", "items": "items", "sets": "items", "monsters": "monsters", "zones": "zones", "quests": "quests", "classes": "wiki", "home": "wiki"}.get(sec)
    return want if want and ARTS.get(want) else None
def render(path, tpl, meta, jsonld=(), **ctx):
    t = env.get_template(tpl)
    ctx["art"] = auto_art(path, ctx)
    out = t.render(site=SITE, path=path, meta=meta, jsonld=list(jsonld), **ctx)
    d = os.path.join(OUT, path.strip("/"))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w") as f: f.write(out)
    if not meta.get("noindex"): PAGES.append(path)
    TITLES[meta["title"]].append(path); DESCS[meta["description"]].append(path)
TITLES = collections.defaultdict(list); DESCS = collections.defaultdict(list)

if os.path.exists(OUT): shutil.rmtree(OUT)
os.makedirs(OUT)

# ================= КЛАССЫ =================
def own_skills(c):
    by = collections.OrderedDict()
    for s in sorted(c["skills"], key=lambda s: (s["minPlayerLevel"], s["skillId"], s["skillLevel"])):
        by.setdefault(s["skillId"], []).append(s)
    return by
def class_icon(c):
    by = own_skills(c)
    cand = [sid for sid, lv in by.items() if SKILL.get(sid, {}).get(lv[0]["skillLevel"], {}).get("iconFile") in ICON_OK]
    act = [sid for sid in cand if SKILL[sid][by[sid][0]["skillLevel"]]["operateType"] == "OP_ACTIVE"]
    pick = (act or cand)
    if not pick: return icon(None)
    sid = pick[-1] if c["professionLevel"] else pick[0]
    return icon(SKILL[sid][by[sid][0]["skillLevel"]]["iconFile"])
CICON = {c["id"]: class_icon(c) for c in classes}
CHILD = collections.defaultdict(list)
for c in classes:
    if c["parentClassId"] is not None: CHILD[c["parentClassId"]].append(c["id"])
def chain(cid):
    out = []
    while cid is not None: out.append(cid); cid = CLS[cid]["parentClassId"]
    return out[::-1]
def is_mage(cid): return "Mystic" in CLS[chain(cid)[0]]["name"]

RACE_TEXT = {
 "Human": "Самая гибкая раса: есть танки, луки, кинжалы, саммонеры и оба вида хилеров. Хороший выбор, если ещё не решили, чем играть.",
 "Elf": "Лучшая скорость бега и каста. Эльфы дают сильных лучников, баферов-менестрелей и хилера Мудреца Евы.",
 "Dark Elf": "Самая высокая атака среди рас при низкой защите. Сильнейшие нюкеры и танцоры смерти, но ошибки прощают хуже.",
 "Orc": "Много HP и сопротивления. Отсюда Разрушители, Монахи и баферы-Вестники Войны, без которых не обходится пати.",
 "Dwarf": "Единственная раса с крафтом и спойлом. Кузнецы делают вещи, Охотники за Наградой добывают для них материалы.",
}
races_ctx = []
for race in ru.RACE_ORDER:
    roots = [c for c in classes if c["race"] == race and c["professionLevel"] == 0]
    branches = []
    for r in roots:
        for f in CHILD[r["id"]]:
            its = [f] + [x for s in CHILD[f] for x in [s] + CHILD[s]]
            branches.append({"name": ru.CLASS_RU[f], "icon": CICON[f], "kind": "маги" if is_mage(f) else "воины",
                "items": [{"ru": ru.CLASS_RU[x], "en": CLS[x]["name"], "url": curl(x), "icon": CICON[x], "prof": CLS[x]["professionLevel"],
                           "prof_ru": ["база", "1-я профессия", "2-я профессия", "3-я профессия"][CLS[x]["professionLevel"]]} for x in its]})
    races_ctx.append({"img": f"/static/media/race-{ru.RACE_SLUG[race]}.jpg" if SITE["has_races"] else None, "ru": ru.RACE_RU[race], "slug": ru.RACE_SLUG[race], "text": RACE_TEXT[race], "branches": branches})

bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Классы", None)]
render("/wiki/classes/", "classes.html",
       {"title": "Классы Lineage 2 Interlude – умения и профессии | Goldwar",
        "description": "Все 89 классов Interlude по расам: путь от базового класса до третьей профессии, иконки и список умений с уровнем изучения и стоимостью SP."},
       [bc_ld(bc)], section="wiki", wsec="classes",
       intro="Пять рас, 89 классов и три смены профессии: на 20, 40 и 76 уровне. Выберите ветку, чтобы увидеть, какие умения она даёт и на каком уровне их учить.",
       races=races_ctx)
for c in classes:
    SEARCH.append([f'{ru.CLASS_RU[c["id"]]}', curl(c["id"]), CICON[c["id"]], "класс", c["name"]])

OP_RU = {"OP_ACTIVE": "Активное", "OP_PASSIVE": "Пассивное", "OP_TOGGLE": "Переключаемое"}
for c in classes:
    cid = c["id"]; rn = ru.CLASS_RU[cid]; ch = chain(cid)
    by = own_skills(c)
    rows = []; n_act = n_pas = 0; sp_total = 0
    for sid, lv in by.items():
        sk = SKILL.get(sid, {}); top = sk.get(lv[-1]["skillLevel"]) or {}
        first = sk.get(lv[0]["skillLevel"]) or {}
        if not first: continue
        op = first.get("operateType")
        if op == "OP_PASSIVE": n_pas += 1
        else: n_act += 1
        sp_total += sum(max(0, x["spCost"] or 0) for x in lv)
        levels = f'{lv[0]["skillLevel"]}–{lv[-1]["skillLevel"]}' if len(lv) > 1 else str(lv[-1]["skillLevel"])
        learn = f'{lv[0]["minPlayerLevel"]}' + (f'–{lv[-1]["minPlayerLevel"]}' if lv[-1]["minPlayerLevel"] != lv[0]["minPlayerLevel"] else "")
        mp = top.get("mpConsume"); rd = top.get("reuseDelay")
        rows.append([
            f'<span class="it"><img src="/static/i/{icon(first.get("iconFile"))}" alt="" width="32" height="32" loading="lazy"><span>{esc(first["name"])}<small>{OP_RU.get(op, "")}</small></span></span>',
            f'<span class="lvl-pill">{learn}</span>', levels, fmt(mp) if mp else "–",
            (fmt(round(rd / 1000, 1)) + " с") if rd else "–", (fmt(sum(max(0, x["spCost"] or 0) for x in lv)) or "–") if sum(max(0, x["spCost"] or 0) for x in lv) else "книга"])
    parent = c["parentClassId"]
    kids = CHILD.get(cid, [])
    LV = ["база", "20 ур.", "40 ур.", "76 ур."]
    def node(x, cur=False):
        return (f'<a class="pn{" cur" if cur else ""}" href="{curl(x)}"><img src="/static/i/{CICON[x]}" alt="" width="40" height="40" loading="lazy">'
                f'<span><b>{ru.CLASS_RU[x]}</b><small>{LV[CLS[x]["professionLevel"]]}</small></span></a>')
    path_html = '<div class="pathd">' + "".join(f'<div class="pcol">{node(x, x == cid)}</div>' for x in ch)
    if kids: path_html += '<div class="pcol pkids">' + "".join(node(k) for k in kids) + "</div>"
    path_html += "</div>"
    prof = ru.PROF_RU[c["professionLevel"]]
    race_ru = ru.RACE_RU[c["race"]]
    role = "маг" if is_mage(cid) else "воин"
    intro = (f'{rn} ({c["name"]}) – {"базовый класс" if c["professionLevel"]==0 else ["", "первая", "вторая", "третья"][c["professionLevel"]] + " профессия"} '
             f'расы {race_ru}, ветка «{ru.CLASS_RU[ch[1]] if len(ch)>1 else rn}». '
             f'С этой профессией приходит {len(rows)} {plural(len(rows),"умение","умения","умений")}: {n_act} активных и {n_pas} пассивных, '
             f'на все уровни уходит {fmt(sp_total)} SP.')
    if parent is not None:
        intro += f' Умения прошлых профессий остаются – их список на странице класса <a href="{curl(parent)}">{ru.CLASS_RU[parent]}</a>.'
    secs = [{"id": "path", "title": "Путь развития", "html": path_html},
            {"id": "skills", "title": f"Умения класса {rn}",
             "text": "Уровень изучения – уровень персонажа, с которого умение можно взять у учителя. MP и перезарядка указаны для последнего уровня умения.",
             "html": '<div class="tbl-wrap">' + table(["Умение", "Учить с ур.", "Уровни", "MP>", "Перезарядка>", "SP всего>"], rows) + "</div>"}]
    faq = [(f"На каком уровне можно стать {rn}?",
            {0: f"{rn} – стартовый класс, он выбирается при создании персонажа.", 1: f"Первую профессию {rn} берут с 20 уровня у мастера класса в городе.",
             2: f"Вторую профессию {rn} получают с 40 уровня после квеста на профессию.", 3: f"Третью профессию {rn} берут с 76 уровня после квеста на третью профессию."}[c["professionLevel"]]),
           (f"Сколько SP нужно на все умения {rn}?", f"На умения, которые приходят с этой профессией, уходит {fmt(sp_total)} SP. Умения прошлых профессий считаются отдельно.")]
    if kids:
        faq.append((f"Во что развивается {rn}?", f'{rn} развивается в {" или ".join(ru.CLASS_RU[k] for k in kids)}.'))
    side = [{"title": "Класс", "props": [("Раса", race_ru), ("Тип", role.capitalize()), ("Профессия", ["базовый класс", "1-я, 20 ур.", "2-я, 40 ур.", "3-я, 76 ур."][c["professionLevel"]]),
              ("Активных умений", str(n_act)), ("Пассивных умений", str(n_pas)), ("SP на умения", fmt(sp_total))]},
]
    path = curl(cid)
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Классы", "/wiki/classes/"), (rn, None)]
    t = clip_title(f'{rn} ({c["name"]}) – умения Interlude')
    d = f'{rn} ({c["name"]}), {prof.lower()}, {race_ru.lower()}: {len(rows)} {plural(len(rows),"умение","умения","умений")} с уровнем изучения, MP, перезарядкой и стоимостью SP.'
    render(path, "entry.html", {"title": t, "description": d},
           [bc_ld(bc), faq_ld(faq)], section="wiki", wsec="classes", bc=bc, icon=CICON[cid], h1=f"{rn}",
           sub=f'{c["name"]} <span>{race_ru}</span> <span>{prof}</span>', intro=intro, sections=secs, faq=faq, side=side,
           portrait=f"/static/media/race-{ru.RACE_SLUG[c['race']]}.jpg" if SITE["has_races"] else None)

# ================= ПРЕДМЕТЫ =================
def item_stats(i):
    p = []
    if i["type"] == "weapon":
        for k, n in (("pAtk", "Физ. атака"), ("mAtk", "Маг. атака"), ("pAtkSpd", "Скорость атаки"), ("rCrit", "Крит"), ("sDef", "Защита щитом"), ("rShld", "Шанс блока"), ("rEvas", "Уклонение")):
            if i.get(k): p.append((n, fmt(i[k]) + ("%" if k == "rShld" else "")))
        if i.get("soulshots"): p.append(("Расход заряда души", str(i["soulshots"])))
        if i.get("spiritshots"): p.append(("Расход заряда духа", str(i["spiritshots"])))
        if i.get("mpConsume"): p.append(("MP за выстрел", str(i["mpConsume"])))
    if i["type"] == "armor":
        for k, n in (("pDef", "Физ. защита"), ("mDef", "Маг. защита")):
            if i.get(k): p.append((n, fmt(i[k])))
    p.append(("Вес", fmt(i["weight"]))) if i.get("weight") else None
    if i.get("crystalCount"): p.append(("Кристаллов при разбивке", fmt(i["crystalCount"])))
    if i.get("price"): p.append(("Цена продажи в магазин", fmt(i["price"] // 2) + " аден"))
    return p

for iid in sorted(PUB):
    i = ITEM[iid]; name = i["name"]; kind = item_kind(i); g = i["grade"]
    gtxt = f"{ru.GRADE_RU[g]}-грейда" if g != "none" else "без грейда"
    secs = []; src_parts = []
    def _uniq(lst):
        best = {}
        for n, r in lst:
            k = (NPC[n]["name"], NPC[n]["level"])
            if k not in best or r[3] > best[k][1][3] or (r[3] == best[k][1][3] and MPRIMARY.get(n) == n): best[k] = (n, r)
        return list(best.values())
    dr = _uniq(DROPPED_BY.get(iid, [])); sp = _uniq(SPOILED_BY.get(iid, []))
    if dr:
        rows = sorted(dr, key=lambda x: -x[1][3])[:60]
        secs.append({"id": "drop", "title": f"Где выбить {name}", "text": "Шанс базовый, из файлов игры. Рейты сервера применяются поверх него.",
                     "html": '<div class="tbl-wrap">' + table(["Монстр", "Ур.>", "Кол-во>", "Шанс>"],
                       [[npc_cell(n, ru.NPC_TYPE_RU.get(NPC[n]["npcType"], "")), str(NPC[n]["level"]), qty(r[1], r[2]), f'<span class="chance">{pct(r[3])}</span>'] for n, r in rows]) + "</div>"})
        best = rows[0]; src_parts.append(f'падает с {len(dr)} {plural(len(dr),"монстра","монстров","монстров")}, чаще всего с {NPC[best[0]]["name"]} ({pct(best[1][3])})')
    if sp:
        rows = sorted(sp, key=lambda x: -x[1][3])[:60]
        secs.append({"id": "spoil", "title": f"Спойл {name}", "text": "Спойл доступен гномам-собирателям и Охотникам за Наградой.",
                     "html": '<div class="tbl-wrap">' + table(["Монстр", "Ур.>", "Кол-во>", "Шанс>"],
                       [[npc_cell(n), str(NPC[n]["level"]), qty(r[1], r[2]), f'<span class="chance spoil">{pct(r[3])}</span>'] for n, r in rows]) + "</div>"})
        src_parts.append(f'спойлится с {len(sp)} {plural(len(sp),"монстра","монстров","монстров")}')
    rc = RECIPE_FOR.get(iid)
    if rc:
        secs.append({"id": "craft", "title": f"Крафт {name}",
                     "text": f'Рецепт: {item_cell(rc["recipeItemId"]) if rc["recipeItemId"] in ITEM else ""} Уровень крафта {rc["level"]}, шанс {rc["successRate"]}%, {fmt(rc["mpConsume"])} MP, на выходе {rc["productCount"]} шт.',
                     "html": '<div class="tbl-wrap">' + table(["Ингредиент", "Нужно>"], [[item_cell(x["itemId"]), fmt(x["count"])] for x in rc["ingredients"]]) + "</div>"})
        src_parts.append(f'крафтится {"гномом" if rc["isDwarven"] else "любой расой"} на {rc["level"]} уровне крафта')
    rb = RECIPE_BY_ITEM.get(iid)
    if rb and rb["productItemId"] in ITEM:
        secs.append({"id": "recipe", "title": "Что создаёт этот рецепт",
                     "html": '<div class="tbl-wrap">' + table(["Результат", "Шанс>", "Ур. крафта>"], [[item_cell(rb["productItemId"]), f'{rb["successRate"]}%', str(rb["level"])]]) + "</div>"})
    if USED_IN.get(iid):
        rows = USED_IN[iid][:40]
        secs.append({"id": "used", "title": f"Где используется {name}",
                     "html": '<div class="tbl-wrap">' + table(["Что крафтится", "Нужно>"], [[item_cell(r["productItemId"]), fmt(next(x["count"] for x in r["ingredients"] if x["itemId"] == iid))] for r in rows if r["productItemId"] in ITEM]) + "</div>"})
    if SOLD.get(iid):
        rows = {}
        for n, pr in SOLD[iid]:
            if n in NPC: rows[n] = pr
        if rows:
            secs.append({"id": "shop", "title": "Продаётся у NPC",
                         "html": '<div class="tbl-wrap">' + table(["NPC", "Цена>"], [[esc(NPC[n]["name"]) + (f' <span class="muted">{esc(NPC[n]["title"])}</span>' if NPC[n].get("title") else ""), (fmt(p) + " аден") if p else "–"] for n, p in list(rows.items())[:20]]) + "</div>"})
            src_parts.append("продаётся в магазине")
    st = SET_OF.get(iid)
    if st:
        pcs = [v for v in st["pieces"].values() if v]
        secs.append({"id": "set", "title": f"Входит в {st['name']}",
                     "html": '<div class="tbl-wrap">' + table(["Часть сета", "Грейд"], [[item_cell(v), gbadge(ITEM[v]["grade"])] for v in pcs if v in ITEM]) + "</div>"})
    if QUEST_REWARD.get(iid):
        secs.append({"id": "quest", "title": "Награда за квест",
                     "html": '<div class="chips">' + "".join(f'<a class="chip" href="{qurl(q["id"])}">{esc(q["name"])}</a>' for q in QUEST_REWARD[iid][:12]) + "</div>"})

    stats = item_stats(i)
    s1 = f"{name} – {kind.lower()} {gtxt} в Lineage 2 Interlude."
    if i["type"] == "weapon" and i.get("pAtk"):
        s1 += f' Физ. атака {fmt(i["pAtk"])}, маг. атака {fmt(i.get("mAtk"))}' + (f', скорость атаки {fmt(i["pAtkSpd"])}' if i.get("pAtkSpd") else "") + "."
    elif i["type"] == "armor" and (i.get("pDef") or i.get("mDef")):
        s1 += (f' Физ. защита {fmt(i["pDef"])}.' if i.get("pDef") else f' Маг. защита {fmt(i["mDef"])}.')
    s2 = (" Где взять: " + "; ".join(src_parts) + ".") if src_parts else " В открытых данных нет монстров, с которых он падает: обычно такие вещи дают за квест, ивент или в обмен у NPC."
    if st: s2 += f' Часть сета <a href="#set">{esc(st["name"])}</a>.'
    path = iurl(iid)
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", "/wiki/items/"), (name, None)]
    tail = {"weapon": f"{kind.lower()} {gtxt}" if g != "none" else kind.lower(), "armor": f"{kind.split(',')[0].lower()} {gtxt}" if g != "none" else kind.split(',')[0].lower()}.get(i["type"], kind.lower())
    t = clip_title(f"{name} – {tail}") if len(f"{name} – {tail}") <= 60 else (clip_title(name + " – Lineage 2") if len(name) <= 45 else name)
    if dr: dd = f'Падает с {len(dr)} {plural(len(dr),"монстра","монстров","монстров")}, лучший шанс у {NPC[sorted(dr, key=lambda x:-x[1][3])[0][0]]["name"]}.'
    elif rc: dd = f'Крафт: {len(rc["ingredients"])} {plural(len(rc["ingredients"]),"ингредиент","ингредиента","ингредиентов")}, шанс {rc["successRate"]}%.'
    elif SOLD.get(iid): dd = "Продаётся у NPC, цена и торговцы на странице."
    else: dd = "Характеристики и откуда берётся."
    statline = ", ".join(f"{k} {v}" for k, v in stats[:3])
    desc = f'{name}: {kind.lower()} {gtxt}. {statline + ". " if statline else ""}{dd}'
    if len(desc) > 165: desc = desc[:162].rsplit(" ", 1)[0] + "…"
    side = [{"title": "Характеристики", "props": [("Тип", kind), ("Грейд", gbadge(g))] + stats, "note": f"ID в игре: {iid}"}]
    variant = PRIMARY.get(iid, iid) != iid
    if variant:
        t = clip_title(f"{name} (вариант {iid})"); desc = f"{name}, вариант с ID {iid}. " + desc
    render(path, "entry.html", {"title": t, "description": desc[:165], "og_type": "article", "noindex": variant, "canonical": iurl(PRIMARY[iid]) if variant else None},
           [bc_ld(bc)], section="wiki", wsec="items", bc=bc, icon=icon(i.get("iconFile")), h1=name,
           sub=f'{gbadge(g)} <span>{kind}</span>', intro=s1 + s2, sections=secs, faq=None, side=side)
    if not variant: SEARCH.append([name, path, icon(i.get("iconFile")), kind.split(",")[0].lower()])

# --- списки предметов ---
def items_table(lst, mode):
    rows = []
    for i in lst:
        if mode == "weapon": rows.append([item_cell(i["id"], item_kind(i)), gbadge(i["grade"]), fmt(i.get("pAtk")), fmt(i.get("mAtk")), fmt(i.get("pAtkSpd")) if i.get("pAtkSpd") else "–", fmt(i.get("weight"))])
        elif mode == "armor": rows.append([item_cell(i["id"], item_kind(i)), gbadge(i["grade"]), fmt(i.get("pDef")) if i.get("pDef") else "–", fmt(i.get("mDef")) if i.get("mDef") else "–", fmt(i.get("weight"))])
        else: rows.append([item_cell(i["id"], item_kind(i)), fmt(len(DROPPED_BY.get(i["id"], [])) + len(SPOILED_BY.get(i["id"], []))), "да" if i["id"] in RECIPE_FOR else "–"])
    head = {"weapon": ["Предмет", "Грейд", "Физ. атака>", "Маг. атака>", "Скорость>", "Вес>"],
            "armor": ["Предмет", "Грейд", "Физ. защита>", "Маг. защита>", "Вес>"],
            "etc": ["Предмет", "Источников дропа>", "Крафт>"]}[mode]
    return table(head, rows)
GORDER = ["s", "a", "b", "c", "d", "none"]
def grade_groups(lst, mode, sort_key):
    out = []
    for g in GORDER:
        gl = sorted([i for i in lst if i["grade"] == g], key=sort_key)
        if gl: out.append({"title": (f"{ru.GRADE_RU[g]}-грейд" if g != "none" else "Без грейда") + f" – {len(gl)}", "id": f"g-{g}", "html": items_table(gl, mode)})
    return out

ITEM_CATS = []  # (path, title, h1, intro, groups, filters_key)
wtypes = collections.OrderedDict((k, ru.WEAPON_RU_PL[k]) for k in ["SWORD", "BIGSWORD", "BLUNT", "BIGBLUNT", "DAGGER", "BOW", "POLE", "DUAL", "DUALFIST", "ETC"])
weapons = [i for i in items if i["type"] == "weapon" and i["id"] in PUB]
wfilters = [(v, f"/wiki/items/weapons/{slug(k)}/") for k, v in wtypes.items()]
for k, v in wtypes.items():
    lst = [i for i in weapons if (i.get("weaponType") == k or (k == "DUALFIST" and i.get("weaponType") == "FIST")) and i["bodypart"] != "lhand"]
    p = f"/wiki/items/weapons/{slug(k)}/"
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", "/wiki/items/"), (v, None)]
    top = max(lst, key=lambda i: i.get("pAtk") or 0)
    render(p, "list.html", {"title": clip_title(f"{v} в Lineage 2 Interlude – все грейды"),
                            "description": f"{v} Interlude: {len(lst)} шт. от без грейда до S. Физ. и маг. атака, скорость и вес в одной таблице, самая сильная – {top['name']}."},
           [bc_ld(bc)], section="wiki", wsec="items", bc=bc, h1=f"{v} Interlude",
           intro=f"{len(lst)} позиций, сгруппированных по грейдам. В каждой строке ссылка на страницу предмета: там дроп, спойл и крафт.",
           filters=[(a, b, b == p) for a, b in wfilters], groups=grade_groups(lst, "weapon", lambda i: -(i.get("pAtk") or 0)), filter_box=True)
ARM = [("Шлемы", "head", ["head"]), ("Верх доспеха", "chest", ["chest"]), ("Цельные доспехи", "fullarmor", ["fullarmor"]),
       ("Низ доспеха", "legs", ["legs"]), ("Перчатки", "gloves", ["gloves"]), ("Ботинки", "boots", ["feet"]), ("Щиты", "shields", ["lhand"])]
afilters = [(a, f"/wiki/items/armor/{b}/") for a, b, _ in ARM]
for title, sl, parts in ARM:
    lst = [i for i in items if i["id"] in PUB and i["bodypart"] in parts and i["type"] in ("armor", "weapon")]
    p = f"/wiki/items/armor/{sl}/"
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", "/wiki/items/"), (title, None)]
    render(p, "list.html", {"title": clip_title(f"{title} Lineage 2 Interlude – защита и грейды"),
                            "description": f"{title} Interlude: {len(lst)} предметов с физ. и маг. защитой и весом по грейдам D, C, B, A и S. По ссылке – где выбить и как скрафтить."},
           [bc_ld(bc)], section="wiki", wsec="items", bc=bc, h1=f"{title} Interlude",
           intro=f"{len(lst)} предметов. Тяжёлая, лёгкая и магическая броня в одной таблице, тип указан под названием.",
           filters=[(a, b, b == p) for a, b in afilters], groups=grade_groups(lst, "armor", lambda i: -((i.get("pDef") or 0) + (i.get("sDef") or 0))), filter_box=True)
jew = [i for i in items if i["id"] in PUB and i["bodypart"] in ("rear;lear", "neck", "rfinger;lfinger")]
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", "/wiki/items/"), ("Бижутерия", None)]
render("/wiki/items/jewelry/", "list.html", {"title": "Бижутерия Lineage 2 Interlude – серьги, кольца | Goldwar",
       "description": f"Серьги, ожерелья и кольца Interlude: {len(jew)} предметов с магической защитой по грейдам. Эпическая бижутерия рейд-боссов тоже здесь."},
       [bc_ld(bc)], section="wiki", wsec="items", bc=bc, h1="Бижутерия Interlude",
       intro="Серьги, ожерелья и кольца дают магическую защиту. Эпические украшения падают только с рейд-боссов – источник указан на странице каждого.",
       filters=None, groups=grade_groups(jew, "armor", lambda i: -(i.get("mDef") or 0)), filter_box=True)
ETC_CATS = [("Материалы", "materials", ["material"]), ("Рецепты", "recipes", ["recipe"]), ("Свитки", "scrolls", ["scroll", "scrl_enchant_wp", "scrl_enchant_am", "bless_scrl_enchant_wp", "bless_scrl_enchant_am"]),
            ("Зелья и эликсиры", "potions", ["potion", "elixir", "herb"]), ("Краски", "dyes", ["dye"]), ("Семена и урожай", "seeds", ["seed", "seed2", "crop", "maturecrop", "harvest"])]
efilters = [(a, f"/wiki/items/{b}/") for a, b, _ in ETC_CATS]
for title, sl, types in ETC_CATS:
    lst = sorted([i for i in items if i["id"] in PUB and i["type"] == "etcitem" and i.get("etcItemType") in types], key=lambda i: i["name"])
    p = f"/wiki/items/{sl}/"
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", "/wiki/items/"), (title, None)]
    render(p, "list.html", {"title": clip_title(f"{title} Lineage 2 Interlude – где взять"),
                            "description": f"{title} Interlude: {len(lst)} позиций. Для каждой – число монстров, с которых она падает, и можно ли её скрафтить."},
           [bc_ld(bc)], section="wiki", wsec="items", bc=bc, h1=f"{title} Interlude",
           intro=f"{len(lst)} позиций. Колонка «Источников дропа» показывает, со скольких монстров предмет падает или спойлится.",
           filters=[(a, b, b == p) for a, b in efilters], groups=[{"title": None, "count": f"{len(lst)} позиций", "id": "all", "html": items_table(lst, "etc")}], filter_box=True)
# сеты
set_rows = []
for st in sorted(sets, key=lambda s: GORDER.index(ITEM.get(s["pieces"].get("chest") or 0, {"grade": "none"})["grade"]) if s["pieces"].get("chest") in ITEM else 9):
    ch = st["pieces"].get("chest"); pcs = [v for v in st["pieces"].values() if v and v in ITEM]
    g = ITEM[ch]["grade"] if ch in ITEM else "none"
    pdef = sum(ITEM[v].get("pDef") or 0 for v in pcs)
    set_rows.append([item_cell(ch, f"{len(pcs)} {plural(len(pcs),'часть','части','частей')}") if ch in ITEM else esc(st["name"]), esc(st["name"]), gbadge(g), fmt(pdef)])
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", "/wiki/items/"), ("Сеты", None)]
render("/wiki/items/sets/", "list.html", {"title": "Сеты брони Lineage 2 Interlude – все грейды | Goldwar",
       "description": f"Все {len(sets)} сетов брони Interlude: тяжёлые, лёгкие и магические, от Wooden до Major Arcana. Суммарная физ. защита и состав каждого сета."},
       [bc_ld(bc)], section="wiki", wsec="sets", bc=bc, h1="Сеты брони Interlude",
       intro=f"{len(sets)} сетов. Физ. защита посчитана по всем частям сета вместе; бонус за полный комплект смотрите на странице верхней части.",
       filters=None, groups=[{"title": None, "count": f"{len(sets)} сетов", "id": "sets", "html": table(["Верх сета", "Сет", "Грейд", "Физ. защита всего>"], set_rows)}], filter_box=True)

# хаб предметов
def pick_icons(pred, n=4):
    out = []
    for i in items:
        if pred(i) and i.get("iconFile") in ICON_OK and i["id"] in PUB: out.append(icon(i["iconFile"]))
        if len(out) >= n: break
    return out
hub = [
    {"title": "Оружие", "href": "/wiki/items/weapons/sword/", "cnt": fmt(len(weapons)), "cls": "wide", "text": "Мечи, луки, кинжалы, парное и двуручное оружие по грейдам: атака, скорость и откуда падает.", "icons": pick_icons(lambda i: i["type"] == "weapon" and i["grade"] == "s", 6)},
    {"title": "Броня", "href": "/wiki/items/armor/chest/", "cnt": fmt(sum(1 for i in items if i["id"] in PUB and i["bodypart"] in ("head","chest","fullarmor","legs","gloves","feet","lhand"))), "cls": "", "text": "Шлемы, доспехи, перчатки, ботинки и щиты.", "icons": pick_icons(lambda i: i["bodypart"] == "chest" and i["grade"] == "a")},
    {"title": "Сеты", "href": "/wiki/items/sets/", "cnt": f"{len(sets)} сетов", "cls": "", "text": "Полные комплекты брони и их состав.", "icons": pick_icons(lambda i: i["bodypart"] == "fullarmor" and i["grade"] == "s")},
    {"title": "Бижутерия", "href": "/wiki/items/jewelry/", "cnt": f"{len(jew)} шт.", "cls": "", "text": "Серьги, кольца, ожерелья и эпическая бижутерия.", "icons": pick_icons(lambda i: i["bodypart"] == "neck" and i["grade"] in ("a", "s"))},
    {"title": "Материалы и рецепты", "href": "/wiki/items/materials/", "cnt": fmt(sum(1 for i in items if i["id"] in PUB and i.get("etcItemType") in ("material","recipe"))), "cls": "", "text": "Всё для крафта: что падает, что крафтится и из чего.", "icons": pick_icons(lambda i: i.get("etcItemType") == "material")},
    {"title": "Свитки и зелья", "href": "/wiki/items/scrolls/", "cnt": fmt(sum(1 for i in items if i["id"] in PUB and i.get("etcItemType") in ("scroll","potion","elixir","herb","scrl_enchant_wp","scrl_enchant_am","bless_scrl_enchant_wp","bless_scrl_enchant_am"))), "cls": "", "text": "Заточка, телепорт, баночки и эликсиры.", "icons": pick_icons(lambda i: i.get("etcItemType") in ("scroll", "potion"))},
]
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Предметы", None)]
render("/wiki/items/", "list.html", {"title": "Предметы Lineage 2 Interlude – оружие, броня | Goldwar",
       "description": f"База предметов Interlude: {fmt(len(PUB))} позиций. Оружие и броня по грейдам, сеты, бижутерия, материалы и рецепты с дропом и крафтом."},
       [bc_ld(bc)], section="wiki", wsec="items", bc=bc, h1="Предметы Interlude",
       intro=f"{fmt(len(PUB))} предметов с характеристиками, дропом, спойлом и крафтом. Выберите раздел или найдите предмет поиском сверху.",
       filters=None, index=[{"title": h["title"], "href": h["href"], "count": re.sub(r"[^0-9\u00a0]", "", h["cnt"]).strip(), "desc": h["text"], "icons": h["icons"][:6]} for h in hub], groups=[], filter_box=False)

# ================= МОНСТРЫ =================
def mob_where(nid):
    z = MOB_ZONE.get(nid); r = MOB_REGION.get(nid)
    if z: return ZONE[z]["name"] + (f", {r}" if r else "")
    return r or "место не указано"
BANDS = [(1, 20), (21, 40), (41, 52), (53, 61), (62, 70), (71, 76), (77, 90)]
def band_path(a, b): return f"/wiki/monsters/{a}-{b}/"
bfilters = [(f"{a}–{b} ур.", band_path(a, b)) for a, b in BANDS]
regular = [n for n in mobs if n["npcType"] == "Monster" and MPRIMARY.get(n["id"], n["id"]) == n["id"]]
for a, b in BANDS:
    lst = sorted([n for n in regular if a <= n["level"] <= b], key=lambda n: (n["level"], n["name"]))
    rows = [[npc_cell(n["id"], mob_where(n["id"])), f'<span class="lvl-pill">{n["level"]}</span>', fmt(round(n["hp"])), fmt(n["exp"]), fmt(n["sp"]),
             "да" if DROP.get(n["id"], ([], []))[1] else "–"] for n in lst]
    p = band_path(a, b)
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Монстры", "/wiki/monsters/"), (f"{a}–{b} уровень", None)]
    render(p, "list.html", {"title": clip_title(f"Монстры {a}–{b} уровня Lineage 2 Interlude"),
                            "description": f"{len(lst)} монстров {a}–{b} уровня: где стоят, HP, опыт и SP, есть ли спойл. Дроп каждого – на его странице."},
           [bc_ld(bc)], section="wiki", wsec="monsters", bc=bc, h1=f"Монстры {a}–{b} уровня",
           intro=f"{len(lst)} монстров. Под названием – зона охоты и ближайший город. Опыт и SP указаны базовые, на сервере их умножает рейт.",
           filters=[(x, y, y == p) for x, y in bfilters], groups=[{"title": None, "count": f"{len(lst)} монстров", "id": "m", "html": table(["Монстр", "Ур.", "HP>", "Опыт>", "SP>", "Спойл>"], rows)}], filter_box=True)
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Монстры", None)]
band_tiles = []
for a, b in BANDS:
    n = sum(1 for x in regular if a <= x["level"] <= b)
    band_tiles.append([f'<a class="it" href="{band_path(a,b)}"><span>Монстры {a}–{b} уровня</span></a>', fmt(n)])
render("/wiki/monsters/", "list.html", {"title": "Монстры Lineage 2 Interlude – дроп, спойл, где стоят | Goldwar",
       "description": f"{fmt(len(regular))} монстров Interlude по уровням: что падает, что спойлится, сколько опыта и где искать. Рейд-боссы – отдельным списком."},
       [bc_ld(bc)], section="wiki", wsec="monsters", bc=bc, h1="Монстры Interlude",
       intro=f'{fmt(len(regular))} обычных монстров разбиты по уровням. Боссы собраны отдельно – в <a href="/wiki/raid-bosses/">списке рейд-боссов</a>.',
       filters=[(x, y, False) for x, y in bfilters], groups=[{"title": None, "count": "Уровни", "id": "b", "html": table(["Диапазон", "Монстров>"], band_tiles)}], filter_box=False)

for n in mobs:
    nid = n["id"]; name = n["name"]; lvl = n["level"]; typ = ru.NPC_TYPE_RU[n["npcType"]]
    reg, sp = DROP.get(nid, ([], []))
    secs = []
    adena = [r for r in reg if r[0] == 57]
    if reg:
        secs.append({"id": "drop", "title": f"Дроп с {name}", "text": "Шансы базовые, из файлов игры; рейты сервера применяются поверх.",
                     "html": '<div class="tbl-wrap">' + table(["Предмет", "Кол-во>", "Шанс>"], [[item_cell(r[0]), qty(r[1], r[2]), f'<span class="chance">{pct(r[3])}</span>'] for r in reg[:80]]) + "</div>"})
    if sp:
        secs.append({"id": "spoil", "title": f"Спойл с {name}",
                     "html": '<div class="tbl-wrap">' + table(["Предмет", "Кол-во>", "Шанс>"], [[item_cell(r[0]), qty(r[1], r[2]), f'<span class="chance spoil">{pct(r[3])}</span>'] for r in sp[:80]]) + "</div>"})
    zid = MOB_ZONE.get(nid)
    if zid:
        neigh = sorted([x for x in ZONE_MOBS[zid] if x != nid and NPC[x]["npcType"] == "Monster"], key=lambda x: NPC[x]["level"])[:16]
        if neigh:
            secs.append({"id": "near", "title": f"Кто ещё живёт в {ZONE[zid]['name']}",
                         "html": '<div class="chips">' + "".join(f'<a class="chip" href="{murl(x)}"><span class="lvl-pill" style="min-width:32px;padding:1px 6px">{NPC[x]["level"]}</span>{esc(NPC[x]["name"])}</a>' for x in neigh) + "</div>"})
    where = mob_where(nid)
    intro = f"{name} – {typ.lower()} {lvl} уровня в Lineage 2 Interlude. "
    intro += (f'Стоит в зоне <a href="{zurl(zid)}">{esc(ZONE[zid]["name"])}</a>' + (f" ({MOB_REGION[nid]})" if MOB_REGION.get(nid) else "") + ". ") if zid else (f"Встречается у {where}. " if MOB_REGION.get(nid) else "")
    intro += f'HP {fmt(round(n["hp"]))}, за убийство {fmt(n["exp"])} опыта и {fmt(n["sp"])} SP без учёта рейтов.'
    if reg: intro += f' С него падает {len(reg)} {plural(len(reg),"предмет","предмета","предметов")}' + (f", спойлится ещё {len(sp)}." if sp else ".")
    side = [{"title": "Параметры", "props": [("Уровень", str(lvl)), ("Тип", typ), ("HP", fmt(round(n["hp"]))), ("MP", fmt(round(n["mp"]))),
             ("Физ. атака", fmt(round(n["pAtk"]))), ("Физ. защита", fmt(round(n["pDef"]))), ("Маг. атака", fmt(round(n["mAtk"]))), ("Маг. защита", fmt(round(n["mDef"]))),
             ("Опыт", fmt(n["exp"])), ("SP", fmt(n["sp"])), ("Агрессивный", "да" if n.get("aiAggro") else "нет")], "note": f"ID в игре: {nid}"}]
    faq = None
    if n["npcType"] != "Monster":
        best = [ITEM[r[0]]["name"] for r in reg if r[0] in ITEM and r[0] != 57][:3]
        faq = [(f"Где найти {name}?", f"{name} появляется {('в зоне ' + ZONE[zid]['name']) if zid else ('в районе ' + where)}. Уровень босса – {lvl}."),
               (f"Что падает с {name}?", (f"С босса падает {len(reg)} {plural(len(reg),'предмет','предмета','предметов')}, среди них " + ", ".join(best) + ".") if best else "Список дропа – в таблице выше."),
               (f"Даёт ли {name} Золотой ключ?", "Золотые ключи на Goldwar выпадают с рейд-боссов. Какие именно боссы их дают, администрация уточняет в Telegram-канале сервера.")]
    path = murl(nid)
    sec_name = "Рейд-боссы" if n["npcType"] != "Monster" else "Монстры"
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), (sec_name, "/wiki/raid-bosses/" if n["npcType"] != "Monster" else "/wiki/monsters/"), (name, None)]
    t = clip_title(f"{name} – {'рейд-босс' if n['npcType']!='Monster' else 'монстр'} {lvl} ур., дроп")
    best_item = next((ITEM[r[0]]["name"] for r in reg if r[0] in ITEM and r[0] != 57), None)
    desc = f"{name}, {typ.lower()} {lvl} уровня" + (f", {ZONE[zid]['name']}" if zid else "") + f". HP {fmt(round(n['hp']))}, {len(reg)} предм. в дропе" + (f", {len(sp)} в спойле" if sp else "") + (f", в том числе {best_item}." if best_item else ".")
    if len(desc) > 165: desc = desc[:162].rsplit(" ", 1)[0] + "…"
    lds = [bc_ld(bc)] + ([faq_ld(faq)] if faq else [])
    mvar = MPRIMARY.get(nid, nid) != nid
    if mvar: t = clip_title(f"{name} {lvl} ур. (ID {nid})"); desc = (f"Вариант ID {nid}. " + desc)[:165]
    _can = murl(MPRIMARY[nid]) if mvar else (f"/npc/{nid}-{slug(GW[nid]['name'])}/" if nid in GW else None)
    render(path, "entry.html", {"title": t, "description": desc, "og_type": "article", "noindex": mvar, "canonical": _can}, lds,
           section="wiki" if n["npcType"] == "Monster" else "raid", wsec="monsters" if n["npcType"] == "Monster" else "raid", bc=bc, icon=None, h1=name,
           sub=f'<span class="lvl-pill">{lvl} ур.</span> <span>{typ}</span> <span>{esc(where)}</span>', intro=intro, sections=secs, faq=faq, side=side)
    if not mvar: SEARCH.append([name, path, None, f"{typ.lower()} {lvl}"])

# рейд-боссы
rbs = sorted([n for n in mobs if n["npcType"] != "Monster" and MPRIMARY.get(n["id"], n["id"]) == n["id"]], key=lambda n: (n["level"], n["name"]))
rows = [[npc_cell(n["id"], mob_where(n["id"])), f'<span class="lvl-pill">{n["level"]}</span>', ru.NPC_TYPE_RU[n["npcType"]], fmt(round(n["hp"])), fmt(len(DROP.get(n["id"], ([], []))[0]))] for n in rbs]
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Рейд-боссы", None)]
render("/wiki/raid-bosses/", "list.html", {"title": "Рейд-боссы Lineage 2 Interlude – где стоят, дроп | Goldwar",
       "description": f"Все {len(rbs)} рейд-боссов и эпических боссов Interlude по уровням: где появляются, сколько HP и что с них падает. С боссов Goldwar идут Золотые ключи."},
       [bc_ld(bc)], section="raid", wsec="raid", bc=bc, h1="Рейд-боссы Interlude",
       intro=f"{len(rbs)} боссов от {rbs[0]['level']} до {rbs[-1]['level']} уровня, включая эпических: Антараса, Валакаса, Баюма и Закена. На Goldwar с рейд-боссов падают Золотые ключи к сундукам.",
       filters=None, groups=[{"title": None, "count": f"{len(rbs)} боссов", "id": "rb", "html": table(["Босс", "Ур.", "Тип", "HP>", "Предметов в дропе>"], rows)}], filter_box=True, art="raid" if SITE["has_raidart"] else None)

# ================= ЗОНЫ =================
zrows = []
for z in sorted(zones, key=lambda z: (z["minLevel"] or 0, z["name"])):
    ms = sorted(ZONE_MOBS.get(z["id"], []), key=lambda x: NPC[x]["level"])
    if not ms: continue
    lv = [NPC[x]["level"] for x in ms]
    reg = region_of(z["x"], z["y"])
    zrows.append([f'<a class="it" href="{zurl(z["id"])}"><span>{esc(z["name"])}<small>{esc(reg or "")}</small></span></a>', f'<span class="lvl-pill">{min(lv)}–{max(lv)}</span>', str(len(ms)),
                  str(sum(1 for x in ms if NPC[x]["npcType"] != "Monster"))])
    rows = [[npc_cell(x), f'<span class="lvl-pill">{NPC[x]["level"]}</span>', ru.NPC_TYPE_RU[NPC[x]["npcType"]], fmt(NPC[x]["exp"]), "да" if DROP.get(x, ([], []))[1] else "–"] for x in ms]
    path = zurl(z["id"]); name = z["name"]
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Зоны охоты", "/wiki/zones/"), (name, None)]
    nb = sum(1 for x in ms if NPC[x]["npcType"] != "Monster")
    intro = f"{name} – зона охоты для персонажей {min(lv)}–{max(lv)} уровня" + (f" рядом с городом {reg}" if reg else "") + f". Здесь {len(ms)} {plural(len(ms),'вид','вида','видов')} монстров" + (f", из них {nb} {plural(nb,'босс','босса','боссов')}" if nb else "") + "."
    spoilers = [x for x in ms if DROP.get(x, ([], []))[1]]
    if spoilers: intro += f" Спойл есть у {len(spoilers)} из них – гномам сюда."
    render(path, "entry.html", {"title": clip_title(f"{name} – зона охоты {min(lv)}–{max(lv)} ур."),
                                "description": f"{name}: {len(ms)} видов монстров {min(lv)}–{max(lv)} уровня" + (f" у {reg}" if reg else "") + ". Опыт, спойл и ссылки на дроп каждого монстра."},
           [bc_ld(bc)], section="wiki", wsec="zones", bc=bc, icon=None, h1=name,
           sub=f'<span class="lvl-pill">{min(lv)}–{max(lv)} ур.</span> <span>{esc(reg or "")}</span>', intro=intro,
           sections=[{"id": "mobs", "title": f"Монстры в {name}", "html": '<div class="tbl-wrap">' + table(["Монстр", "Ур.", "Тип", "Опыт>", "Спойл>"], rows) + "</div>"}],
           faq=None, side=[{"title": "Зона", "props": [("Уровни", f"{min(lv)}–{max(lv)}"), ("Видов монстров", str(len(ms))), ("Боссов", str(nb)), ("Город рядом", esc(reg or "–"))]}])
    SEARCH.append([name, path, None, "зона охоты"])
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Зоны охоты", None)]
render("/wiki/zones/", "list.html", {"title": "Зоны охоты Lineage 2 Interlude по уровням | Goldwar",
       "description": f"{len(zrows)} зон охоты Interlude с уровнями монстров, ближайшим городом и числом боссов. Куда идти качаться на своём уровне."},
       [bc_ld(bc)], section="wiki", wsec="zones", bc=bc, h1="Зоны охоты Interlude",
       intro=f"{len(zrows)} зон, отсортированы по уровню. Уровни посчитаны по монстрам, которые реально стоят в зоне, а не по старым таблицам.",
       filters=None, groups=[{"title": None, "count": f"{len(zrows)} зон", "id": "z", "html": table(["Зона", "Уровни", "Видов монстров>", "Боссов>"], zrows)}], filter_box=True)

# ================= КВЕСТЫ =================
qrows = []
QDUP = collections.Counter(q["name"] for q in quests)
for q in sorted(quests, key=lambda q: (q.get("levelMin") or 0, q["id"])):
    name = q["name"]; path = qurl(q["id"]); rw = q.get("rewards") or {}
    starts = [NPC[x]["name"] for x in q.get("startNpcIds", []) if x in NPC]
    kills = [x for x in q.get("killNpcIds", []) if x in NPC]
    talk = [x for x in q.get("talkNpcIds", []) if x in NPC]
    rw_items = [x for x in rw.get("items") or [] if x["itemId"] in ITEM]
    reward_txt = ", ".join(f'{ITEM[x["itemId"]]["name"]} ×{fmt(x["count"])}' for x in rw_items[:4])
    qrows.append([f'<a class="it" href="{path}"><span>{esc(name)}<small>{esc(", ".join(starts[:1]))}</small></span></a>', f'<span class="lvl-pill">{q.get("levelMin") or "–"}</span>',
                  "да" if q.get("repeatable") else "–", esc(reward_txt) or "–"])
    secs = []
    if rw_items or rw.get("adena") or rw.get("exp"):
        props = [[item_cell(x["itemId"]), fmt(x["count"])] for x in rw_items]
        if rw.get("adena"): props.append(["Адена", fmt(rw["adena"])])
        if rw.get("exp"): props.append(["Опыт", fmt(rw["exp"])])
        if rw.get("sp"): props.append(["SP", fmt(rw["sp"])])
        secs.append({"id": "reward", "title": "Награда", "html": '<div class="tbl-wrap">' + table(["Что", "Сколько>"], props) + "</div>"})
    if kills:
        secs.append({"id": "kill", "title": "Кого нужно убить", "html": '<div class="tbl-wrap">' + table(["Монстр", "Ур."], [[npc_cell(x, mob_where(x) if x in MOB else ""), str(NPC[x]["level"])] for x in kills]) + "</div>"})
    if talk:
        secs.append({"id": "npc", "title": "С кем говорить", "html": '<div class="chips">' + "".join(f'<span class="chip" style="padding-left:12px">{esc(NPC[x]["name"])}</span>' for x in talk) + "</div>"})
    qn = qnames.get(str(q["id"]))
    if qn and qn.get("steps"):
        steps = "".join(f'<details><summary>{k+1}. {esc(s.get("title") or "")}</summary><p>{esc((s.get("description") or "").replace(chr(92)+"n"," "))}</p></details>' for k, s in enumerate(qn["steps"]))
        secs.append({"id": "steps", "title": "Шаги квеста", "text": "Текст шагов из английского клиента. Русский перевод подставим из клиента сервера.", "html": f'<div class="faq">{steps}</div>'})
    intro = f"{name} – {'повторяемый ' if q.get('repeatable') else ''}квест Lineage 2 Interlude с {q.get('levelMin') or 1} уровня."
    if starts: intro += f" Берётся у NPC {starts[0]}."
    if kills: intro += f" По ходу нужно убить {len(kills)} {plural(len(kills),'вид','вида','видов')} монстров."
    if reward_txt: intro += f" Награда: {reward_txt}."
    bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Квесты", "/wiki/quests/"), (name, None)]
    _qt = f"Квест {name} – прохождение, награда" if QDUP[name] == 1 else f"Квест {name} – {starts[0] if starts else q['id']}"
    render(path, "entry.html", {"title": clip_title(_qt),
                                "description": (f"Квест {name} с {q.get('levelMin') or 1} уровня" + (f", NPC {starts[0]}" if starts else "") + (f". Награда: {reward_txt}" if reward_txt else "") + ". Кого убить и с кем говорить.")[:165]},
           [bc_ld(bc)], section="wiki", wsec="quests", bc=bc, icon=icon(ITEM[rw_items[0]["itemId"]]["iconFile"]) if rw_items else None, h1=f"Квест {name}",
           sub=f'<span class="lvl-pill">с {q.get("levelMin") or 1} ур.</span>' + (" <span>повторяемый</span>" if q.get("repeatable") else ""), intro=intro, sections=secs, faq=None,
           side=[{"title": "Квест", "props": [("Уровень", str(q.get("levelMin") or 1)), ("Повторяемый", "да" if q.get("repeatable") else "нет"), ("Стартовый NPC", esc(starts[0]) if starts else "–"), ("NPC по ходу", str(len(talk))), ("Монстров убить", str(len(kills)))]}])
    SEARCH.append([name, path, None, "квест"])
bc = [("Goldwar", "/"), ("База знаний", "/wiki/"), ("Квесты", None)]
render("/wiki/quests/", "list.html", {"title": "Квесты Lineage 2 Interlude по уровням | Goldwar",
       "description": f"{len(quests)} квестов Interlude: с какого уровня, у кого взять, кого убить и что дают в награду. Повторяемые квесты отмечены."},
       [bc_ld(bc)], section="wiki", wsec="quests", bc=bc, h1="Квесты Interlude",
       intro=f"{len(quests)} квестов от первого уровня до эпических. Под названием – NPC, у которого квест берётся.",
       filters=None, groups=[{"title": None, "count": f"{len(quests)} квестов", "id": "q", "html": table(["Квест", "С ур.", "Повтор>", "Награда"], qrows)}], filter_box=True)

# ================= РАЗДЕЛ СЕРВЕРА: боссы, эпики, дроп (по файлам Goldwar) =================
GW_SNAV = [{"key": "bosses", "title": "Рейд-боссы", "href": "/bosses/"}, {"key": "epic", "title": "Эпик-боссы", "href": "/epic/"},
           {"key": "drop", "title": "Монстры и дроп", "href": "/drop/"}, {"key": "items", "title": "Где выбить предмет", "href": "/drop/items/"}]
GW_SEARCH = []
UNKNOWN_ITEMS = set()
def gw_url(nid): return f"/npc/{nid}-{slug(GW[nid]['name'])}/"
def gw_dname(nid):
    n = GW[nid]["name"]
    return n + " (Goldwar)" if nid >= 50000 and sum(1 for g in GW.values() if g["name"] == n) > 1 else n
# имена предметов из клиента сервера (ItemName)
CNAME = {}
for _l in open(os.path.join(HERE, "data/itemname.txt"), encoding="utf-8", errors="replace"):
    _p = _l.rstrip("\r\n").split("\t")
    if len(_p) < 4 or not _p[0].isdigit(): continue
    _nm = _p[1].split("*")[0].strip(); _add = _p[2].strip()
    _d = _p[3][2:] if _p[3].startswith("a,") else _p[3]
    _d = _d.replace("\\0", "").replace("\\n", " ").strip()
    if _nm: CNAME[int(_p[0])] = (_nm, _add, _d)
_NAMEIDX = {}
for _i in ITEM.values(): _NAMEIDX.setdefault(_i["name"].lower(), _i)
def gw_custom_item(iid):
    if iid not in CNAME: return iid not in ITEM
    return iid not in ITEM or CNAME[iid][0].lower() != ITEM[iid]["name"].lower().split(" - ")[0] and CNAME[iid][0].lower() != ITEM[iid]["name"].lower()
def gw_i(iid): return None if gw_custom_item(iid) else ITEM.get(iid)
def gw_iname(iid):
    if iid in CNAME and gw_custom_item(iid):
        n, a, _ = CNAME[iid]
        n = n[:1].upper() + n[1:]
        return f"{n} ({a})" if a else n
    if iid in ITEM: return ITEM[iid]["name"]
    UNKNOWN_ITEMS.add(iid); return f"Предмет #{iid}"
_CICON = (("shield", "shield_imperial_crusader_shield_i00.png"), ("earring", "Accessory_tateossian_earring_i00.png"),
          ("necklace", "Accessory_tateossian_necklace_i00.png"), ("ring of", "Accessory_tateossian_ring_i00.png"),
          ("crown", "etc_ancient_crown_i02.png"), ("box", "etc_treasure_box_i06.png"), ("bow", "weapon_shyid_bow_i00.png"),
          ("fan", "weapon_arcana_mace_i00.png"), ("knife", "weapon_angel_slayer_i00.png"), ("trident", "weapon_saint_spear_i00.png"),
          ("dreadbane", "weapon_halbard_i00.png"), ("cudgel", "weapon_basalt_battlehammer_i00.png"),
          ("sword", "weapon_sword_of_valhalla_i00.png"), ("blade", "weapon_forgotten_blade_i00.png"))
def gw_icon(iid):
    i = gw_i(iid)
    if i: return i.get("iconFile")
    if iid not in CNAME: return None
    _jw = "jewel_" + CNAME[iid][0].split()[-1].lower() + ".png"
    if gw_ckind(iid) in ("серьга", "кольцо", "ожерелье") and os.path.exists(os.path.join(CUSTOM_ICONS, _jw)): return _jw
    if CNAME[iid][1].lower() == "goldwar" and gw_ckind(iid) in ("оружие", "щит"): return "goldwar_weapon.png"
    j = _NAMEIDX.get(CNAME[iid][0].lower())
    if j and j.get("iconFile") and "monster" not in j["iconFile"]: return j["iconFile"]
    n = CNAME[iid][0].lower()
    for k, f in _CICON:
        if k in n: return f
    return None
def gi_url(iid): return f"/drop/item/{iid}-{slug(gw_iname(iid))}/"
def gw_ckind(iid):
    n = CNAME.get(iid, ("", "", ""))
    t = (n[0] + " " + n[2]).lower()
    for k, v in (("shield", "щит"), ("earring", "серьга"), ("ring of", "кольцо"), ("necklace", "ожерелье"), ("crown", "корона"),
                 ("box", "сундук"), ("weapon", "оружие"), ("bow", "оружие"), ("sword", "оружие"), ("edge", "оружие")):
        if k in t: return v
    return "предмет сервера"
_EFF = (("critical attack", "крит"), ("atk. speed", "скорость атаки"), ("casting speed", "скорость каста"), ("accuracy", "точность"),
        ("evasion", "уклонение"), ("maximum hp", "HP"), ("critical damage", "крит. урон"))
def gw_eff(iid):
    d = CNAME.get(iid, ("", "", ""))[2].lower()
    hits = sorted((d.find(k), v) for k, v in _EFF if k in d)
    return " + ".join(v for _, v in hits[:2])
def gw_item_cell(iid, extra=""):
    i = gw_i(iid); ic = icon(gw_icon(iid))
    g = f' {gbadge(i["grade"])}' if i and i["grade"] != "none" else ""
    tip = f' data-i="{iid}"' if iid in PUB and i else ""
    return f'<a class="it" href="{gi_url(iid)}"{tip}><img src="/static/i/{ic}" alt="" width="32" height="32" loading="lazy"><span>{esc(gw_iname(iid))}{g}{("<small>"+extra+"</small>") if extra else ""}</span></a>'
def gw_npc_cell(nid, extra=""):
    return f'<a class="it" href="{gw_url(nid)}"><span>{esc(gw_dname(nid))}{("<small>"+esc(extra)+"</small>") if extra else ""}</span></a>'
GW_TYPE = {"Monster": "Монстр", "RaidBoss": "Рейд-босс", "GrandBoss": "Эпик-босс"}
def gw_place(nid):
    z, r = gw_where(nid)
    return ", ".join(x for x in (z, r) if x) or ""
def gw_common(**kw):
    return dict(section=kw.pop("section"), wsec=kw.pop("wsec"), snav=GW_SNAV, sindex="/static/gw-search.json", splace="Босс, монстр или предмет…", **kw)

# одинаковые NPC (имя + уровень) – одна каноническая страница
_gg = collections.defaultdict(list)
for k_, g_ in GW.items(): _gg[(g_["name"], g_["level"], tuple(g_["drop"]), tuple(g_["spoil"]))].append(k_)
GW_PRIMARY = {}
for _ids in _gg.values():
    _p = min(_ids, key=lambda x: (0 if GW_SPAWN.get(x) else 1, x))
    for x in _ids: GW_PRIMARY[x] = _p
# страницы NPC
_namecount = collections.Counter(g_["name"] for g_ in GW.values() if GW_PRIMARY.get(g_["id"], g_["id"]) == g_["id"])
for nid, g in GW.items():
    name, lvl, typ = g["name"], g["level"], GW_TYPE[g["type"]]
    if gw_custom(nid) and _namecount[name] > 1: name = f"{name} (Goldwar)"
    place = gw_place(nid)
    secs = []
    if g["drop"]:
        secs.append({"id": "drop", "title": f"Дроп с {name}", "text": "Шансы из файлов сервера Goldwar.",
                     "html": '<div class="tbl-wrap">' + table(["Предмет", "Кол-во>", "Шанс>"], [[gw_item_cell(r[0]), qty(r[1], r[2]), f'<span class="chance">{pct(r[3])}</span>'] for r in g["drop"]]) + "</div>"})
    if g["spoil"]:
        secs.append({"id": "spoil", "title": f"Спойл с {name}",
                     "html": '<div class="tbl-wrap">' + table(["Предмет", "Кол-во>", "Шанс>"], [[gw_item_cell(r[0]), qty(r[1], r[2]), f'<span class="chance spoil">{pct(r[3])}</span>'] for r in g["spoil"]]) + "</div>"})
    if g["minions"]:
        secs.append({"id": "minions", "title": "Свита", "text": "Появляется вместе с боссом.",
                     "html": '<div class="chips">' + "".join(f'<span class="chip" style="padding-left:12px">{esc(GW_NAMES.get(m, "#"+str(m)))} ×{a if a == b else f"{a}–{b}"}</span>' for m, a, b in g["minions"]) + "</div>"})
    best = [gw_iname(r[0]) for r in g["drop"] if r[0] != 57][:3]
    intro = f"{name} – {typ.lower()} {lvl} уровня на сервере Goldwar." + (f" Место: {place}." if place else "")
    intro += f" HP {fmt(round(g['hp']))}" + (f", за убийство {fmt(g['exp'])} опыта и {fmt(g['sp'])} SP" if g["exp"] else "") + "."
    if g["drop"]: intro += f" В дропе {len(g['drop'])} {plural(len(g['drop']),'позиция','позиции','позиций')}" + (f", главное – {', '.join(best)}" if best else "") + "."
    if g["minions"]: intro += f" Ходит со свитой из {sum(m[2] for m in g['minions'])} существ."
    faq = None
    if g["type"] != "Monster":
        faq = [(f"Где найти {name}?", f"{name} появляется {('в локации ' + place) if place else 'в своей локации'}. Уровень – {lvl}."),
               (f"Что падает с {name} на Goldwar?", (f"Главное в дропе: {', '.join(best)}. Полный список с шансами – в таблице на этой странице." if best else "Полный список с шансами – в таблице на этой странице.")),
               (f"Сколько HP у {name}?", f"{fmt(round(g['hp']))} HP, физ. защита {fmt(round(g['pDef']))}, маг. защита {fmt(round(g['mDef']))}.")]
    side = [{"title": "Параметры", "props": [("Уровень", str(lvl)), ("Тип", typ), ("HP", fmt(round(g["hp"]))), ("MP", fmt(round(g["mp"]))),
             ("Физ. атака", fmt(round(g["pAtk"]))), ("Физ. защита", fmt(round(g["pDef"]))), ("Маг. атака", fmt(round(g["mAtk"]))), ("Маг. защита", fmt(round(g["mDef"]))),
             ("Опыт", fmt(g["exp"])), ("SP", fmt(g["sp"])), ("Агрессивный", "да" if g["aggro"] else "нет")], "note": f"ID на сервере: {nid}"}]
    sec_t, sec_u, wsec = {"RaidBoss": ("Рейд-боссы", "/bosses/", "bosses"), "GrandBoss": ("Эпик-боссы", "/epic/", "epic"), "Monster": ("Монстры и дроп", "/drop/", "drop")}[g["type"]]
    bc = [("Goldwar", "/"), (sec_t, sec_u), (name, None)]
    tl = {"RaidBoss": "рейд-босс", "GrandBoss": "эпик-босс", "Monster": "монстр"}[g["type"]]
    t = f"{name} – {tl} {lvl} ур., дроп на Goldwar"
    if len(t) > 60: t = clip_title(f"{name} – {tl}, дроп")
    desc = (f"{name}, {tl} {lvl} уровня на Goldwar" + (f" ({place})" if place else "") + f". HP {fmt(round(g['hp']))}, {len(g['drop'])} {plural(len(g['drop']),'позиция','позиции','позиций')} в дропе" + (f", {len(g['spoil'])} в спойле" if g["spoil"] else "") + (f": {', '.join(best[:2])}." if best else "."))[:165]
    _var = GW_PRIMARY[nid] != nid
    if _var: t = clip_title(f"{name} {lvl} ур. (ID {nid})"); desc = (f"Вариант ID {nid}. " + desc)[:165]
    render(gw_url(nid), "entry.html", {"title": t, "description": desc, "og_type": "article", "noindex": _var, "canonical": gw_url(GW_PRIMARY[nid]) if _var else None}, [bc_ld(bc)] + ([faq_ld(faq)] if faq else []),
           bc=bc, icon=None, h1=name, sub=f'<span class="lvl-pill">{lvl} ур.</span> <span>{typ}</span>' + (f' <span>{esc(place)}</span>' if place else ""),
           intro=intro, sections=secs, faq=faq, side=side, art="raid" if g["type"] != "Monster" and ARTS.get("raid") else ("monsters" if ARTS.get("monsters") else None),
           **gw_common(section="bosses" if g["type"] == "RaidBoss" else ("epic" if g["type"] == "GrandBoss" else "drop"), wsec=wsec))
    if not _var: GW_SEARCH.append([name, gw_url(nid), None, f"{tl} {lvl}"])

def gw_list(kind):
    return sorted([g for g in GW.values() if g["type"] == kind and GW_PRIMARY[g["id"]] == g["id"]], key=lambda g: (g["level"], g["name"]))
for kind, path, h1, wsec, tl in (("RaidBoss", "/bosses/", "Рейд-боссы Goldwar", "bosses", "рейд-боссов"), ("GrandBoss", "/epic/", "Эпик-боссы Goldwar", "epic", "эпик-боссов")):
    lst = gw_list(kind)
    rows = [[gw_npc_cell(g["id"], gw_place(g["id"])), f'<span class="lvl-pill">{g["level"]}</span>', fmt(round(g["hp"])), str(len(g["drop"])), str(sum(m[2] for m in g["minions"])) if g["minions"] else "–"] for g in lst]
    bc = [("Goldwar", "/"), (h1.replace(" Goldwar", ""), None)]
    if kind == "RaidBoss":
        meta = {"title": "Рейд-боссы Goldwar x50 – дроп, уровни, места",
                "description": f"Все {len(lst)} рейд-боссов сервера Goldwar от {lst[0]['level']} до {lst[-1]['level']} уровня: где стоят, HP, свита и полный дроп с шансами из файлов сервера."}
        intro = f"{len(lst)} {plural(len(lst),'босс','босса','боссов')} от {lst[0]['level']} до {lst[-1]['level']} уровня, включая собственных боссов сервера. С рейд-боссов падают Золотые ключи к сундукам. Дроп и шансы – из файлов сервера."
    else:
        meta = {"title": "Эпик-боссы Goldwar x50 – Антарас, Валакас, Баюм",
                "description": f"{len(lst)} эпик-боссов Goldwar: Queen Ant, Core, Orfen, Zaken, Baium, Antharas, Valakas. Уровень, HP, свита и полный дроп с шансами."}
        intro = f"{len(lst)} эпических боссов – главные цели кланов. У каждого: уровень, HP, свита и дроп с шансами из файлов сервера Goldwar."
    render(path, "list.html", meta, [bc_ld(bc)], bc=bc, h1=h1, intro=intro, filters=None,
           groups=[{"title": None, "count": f"{len(lst)} {tl}", "id": "l", "html": table(["Босс", "Ур.", "HP>", "Предметов в дропе>", "Свита>"], rows)}],
           filter_box=True, art="raid" if ARTS.get("raid") else None, **gw_common(section=wsec, wsec=wsec))

GBANDS = [(1, 20), (21, 40), (41, 60), (61, 70), (71, 75), (76, 80)]
mons = gw_list("Monster")
bands = [(a, b, [g for g in mons if a <= g["level"] <= b]) for a, b in GBANDS]
bands = [x for x in bands if x[2]]
bf = [(f"{a}–{b} ур.", f"/drop/{a}-{b}/") for a, b, _ in bands]
for a, b, lst in bands:
    p = f"/drop/{a}-{b}/"
    rows = [[gw_npc_cell(g["id"], gw_place(g["id"])), f'<span class="lvl-pill">{g["level"]}</span>', fmt(round(g["hp"])), fmt(g["exp"]), str(len(g["drop"])), "да" if g["spoil"] else "–"] for g in lst]
    bc = [("Goldwar", "/"), ("Монстры и дроп", "/drop/"), (f"{a}–{b} уровень", None)]
    render(p, "list.html", {"title": clip_title(f"Монстры {a}–{b} уровня на Goldwar – дроп"),
           "description": f"{len(lst)} монстров {a}–{b} уровня с дропом на сервере Goldwar: где стоят, HP, опыт, сколько позиций в дропе и есть ли спойл."},
           [bc_ld(bc)], bc=bc, h1=f"Монстры {a}–{b} уровня", intro=f"{len(lst)} монстров, у которых на Goldwar включён дроп. Под названием – локация.",
           filters=[(x, y, y == p) for x, y in bf], groups=[{"title": None, "count": f"{len(lst)} монстров", "id": "m", "html": table(["Монстр", "Ур.", "HP>", "Опыт>", "Дроп>", "Спойл>"], rows)}],
           filter_box=True, art="monsters" if ARTS.get("monsters") else None, **gw_common(section="drop", wsec="drop"))
bc = [("Goldwar", "/"), ("Монстры и дроп", None)]
render("/drop/", "list.html", {"title": "Монстры и дроп Goldwar x50 – где фармить",
       "description": f"{len(mons)} монстров с дропом на сервере Goldwar по уровням. Что падает, где стоят, сколько опыта. Поиск предмета по дропу."},
       [bc_ld(bc)], bc=bc, h1="Монстры и дроп", intro=f"На Goldwar дроп включён у {len(mons)} {plural(len(mons),'монстра','монстров','монстров')}. Выберите уровень или найдите предмет – покажем, кто его роняет.",
       filters=[(x, y, False) for x, y in bf] + [("Где выбить предмет", "/drop/items/", False)],
       groups=[{"title": None, "count": "Уровни", "id": "b", "html": table(["Диапазон", "Монстров>"], [[f'<a class="it" href="/drop/{a}-{b}/"><span>Монстры {a}–{b} уровня</span></a>', str(len(l))] for a, b, l in bands])}],
       filter_box=False, art="monsters" if ARTS.get("monsters") else None, **gw_common(section="drop", wsec="drop"))

# где выбить предмет
irows = []
_inames = collections.Counter(gw_iname(x) for x in GW_ITEM)
for iid, src in sorted(GW_ITEM.items(), key=lambda kv: gw_iname(kv[0])):
    if iid == 57: continue
    nm = gw_iname(iid)
    best = {}
    for nid, r, sp in src:
        nid = GW_PRIMARY[nid]
        k = (nid, sp)
        if k not in best or r[3] > best[k][1][3]: best[k] = (nid, r, sp)
    src = sorted(best.values(), key=lambda x: -x[1][3])
    rows = [[gw_npc_cell(n, GW_TYPE[GW[n]["type"]] + (", спойл" if sp else "")), f'<span class="lvl-pill">{GW[n]["level"]}</span>', qty(r[1], r[2]), f'<span class="chance{" spoil" if sp else ""}">{pct(r[3])}</span>'] for n, r, sp in src]
    top = src[0]
    p = gi_url(iid)
    i = gw_i(iid)
    cdesc = CNAME[iid][2] if iid in CNAME and not i else ""
    kind = item_kind(i).lower() if i else "предмет"
    bc = [("Goldwar", "/"), ("Где выбить предмет", "/drop/items/"), (nm, None)]
    intro = f"{nm} на сервере Goldwar падает с {len(src)} {plural(len(src),'источника','источников','источников')}. Лучший шанс – {pct(top[1][3])} у {GW[top[0]]['name']} ({GW[top[0]]['level']} ур.)."
    if not i: kind = gw_ckind(iid)
    tnm = nm if _inames[nm] < 2 else f"{nm} ({kind})" if i else f"{nm}, {gw_eff(iid)}" if gw_eff(iid) else f"{nm} #{iid}"
    if _inames[nm] > 1 and sum(1 for x in GW_ITEM if gw_iname(x) == nm and ITEM.get(x) and item_kind(ITEM[x]).lower() == kind) > 1: tnm = f"{nm} #{iid}"
    render(p, "entry.html", {"title": f"Где выбить {tnm} – дроп Goldwar" if len(tnm) < 36 else f"Где выбить {tnm}"[:70],
           "description": f"{nm}: {len(src)} {plural(len(src),'источник','источника','источников')} дропа на Goldwar. Лучший шанс {pct(top[1][3])} у {GW[top[0]]['name']}, {GW[top[0]]['level']} ур."[:165]},
           [bc_ld(bc)], bc=bc, icon=icon(gw_icon(iid)), h1=f"Где выбить {tnm if not i else nm}", sub=(gbadge(i["grade"]) + f" <span>{item_kind(i)}</span>") if i else f"<span>{gw_ckind(iid).capitalize()}</span>",
           intro=intro, sections=[{"id": "src", "title": "Кто роняет", "text": "Шансы из файлов сервера Goldwar.", "html": '<div class="tbl-wrap">' + table(["Источник", "Ур.", "Кол-во>", "Шанс>"], rows) + "</div>"}] + ([{"id": "about", "title": "Свойства предмета", "text": "Описание из клиента Goldwar.", "html": f'<p lang="en">{esc(cdesc)}</p>'}] if cdesc else []),
           faq=None, side=[{"title": "Предмет", "props": ([("Тип", item_kind(i)), ("Грейд", gbadge(i["grade"]))] + item_stats(i)[:6]) if i else [("Тип", gw_ckind(iid).capitalize()), ("ID", str(iid))]}],
           art="items" if ARTS.get("items") else None, **gw_common(section="drop", wsec="items"))
    irows.append([gw_item_cell(iid, kind), str(len(src)), f'<span class="chance">{pct(top[1][3])}</span>'])
    GW_SEARCH.append([nm, p, icon(gw_icon(iid)) if gw_icon(iid) in ICON_OK else None, "дроп"])
bc = [("Goldwar", "/"), ("Где выбить предмет", None)]
render("/drop/items/", "list.html", {"title": "Где выбить предмет на Goldwar – дроп с монстров",
       "description": f"{len(irows)} предметов, которые падают с монстров и боссов Goldwar. Для каждого: сколько источников и лучший шанс по файлам сервера."},
       [bc_ld(bc)], bc=bc, h1="Где выбить предмет", intro=f"{len(irows)} предметов из дропа сервера. Откройте предмет – увидите всех, кто его роняет, с шансами.",
       filters=None, groups=[{"title": None, "count": f"{len(irows)} предметов", "id": "i", "html": table(["Предмет", "Источников>", "Лучший шанс>"], irows)}],
       filter_box=True, art="items" if ARTS.get("items") else None, **gw_common(section="drop", wsec="items"))
print("goldwar npcs", len(GW), "items", len(irows), "unknown items", sorted(UNKNOWN_ITEMS))


# ================= ОБЗОР ВИКИ, ГЛАВНАЯ =================
stats = {"classes": len(classes), "skills_fmt": fmt(len(SKILL)), "items_fmt": fmt(len(PUB)), "monsters_fmt": fmt(len(regular)),
         "raid": len(rbs), "zones": len(zrows), "quests": len(quests), "sets": len(sets)}
tiles = [
    {"title": "Классы и умения", "href": "/wiki/classes/", "cnt": f"{len(classes)} классов", "cls": "wide", "text": "Все профессии пяти рас, умения по уровням, MP, перезарядка и стоимость SP.", "icons": [CICON[x] for x in (88, 92, 94, 97, 100, 107, 113, 118)]},
    {"title": "Предметы", "href": "/wiki/items/weapons/sword/", "cnt": f"{fmt(len(PUB))} шт.", "cls": "", "text": "Оружие, броня, бижутерия, материалы и рецепты.", "icons": pick_icons(lambda i: i["type"] == "weapon" and i["grade"] == "s")},
    {"title": "Монстры", "href": "/wiki/monsters/", "cnt": f"{fmt(len(regular))}", "cls": "half", "text": "Дроп, спойл, HP и опыт. Разбиты по уровням.", "icons": pick_icons(lambda i: i.get("etcItemType") == "material", 5)},
    {"title": "Рейд-боссы", "href": "/wiki/raid-bosses/", "cnt": f"{len(rbs)} боссов", "cls": "half", "text": "Источник Золотых ключей. Где стоят и что роняют.", "icons": pick_icons(lambda i: i["bodypart"] in ("neck", "rear;lear", "rfinger;lfinger") and i["grade"] == "a", 5)},
    {"title": "Зоны охоты", "href": "/wiki/zones/", "cnt": f"{len(zrows)} зон", "cls": "", "text": "Куда идти на своём уровне.", "icons": []},
    {"title": "Квесты", "href": "/wiki/quests/", "cnt": f"{len(quests)}", "cls": "", "text": "Награды, NPC и монстры по каждому квесту.", "icons": []},
    {"title": "Сеты брони", "href": "/wiki/items/sets/", "cnt": f"{len(sets)}", "cls": "", "text": "Полные комплекты и их защита.", "icons": pick_icons(lambda i: i["bodypart"] == "fullarmor" and i["grade"] == "s", 3)},
]
bc = [("Goldwar", "/"), ("База знаний", None)]
render("/wiki/", "wiki_home.html", {"title": "База знаний Lineage 2 Interlude – Goldwar Wiki",
       "description": f"Классы, {fmt(len(SKILL))} умений, {fmt(len(PUB))} предметов, {fmt(len(regular))} монстров с дропом и спойлом, рейд-боссы, зоны и квесты Interlude."},
       [bc_ld(bc), {"@context": "https://schema.org", "@type": "WebSite", "name": "Goldwar Wiki", "url": BASE + "/wiki/",
                    "potentialAction": {"@type": "SearchAction", "target": BASE + "/wiki/?q={search_term_string}", "query-input": "required name=search_term_string"}}],
       section="wiki", wsec="home", stats=stats, index=[{"title": t["title"], "href": t["href"], "count": re.sub(r"[^0-9\u00a0]", "", t["cnt"]).strip(), "desc": t["text"], "icons": t["icons"][:6]} for t in tiles])

boss_pick = []
_ep = sorted([g for g in GW.values() if g["type"] == "GrandBoss"], key=lambda g: g["level"])
_cr = sorted([g for g in GW.values() if g["type"] == "RaidBoss" and g["id"] >= 90000], key=lambda g: -g["level"])
for g in ([x for x in _ep if x["name"] in ("Queen Ant", "Zaken", "Baium", "Antharas")] + _cr[:4]):
    boss_pick.append({"name": gw_dname(g["id"]), "level": g["level"], "url": gw_url(g["id"]), "where": gw_place(g["id"]) or GW_TYPE[g["type"]]})
stats["raid"] = sum(1 for g in GW.values() if g["type"] == "RaidBoss")
GW_INDEX = [
    {"title": "Рейд-боссы", "href": "/bosses/", "count": str(stats["raid"]), "desc": "Источник Золотых ключей: где стоят, свита и дроп с шансами сервера", "icons": pick_icons(lambda i: i["bodypart"] in ("neck", "rear;lear", "rfinger;lfinger") and i["grade"] == "a", 6)},
    {"title": "Эпик-боссы", "href": "/epic/", "count": str(len(_ep)), "desc": "Queen Ant, Core, Orfen, Zaken, Baium, Antharas, Valakas", "icons": pick_icons(lambda i: i["bodypart"] in ("neck", "rear;lear", "rfinger;lfinger") and i["grade"] == "s", 6)},
    {"title": "Монстры и дроп", "href": "/drop/", "count": str(len(mons)), "desc": "Где фармить на своём уровне и что падает", "icons": pick_icons(lambda i: i.get("etcItemType") == "material", 6)},
    {"title": "Где выбить предмет", "href": "/drop/items/", "count": str(len(irows)), "desc": "Найдите предмет – покажем всех, кто его роняет", "icons": pick_icons(lambda i: i["type"] == "weapon" and i["grade"] == "s", 6)},
]
render("/", "home.html", {"title": "Goldwar – сервер Lineage 2 Interlude x50",
       "description": "Goldwar – сервер Lineage 2 Interlude x50 с PvP-концепцией и Золотыми сундуками. Регистрация за минуту, клиент одним архивом, база знаний по игре.",
       "og_title": "Goldwar x50 – Lineage 2 Interlude"},
       [{"@context": "https://schema.org", "@type": "VideoGame", "name": "Goldwar", "url": BASE + "/", "genre": "MMORPG", "gamePlatform": "PC",
         "description": "Сервер Lineage 2 на хрониках Interlude с рейтами x50.", "inLanguage": ["ru", "en", "es", "el"]},
        {"@context": "https://schema.org", "@type": "Organization", "name": "Goldwar", "url": BASE + "/", "sameAs": [s["href"] for s in SITE["socials"]]}],
       section="home", stats=stats, bosses=boss_pick, index=GW_INDEX, coin_icon=icon("etc_coins_gold_i00.png"),
       chest_icons=[icon("etc_box_of_adventure_5_i00.png"), icon("etc_key_i00.png"), icon("etc_coins_gold_i00.png")],
       kb_icons={"classes": [CICON[x] for x in (88, 94, 100, 113)], "items": pick_icons(lambda i: i["type"] == "weapon" and i["grade"] == "s")})

# служебные страницы
simple = {
 "/files/": ("Скачать клиент Goldwar", "Полный клиент Interlude одним архивом и порядок установки.",
   "<h2 style='font-size:2rem;margin-bottom:16px'>Установка</h2><ol style='color:var(--text-2);line-height:1.9'><li>Скачайте архив клиента.</li><li>Распакуйте его в папку без кириллицы в пути, например C:\\Games\\Goldwar.</li><li>Запустите system\\l2.exe и войдите с логином и паролем от аккаунта на acp.goldwar.net.</li></ol><p class='muted' style='margin-top:24px'>Ссылку на архив и требования к компьютеру добавит администрация сервера.</p>", True),
 "/support/": ("Поддержка Goldwar", "Вопросы по аккаунту, донату и игре решаются в Telegram и Discord.",
   "<p style='color:var(--text-2)'>Быстрее всего администрация отвечает в чате Telegram. Для ивентов и спорных ситуаций приложите скриншот.</p><div class='socials' style='margin-top:24px'>" + "".join(f"<a href='{s['href']}' target='_blank' rel='noopener'>{s['icon']}{s['title']}</a>" for s in SITE["socials"]) + "</div>", False),
 "/privacy/": ("Политика конфиденциальности", "Текст переносится со старого сайта goldwar.net.", "<p class='muted'>Текст переносится со старого сайта.</p>", True),
 "/terms/": ("Пользовательское соглашение", "Текст переносится со старого сайта goldwar.net.", "<p class='muted'>Текст переносится со старого сайта.</p>", True),
}
for p, (h, intro, body, noidx) in simple.items():
    render(p, "page.html", {"title": f"{h} | Goldwar" if len(h) < 50 else h, "description": f"{h}. {intro}"[:160], "noindex": noidx},
           [], section={"/files/": "files", "/support/": "support"}.get(p, ""), h1=h, intro=intro, body=body)

# ================= СТАТИКА =================
os.makedirs(f"{OUT}/static/i", exist_ok=True)
for f in USED_ICONS:
    im = Image.open(f"{CUSTOM_ICONS}/{f}" if os.path.exists(f"{CUSTOM_ICONS}/{f}") else f"{ICONS}/{f}").convert("RGBA")
    if im.size[0] <= 32:
        im = im.resize((64, 64), Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    im.save(f"{OUT}/static/i/{f[:-4]}.webp", "WEBP", quality=90, method=6)
shutil.copytree(os.path.join(HERE, "static/css"), f"{OUT}/static/css")
shutil.copytree(os.path.join(HERE, "static/js"), f"{OUT}/static/js")
os.makedirs(f"{OUT}/static/fonts")
for f in ["prata-cyrillic-400-normal", "prata-latin-400-normal",
          "onest-cyrillic-400-normal", "onest-latin-400-normal", "onest-cyrillic-500-normal", "onest-latin-500-normal", "onest-cyrillic-600-normal", "onest-latin-600-normal"]:
    fam = "prata" if f.startswith("prata") else "onest"
    _fp = os.path.join(HERE, "fonts", f"{f}.woff2")
    if not os.path.exists(_fp): _fp = os.path.join(HERE, f"node_modules/@fontsource/{fam}/files/{f}.woff2")
    shutil.copy(_fp, f"{OUT}/static/fonts/")
os.makedirs(f"{OUT}/static/media", exist_ok=True)
if SITE["has_logo"]:
    im = Image.open(f"{ASSETS}/logoGold.png").convert("RGBA"); im = im.crop(im.getchannel("A").getbbox())
    lg = im.copy(); lg.thumbnail((640, 180), Image.LANCZOS); lg.save(f"{OUT}/static/media/logo.webp", "WEBP", quality=92)
    g = im.crop((0, 0, int(im.height * 0.74), im.height)); sq = Image.new("RGBA", (max(g.size),) * 2, (0, 0, 0, 0)); sq.paste(g, ((sq.width - g.width) // 2, (sq.height - g.height) // 2))
    sq.resize((64, 64), Image.LANCZOS).save(f"{OUT}/static/media/favicon-g.png")
    ap = Image.new("RGBA", sq.size, (13, 10, 7, 255)); ap.alpha_composite(sq); ap.convert("RGB").resize((180, 180), Image.LANCZOS).save(f"{OUT}/static/media/apple-touch-icon.png")
def _img(src, dst, size, crop=None, q=82):
    im = Image.open(src).convert("RGB")
    if crop: im = im.crop(crop(im))
    im.thumbnail(size, Image.LANCZOS); im.save(f"{OUT}/static/media/{dst}", quality=q, optimize=True, progressive=True)
if os.path.exists(f"{ASSETS}/chest.jpg"): _img(f"{ASSETS}/chest.jpg", "chest.jpg", (900, 900))
elif os.path.exists(f"{ASSETS}/sunduk.png"):
    im = Image.open(f"{ASSETS}/sunduk.png").convert("RGBA"); im.thumbnail((720, 720)); im.save(f"{OUT}/static/media/chest.webp", "WEBP", quality=88)
if SITE["has_coin"]:
    im = Image.open(f"{ASSETS}/goldcoin.png").convert("RGBA"); im.thumbnail((96, 96)); im.save(f"{OUT}/static/media/goldcoin.webp", "WEBP", quality=92)
if os.path.exists(f"{ASSETS}/hero.mp4"): shutil.copy(f"{ASSETS}/hero.mp4", f"{OUT}/static/media/hero.mp4")
elif os.path.exists(f"{ASSETS}/video.mp4"): shutil.copy(f"{ASSETS}/video.mp4", f"{OUT}/static/media/hero.mp4")
if os.path.exists(f"{ASSETS}/hero.jpg"): _img(f"{ASSETS}/hero.jpg", "hero.jpg", (2400, 1400))
if os.path.exists(f"{ASSETS}/wiki.mp4"):
    shutil.copy(f"{ASSETS}/wiki.mp4", f"{OUT}/static/media/wiki.mp4")
    if os.path.exists(f"{ASSETS}/wiki-poster.jpg"): _img(f"{ASSETS}/wiki-poster.jpg", "wiki-poster.jpg", (1600, 900))
for n in ("wiki", "raid", "items", "monsters", "zones", "quests"):
    if os.path.exists(f"{ASSETS}/{n}.jpg"): _img(f"{ASSETS}/{n}.jpg", f"{n}.jpg", (2400, 1100))
for r in ("human", "elf", "dark-elf", "orc", "dwarf"):
    if os.path.exists(f"{ASSETS}/race-{r}.jpg"): _img(f"{ASSETS}/race-{r}.jpg", f"race-{r}.jpg", (320, 320), q=84)
_ogsrc = f"{ASSETS}/hero-still.jpg" if os.path.exists(f"{ASSETS}/hero-still.jpg") else f"{ASSETS}/hero.jpg"
if os.path.exists(_ogsrc):
    _img(_ogsrc, "og.jpg", (1200, 630), crop=lambda im: (0, 0, im.width, min(im.height, int(im.width * 630 / 1200))) if im.width / im.height < 1200 / 630 else ((im.width - int(im.height * 1200 / 630)) // 2, 0, (im.width + int(im.height * 1200 / 630)) // 2, im.height))
# фавикон и og из иконки монет, пока нет своих
if os.path.exists(f"{OUT}/static/media/favicon-g.png"): shutil.move(f"{OUT}/static/media/favicon-g.png", f"{OUT}/static/media/favicon.png")
else: Image.open(f"{ICONS}/etc_coins_gold_i00.png").convert("RGBA").resize((64, 64), Image.LANCZOS).save(f"{OUT}/static/media/favicon.png")
if not os.path.exists(f"{OUT}/static/media/og.jpg"): Image.new("RGB", (1200, 630), (13, 10, 7)).save(f"{OUT}/static/media/og.jpg", quality=85)

os.makedirs(f"{OUT}/static/tip", exist_ok=True)
for iid in PUB:
    i = ITEM[iid]
    tip = {"n": i["name"], "i": icon(i.get("iconFile")) if i.get("iconFile") in ICON_OK else None, "g": i["grade"], "k": item_kind(i),
           "s": [[k, str(v)] for k, v in item_stats(i) if k not in ("Цена продажи в магазин", "Кристаллов при разбивке")][:7]}
    nd = len({NPC[n]["name"] for n, _ in DROPPED_BY.get(iid, [])}); ns = len({NPC[n]["name"] for n, _ in SPOILED_BY.get(iid, [])})
    src = []
    if nd: src.append(f"дроп: {nd} {plural(nd,'монстр','монстра','монстров')}")
    if ns: src.append(f"спойл: {ns}")
    if iid in RECIPE_FOR: src.append("крафт")
    if SOLD.get(iid): src.append("магазин")
    tip["src"] = ", ".join(src)
    with open(f"{OUT}/static/tip/{iid}.json", "w") as f: json.dump(tip, f, ensure_ascii=False, separators=(",", ":"))
with open(f"{OUT}/static/gw-search.json", "w") as f: json.dump(GW_SEARCH, f, ensure_ascii=False, separators=(",", ":"))
with open(f"{OUT}/static/search.json", "w") as f: json.dump(SEARCH, f, ensure_ascii=False, separators=(",", ":"))
with open(f"{OUT}/sitemap.xml", "w") as f:
    f.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
    for p in sorted(set(PAGES)): f.write(f"<url><loc>{BASE}{p}</loc><lastmod>{TODAY}</lastmod></url>\n")
    f.write("</urlset>\n")
with open(f"{OUT}/robots.txt", "w") as f:
    f.write(f"User-agent: *\nAllow: /\nDisallow: /static/search.json\n\nSitemap: {BASE}/sitemap.xml\n")
with open(f"{OUT}/llms.txt", "w") as f:
    f.write(f"# Goldwar\n\n> Сервер Lineage 2 на хрониках Interlude (C6) с рейтами x50, PvP-концепцией и системой Золотых сундуков. Сайт включает базу знаний по Interlude.\n\n"
            f"## Разделы\n\n- [База знаний]({BASE}/wiki/): обзор базы\n- [Классы]({BASE}/wiki/classes/): {len(classes)} классов с умениями по уровням\n"
            f"- [Предметы]({BASE}/wiki/items/weapons/sword/): {fmt(len(PUB))} предметов с дропом, спойлом и крафтом\n- [Монстры]({BASE}/wiki/monsters/): {fmt(len(regular))} монстров по уровням\n"
            f"- [Рейд-боссы]({BASE}/wiki/raid-bosses/): {len(rbs)} боссов\n- [Зоны охоты]({BASE}/wiki/zones/)\n- [Квесты]({BASE}/wiki/quests/)\n\n"
            f"## Игра\n\n- Регистрация: https://acp.goldwar.net/register/\n- Файлы: {BASE}/files/\n- Telegram: https://t.me/GoldwarChannel\n")
# .htaccess: на тестовом адресе запрет индексации; GW_PROD=1 – боевая сборка для goldwar.net
_ht = open(os.path.join(HERE, "htaccess.txt")).read()
if os.environ.get("GW_PROD") != "1": _ht = 'Header set X-Robots-Tag "noindex, nofollow"\n' + _ht
with open(f"{OUT}/.htaccess", "w") as f: f.write(_ht)
with open(f"{OUT}/404.html", "w") as f:
    f.write(env.get_template("page.html").render(site=SITE, path="/404/", meta={"title": "Страница не найдена | Goldwar", "description": "Страница не найдена.", "noindex": True}, jsonld=[], section="",
                                                h1="Страница не найдена", intro="Такой страницы нет. Попробуйте поиск в базе знаний.", body="<a class='btn btn-gold' href='/wiki/'>В базу знаний</a>"))

dup_t = {k: v for k, v in TITLES.items() if len(v) > 1}; dup_d = {k: v for k, v in DESCS.items() if len(v) > 1}
print("pages", len(PAGES), "icons", len(USED_ICONS), "search", len(SEARCH))
print("dup titles", len(dup_t), list(dup_t.items())[:5])
print("dup descs", len(dup_d), list(dup_d.items())[:3])
print("long titles", sum(1 for t in TITLES if len(t) > 60), [t for t in TITLES if len(t) > 60][:5])
