#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回归测试：覆盖 0/1/5/20 单、去重累积、比价与活动价识别。

运行:  python tests/run_tests.py
全部通过时退出码 0。
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
SCRIPTS = HERE.parent / "scripts"
FIX = HERE / "fixtures"
PY = sys.executable

fails = []


def run(*args):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} 失败:\n{r.stderr}")
    return r.stdout


def expect(name, text, must=(), must_not=()):
    for s in must:
        if s not in text:
            fails.append(f"[{name}] 缺少: {s}")
    for s in must_not:
        if s in text:
            fails.append(f"[{name}] 不该出现: {s}")
    print(f"  {'FAIL' if any(name in f for f in fails) else 'ok  '} {name}")


def main():
    if not (FIX / "orders_20.txt").exists():
        print("生成 fixture ...")
        run(HERE / "gen_fixtures.py")

    tmp = Path(tempfile.mkdtemp())

    print("订单分析：")
    for name, must, must_not in [
        ("orders_0", ["未查到历史餐饮订单"], ["样本不足"]),
        ("orders_1", ["样本不足 5 单"], []),
        ("orders_5", ["板烧鸡腿堡三件套", "最常买套餐"], ["样本不足 5 单"]),
        ("orders_20", ["20 单", "板烧鸡腿堡三件套 × 8"], ["样本不足 5 单", "从未点过的品类"]),
    ]:
        out = tmp / f"{name}.txt"
        run(SCRIPTS / "analyze_orders.py", FIX / f"{name}.txt", "--out", out,
            "--now", "2026-10-24 12:54")
        expect(name, out.read_text(encoding="utf-8"), must, must_not)

    print("偏好累积去重：")
    prefs = tmp / "prefs.json"
    run(SCRIPTS / "analyze_orders.py", FIX / "orders_20.txt", "--prefs", prefs,
        "--out", tmp / "p1.txt", "--now", "2026-10-24 12:54")
    run(SCRIPTS / "analyze_orders.py", FIX / "orders_20.txt", "--prefs", prefs,
        "--out", tmp / "p2.txt", "--now", "2026-10-24 12:54")
    expect("dedupe", (tmp / "p2.txt").read_text(encoding="utf-8"), ["本次新增 0 单"],
           ["本次新增 20 单"])
    p = json.loads(prefs.read_text(encoding="utf-8"))
    expect("prefs_count", json.dumps({"n": p["order_count"]}), ['"n": 20'])

    print("比价引擎：")
    menu = {
        "data": {"meals": {
            "1": {"name": "巨无霸", "currentPrice": "24", "originalPrice": "24"},
            "2": {"name": "巨无霸四件套", "currentPrice": "30", "originalPrice": "55"},
            "3": {"name": "巨无霸三件套", "currentPrice": "39.5", "originalPrice": "39.5"},
            "4": {"name": "薯条", "currentPrice": "14.5", "originalPrice": "14.5"},
            "5": {"name": "可乐", "currentPrice": "10", "originalPrice": "10"},
        }}
    }
    mpath = tmp / "menu.json"
    mpath.write_text(json.dumps(menu, ensure_ascii=False), encoding="utf-8")
    out = tmp / "deal.txt"
    run(SCRIPTS / "best_deal.py", "deal", "--menu", mpath, "--target", "巨无霸",
        "--now", "2026-10-24 12:54", "--out", out)
    expect("deal_promo", out.read_text(encoding="utf-8"),
           ["活动价", "只比单点多", "套餐省"])

    print("券可用性：")
    coupon = ("共 2 张\n\n## 9.9元巨无霸\n- **优惠**: ¥9.9 (用券价格)\n"
              "- **有效期**: 2026-10-26 10:30-2026-10-30 23:59 周一、二、三、四、五 10:30-23:59\n\n"
              "## 全时段券\n- **优惠**: ¥15 (用券价格)\n"
              "- **有效期**: 2026-10-24 00:00-2026-10-30 23:59\n")
    cpath = tmp / "cp.txt"
    cpath.write_text(coupon, encoding="utf-8")
    js = tmp / "cp.json"
    run(SCRIPTS / "best_deal.py", "coupons", cpath, "--now", "2026-10-24 12:54", "--out", js)
    data = json.loads(js.read_text(encoding="utf-8"))
    expect("coupon_weekday", json.dumps(data, ensure_ascii=False),
           ['"ok": false', '"ok": true', "不在有效期"])

    print()
    if fails:
        print("失败项：")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
