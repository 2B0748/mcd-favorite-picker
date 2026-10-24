#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成本仓库的静态视觉素材（徽章 / 封面 / 流程图 / 比价图）。

风格：奶油底 + 深咖 + 暖黄 + 砖红，与 README 正文一致。
全部纯代码排版，可随时改字重跑，不依赖外部素材或第三方库。

用法:  python tools/gen_assets.py
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets"
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "badges").mkdir(exist_ok=True)

CREAM = "#f7f2e6"
CARD = "#fffdf8"
DARK = "#251b16"
COFFEE = "#4c453f"
GOLD = "#ffc72c"
KHAKI = "#b7975a"
BORDER = "#e4d4b8"
RED = "#c94331"
MUTED = "#88725b"

FONT = "'Microsoft YaHei','PingFang SC','Noto Sans SC',sans-serif"


def width_of(text, size=12):
    """粗估文本宽度：CJK 按 1.0em，其余按 0.56em。"""
    w = 0.0
    for ch in text:
        w += size if ord(ch) > 127 else size * 0.56
    return w


def write(name, svg):
    p = OUT / name
    p.write_text(svg, encoding="utf-8")
    print(f"{name}  {len(svg)}B")


def badge(fname, left, right, color, label):
    size = 12
    lw = width_of(left, size) + 20
    rw = width_of(right, size) + 20
    w = lw + rw
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="26" role="img" aria-label="{label}">
<rect width="{w:.0f}" height="26" rx="5" fill="{color}"/>
<path d="M5 0H{lw:.0f}V26H5Q0 26 0 21V5Q0 0 5 0" fill="{COFFEE}"/>
<g fill="#fff" font-family="{FONT}" font-size="{size}" text-anchor="middle">
<text x="{lw / 2:.1f}" y="17">{left}</text>
<text x="{lw + rw / 2:.1f}" y="17">{right}</text>
</g></svg>'''
    write(f"badges/{fname}.svg", svg)


def cover():
    w, h = 1280, 430
    rows = [("单点", 24.0, ""), ("四件套", 28.0, "promo"),
            ("三件套", 38.5, ""), ("自组", 48.5, "worst")]
    maxp = 48.5
    bar_x, bar_max = 858, 210
    parts = []
    for i, (name, price, kind) in enumerate(rows):
        y = 178 + i * 46
        bw = max(14, bar_max * price / maxp)
        color = GOLD if kind == "promo" else ("#d5c9b2" if kind == "worst" else KHAKI)
        txtcol = DARK if kind == "promo" else MUTED
        parts.append(
            f'<text x="{bar_x}" y="{y + 15}" fill="{MUTED}" font-size="14">{name}</text>'
            f'<rect x="{bar_x + 74}" y="{y}" width="{bw:.0f}" height="22" rx="6" fill="{color}"/>'
            f'<text x="{bar_x + 74 + bw + 10:.0f}" y="{y + 16}" fill="{txtcol}" font-size="14"'
            f'{" font-weight=\"700\"" if kind == "promo" else ""}>¥{price:.2f}</text>')

    chips = [("35 个官方工具", 96), ("160 条营养数据", 250), ("4 类比价方案", 424), ("8 项回归", 570)]
    chip_svg = "".join(
        f'<rect x="{x}" y="330" width="{width_of(t, 14) + 28:.0f}" height="34" rx="17" '
        f'fill="none" stroke="{BORDER}"/>'
        f'<text x="{x + (width_of(t, 14) + 28) / 2:.0f}" y="352" fill="{COFFEE}" '
        f'font-size="14" text-anchor="middle">{t}</text>'
        for t, x in chips)

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img"
     aria-label="麦门口味雷达：读历史订单、按时段推荐、算出最省点法">
<title>麦门口味雷达</title>
<rect width="{w}" height="{h}" rx="24" fill="{CREAM}"/>
<text x="72" y="92" fill="{KHAKI}" font-size="16" letter-spacing="2">WORKBUDDY SKILL · 麦当劳官方 MCP</text>
<text x="72" y="176" fill="{DARK}" font-size="58" font-weight="700">麦门口味雷达</text>
<text x="72" y="226" fill="{COFFEE}" font-size="23">读你的历史订单，算出你的常点，按当下的时段推荐</text>
<text x="72" y="264" fill="{MUTED}" font-size="23">再顺手把「单点 / 套餐 / 用券 / 自组」算一遍，看谁最省</text>
<rect x="800" y="66" width="408" height="240" rx="18" fill="{CARD}" stroke="{BORDER}"/>
<text x="828" y="104" fill="{DARK}" font-size="16" font-weight="700">同一份板烧，四种点法</text>
{"".join(parts)}
{chip_svg}
<rect x="0" y="{h - 8}" width="{w}" height="8" rx="4" fill="{RED}"/>
</svg>'''
    write("cover.svg", svg)


def workflow():
    steps = [
        ("01", "说出需求", "想吃什么、在哪、几点"),
        ("02", "算出门味", "订单去重累积偏好"),
        ("03", "查菜单核价", "在售餐品与实时价"),
        ("04", "比价出结论", "四类方案与差价"),
    ]
    x0, bw, gap, top, bh = 35, 295, 50, 35, 148
    cells = []
    for i, (num, title, sub) in enumerate(steps):
        x = x0 + i * (bw + gap)
        dark = i == 2
        cells.append(
            f'<rect x="{x}" y="{top}" width="{bw}" height="{bh}" rx="15" '
            f'fill="{DARK if dark else CARD}" stroke="{BORDER}"/>'
            f'<text x="{x + 21}" y="{top + 37}" fill="{KHAKI}" font-size="17">{num}</text>'
            f'<text x="{x + 21}" y="{top + 76}" fill="{GOLD if dark else DARK}" '
            f'font-size="25" font-weight="700">{title}</text>'
            f'<text x="{x + 21}" y="{top + 115}" fill="{"#d4bea0" if dark else MUTED}" '
            f'font-size="16">{sub}</text>')
        if i < 3:
            ax = x + bw + 13
            cells.append(f'<path d="M{ax} 109h19l-5 -5m5 5l-5 5" fill="none" '
                         f'stroke="{KHAKI}" stroke-width="2"/>')
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="220" viewBox="0 0 1400 220"
     role="img" aria-label="从需求到餐单结论的四步流程">
<title>四步流程</title>
<rect width="1400" height="220" rx="20" fill="{CREAM}"/>
<g font-family="{FONT}">{"".join(cells)}</g>
</svg>'''
    write("workflow.svg", svg)


def deal_chart():
    rows = [
        ("单点", "板烧鸡腿堡", 24.0, "基准"),
        ("套餐", "板烧鸡腿堡四件套", 28.0, "活动价 · 原价 ¥60"),
        ("套餐", "板烧鸡腿堡三件套", 38.5, ""),
        ("自组", "堡 + 薯条 + 雪碧", 48.5, "比套餐贵 ¥10"),
    ]
    w, h = 1040, 400
    maxp, bar_x, bar_max = 48.5, 330, 480
    bars = []
    for i, (kind, name, price, note) in enumerate(rows):
        y = 108 + i * 62
        bw = max(16, bar_max * price / maxp)
        promo = "活动价" in note
        worst = "贵" in note
        color = GOLD if promo else ("#d5c9b2" if worst else KHAKI)
        bars.append(
            f'<text x="56" y="{y + 17}" fill="{KHAKI}" font-size="14">{kind}</text>'
            f'<text x="120" y="{y + 17}" fill="{DARK}" font-size="16">{name}</text>'
            f'<rect x="{bar_x}" y="{y}" width="{bw:.0f}" height="26" rx="7" fill="{color}"/>'
            f'<text x="{bar_x + bw + 14:.0f}" y="{y + 19}" fill="{DARK if promo else COFFEE}" '
            f'font-size="17"{" font-weight=\"700\"" if promo else ""}>¥{price:.2f}</text>'
            + (f'<text x="{bar_x + bw + 86:.0f}" y="{y + 19}" fill="{MUTED}" font-size="13">{note}</text>' if note else ""))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"
     role="img" aria-label="同一门店同一目标下四种点法的价格对比">
<title>四种点法比价</title>
<rect width="{w}" height="{h}" rx="20" fill="{CREAM}"/>
<g font-family="{FONT}">
<text x="56" y="56" fill="{DARK}" font-size="24" font-weight="700">同样想吃板烧，价格差了一倍</text>
<text x="56" y="84" fill="{MUTED}" font-size="14">同一门店 · 到店自取 · 2026-10-24 实测快照，金额单位为元</text>
{"".join(bars)}
<rect x="56" y="356" width="{w - 112}" height="1" fill="{BORDER}"/>
<text x="56" y="382" fill="{MUTED}" font-size="13">结论：四件套比单点只贵 ¥4，却多出小食与饮品；套餐比自组省 ¥10.00</text>
</g></svg>'''
    write("deal-comparison.svg", svg)


if __name__ == "__main__":
    badge("python", "Python", "3.10+ 标准库", RED, "Python 3.10 及以上，仅用标准库")
    badge("forecast", "免 Token", "本地计算", KHAKI, "偏好统计与比价不联网")
    badge("mcp", "MCP", "官方菜单", RED, "数据来自麦当劳官方 MCP")
    badge("tests", "回归", "8 项全绿", KHAKI, "离线回归测试通过")
    badge("license", "MIT", "许可", COFFEE, "MIT 许可证")
    cover()
    workflow()
    deal_chart()
