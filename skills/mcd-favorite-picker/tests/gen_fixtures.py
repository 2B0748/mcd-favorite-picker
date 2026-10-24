#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 4 组订单 fixture（确定性，可重复生成）。"""

import json
from pathlib import Path

HERE = Path(__file__).parent / "fixtures"
HERE.mkdir(parents=True, exist_ok=True)


def order(oid, when, items, total):
    """items: [(productName, qty, [sub names])]"""
    return {
        "orderId": oid,
        "orderType": "1",
        "createTime": when,
        "beType": "1",
        "beCode": "",
        "storeCode": "3450024",
        "storeName": "测试餐厅",
        "orderStatus": "订单已完成",
        "realTotalAmount": str(total),
        "orderProductList": [
            {
                "productCode": f"P{i}",
                "productName": name,
                "quantity": qty,
                "comboItemList": [{"productCode": f"S{j}", "name": s, "quantity": 1}
                                  for j, s in enumerate(subs)],
            }
            for i, (name, qty, subs) in enumerate(items)
        ],
    }


def wrap(orders):
    return {"success": True, "code": 200, "message": "请求成功",
            "data": {"list": orders}}


def write(name, orders):
    text = ("# API Response Information\n\n## Original Response\n\n"
            + json.dumps(wrap(orders), ensure_ascii=False))
    (HERE / name).write_text(text, encoding="utf-8")
    print(f"{name}: {len(orders)} orders")


write("orders_0.txt", [])

write("orders_1.txt", [
    order("A1", "2026-08-15 14:16:14",
          [("大堡口福三件套", 1, ["Hold不住鸡排堡（椒盐风味）", "中薯条", "雪碧中杯"])], 22.9),
])

write("orders_5.txt", [
    order("B1", "2026-09-01 12:10:00", [("板烧鸡腿堡三件套", 1, ["板烧鸡腿堡", "中薯条", "可乐中杯"])], 38.5),
    order("B2", "2026-09-08 12:30:00", [("板烧鸡腿堡三件套", 1, ["板烧鸡腿堡", "大薯条", "可乐中杯"])], 41.0),
    order("B3", "2026-09-15 08:20:00", [("猪柳蛋麦满分", 1, []), ("小杯鲜萃咖啡", 1, [])], 25.0),
    order("B4", "2026-09-22 12:45:00", [("板烧鸡腿堡三件套", 2, ["板烧鸡腿堡", "中薯条", "雪碧中杯"])], 77.0),
    order("B5", "2026-09-29 18:05:00", [("麦辣鸡腿汉堡三件套", 1, ["麦辣鸡腿汉堡", "中薯条", "可乐中杯"])], 38.0),
])

many = []
plan = [
    ("12:20", [("板烧鸡腿堡三件套", 1, ["板烧鸡腿堡", "中薯条", "可乐中杯"])], 38.5),
    ("08:10", [("吉士蛋麦满分", 1, []), ("豆浆", 1, [])], 22.0),
    ("12:05", [("巨无霸三件套", 1, ["巨无霸", "大薯条", "雪碧中杯"])], 39.5),
    ("15:30", [("奥利奥麦旋风", 1, [])], 12.0),
    ("19:20", [("板烧鸡腿堡三件套", 1, ["板烧鸡腿堡", "中薯条", "可乐中杯"])], 38.5),
]
for i in range(20):
    hm, items, total = plan[i % len(plan)]
    day = 1 + (i * 3) % 27
    many.append(order(f"C{i:02d}", f"2026-07-{day:02d} {hm}:00", items, total))
write("orders_20.txt", many)
