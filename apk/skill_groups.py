# -*- coding: utf-8 -*-
"""武学分组：按「可准备位置」把武学分成可折叠的几组。

**数据来源不再是关键词猜测**：`apk/skill_class.py` 由 `scripts/build_skill_class.py`
从 https://whfie.github.io/fzjhskill/ 的 skill.json 生成，774 门 id 与我们 names.json
完全一致，直接给出每门武学的「可准备为:xxx」位置。

关键点：**一门武学可以有多个位置**（太玄经 = 拳脚 + 内功 + 招架；774 门里有 412 门
可准备为招架），所以分组是多对多：同一门武学在每个可准备位置的分组里都会出现，
各组门数之和大于角色实际武学数是正常的。

只有表里没有位置信息的 85 门，才退回名称/英文 id 关键词兜底（判不准就进「其他」）。

生成/更新位置表：
    python scripts/build_skill_class.py --fetch
"""

try:
    from skill_class import CLASS as CLASS_MAP
    from skill_class import POS_ORDER
except Exception:                      # 老版本热更包里可能还没有这个模块
    CLASS_MAP = {}
    POS_ORDER = ["内功", "轻功", "拳脚", "招架", "剑法", "刀法", "棍法",
                 "枪法", "鞭法", "斧法", "暗器", "双持", "乐器", "学识"]

OTHER = "其他"
ORDER = list(POS_ORDER) + [OTHER]

# 仅用于表里查不到位置时的兜底（顺序即优先级）
NAME_RULES = [
    ("招架", ("招架", "格挡", "御守", "铁布衫", "金钟罩")),
    ("剑法", ("剑",)),
    ("刀法", ("刀",)),
    ("棍法", ("棍", "杖")),
    ("枪法", ("枪",)),
    ("鞭法", ("鞭",)),
    ("斧法", ("斧", "锤", "戟", "钺")),
    ("暗器", ("暗器", "箭", "针", "镖")),
    ("拳脚", ("拳", "掌", "指", "爪", "抓", "腿", "脚", "手", "肘", "膝")),
    ("轻功", ("身法", "步", "轻功", "遁", "纵", "踏", "飞", "翔", "腾")),
    ("内功", ("心法", "内功", "神功", "真经", "心经", "禅", "罡", "周天",
              "元气", "真元", "吐纳", "内息", "功", "气")),
    ("学识", ("术", "书", "录", "谱", "篇", "章", "集", "曲", "音", "律",
              "经", "诀", "决", "阵", "图", "策", "弦", "奏", "琴", "棋", "藏")),
]

ID_RULES = [
    ("内功", ("heart", "internal", "meditation", "neigong", "sutra", "scripture")),
    ("轻功", ("step", "agility", "light", "cloud", "fly", "dash", "swift")),
    ("剑法", ("sword", "sowrd", "lswd")),
    ("刀法", ("blade", "saber", "knife")),
    ("棍法", ("staff", "club", "stick")),
    ("枪法", ("spear", "pike")),
    ("鞭法", ("whip",)),
    ("斧法", ("axe", "hammer", "halberd")),
    ("暗器", ("hidden", "dart", "needle", "bow", "arrow")),
    ("拳脚", ("fist", "palm", "claw", "finger", "leg", "foot", "kick",
              "elbow", "hand", "punch")),
    ("学识", ("book", "knowledge", "study", "music", "song", "poem", "scroll")),
]


def _fallback(name, sid):
    """表里没有位置信息时的关键词兜底。"""
    name = str(name or "")
    for cat, keys in NAME_RULES:
        if any(k in name for k in keys):
            return cat
    raw_id = str(sid or "")
    if any(c.isupper() for c in raw_id):     # 只看英文驼峰 id，拼音 id 不参与
        low = raw_id.lower()
        for cat, keys in ID_RULES:
            if any(k in low for k in keys):
                return cat
    return OTHER


def positions_of(skill):
    """返回该武学的所有可准备位置（列表，可能多个）。"""
    sid = str(skill.get("id") or "")
    raw = CLASS_MAP.get(sid)
    if raw:
        return [p for p in raw.split(",") if p]
    return [_fallback(skill.get("n"), sid)]


def group(skills):
    """按位置分组：[(位置, [武学...])]，多位置的武学会出现在多个组里。

    组内按等级降序、同级按名称；只返回非空组。
    """
    buckets = {}
    for s in skills or []:
        for pos in positions_of(s):
            buckets.setdefault(pos, []).append(s)
    out = []
    for pos in ORDER:
        items = buckets.pop(pos, None)
        if items:
            items.sort(key=lambda x: (-(x.get("lv") or 0), str(x.get("n") or "")))
            out.append((pos, items))
    for pos, items in buckets.items():       # ORDER 之外的兜底
        items.sort(key=lambda x: (-(x.get("lv") or 0), str(x.get("n") or "")))
        out.append((pos, items))
    return out


def _main():
    """生成校对表：按位置列出所有武学，并标出多位置。"""
    import json
    import os
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "names.json"), encoding="utf-8") as f:
        data = json.load(f)
    skills = [{"id": k, "n": v, "lv": 0} for k, v in (data.get("skills") or {}).items()]

    out = sys.stdout
    out.write("# 武学可准备位置表（按网页数据生成）\n\n")
    out.write("> 数据来源：https://whfie.github.io/fzjhskill/ 的 `public/data/skill.json.gz`\n")
    out.write("> 一门武学可以有多个位置，因此各组门数之和大于 774。\n")
    out.write("> 生成命令：`python scripts/build_skill_class.py --fetch`\n\n")

    multi = [s for s in skills if len(positions_of(s)) > 1]
    out.write("共 %d 门，其中多位置 %d 门。\n\n" % (len(skills), len(multi)))

    for pos, items in group(skills):
        out.write("## %s（%d 门）\n\n" % (pos, len(items)))
        for s in items:
            others = [p for p in positions_of(s) if p != pos]
            mark = ("（兼：%s）" % "、".join(others)) if others else ""
            out.write("- %s%s\n" % (s["n"], mark))
        out.write("\n")


if __name__ == "__main__":
    _main()
