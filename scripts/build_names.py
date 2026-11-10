# -*- coding: utf-8 -*-
"""生成「id → 中文名」映射表（一次性运行，产物 data/names.json）

技能名来自 APK 内的 Lua 数据表，装备名来自站点导出的 equipment.json。
装备名里带颜色标记（YEL…NOR / HIC$N 之类），这里统一剥掉。

用法:
  python scripts/build_names.py [--game-root "D:\\Program Files\\Netease\\fangzhijianghu"]
"""
import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ROOT = r"D:\Program Files\Netease\fangzhijianghu"

RE_COLOR = re.compile(r"\$[A-Za-z]|(?<![A-Za-z])[A-Z]{3}(?![A-Za-z])")

# APK 里的技能表（本版本 770 条）没收进来的新技能。
# 来源：whfie/fzjhskill 的 public/data/skill.json（774 条，2026-11 抓取），对过名字无误。
SKILL_OVERRIDES = {
    "swalVanish": "燕不留痕",
    "inchGleamStrid": "寸芒行",
    "primBindAsceDrag": "太初缚龙诀",
    "chronStartlString": "惊弦录",
}


def clean(s):
    if not isinstance(s, str):
        return s
    return RE_COLOR.sub("", s).strip()


def main():
    root = DEFAULT_ROOT
    if "--game-root" in sys.argv:
        root = sys.argv[sys.argv.index("--game-root") + 1]

    sys.path.insert(0, os.path.join(root, "tools"))
    import luatable

    out = {"skills": {}, "equips": {}}

    skill_lua = os.path.join(root, "apk-lua-all", "assets", "res", "script", "skill", "skill.lua")
    if os.path.exists(skill_lua):
        d = luatable.parse_file(skill_lua)
        for k, v in (d.get("skills") or {}).items():
            if isinstance(v, dict) and v.get("name"):
                out["skills"][k] = clean(v["name"])
        print("技能名 %d 条" % len(out["skills"]))
    else:
        print("!! 未找到 skill.lua: %s" % skill_lua)

    added = 0
    for k, v in SKILL_OVERRIDES.items():
        if k not in out["skills"]:
            out["skills"][k] = v
            added += 1
    if added:
        print("技能名补录 %d 条（新版技能表未收录）：%s" % (
            added, "、".join(SKILL_OVERRIDES[k] for k in SKILL_OVERRIDES)))

    eq_json = os.path.join(root, "site-data", "equipment.json")
    if os.path.exists(eq_json):
        with io.open(eq_json, encoding="utf-8") as f:
            eq = json.load(f)
        for k, v in eq.items():
            if isinstance(v, dict) and v.get("name"):
                out["equips"][k] = clean(v["name"])
        print("装备名 %d 条" % len(out["equips"]))
    else:
        print("!! 未找到 equipment.json: %s" % eq_json)

    p = os.path.join(BASE, "data", "names.json")
    with io.open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("已写入 %s（%.1f KB）" % (p, os.path.getsize(p) / 1024.0))
    for k in list(out["equips"])[:3]:
        print("  装备样例: %s -> %s" % (k, out["equips"][k]))


if __name__ == "__main__":
    main()
