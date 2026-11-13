# -*- coding: utf-8 -*-
"""武学分类：把「武学 N 门」按类型分组成 7 组。

游戏接口里每门武学只有 id / 名称 / 等级，**没有分类字段**，所以这里用两条线索
做初判：先看中文名后缀（剑法/掌/心法…），再看英文 id 关键词（Sword/Palm/Heart…）。
两条都对不上的落进「其他」，界面上照样能看到，只是不归类。

校对只改本文件：
  * NAME_RULES  按顺序匹配名称后缀，先命中先算；
  * ID_RULES    名称没命中时看英文 id；
  * OVERRIDES   点名指定，优先级最高（用来纠正自动判错的）。

生成校对表（列出全部武学及判定结果）：
    python skill_groups.py > ../docs/武学分类校对表.md
"""

ORDER = ["内功", "轻功", "拳脚", "兵器", "招架", "学识", "其他"]

# 名称关键词（按顺序匹配，先命中先算；越靠后越宽泛，用兜底）
NAME_RULES = [
    ("招架", ("招架", "格挡", "御守", "铁布衫", "金钟罩", "不坏身")),
    ("兵器", ("剑", "刀", "棍", "枪", "鞭", "锤", "匕", "斧", "戟", "钩", "笔",
              "弓", "箭", "暗器", "杖", "锏", "镗", "钺", "环", "轮", "杵", "刃")),
    ("拳脚", ("拳", "掌", "指", "爪", "抓", "腿", "脚", "手", "肘", "膝",
              "咬", "啄")),
    ("轻功", ("身法", "步", "轻功", "遁", "纵", "踏", "飞", "翔", "腾", "云",
              "烟", "影")),
    ("内功", ("心法", "内功", "神功", "真经", "心经", "禅", "罡", "周天",
              "元气", "真元", "吐纳", "内息")),
    ("学识", ("术", "书", "录", "谱", "篇", "章", "集", "曲", "音", "律",
              "经", "诀", "决", "阵", "图", "策", "弦", "奏", "琴", "棋", "藏",
              "册", "技", "义", "乐器", "乐", "箫", "笛", "鼓", "钟", "琶")),
    # 兜底：只剩「功 / 气 / 法」这类泛后缀的，按内功处理
    ("内功", ("功", "气", "法", "劲")),
]

# 英文 id 关键词（名称没命中时才用）
ID_RULES = [
    ("内功", ("heart", "internal", "meditation", "neigong", "sutra",
              "scripture", "breath")),
    ("招架", ("parry", "block", "guard", "shield")),
    ("轻功", ("step", "agility", "light", "cloud", "fly", "dash", "swift",
              "shadow", "wind", "sky")),
    ("兵器", ("sword", "sowrd", "blade", "saber", "staff", "spear", "whip",
              "hammer", "dagger", "axe", "bow", "arrow", "hook", "club",
              "pike", "pen", "lswd", "knife", "halberd", "mace")),
    ("拳脚", ("fist", "palm", "claw", "finger", "leg", "foot", "kick",
              "elbow", "hand", "strike", "punch", "snap")),
    ("学识", ("book", "knowledge", "study", "music", "song", "poem",
              "scroll", "classic", "array")),
]

# 点名纠正（名称 → 类型），优先级最高
OVERRIDES = {
    "八门气功": "内功",
    "何惧死": "内功",
    "无惧战": "拳脚",
    "不坏身": "招架",
    "独入黄泉": "拳脚",
    "红尘八音": "学识",
    "入阵曲": "学识",
}

_AMBIGUOUS_HINT = ("法", "功", "式", "招", "击", "绝", "学")


def group_of(name, sid=""):
    """返回 (分类, 置信度)。置信度 high=名称命中 / mid=仅英文命中 / low=都没命中。"""
    name = str(name or "")
    if name in OVERRIDES:
        return OVERRIDES[name], "high"
    for cat, keys in NAME_RULES:
        if any(k in name for k in keys):
            return cat, "high"
    # 拼音 id（如 jibenqinfa / wangshenggong）全小写无驼峰，关键词匹配会误伤，
    # 只对英文驼峰 id 用 ID 规则。
    raw_id = str(sid or "")
    low_id = raw_id.lower() if any(c.isupper() for c in raw_id) else ""
    if low_id:
        for cat, keys in ID_RULES:
            if any(k in low_id for k in keys):
                return cat, "mid"
    return "其他", "low"


def is_ambiguous(name):
    """名称只有「法 / 功 / 式」这类泛后缀——自动判定最容易错的一批。"""
    return str(name or "").endswith(_AMBIGUOUS_HINT)


def group(skills):
    """把 skills 列表分组成 [(分类, [items...])]，按 ORDER 排序，组内等级降序。"""
    buckets = {c: [] for c in ORDER}
    for s in skills or []:
        cat, _conf = group_of(s.get("n"), s.get("id"))
        buckets.setdefault(cat, []).append(s)
    out = []
    for c in ORDER:
        items = buckets.get(c) or []
        if not items:
            continue
        items.sort(key=lambda x: (-(x.get("lv") or 0), str(x.get("n") or "")))
        out.append((c, items))
    # ORDER 之外的分类（理论上没有）兜底追加
    for c, items in buckets.items():
        if c not in ORDER and items:
            items.sort(key=lambda x: (-(x.get("lv") or 0), str(x.get("n") or "")))
            out.append((c, items))
    return out


def _main():
    import io
    import json
    import os
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    with io.open(os.path.join(here, "names.json"), encoding="utf-8") as f:
        data = json.load(f)
    skills = [{"id": k, "n": v, "lv": 0} for k, v in (data.get("skills") or {}).items()]
    out = sys.stdout
    out.write("# 武学分类校对表\n\n")
    out.write("> 自动初判结果，按类型分组。带 ⚠️ 的是泛后缀（法/功/式…）判定，最容易错。\n")
    out.write("> 改 `apk/skill_groups.py` 里的 `OVERRIDES`（点名）或 `NAME_RULES`（规则）即可。\n\n")
    total = 0
    for cat, items in group(skills):
        total += len(items)
        out.write("## %s（%d 门）\n\n" % (cat, len(items)))
        for s in items:
            mark = " ⚠️" if is_ambiguous(s["n"]) else ""
            out.write("- %s%s\n" % (s["n"], mark))
        out.write("\n")
    out.write("\n合计 %d 门\n" % total)


if __name__ == "__main__":
    _main()
