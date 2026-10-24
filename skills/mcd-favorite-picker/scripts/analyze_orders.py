#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦当劳历史订单偏好分析 + prefs.json 快照累积（纯本地，不联网）

用法:
    python analyze_orders.py <订单文本文件> [--out 报告] [--prefs prefs.json] [--json] [--now "..."]
    python analyze_orders.py --show-prefs prefs.json

输入: MCP `order-list` 返回的 content[0].text 原文（含 markdown 包裹），或原始 JSON。
输出: 最常买套餐 / 最爱汉堡 / 最爱小食 / 最爱饮品甜品 / 时段分布 / 负向偏好 / 近期重复。

prefs.json 的价值: 订单接口每次可能只返回近期若干单。用 orderId 去重后增量累积，
偏好计数就不会因"翻页看不到更早的单"而丢失，也不会因为重复跑而重复计数。
"""

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BREAKFAST = ("麦满分", "粥", "油条", "薯饼", "豆浆", "蛋堡", "热香饼", "松饼",
             "烘焙", "早餐", "满福")
BURGER = ("巨无霸", "板烧", "麦辣", "吉士", "安格斯", "鸡排堡", "鱼柳", "双吉",
          "堡", "汉堡", "麦香鸡", "麦香鱼")
DRINK = ("可乐", "雪碧", "芬达", "咖啡", "拿铁", "美式", "摩卡", "茶", "果汁",
         "橙汁", "奶茶", "矿泉水", "饮用水", "柠檬", "奶")
DESSERT = ("新地", "圣代", "甜筒", "麦旋风", "冰淇淋", "蛋糕", "提拉米苏", "圆筒")
SNACK = ("薯条", "麦乐鸡", "鸡块", "鸡翅", "派", "玉米", "沙拉", "那么大", "薯角",
         "鸡排", "鸡柳", "洋葱圈", "脆汁鸡")

CATS = ("汉堡", "小食", "饮品", "甜品", "早餐", "其他")


def classify(name):
    n = name or ""
    for kw in BREAKFAST:
        if kw in n:
            return "早餐"
    for kw in DRINK:
        if kw in n:
            return "饮品"
    for kw in BURGER:
        if kw in n:
            return "汉堡"
    for kw in DESSERT:
        if kw in n:
            return "甜品"
    for kw in SNACK:
        if kw in n:
            return "小食"
    return "其他"


def bucket(hour, minute=0):
    m = hour * 60 + minute
    if 300 <= m < 630:
        return "早餐"
    if 630 <= m < 840:
        return "午餐"
    if 840 <= m < 1020:
        return "下午茶"
    if 1020 <= m < 1320:
        return "晚餐"
    return "夜宵"


def extract_payload(text):
    marker = "## Original Response"
    body = text.split(marker, 1)[1] if marker in text else text
    body = body.strip()
    if body.startswith("```"):
        body = re.sub(r"^```[a-zA-Z]*\s*", "", body)
        body = re.sub(r"\s*```$", "", body)
    try:
        return json.loads(body)
    except Exception:
        pass
    s, e = body.find("{"), body.rfind("}")
    if s != -1 and e > s:
        try:
            return json.loads(body[s:e + 1])
        except Exception:
            pass
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except Exception:
                continue
    raise SystemExit("无法从输入中解析出 JSON，请确认这是 order-list 的返回原文")


def yuan(v):
    try:
        x = float(str(v).replace(",", "").strip() or 0)
    except Exception:
        return 0.0
    return x / 100 if x > 10000 else x


def parse_time(s):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def empty_prefs():
    return {
        "version": 1,
        "updated_at": "",
        "seen_order_ids": [],
        "order_count": 0,
        "span": [None, None],
        "spend_total": 0.0,
        "combos": {},
        "items": {},
        "buckets": {},
    }


def bump(d, key, n=1, day=None):
    e = d.setdefault(key, {"count": 0, "last": None})
    e["count"] += n
    if day and (e["last"] is None or day > e["last"]):
        e["last"] = day


def update_prefs(prefs, payload, now):
    """把本次返回里「没见过的订单」增量合并进 prefs。返回新增订单数。"""
    orders = (payload.get("data") or {}).get("list") or []
    seen = set(prefs.get("seen_order_ids") or [])
    new = 0
    for o in orders:
        oid = o.get("orderId") or ""
        if oid and oid in seen:
            continue
        dt = parse_time(o.get("createTime") or "")
        day = dt.strftime("%Y-%m-%d") if dt else None
        b = bucket(dt.hour, dt.minute) if dt else "未知"
        prefs["buckets"][b] = prefs["buckets"].get(b, 0) + 1
        prefs["spend_total"] = round(prefs["spend_total"] + yuan(o.get("realTotalAmount")), 2)
        prefs["order_count"] += 1
        if day:
            lo, hi = prefs["span"]
            prefs["span"] = [min(x for x in (lo, day) if x) if lo else day,
                             max(x for x in (hi, day) if x) if hi else day]
        for p in o.get("orderProductList") or []:
            qty = int(p.get("quantity") or 1)
            name = (p.get("productName") or "").strip()
            subs = p.get("comboItemList") or []
            if subs:
                if name:
                    bump(prefs["combos"], name, qty, day)
                for s in subs:
                    sn = (s.get("name") or "").strip()
                    if sn:
                        bump(prefs["items"], sn, int(s.get("quantity") or 1), day)
            elif name:
                bump(prefs["items"], name, qty, day)
        if oid:
            seen.add(oid)
        new += 1
    prefs["seen_order_ids"] = sorted(seen)
    prefs["updated_at"] = now.strftime("%Y-%m-%d %H:%M")
    return new


def grouped(prefs):
    g = {c: Counter() for c in CATS}
    for name, e in prefs["items"].items():
        g[classify(name)][name] = e["count"]
    return g


def never_categories(prefs):
    g = grouped(prefs)
    return [c for c in CATS if c not in ("其他",) and sum(g[c].values()) == 0]


def recent_repeats(prefs, now, days=7):
    cutoff = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    return {n: e["last"] for n, e in prefs["items"].items()
            if e.get("last") and e["last"] >= cutoff}


def render(prefs, now):
    L = []
    n = prefs["order_count"]
    if not n:
        return "未查到历史餐饮订单。建议走冷启动模式：按当前菜单 + 时段 + 券推荐，不要编造历史偏好。"

    lo, hi = prefs["span"]
    L.append(f"样本：{n} 单，{lo or '?'} ~ {hi or '?'}")
    L.append(f"累计：¥{prefs['spend_total']:.2f}，客单价约 ¥{prefs['spend_total'] / n:.2f}")
    if n < 5:
        L.append("⚠ 样本不足 5 单，偏好结论仅供参考（不要下强断言）")

    def block(title, counter, k=3):
        top = counter.most_common(k)
        if not top:
            return
        L.append("")
        L.append(f"{title}：")
        for i, (name, cnt) in enumerate(top, 1):
            last = ""
            src = prefs["items"].get(name) or prefs["combos"].get(name)
            if src and src.get("last"):
                last = f"（最近 {src['last']}）"
            L.append(f"  {i}. {name} × {cnt}{last}")

    combos = Counter({k: v["count"] for k, v in prefs["combos"].items()})
    block("最常买套餐", combos)
    g = grouped(prefs)
    block("最爱汉堡", g["汉堡"])
    block("最爱小食", g["小食"])
    block("饮品", g["饮品"])
    block("甜品", g["甜品"])
    block("早餐常点", g["早餐"])

    if prefs["buckets"]:
        L.append("")
        L.append("下单时段分布：" + "，".join(
            f"{k} {v} 单" for k, v in sorted(prefs["buckets"].items(), key=lambda x: -x[1])))

    rep = recent_repeats(prefs, now)
    if rep:
        L.append("")
        L.append("近 7 天已吃过（推荐时降权）：" + "、".join(f"{k}({v})" for k, v in rep.items()))

    nv = never_categories(prefs)
    if nv:
        tag = "弱提示" if n < 8 else "可作负向偏好"
        L.append("")
        L.append(f"从未点过的品类（{tag}）：" + "、".join(nv))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="order-list 返回原文所在文件")
    ap.add_argument("--out", help="报告写入该文件")
    ap.add_argument("--prefs", help="prefs.json 路径（存在则增量合并，不存在则新建）")
    ap.add_argument("--show-prefs", help="只读取并渲染已有 prefs.json")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    ap.add_argument("--now", help='当前时间，格式 "YYYY-MM-DD HH:MM"，默认取系统时间')
    a = ap.parse_args()

    now = parse_time(a.now) if a.now else datetime.now()

    if a.show_prefs:
        prefs = json.loads(Path(a.show_prefs).read_text(encoding="utf-8-sig"))
        text = json.dumps(prefs, ensure_ascii=False, indent=2) if a.json else render(prefs, now)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
            print(f"written -> {a.out}")
        else:
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass
            print(text)
        return

    if not a.input:
        raise SystemExit("需要 input 文件，或改用 --show-prefs")

    raw = Path(a.input).read_text(encoding="utf-8-sig", errors="ignore")
    payload = extract_payload(raw)

    if a.prefs:
        p = Path(a.prefs)
        prefs = json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else empty_prefs()
        added = update_prefs(prefs, payload, now)
        p.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        prefs = empty_prefs()
        added = update_prefs(prefs, payload, now)

    if a.json:
        text = json.dumps(prefs, ensure_ascii=False, indent=2)
    else:
        text = f"（本次新增 {added} 单）\n" + render(prefs, now)

    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"written -> {a.out}")
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        print(text)


if __name__ == "__main__":
    main()
