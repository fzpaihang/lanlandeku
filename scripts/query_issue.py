#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Issue 驱动的实时查询。

网页把 UID 拼成 Issue 标题提交，本脚本由 .github/workflows/query.yml 触发：
    标题：[QUERY] 7257325   或   [QUERY] 7257325 @taptap
    流程：解析 → 调游戏接口（握手 + get_user_info）→ 回帖结果 → 关闭 Issue

环境变量（workflow 注入）：
    ISSUE_TITLE / ISSUE_NUMBER / GH_TOKEN / FZJH_SERVERS / FZJH_HOTVER
"""
import json
import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apk"))
sys.path.insert(0, os.path.join(ROOT, "cloud"))

import lookup_core as L  # noqa: E402
import fetch as F        # noqa: E402
from archive_name import archive  # noqa: E402

L.CACHE_PATH = "/tmp/fzjh_issue_cache.json"

TITLE_RE = re.compile(r"^\[QUERY\]\s*(\d{5,12})(?:\s*@\s*([A-Za-z0-9_]+))?", re.I)


def fmt(v, suffix=""):
    if v is None or v == "":
        return "—"
    return "%s%s" % (v, suffix)


def build_markdown(prof, elapsed, arch="off"):
    lines = [
        "## 查询成功",
        "",
        "| 项目 | 值 |",
        "|---|---|",
        "| 昵称 | **%s** |" % (prof.get("name") or "—"),
        "| 分区 | %s（`%s`） |" % (prof.get("serverName") or "—", prof.get("server") or "—"),
        "| UID | `%s` |" % prof.get("uid"),
        "| 等级 | %s |" % fmt(prof.get("lv"), "（经验反算）" if prof.get("lvEstimated") else ""),
        "| 门派 | %s |" % fmt(prof.get("menpai")),
        "| 经验 | %s |" % L.fmt_big(prof.get("exp")),
        "| 武学造诣 | %s |" % fmt(prof.get("kongfu")),
        "| 福缘 | %s |" % fmt(prof.get("fuyuan")),
        "| 排名 | %s |" % ("第 %s 名" % prof["rank"] if prof.get("rank") else "未上榜"),
        "| 传承 | %s |" % fmt(prof.get("inheritCount"), " 世"),
        "| 武学 | %s 门 |" % len(prof.get("skills") or []),
        "| 装备 | %s 件 |" % len(prof.get("equips") or []),
        "",
        "查询耗时 **%.1f 秒** · 数据时间 %s" % (elapsed, prof.get("fetchedAt") or "—"),
    ]

    prepared = prof.get("prepared") or {}
    if prepared:
        lines += ["", "<details><summary>准备位 %d 个</summary>" % len(prepared), ""]
        for k, v in prepared.items():
            lines.append("- %s：%s" % (k, v))
        lines += ["", "</details>"]

    history = prof.get("history") or []
    if history:
        names = " → ".join([history[0].get("p") or "初代"] + [x.get("n") or "—" for x in history])
        lines += ["", "<details><summary>传承历程</summary>", "", names, "", "</details>"]

    ARCH_TXT = {
        "ok": "✅ 已收录进昵称索引，下次可直接用昵称搜到",
        "same": "已在昵称索引里，无需重复收录",
        "off": "未配置归档（缺 GH_TOKEN / GH_REPO）",
        "skip": "档案缺少 uid 或昵称，未收录",
        "full": "昵称索引已满（5000 条），本次未收录",
        "conflict": "归档写入冲突，下次查询会重试",
    }
    if arch in ARCH_TXT:
        tail = ARCH_TXT[arch]
    elif str(arch).startswith("http"):
        tail = "归档失败（GitHub 返回 %s），检查 GH_TOKEN 的 Contents 权限" % str(arch)[4:]
    else:
        tail = "归档失败：%s" % arch

    lines += [
        "",
        "---",
        "由 GitHub Actions 实时查询，结果仅供娱乐参考。",
        "",
        "**昵称索引**：%s" % tail,
    ]
    return "\n".join(lines)


def gh(*args):
    subprocess.run(["gh"] + list(args), check=True)


def main():
    title = (os.environ.get("ISSUE_TITLE") or "").strip()
    number = os.environ.get("ISSUE_NUMBER") or ""
    m = TITLE_RE.match(title)
    if not m:
        print("标题格式不匹配，跳过：%r" % title)
        return 0

    uid = int(m.group(1))
    server = (m.group(2) or L.AUTO_SERVER).lower()
    print("解析：uid=%s server=%s issue=#%s" % (uid, server, number))

    t0 = time.time()
    try:
        servers = F.load_servers()
        by_key = {s["key"]: s for s in servers}
        if server not in ("auto", "all") and server not in by_key:
            server = L.AUTO_SERVER
        cfg = {"servers": servers, "hotver": int(os.environ.get("FZJH_HOTVER") or 18464)}
        prof = L.lookup(uid, server=server, cfg=cfg, cache={})
    except SystemExit as e:
        prof = None
        err = "配置缺失：%s" % e
    except Exception as e:
        prof = None
        err = "%s: %s" % (type(e).__name__, e)
    else:
        err = None

    elapsed = time.time() - t0

    if prof:
        arch = archive(prof)
        print("归档结果：%s" % arch)
        body = build_markdown(prof, elapsed, arch)
    elif err:
        body = "## 查询失败\n\n```\n%s\n```\n\n---\nGitHub Actions 执行异常，稍后重试或检查 Secrets。" % err
    else:
        body = (
            "## 没查到\n\n"
            "UID `%s` 在自动模式下没有命中。可能是：\n\n"
            "- UID 写错（应为游戏个人信息页里的 5–12 位角色 ID）\n"
            "- 角色在其他分区，换个分区再试（在标题后加 `@taptap_3` 这种后缀）\n\n"
            "---\nGitHub Actions 实时查询" % uid
        )

    with open("/tmp/issue-comment.md", "w", encoding="utf-8") as f:
        f.write(body)
    gh("issue", "comment", str(number), "--body-file", "/tmp/issue-comment.md")
    print("已回帖")
    return 0


if __name__ == "__main__":
    sys.exit(main())
