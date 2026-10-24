#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一条命令跑完整个推荐链路：不需要任何 Agent，也不需要客户端支持 MCP。

    订单 → 偏好 → 门店 → 菜单 → 券 → 比价 → 报告（可选画像卡）

这样任何能执行命令的 Agent（Claude Code / Codex / Cursor / Cline / Aider…）
甚至人肉终端，都能用上同一套逻辑；支持 MCP 的客户端则可以跳过本脚本，
直接按 SKILL.md 的流程调工具。

用法:
    python run_recommend.py --store 3450024 --target 板烧
    python run_recommend.py --city 芜湖 --keyword 步行街 --target 板烧 --out-dir ./out --card

Token: 环境变量 MCD_MCP_TOKEN，或 ~/.mcd_mcp_token，或 --token-file。
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_orders as ao          # noqa: E402
import best_deal as bd               # noqa: E402
from mcp_client import McpClient, McpError   # noqa: E402


def safe(fn, default=None, warn=None):
    try:
        return fn(), None
    except Exception as e:
        msg = f"{warn or '步骤'}失败：{e}"
        return default, msg


def pick_store(cli, store, city, keyword):
    if store:
        return {"storeCode": str(store), "storeName": "（指定门店）"}
    if not (city and keyword):
        raise McpError("需要 --store，或同时提供 --city 与 --keyword 来搜索门店")
    text = cli.call("query-nearby-stores",
                    {"beType": 1, "searchType": 2, "city": city, "keyword": keyword})
    payload = ao.extract_payload(text)
    if not payload.get("success", True):
        raise McpError(payload.get("message") or "门店搜索失败")
    stores = payload.get("data") or []
    if isinstance(stores, dict):
        stores = stores.get("list") or []
    if not stores:
        raise McpError("没有搜到门店，换个更具体的地标试试")
    return stores[0]


def build_menu(cli, store_code):
    text = cli.call("query-meals",
                    {"storeCode": store_code, "orderType": 1, "beType": 1})
    payload = ao.extract_payload(text)
    if not payload.get("success", True):
        raise McpError(payload.get("message") or "菜单查询失败")
    meals = ((payload.get("data") or {}).get("meals")) or {}
    return {c: v for c, v in meals.items() if isinstance(v, dict)}


def claimable(text):
    """available-coupons 是另一个格式，只取标题与状态做提示。"""
    out = []
    for block in re.split(r"\n(?=- 优惠券标题)", text):
        t = re.search(r"优惠券标题[:：]\s*(.+?)\s*\\?\s*$", block, re.M)
        s = re.search(r"状态[:：]\s*(\S+)", block)
        if t:
            out.append({"title": t.group(1).strip(), "state": s.group(1) if s else ""})
    return out


def main():
    ap = argparse.ArgumentParser(description="麦当劳口味推荐 · 一键跑通")
    ap.add_argument("--target", default="板烧", help="想吃什么（关键词，越短越好）")
    ap.add_argument("--store", help="门店编码，已知就直接用")
    ap.add_argument("--city", help="城市，配合 --keyword 搜索门店")
    ap.add_argument("--keyword", help="地标/商圈关键词")
    ap.add_argument("--now", help='时间，格式 "YYYY-MM-DD HH:MM"，默认当前')
    ap.add_argument("--out-dir", default=".", help="报告与 prefs 输出目录")
    ap.add_argument("--card", action="store_true", help="额外生成口味画像卡")
    ap.add_argument("--token-file")
    ap.add_argument("--url")
    a = ap.parse_args()

    now = datetime.strptime(a.now, "%Y-%m-%d %H:%M") if a.now else datetime.now()
    out_dir = Path(a.out_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    warnings = []

    try:
        cli = McpClient(url=a.url, token_file=a.token_file)
    except McpError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 2

    # 1. 历史订单 → 偏好
    prefs_path = out_dir / "prefs.json"
    prefs = (json.loads(prefs_path.read_text(encoding="utf-8"))
             if prefs_path.exists() else ao.empty_prefs())
    text, err = safe(lambda: cli.call("order-list"), "", "查询历史订单")
    if err:
        warnings.append(err)
    else:
        try:
            added = ao.update_prefs(prefs, ao.extract_payload(text), now)
            prefs_path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
            prefs["_added"] = added
        except Exception as e:
            warnings.append(f"解析历史订单失败：{e}")

    # 2. 门店
    try:
        store = pick_store(cli, a.store, a.city, a.keyword)
    except McpError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 2
    code = str(store.get("storeCode") or a.store or "")

    # 3. 菜单
    menu, err = safe(lambda: build_menu(cli, code), {}, "查询菜单")
    if err:
        warnings.append(err)

    # 4. 券
    cps, err = safe(lambda: bd.parse_coupons(cli.call("query-my-coupons", {}), now), [], "读取券包")
    if err:
        warnings.append(err)
    claims, err2 = safe(lambda: claimable(cli.call("available-coupons", {})), [], "读取可领券")
    if err2:
        warnings.append(err2)

    # 5. 营养
    nut, _ = safe(lambda: bd.parse_nutrition_text(cli.call("list-nutrition-foods", {})), None)

    # 6. 比价
    deal = "（跳过：没有拿到菜单）"
    if menu:
        plans = bd.build_plans(menu, a.target, cps, nut)
        deal = bd.render_deal(plans, a.target, now)
    else:
        warnings.append("菜单为空，无法比价")

    # 7. 组装报告
    slot = ao.bucket(now.hour, now.minute)
    L = [f"# 麦当劳今天吃什么 · {now:%Y-%m-%d %H:%M}（{slot}）", ""]
    L.append(f"- 门店：{store.get('storeName') or '—'}（{code}）")
    L.append(f"- 目标：{a.target}")
    L.append(f"- 在售餐品：{len(menu)} 个" if menu else "- 在售餐品：未获取")
    L.append("")
    L.append("## 你的常点")
    L.append("")
    L.append(ao.render(prefs, now))
    L.append("")
    L.append("## 怎么点最省")
    L.append("")
    L.append(deal)

    usable = [c for c in cps if c["usable"]["ok"]]
    blocked = [c for c in cps if not c["usable"]["ok"]]
    L += ["", "## 券", ""]
    if not cps:
        L.append("券包为空，或该门店当前无可用券。")
    for c in usable:
        L.append(f"- 可用：{c['title']}（券价 ¥{c['price']}）")
    for c in blocked:
        L.append(f"- 不可用：{c['title']}（{c['usable']['why']}）")
    if claims:
        L.append("- 可领取：" + "、".join(f"{x['title']}[{x['state']}]" for x in claims))

    if warnings:
        L += ["", "## 过程中的问题", ""]
        L += [f"- {w}" for w in warnings]
    L += ["", "---", "",
          "价格与活动为查询时快照，以官方下单页为准；本工具不下单。"]

    report = "\n".join(L)
    rp = out_dir / "今日推荐.md"
    rp.write_text(report, encoding="utf-8")

    card_note = ""
    if a.card:
        try:
            import make_card
            html = make_card.render(prefs)
            (out_dir / "口味画像卡.html").write_text(html, encoding="utf-8")
            card_note = f"  画像卡 -> {out_dir / '口味画像卡.html'}\n"
        except Exception as e:
            card_note = f"  画像卡生成失败：{e}\n"

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print(report)
    print()
    print(f"报告 -> {rp}")
    print(f"偏好 -> {prefs_path}")
    print(card_note, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
