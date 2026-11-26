# -*- coding: utf-8 -*-
"""解析本次要刷新的分区：cron → 分区 → 中文名。

以前这三段映射写在 `refresh.yml` 的两个 shell `case` 里，改 cron 必须同步改
`case` 和 `label`，漏一处就会静默跑错区（或落到兜底跑六区全量）。抽到这里
之后可以本地逐条验证，工作流只负责调用。

2026-11-26 起手动触发（workflow_dispatch）的 `server` 从 choice 改成 string，
支持逗号一次跑多个分区（看门狗用它把「所有过期分区」塞进一个 run，避免派 N 个 run
被 concurrency 组掐掉）。`--server` 早就支持逗号串，这里只负责把中文名拼对、
把写错的分区名挡下来。

用法（CI，stdout 直接追加到 $GITHUB_OUTPUT）：
  python scripts/plan_refresh.py --schedule "$SCHED" --mode "$MODE" --pick "$PICK" >> "$GITHUB_OUTPUT"

用法（本地核对）：
  python scripts/plan_refresh.py --schedule "0 20 * * *"
  python scripts/plan_refresh.py --mode full --pick taptap_4
  python scripts/plan_refresh.py --mode full --pick taptap_2,taptap_3
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 名人堂（游戏 boardType=4，指标=江湖阅历 yueli）单独一条定时任务，十一区一次抓全。
# 它和高手榜共用 fetch.py，但产出的是 hall.json，所以目标值用 "hall11" 这个标记，
# 由 refresh.yml 换成真实分区串（--server 支持逗号分隔），并带上 --board 4。
HALL_TARGET = "hall11"
HALL_KEYS = ("taptap", "taptap_2", "taptap_3", "taptap_4", "4399",
             "yyh", "guanfang", "huawei", "ios1", "ios2", "ios3")
HALL_BOARD = 4

# cron(UTC) → (目标分区, 中文名)；与 refresh.yml 的 schedule 列表一一对应
SCHEDULE_MAP = {
    "0 22 * * *": ("taptap", "苍松迎客"),
    "55 15 * * *": ("taptap_2,taptap_3", "白鹤+丹凤"),
    "0 20 * * *": ("yyh,ios1", "应用汇+老马识途"),   # 次日 04:00 北京时间
    "0 4 * * *": ("taptap_4", "墨羽惊鸿"),
    "0 10 * * *": ("4399", "4399"),
    "0 8 * * *": ("guanfang", "其他服"),     # 16:00 北京时间
    "0 18 * * *": ("huawei", "华为"),        # 次日 02:00 北京时间
    "0 0 * * *": ("ios2", "野马分鬃"),       # 08:00 北京时间
    "0 2 * * *": ("ios3", "仙人指路"),       # 10:00 北京时间
    "0 12 * * *": (HALL_TARGET, "名人堂（11 区）"),   # 20:00 北京时间
}

# 分区 → 中文名（提交信息与摘要用）。多区组合优先查这张表，
# 查不到再按单区名用 + 拼起来，所以原有的组合名（白鹤+丹凤）不会变。
LABELS = {
    "all": "全部",
    "taptap": "苍松迎客",
    "taptap_2,taptap_3": "白鹤+丹凤",
    "taptap_2": "白鹤亮翅",
    "taptap_3": "丹凤朝阳",
    "taptap_4": "墨羽惊鸿",
    "4399": "4399",
    "yyh": "应用汇",
    "guanfang": "其他服",
    "huawei": "华为",
    "ios1": "老马识途",
    "yyh,ios1": "应用汇+老马识途",
    "ios2": "野马分鬃",
    "ios3": "仙人指路",
    HALL_TARGET: "名人堂（11 区）",
}


def split_pick(pick):
    """把 "a, b ，c" 拆成 ['a','b','c']：容忍空格、中文逗号、顿号，去重保序。"""
    text = str(pick or "")
    for ch in ("，", "、", ";", "；"):
        text = text.replace(ch, ",")
    parts = []
    for raw in text.split(","):
        k = raw.strip()
        if k and k not in parts:
            parts.append(k)
    return parts


def label_for(parts):
    """给一组分区名拼中文名；顺带挡住写错的名字（免得静默抓 0 个区）。"""
    target = ",".join(parts)
    if target in LABELS:
        return LABELS[target]
    unknown = [k for k in parts if k not in LABELS]
    if unknown:
        raise SystemExit("未知分区：%s（可选：%s）" % (
            "、".join(unknown),
            "、".join(k for k in LABELS if k != "all")))
    return "+".join(LABELS[k] for k in parts)


def plan(schedule="", mode="", pick=""):
    """返回 (target, label)。空 mode 表示定时触发，按 cron 反查。"""
    if mode:
        parts = split_pick(pick)
        if not parts:
            return "all", LABELS["all"]
        if HALL_TARGET in parts and len(parts) > 1:
            # --board 是全局参数，一个 run 只能有一个 board，混跑会把高手榜抓成名人堂
            raise SystemExit("hall11 不能和其它分区混在一次运行里：--board 是全局参数，"
                             "要补名人堂请单独派发一次")
        return ",".join(parts), label_for(parts)
    # github.event.schedule 原样返回 cron，历史上出现过双空格
    key = " ".join((schedule or "").split())
    target = SCHEDULE_MAP.get(key, ("all", ""))[0]
    return target, LABELS.get(target, "全部")


def plan_full(schedule="", mode="", pick=""):
    """返回 (target, label, board, servers)。

    target 是「任务标记」（给 workflow 判断用，hall11 之类不能直接当分区名）；
    servers 才是可以喂给 --server 的分区串（逗号分隔，空表示全部）。
    board 是 game 的榜单编号：1=高手榜（默认），4=名人堂。
    """
    target, label = plan(schedule, mode, pick)
    if target == HALL_TARGET:
        return target, label, HALL_BOARD, ",".join(HALL_KEYS)
    return target, label, 1, target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--schedule", default="", help="github.event.schedule")
    ap.add_argument("--mode", default="", help="手动触发时的 mode（空=定时）")
    ap.add_argument("--pick", default="", help="手动触发时的 server（支持逗号多区）")
    a = ap.parse_args()

    target, label, board, servers = plan_full(a.schedule, a.mode, a.pick)
    print("target=%s" % target)
    print("label=%s" % label)
    print("board=%d" % board)
    print("servers=%s" % servers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
