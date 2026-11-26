# -*- coding: utf-8 -*-
"""解析本次要刷新的分区：cron → 分区 → 中文名。

以前这三段映射写在 `refresh.yml` 的两个 shell `case` 里，改 cron 必须同步改
`case` 和 `label`，漏一处就会静默跑错区（或落到兜底跑六区全量）。抽到这里
之后可以本地逐条验证，工作流只负责调用。

2026-11-26 起手动触发（workflow_dispatch）的 `server` 从 choice 改成 string，
支持逗号一次跑多个分区（看门狗用它把「所有过期分区」塞进一个 run，避免派 N 个 run
被 concurrency 组掐掉）。`--server` 早就支持逗号串，这里只负责把中文名拼对、
把写错的分区名挡下来。

2026-11-26 稍晚：名人堂十一区一次抓全在 CI 里会超时，拆成三批（北京 20:00 / 20:20 / 20:40，
标记 hall_b1 / hall_b2 / hall_b3），每批 board 恒为 4；hall11 = 十一区全集，只作向后兼容保留
（watchdog 派发与历史记录还在用）。看门狗补跑时允许把多批合并成一次 run。

用法（CI，stdout 直接追加到 $GITHUB_OUTPUT）：
  python scripts/plan_refresh.py --schedule "$SCHED" --mode "$MODE" --pick "$PICK" >> "$GITHUB_OUTPUT"

用法（本地核对）：
  python scripts/plan_refresh.py --schedule "0 20 * * *"
  python scripts/plan_refresh.py --schedule "20 12 * * *"
  python scripts/plan_refresh.py --mode full --pick taptap_4
  python scripts/plan_refresh.py --mode full --pick taptap_2,taptap_3
  python scripts/plan_refresh.py --mode full --pick hall_b1,hall_b2
"""
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 名人堂（游戏 boardType=4，指标=江湖阅历 yueli）和高手榜共用 fetch.py，
# 但产出的是 hall.json，所以目标值用「任务标记」，由 refresh.yml 换成真实分区串
# （--server 支持逗号分隔），并带上 --board 4。
#
# 2026-11-26：十一区一次抓全在 CI 里会超时，所以拆成三批（北京 20:00 / 20:20 / 20:40）。
# 每批仍是 board=4，只是分区串不同；看门狗补跑时允许多批合并成一次 run
# （--pick "hall_b1,hall_b2"，board 仍恒为 4）。
# 标记 hall11 = 11 区全集，保留向后兼容（watchdog 派发与历史记录还在用）。
HALL_TARGET = "hall11"
HALL_KEYS = ("taptap", "taptap_2", "taptap_3", "taptap_4", "4399",
             "yyh", "guanfang", "huawei", "ios1", "ios2", "ios3")
HALL_BATCHES = {
    "hall_b1": ("taptap", "taptap_2", "taptap_3", "taptap_4"),
    "hall_b2": ("4399", "yyh", "guanfang", "huawei"),
    "hall_b3": ("ios1", "ios2", "ios3"),
}
HALL_BOARD = 4


def is_hall_marker(name):
    """是不是名人堂任务标记（hall11 全集，或 hall_b1/b2/b3 某批）。"""
    return name == HALL_TARGET or name in HALL_BATCHES


def hall_keys_for(parts):
    """一组 hall 标记 → 分区串（逗号分隔，按 HALL_BATCHES 定义顺序去重保序）。

    hall11 是全集，混在 parts 里时直接返回 11 区。
    """
    if HALL_TARGET in parts:
        return ",".join(HALL_KEYS)
    keys = []
    for batch in HALL_BATCHES:
        if batch in parts:
            for k in HALL_BATCHES[batch]:
                if k not in keys:
                    keys.append(k)
    return ",".join(keys)


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
    "0 12 * * *": ("hall_b1", "名人堂·第1批"),       # 20:00 北京时间
    "20 12 * * *": ("hall_b2", "名人堂·第2批"),      # 20:20 北京时间
    "40 12 * * *": ("hall_b3", "名人堂·第3批"),      # 20:40 北京时间
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
    "hall_b1": "名人堂·第1批",
    "hall_b2": "名人堂·第2批",
    "hall_b3": "名人堂·第3批",
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
        hall = [k for k in parts if is_hall_marker(k)]
        if hall and len(hall) != len(parts):
            # --board 是全局参数，一个 run 只能有一个 board，混跑会把高手榜抓成名人堂。
            # 多个 hall 标记可以合并（看门狗补跑），但绝不能掺普通分区。
            raise SystemExit("hall 标记（%s）不能和普通分区混在一次运行里：--board 是全局参数，"
                             "每个 run 只能有一个 board；名人堂请单独派发一次"
                             % "、".join(hall))
        return ",".join(parts), label_for(parts)
    # github.event.schedule 原样返回 cron，历史上出现过双空格
    key = " ".join((schedule or "").split())
    target = SCHEDULE_MAP.get(key, ("all", ""))[0]
    return target, LABELS.get(target, "全部")


def plan_full(schedule="", mode="", pick=""):
    """返回 (target, label, board, servers)。

    target 是「任务标记」（给 workflow 判断用，hall11 / hall_b1 之类不能直接当分区名）；
    servers 才是可以喂给 --server 的分区串（逗号分隔，空表示全部）。
    board 是 game 的榜单编号：1=高手榜（默认），4=名人堂。
    多个批次标记合并时 servers 取并集，board 仍恒为 4。
    """
    target, label = plan(schedule, mode, pick)
    parts = [k for k in target.split(",") if k]
    if parts and all(is_hall_marker(k) for k in parts):
        return target, label, HALL_BOARD, hall_keys_for(parts)
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
