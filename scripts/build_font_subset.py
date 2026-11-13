# -*- coding: utf-8 -*-
"""生成打进 APK 的中文字体子集：apk/fonts/NotoSansSC-Regular.ttf

为什么要打包字体：App 原来按路径探测系统字体，但
  * /system/fonts/NotoSansCJKsc-Regular.ttf 只有部分 ROM 有；
  * DroidSansFallback.ttf 在 Android 9 之后已被移除；
  * NotoSansCJK-Regular.ttc 是字体集合，face 0 是日文，中文会按日文字形渲染。
三个都落空时 FONT 会退回 Roboto（不含中文）→ 全屏豆腐块。MuMu 是 AOSP，
一定有第一个文件，所以模拟器永远测不出这个故障。

字体源：Windows 自带 NotoSansSC-VF.ttf（Google Noto Sans SC，OFL 1.1，
可随 APK 分发）。流程：固定 wght=400 → 子集化 → 输出单体 ttf。

字符集策略（宁大勿小，Kivy 不做字体回退，缺字就是豆腐块）：
  * CJK 统一表意文字基本区 U+4E00–U+9FFF（20992 字）
  * ASCII、CJK 标点、全角字符、常用符号
  * 真实昵称里出现过的所有字符（data/lookup-index.json 等）

用法：
    python scripts/build_font_subset.py
    python scripts/build_font_subset.py --src "C:/Windows/Fonts/NotoSansSC-VF.ttf"
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "apk", "fonts")
OUT = os.path.join(OUT_DIR, "NotoSansSC-Regular.ttf")
DEFAULT_SRC = r"C:/Windows/Fonts/NotoSansSC-VF.ttf"

# 真实昵称来源：越多越不容易缺字
NICK_FILES = [
    os.path.join(ROOT, "data", "lookup-index.json"),
    os.path.join(ROOT, "data", "cangsong-5zhuan.json"),
    os.path.join(ROOT, "data", "extra-names.json"),
]


def collect_chars():
    chars = set()

    # ASCII 可打印
    chars.update(chr(c) for c in range(0x20, 0x7F))
    # Latin-1 补充（· ° ± × ÷ 等，中文文本里常用）
    chars.update(chr(c) for c in range(0xA0, 0x100))
    # CJK 基本区全量
    chars.update(chr(c) for c in range(0x4E00, 0xA000))
    # CJK 标点 / 假名区（标点在这段开头）
    chars.update(chr(c) for c in range(0x3000, 0x3040))
    # 全角 ASCII
    chars.update(chr(c) for c in range(0xFF00, 0xFFF0))
    # 通用标点：·—…‰°′″等
    chars.update(chr(c) for c in range(0x2000, 0x2070))
    # 箭头整段：‹› 之外还有 ←↑→↓，UI 里迟早会用到
    chars.update(chr(c) for c in range(0x2190, 0x2200))
    # 几何图形整段：▲▼▶◀■□●○◆◇ —— 折叠箭头 ▶ 就在这段，
    # 漏了它武学分组会全变豆腐块（踩过一次）
    chars.update(chr(c) for c in range(0x25A0, 0x2600))
    chars.update("①②③④⑤⑥⑦⑧⑨⑩★☆♥♦✓✗")

    nick = 0
    for path in NICK_FILES:
        try:
            with io.open(path, encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        names = []

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in ("n", "name", "nick", "nickname") and isinstance(v, str):
                        names.append(v)
                    else:
                        walk(v)
            elif isinstance(o, list):
                for it in o:
                    walk(it)

        walk(data)
        for n in names:
            chars.update(n)
            nick += 1

    print("昵称 %d 条，字符集共 %d 个" % (nick, len(chars)))
    return chars


def main():
    src = DEFAULT_SRC
    if "--src" in sys.argv:
        src = sys.argv[sys.argv.index("--src") + 1]
    if not os.path.exists(src):
        raise SystemExit("找不到字体源：%s" % src)

    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    chars = collect_chars()
    os.makedirs(OUT_DIR, exist_ok=True)

    # 1) 固定字重 400，去掉可变轴（Kivy/FreeType 只会取默认实例，留着只是白占体积）
    font = TTFont(src)
    if "fvar" in font:
        try:
            font = instantiateVariableFont(font, {"wght": 400}, inplace=True)
            print("已固定 wght=400")
        except Exception as e:
            print("固定字重失败（忽略）：%s" % e)

    # 2) 子集化
    opts = subset.Options()
    opts.layout_features = ["kern", "locl"]   # 中文用不到复杂排版，省体积
    opts.hinting = False                       # 屏幕渲染用不到点阵 hinting
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.drop_tables += ["DSIG"]
    opts.desubroutinize = True

    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(text="".join(sorted(chars)))
    subsetter.subset(font)

    font.save(OUT)
    size = os.path.getsize(OUT)
    print("已生成 %s（%.2f MB）" % (OUT, size / 1048576.0))

    # 抽查几个易错字是否在表里
    font2 = TTFont(OUT)
    cmap = font2.getBestCmap()
    for ch in "门入江湖放置玩家查询UID0123·—":
        if ord(ch) not in cmap:
            print("  !! 缺字：%s U+%04X" % (ch, ord(ch)))


if __name__ == "__main__":
    main()
