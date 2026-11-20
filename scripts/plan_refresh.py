# -*- coding: utf-8 -*-
"""解析本次要刷新的分区：cron → 分区 → 中文名。

以前这三段映射写在 `refresh.yml` 的两个 shell `case` 里，改 cron 必须同步改
`case` 和 `label`，漏一处就会静默跑错区（或落到兜底跑六区全量）。抽到这里
之后可以本地逐条验证，工作流只负责调用。

用法（CI，stdout 直接追加到 $GITHUB_OUTPUT）：
  python scripts/plan_refresh.py --schedule "$SCHED" --mode "$MODE" --pick "$PICK" >> "$GITHUB_OUTPUT"

用法（本地核对）：
  python scripts/plan_refresh.py --schedule "0 20 * * *"
  python scripts/plan_refresh.py --mode full --pick taptap_4
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

# 分区 → 中文名（提交信息与摘要用）
LABELS = {
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


def plan(schedule="", mode="", pick=""):
    """返回 (target, label)。空 mode 表示定时触发，按 cron 反查。"""
    if mode:
        target = (pick or "all").strip() or "all"
    else:
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
    ap.add_argument("--pick", default="", help="手动触发时的 server")
    a = ap.parse_args()

    target, label, board, servers = plan_full(a.schedule, a.mode, a.pick)
    print("target=%s" % target)
    print("label=%s" % label)
    print("board=%d" % board)
    print("servers=%s" % servers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
