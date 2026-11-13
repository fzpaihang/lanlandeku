# -*- coding: utf-8 -*-
"""生成 apk/skill_class.py：武学 → 可准备位置（多值）

数据来源：https://whfie.github.io/fzjhskill/ 的原始表 public/data/skill.json.gz
（仓库 whfie/fzjhskill）。该表与 apk/names.json 的 774 个武学 id 完全一致，
每门武学带：
  * wxclassify  分类标识（neigong / jian / zhang / quan / zhi …，可逗号分隔）
  * dsc         描述末尾的「可准备为:拳脚、内功、招架」，最准的位置信息

同一门武学可以准备在多个位置（太玄经 = 拳脚 + 内功 + 招架），所以这里输出
多值，界面按「每门武学出现在它所有能准备的位置分组里」展示。

用法：
    python scripts/build_skill_class.py            # 缓存存在就直接用
    python scripts/build_skill_class.py --fetch    # 强制重新下载
"""
import gzip
import io
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APK = os.path.join(ROOT, "apk")
CACHE = os.path.join(APK, "data", "skill.json.gz")
URL = "https://raw.githubusercontent.com/whfie/fzjhskill/master/public/data/skill.json.gz"
OUT = os.path.join(APK, "skill_class.py")

# 位置展示顺序：越靠前越常用
POS_ORDER = ["内功", "轻功", "拳脚", "招架", "剑法", "刀法", "棍法", "枪法",
             "鞭法", "斧法", "暗器", "双持", "乐器", "学识", "其他"]

# wxclassify 标识 → 位置
CLASSIFY = {
    "neigong": "内功",
    "qinggong": "轻功",
    "zhaojia": "招架",
    "quan": "拳脚",
    "zhang": "拳脚",
    "zhi": "拳脚",
    "zhua": "拳脚",
    "tui": "拳脚",
    "jian": "剑法",
    "dao": "刀法",
    "gun": "棍法",
    "qiang": "枪法",
    "bian": "鞭法",
    "fu": "斧法",
    "anqi": "暗器",
    "shuangchi": "双持",
    "qin": "乐器",
    "zhishi": "学识",
}

# 描述里的「可准备为」用词直接就是位置名，只需归一
POS_ALIAS = {
    "拳脚": "拳脚", "内功": "内功", "招架": "招架", "轻功": "轻功",
    "剑法": "剑法", "刀法": "刀法", "棍法": "棍法", "枪法": "枪法",
    "鞭法": "鞭法", "斧法": "斧法", "暗器": "暗器", "双持": "双持",
    "乐器": "乐器", "学识": "学识", "琴": "乐器",
}


def fetch():
    if os.path.exists(CACHE) and "--fetch" not in sys.argv:
        return
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    print("下载 %s" % URL)
    req = urllib.request.Request(URL, headers={"User-Agent": "fzjh-skill"})
    with urllib.request.urlopen(req, timeout=60) as r:
        blob = r.read()
    with open(CACHE, "wb") as f:
        f.write(blob)
    print("已缓存 %d 字节" % len(blob))


def positions_of(item):
    pos = []
    for t in str(item.get("wxclassify") or "").split(","):
        p = CLASSIFY.get(t.strip())
        if p and p not in pos:
            pos.append(p)
    dsc = str(item.get("dsc") or "")
    m = re.search(r"可准备为[:：]\s*([^\n]+)", dsc)
    if m:
        for t in re.split(r"[、,，/ ]+", m.group(1)):
            p = POS_ALIAS.get(t.strip())
            if p and p not in pos:
                pos.append(p)
    pos.sort(key=lambda x: POS_ORDER.index(x) if x in POS_ORDER else 99)
    return pos


def main():
    fetch()
    data = json.loads(gzip.open(CACHE, "rb").read())
    skills = data["skills"]
    with io.open(os.path.join(APK, "names.json"), encoding="utf-8") as f:
        names = json.load(f)["skills"]

    rows = {}
    missing = 0
    multi = 0
    for sid, item in skills.items():
        pos = positions_of(item)
        if not pos:
            missing += 1
            continue
        if len(pos) > 1:
            multi += 1
        rows[sid] = ",".join(pos)

    miss_ids = [sid for sid in names if sid not in rows]
    for sid in miss_ids:          # 表里没有的（理论上没有）留空，界面归「其他」
        rows[sid] = ""

    lines = [
        "# -*- coding: utf-8 -*-",
        '"""武学可准备位置（自动生成，勿手改；改数据请跑 scripts/build_skill_class.py）',
        "",
        "数据来源：https://whfie.github.io/fzjhskill/ 的 public/data/skill.json.gz",
        "同一门武学可能有多个位置（太玄经 = 拳脚+内功+招架），值为逗号分隔的位置名。",
        '"""',
        "",
        "POS_ORDER = %r" % (POS_ORDER,),
        "",
        "CLASS = {",
    ]
    for sid in sorted(rows):
        lines.append('    "%s": "%s",' % (sid, rows[sid]))
    lines.append("}")
    lines.append("")
    text = "\n".join(lines)
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    print("已写 %s：%d 门，多位置 %d 门，无位置信息 %d 门，表外 %d 门"
          % (os.path.basename(OUT), len(rows), multi, missing, len(miss_ids)))
    print("文件大小 %.1f KB" % (os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main()
