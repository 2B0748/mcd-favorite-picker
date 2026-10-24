#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 prefs.json 渲染成一张可分享的「麦门口味画像」卡片。

用法:
    python make_card.py prefs.json [--out card.html] [--png card.png]

- 只用 prefs.json 里的真实数据，样本不足时会在卡面明确标注，不假装懂你。
- --png 需要本机有 Edge / Chrome，会调 headless 截图；没有就只产出 HTML。
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PERSONA = [
    (("板烧",), "板烧原教旨主义者", "多汁、克制、不折腾。一份板烧就是你雷打不动的舒适区。"),
    (("巨无霸",), "巨无霸守门员", "双层牛肉给的是确定感。经典永远不会背叛你。"),
    (("麦辣", "辣"), "无辣不欢派", "辣度是底线，清淡的东西进不了你的购物车。"),
    (("麦香鱼", "鱼"), "鱼派清流", "在牛肉和鸡肉的夹缝里，坚持自己的那一口。"),
    (("吉士", "双吉", "芝士"), "芝士至上主义", "拉丝的那一秒，才是这一餐的高光。"),
    (("麦满分", "粥", "油条", "薯饼"), "早起有饭吃型", "别人还在赖床，你已经在柜台前了。"),
    (("麦乐鸡", "鸡块"), "蘸酱驱动型", "鸡块只是载体，真正的目的是那盒酱。"),
    (("鸡排", "鸡腿"), "酥脆党", "外皮要响、肉要嫩。酥脆是唯一的正义。"),
    (("安格斯", "厚牛"), "厚牛信仰者", "口感要扎实，钱花在肉上不算浪费。"),
]
DRINK = [(("可乐",), "气泡党"), (("雪碧",), "气泡党"),
         (("咖啡", "拿铁", "美式"), "咖啡因续命党"), (("茶",), "茶党")]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def top_of(prefs, cat_kw):
    best, cnt = None, 0
    for name, e in prefs.get("items", {}).items():
        if any(k in name for k in cat_kw) and e["count"] > cnt:
            best, cnt = name, e["count"]
    return best, cnt


def persona(prefs):
    for kws, name, desc in PERSONA:
        item, _ = top_of(prefs, kws)
        if item:
            drink = ""
            for dkws, dname in DRINK:
                if top_of(prefs, dkws)[0]:
                    drink = dname
                    break
            return f"{name} · {drink}" if drink else name, desc
    return "稳重型老饕", "不追新，只选熟悉的那几样。稀有但可靠。"


def bars(prefs, width=260):
    b = prefs.get("buckets") or {}
    if not b:
        return "<div class='muted'>暂无时段数据</div>"
    mx = max(b.values()) or 1
    order = ["早餐", "午餐", "下午茶", "晚餐", "夜宵"]
    rows = []
    for k in order:
        v = b.get(k, 0)
        w = int(width * v / mx) if v else 2
        fill = "#DA291C" if v else "#E8E4DC"
        rows.append(
            f"<div class='bar-row'><span class='bl'>{k}</span>"
            f"<span class='bar' style='width:{w}px;background:{fill}'></span>"
            f"<span class='bv'>{v}</span></div>")
    return "".join(rows)


def top_list(prefs, n=3):
    items = sorted(prefs.get("items", {}).items(), key=lambda x: -x[1]["count"])[:n]
    if not items:
        return "<div class='muted'>还没有足够的点单记录</div>"
    out = []
    for i, (name, e) in enumerate(items, 1):
        last = e.get("last") or ""
        out.append(
            f"<li><span class='rk'>{i}</span><span class='nm'>{name}</span>"
            f"<span class='ct'>×{e['count']}</span>"
            f"<span class='dt'>{last[5:]}</span></li>")
    return "<ul class='tops'>" + "".join(out) + "</ul>"


def render(prefs):
    n = prefs.get("order_count", 0)
    spend = prefs.get("spend_total", 0)
    avg = spend / n if n else 0
    name, desc = persona(prefs)
    lo, hi = (prefs.get("span") or [None, None])[:2]
    thin = n < 5

    badge = ("<div class='warn'>样本仅 %d 单，人格为暂定，多下几单会更准</div>" % n) if thin else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>麦门口味画像</title></head>
<body>
<div class="card">
  <div class="hd">
    <span class="kick">麦当劳口味画像</span>
    <span class="date">{datetime.now():%Y.%m.%d}</span>
  </div>
  <h1>{name}</h1>
  <p class="desc">{desc}</p>
  {badge}
  <div class="nums">
    <div><b>{n}</b><span>有效订单</span></div>
    <div><b>¥{spend:.1f}</b><span>累计消费</span></div>
    <div><b>¥{avg:.1f}</b><span>客单价</span></div>
  </div>
  <div class="sec"><h2>最常点</h2>{top_list(prefs)}</div>
  <div class="sec"><h2>下单时段</h2>{bars(prefs)}</div>
  <div class="ft">
    <span>{lo or '?'} ~ {hi or '?'}</span>
    <span>数据来自麦当劳官方 MCP · 仅本机</span>
  </div>
</div>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #F4F1EA; font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
         display: flex; justify-content: center; padding: 20px; }}
  .card {{ width: 420px; background: #FFFDF7; border: 1px solid #E8E4DC;
          border-top: 6px solid #DA291C; border-radius: 14px; padding: 26px 24px 20px; }}
  .hd {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }}
  .kick {{ font-size: 12px; letter-spacing: 2px; color: #DA291C; font-weight: 500; }}
  .date {{ font-size: 12px; color: #9A958C; }}
  h1 {{ font-size: 25px; line-height: 1.35; color: #1A1A1A; font-weight: 500; letter-spacing: .5px; }}
  .desc {{ font-size: 13px; line-height: 1.7; color: #5C5850; margin-top: 10px; }}
  .warn {{ margin-top: 12px; font-size: 12px; color: #8A5A00; background: #FDF3DC;
          border-radius: 8px; padding: 8px 10px; }}
  .nums {{ display: flex; margin: 22px 0 4px; border-top: 1px solid #EFEBE3;
          border-bottom: 1px solid #EFEBE3; }}
  .nums div {{ flex: 1; padding: 14px 0; text-align: center; }}
  .nums div + div {{ border-left: 1px solid #EFEBE3; }}
  .nums b {{ display: block; font-size: 20px; color: #1A1A1A; font-weight: 500; }}
  .nums span {{ font-size: 11px; color: #9A958C; }}
  .sec {{ margin-top: 20px; }}
  h2 {{ font-size: 12px; color: #9A958C; font-weight: 400; letter-spacing: 1px; margin-bottom: 10px; }}
  .tops {{ list-style: none; }}
  .tops li {{ display: flex; align-items: center; font-size: 13px; padding: 7px 0;
             border-bottom: 1px dashed #F0ECE4; color: #2C2C2A; }}
  .rk {{ width: 18px; color: #C8C3B8; font-size: 12px; }}
  .nm {{ flex: 1; }}
  .ct {{ color: #DA291C; font-size: 12px; margin-left: 8px; }}
  .dt {{ color: #B8B3A8; font-size: 11px; width: 44px; text-align: right; }}
  .bar-row {{ display: flex; align-items: center; font-size: 12px; margin-bottom: 7px; }}
  .bl {{ width: 46px; color: #5C5850; }}
  .bar {{ height: 8px; border-radius: 4px; }}
  .bv {{ margin-left: 8px; color: #B8B3A8; font-size: 11px; }}
  .muted {{ font-size: 12px; color: #B8B3A8; }}
  .ft {{ display: flex; justify-content: space-between; margin-top: 22px; padding-top: 12px;
        border-top: 1px solid #EFEBE3; font-size: 10px; color: #C0BBB0; }}
</style>
</body></html>"""


def trim_png(path):
    """裁掉底部多余空白，让导出的卡片是紧贴内容的。"""
    try:
        import pymupdf as fitz
    except Exception:
        try:
            import fitz
        except Exception:
            return False
    doc = fitz.open(path)
    page = doc[0]
    pix = page.get_pixmap()
    w, h, n = pix.width, pix.height, pix.n
    if n < 3:
        return False
    s, stride = pix.samples, pix.stride
    bg = s[0:3]
    last = h - 1
    for y in range(h - 1, -1, -1):
        off = y * stride
        for x in range(0, w * n, n):
            i = off + x
            if (abs(s[i] - bg[0]) > 6 or abs(s[i + 1] - bg[1]) > 6
                    or abs(s[i + 2] - bg[2]) > 6):
                last = y
                break
        else:
            continue
        break
    if last < h - 2:
        pix2 = page.get_pixmap(clip=fitz.Rect(0, 0, w, min(h, last + 22)))
        pix2.save(path)
    return True


def to_png(html, png):
    for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"):
        if Path(exe).exists():
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            f"--screenshot={png}", "--window-size=480,1100",
                            Path(html).resolve().as_uri()],
                           capture_output=True, timeout=60)
            if Path(png).exists():
                trim_png(png)
                return True
            return False
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefs")
    ap.add_argument("--out", default="麦门口味画像.html")
    ap.add_argument("--png")
    a = ap.parse_args()

    html = render(load(a.prefs))
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"written -> {a.out}")
    if a.png:
        ok = to_png(a.out, a.png)
        print(("written -> " if ok else "PNG 生成失败（未找到 Edge），HTML 已可用 -> ") + a.png)
        if not ok:
            sys.exit(0)


if __name__ == "__main__":
    main()
