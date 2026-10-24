#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳省钱比价引擎（纯本地计算，不联网）

两个子命令:

  1) 解析券包
     python best_deal.py coupons <query-my-coupons 原文.txt> [--now "2026-10-24 12:54"] [--out f.json]

  2) 比价
     python best_deal.py deal --menu meals.json --target 板烧 [--coupons f.json]
                              [--nutrition nutrition.txt] [--now ...] [--out report.txt]

设计要点:
- 价格全部本地算：query-meals 的 data.meals[code].currentPrice 已是「元」，不必每个方案都调 calculate-price。
  只有带券/满减才需要真实算价。
- 券的可用性必须同时校验 日期区间 / 星期限制 / 时段窗口，否则会推荐用不了的券。
- 必须识别「活动价」：currentPrice < originalPrice 时是促销，四件套可能比三件套还便宜，
  这是最容易漏也是最有价值的一条。
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6}


# ---------------- 券 ----------------

def parse_coupons(text, now=None):
    blocks = re.split(r"\n(?=##\s)", text)
    out = []
    for b in blocks:
        m = re.search(r"^##\s+(.+)$", b, re.M)
        if not m:
            continue
        title = m.group(1).strip().strip("*")
        price = re.search(r"¥\s*([\d.]+)", b)
        valid = re.search(r"\*\*有效期\*\*[:：]\s*(.+)", b)
        tags = re.search(r"\*\*标签\*\*[:：]\s*(.+)", b)
        out.append({
            "title": title,
            "price": float(price.group(1)) if price else None,
            "validity_raw": valid.group(1).strip() if valid else "",
            "tags": [t.strip() for t in re.split(r"[、,，]", tags.group(1))] if tags else [],
            "usable": check_usable(valid.group(1) if valid else "", now),
        })
    return out


def check_usable(raw, now=None):
    """同时校验 日期区间 / 星期限制 / 每日时段窗口。"""
    if not raw:
        return {"ok": True, "why": "无有效期限制"}
    now = now or datetime.now()
    rng = (re.search(r"(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}\s*-\s*(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}", raw)
           or re.search(r"(\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})", raw))
    if not rng:
        return {"ok": True, "why": "有效期无法解析，按可用处理"}
    d1 = datetime.strptime(rng.group(1), "%Y-%m-%d").date()
    d2 = datetime.strptime(rng.group(2), "%Y-%m-%d").date()
    if not (d1 <= now.date() <= d2):
        return {"ok": False, "why": f"不在有效期（{d1}~{d2}）"}

    days = [WEEK[c] for c in re.findall(r"周([一二三四五六日])", raw)]
    if days and now.weekday() not in days:
        allow = "".join(k for k, v in WEEK.items() if v in days)
        return {"ok": False, "why": f"仅限周{allow}，今天周{'一二三四五六日'[now.weekday()]}"}

    wins = re.findall(r"(\d{2}:\d{2})-(\d{2}:\d{2})", raw)
    if wins:
        hhmm = now.strftime("%H:%M")
        if not any(a <= hhmm <= b for a, b in wins):
            return {"ok": False, "why": "仅限 " + "/".join(f"{a}-{b}" for a, b in wins) + " 使用"}
    return {"ok": True, "why": "当前可用"}


# ---------------- 菜单 ----------------

def load_menu(path):
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    data = raw.get("data", raw)
    return {c: v for c, v in (data.get("meals") or {}).items() if isinstance(v, dict)}


def _num(v):
    try:
        return round(float(str(v).replace(",", "")), 2)
    except Exception:
        return None


def price_of(m):
    return _num(m.get("currentPrice"))


def orig_of(m):
    return _num(m.get("originalPrice"))


def norm(s):
    s = re.sub(r"[（(].*?[)）]", "", s or "")
    return re.sub(r"[\s·、/_\-]+", "", s).lower()


def find(menu, kw, exclude=(), limit=12):
    """按名称包含匹配 → [(code, name, price, orig)]，按现价升序。"""
    k = norm(kw)
    hits = []
    for code, m in menu.items():
        name = m.get("name") or ""
        if any(x in name for x in exclude):
            continue
        if k and k in norm(name):
            hits.append((code, name, price_of(m), orig_of(m)))
    hits.sort(key=lambda x: (x[2] is None, x[2] or 0))
    return hits[:limit]


# ---------------- 营养 ----------------

def load_nutrition(path):
    txt = Path(path).read_text(encoding="utf-8-sig", errors="ignore")
    if '"data"' in txt:
        s, e = txt.find("{"), txt.rfind("}")
        if s != -1 and e > s:
            try:
                obj = json.loads(txt[s:e + 1])
                if isinstance(obj.get("data"), str):
                    txt = obj["data"]
            except Exception:
                pass
    d, started = {}, False
    for line in txt.splitlines():
        line = line.strip()
        if not started:
            if re.match(r"^\[\d+\]\{", line):
                started = True
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        try:
            d[norm(parts[0])] = {"kcal": float(parts[3]), "protein": float(parts[4]),
                                 "sodium": float(parts[7])}
        except Exception:
            continue
    return d


def kcal_of(nut, name):
    if not nut:
        return None
    k = norm(name)
    if k in nut:
        return nut[k]["kcal"]
    for nk, v in nut.items():
        if k and (k in nk or nk in k):
            return v["kcal"]
    return None


# ---------------- 方案 ----------------

def build_plans(menu, target, coupons, nut):
    plans = []
    singles = find(menu, target, exclude=("套", "件", "组合", "拼盘"))
    combos = [x for x in find(menu, target) if "套" in x[1] or "件" in x[1]]

    # 目标含歧义时（"麦辣"可能是鸡翅也可能是堡），优先把汉堡类作为主品，其余仍展示
    burgers = [x for x in singles if "堡" in x[1]]
    primary = burgers[0] if burgers else (singles[0] if singles else None)

    for _, n, p, o in singles[:2]:
        plans.append({"kind": "单点", "items": [(n, p)], "price": p, "orig": o,
                      "kcal": kcal_of(nut, n), "note": "", "primary": primary and n == primary[1]})

    for _, cn, cp, co in combos:
        promo = bool(co and cp and co > cp)
        plans.append({"kind": "套餐", "items": [(cn, cp)], "price": cp, "orig": co,
                      "kcal": None, "promo": promo,
                      "note": (f"活动价，比原价省 ¥{co - cp:.2f}（原价 ¥{co:.2f}）" if promo
                               else "含小食与饮品")})

    if primary:
        sn, sp = primary[1], primary[2]
        fries = find(menu, "薯条", exclude=("堡", "饼"))
        drinks = [x for x in find(menu, "雪碧") + find(menu, "可乐") if "无糖" not in x[1]]
        if fries and drinks and sp is not None:
            f, d = fries[0], drinks[0]
            total = round(sum(x for x in (sp, f[2], d[2]) if x is not None), 2)
            plans.append({"kind": "自组", "items": [(sn, sp), (f[1], f[2]), (d[1], d[2])],
                          "price": total, "orig": None,
                          "kcal": sum(x for x in (kcal_of(nut, sn), kcal_of(nut, f[1]),
                                                  kcal_of(nut, d[1])) if x) or None,
                          "note": "按单品拼成三件，可自由换配"})

    for cp in coupons:
        if cp.get("price") is None:
            continue
        k = norm(target)
        if k and k in norm(cp["title"]):
            plans.append({"kind": "用券", "items": [(cp["title"], cp["price"])],
                          "price": cp["price"], "orig": None, "kcal": None,
                          "usable": cp["usable"]["ok"],
                          "note": "券价" + ("" if cp["usable"]["ok"] else f"，但{cp['usable']['why']}")})
    return plans


def render_deal(plans, target, now):
    L = [f"目标：{target}　·　{now:%Y-%m-%d %H:%M}"]
    if not plans:
        return "\n".join(L + ["没匹配到方案：检查菜单文件是否加载成功，或把关键词缩短（如「板烧」）。"])

    order = {"单点": 0, "套餐": 1, "用券": 2, "自组": 3}
    plans.sort(key=lambda p: (order.get(p["kind"], 9),
                              p["price"] if p["price"] is not None else 1e9))

    L.append("")
    for p in plans:
        comp = " + ".join(n for n, _ in p["items"])
        price = f"¥{p['price']:.2f}" if p["price"] is not None else "价格未知"
        extra = []
        if p.get("orig") and p["price"] and p["orig"] > p["price"]:
            extra.append(f"原价 ¥{p['orig']:.2f}")
        if p.get("kcal"):
            extra.append(f"{p['kcal']:.0f} kcal")
        if p["kind"] == "套餐":
            extra.append("热量需按套餐构成另算")
        tail = ("｜" + " · ".join(extra)) if extra else ""
        L.append(f"[{p['kind']}] {comp} {price}{tail}")
        if p.get("note"):
            L.append(f"        {p['note']}")

    single = next((p for p in plans if p["kind"] == "单点" and p.get("primary")), None)
    combos = [p for p in plans if p["kind"] == "套餐" and p["price"] is not None]
    combo3 = next((p for p in combos if "三件" in p["items"][0][0]), None)
    selfmade = next((p for p in plans if p["kind"] == "自组"), None)

    L.append("")
    L.append("结论：")
    if single:
        L.append(f"· 只要主品：{single['items'][0][0]} ¥{single['price']:.2f}")
    if combos:
        cheap = min(combos, key=lambda x: x["price"])
        line = f"· 想吃一套：{cheap['items'][0][0]} ¥{cheap['price']:.2f}"
        if cheap.get("promo"):
            line += f"（活动价，原价 ¥{cheap['orig']:.2f}）"
        if single and single["price"] is not None and cheap["price"] > single["price"]:
            line += f" — 只比单点多 ¥{cheap['price'] - single['price']:.2f}，多出小食和饮品"
        L.append(line)
    if combo3 and selfmade and combo3["price"] and selfmade["price"]:
        d = selfmade["price"] - combo3["price"]
        if d > 0:
            L.append(f"· 同构成对比：套餐 ¥{combo3['price']:.2f} vs 自组 ¥{selfmade['price']:.2f}，套餐省 ¥{d:.2f}")

    bad = [p for p in plans if not p.get("usable", True)]
    if bad:
        L.append("· 有券但当前用不了：" + "、".join(p["items"][0][0] for p in bad))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("coupons", help="解析券包 markdown")
    c.add_argument("text")
    c.add_argument("--now")
    c.add_argument("--out")

    d = sub.add_parser("deal", help="生成并比较方案")
    d.add_argument("--menu", required=True)
    d.add_argument("--target", required=True)
    d.add_argument("--coupons")
    d.add_argument("--nutrition")
    d.add_argument("--now")
    d.add_argument("--out")

    a = ap.parse_args()
    now = datetime.strptime(a.now, "%Y-%m-%d %H:%M") if getattr(a, "now", None) else datetime.now()

    if a.cmd == "coupons":
        cps = parse_coupons(Path(a.text).read_text(encoding="utf-8-sig", errors="ignore"), now)
        lines = [json.dumps(cps, ensure_ascii=False, indent=2), ""]
        for cp in cps:
            lines.append(f"  [{'可用' if cp['usable']['ok'] else '不可用'}] "
                         f"{cp['title']}  ¥{cp['price']}  {cp['usable']['why']}")
        out = "\n".join(lines)
        if getattr(a, "out", "") and a.out.lower().endswith(".json"):
            out = lines[0]
    else:
        menu = load_menu(a.menu)
        coupons = json.loads(Path(a.coupons).read_text(encoding="utf-8-sig")) if a.coupons else []
        nut = load_nutrition(a.nutrition) if a.nutrition else None
        out = render_deal(build_plans(menu, a.target, coupons, nut), a.target, now)

    if getattr(a, "out", None):
        Path(a.out).write_text(out, encoding="utf-8")
        print(f"written -> {a.out}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(out)


if __name__ == "__main__":
    main()
