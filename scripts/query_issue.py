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
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apk"))
sys.path.insert(0, os.path.join(ROOT, "cloud"))

import lookup_core as L  # noqa: E402
import fetch as F        # noqa: E402
from archive_name import archive  # noqa: E402

L.CACHE_PATH = "/tmp/fzjh_issue_cache.json"

TITLE_RE = re.compile(r"^\[QUERY\]\s*(\d{5,12})(?:\s*@\s*([A-Za-z0-9_]+))?", re.I)

# ---------------------------------------------------------------- 加速
# 原实现每次重试都重新握手，且单次请求最长等 25 秒——Actions 机房 IP 被限流时
# 一次查询能拖到 40 秒以上。这里改成：复用会话 + 每次请求硬超时 + 短退避。
ATTEMPT_TIMEOUT = 8.0     # 单次尝试（握手+查询）硬超时
ATTEMPT_MAX = 3
DEADLINE = 32.0           # 查询阶段总预算

_KEYS = {}
KEYS_TTL = 180


def _hard_timeout(fn, seconds, default=None):
    box = {}

    def run():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(seconds)
    if th.is_alive():
        return default
    return box.get("v", default)


def _fast_try_one(srv, uid, hotver):
    """与 L.try_one 等价，但复用握手会话，并给整次尝试加硬超时。"""
    srv = dict(srv)
    srv["hotver"] = hotver
    cfg = F.server_cfg(srv)
    key = srv["key"]

    def _do():
        rec = _KEYS.get(key)
        if rec and time.time() - rec[0] < KEYS_TTL:
            keys = rec[1]
        else:
            keys = F.handshake(cfg, time.time())
            _KEYS[key] = (time.time(), keys)
        return F.api_post(cfg, "get_user_info", {"userid": uid, "type": 0}, keys, time.time())

    d = _hard_timeout(_do, ATTEMPT_TIMEOUT, None)
    if d is None:
        _KEYS.pop(key, None)      # 会话可能已失效，下次重新握手
        return None, -1
    data = d.get("data")
    ec = d.get("errcode")
    if ec == 0 and isinstance(data, dict) and data.get("name"):
        return data, 0
    if ec == 20616:
        _KEYS.pop(key, None)
    return None, ec


def _fast_single(uid, srv, cache, hotver, note):
    """重试策略：最多 3 次，退避 0.8/1.5 秒，总时长不超过 DEADLINE。"""
    t0 = time.time()
    for attempt in range(ATTEMPT_MAX):
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, note)
        if ec == 0:
            return None                       # 服务端明确回「没有这个角色」
        if ec not in (20616, -1):
            break
        cache["_limited"] = ec
        if attempt < ATTEMPT_MAX - 1 and time.time() - t0 < DEADLINE:
            time.sleep(0.8 + attempt * 0.7)
    return None


L.try_one = _fast_try_one
L._lookup_single = _fast_single


def fmt(v, suffix=""):
    if v is None or v == "":
        return "—"
    return "%s%s" % (v, suffix)


def build_markdown(prof, elapsed, arch="off"):
    # 机器可读的摘要（HTML 注释，页面上看不见），查询页靠它回显结果
    meta = {
        "uid": prof.get("uid"),
        "n": prof.get("name"),
        "s": prof.get("server"),
        "sn": prof.get("serverName"),
        "lv": prof.get("lv"),
        "m": prof.get("menpai"),
        "exp": prof.get("exp"),
        "k": prof.get("kongfu"),
        "fy": prof.get("fuyuan"),
        "r": prof.get("rank"),
        "ic": prof.get("inheritCount"),
        "sk": len(prof.get("skills") or []),
        "eq": len(prof.get("equips") or []),
        "at": prof.get("fetchedAt"),
        "ms": int((elapsed or 0) * 1000),
    }
    lines = [
        "<!--FZJHJSON %s-->" % json.dumps(meta, ensure_ascii=False, separators=(",", ":")),
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
    server = (m.group(2) or "").strip().lower()
    print("解析：uid=%s server=%r issue=#%s" % (uid, server, number))

    t0 = time.time()

    servers, cfg_err = [], None
    try:
        servers = F.load_servers()
    except SystemExit as e:
        cfg_err = "配置缺失：%s" % e
    except Exception as e:
        cfg_err = "%s: %s" % (type(e).__name__, e)
    by_key = {s["key"]: s for s in servers}

    def post(body):
        with open("/tmp/issue-comment.md", "w", encoding="utf-8") as f:
            f.write(body)
        gh("issue", "comment", str(number), "--body-file", "/tmp/issue-comment.md")
        print("已回帖")

    # 自动匹配已停用：标题必须带 @分区，否则不发起任何请求
    if not cfg_err and (not server or server in ("auto", "all") or server not in by_key):
        lines = [
            "## 请先选择分区",
            "",
            "自动匹配已停用，标题需要带上分区，例如：",
            "",
            "`[QUERY] %s @taptap_3`" % uid,
            "",
            "可选分区：",
            "",
        ]
        lines += ["- `%s` %s" % (s["key"], s["name"]) for s in servers]
        lines += ["", "---", "GitHub Actions 实时查询"]
        post("\n".join(lines))
        return 0

    prof, err = None, cfg_err
    if not err:
        try:
            cfg = {"servers": servers, "hotver": int(os.environ.get("FZJH_HOTVER") or 18464)}
            prof = L.lookup(uid, server=server, cfg=cfg, cache={})
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)

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
            "UID `%s` 在「%s」没有查到。可能是：\n\n"
            "- **分区选错了**——换个区再试（自动匹配已停用，必须选对区）\n"
            "- UID 写错（应为游戏个人信息页里的 5–12 位角色 ID）\n\n"
            "---\nGitHub Actions 实时查询"
            % (uid, (by_key.get(server) or {}).get("name") or server)
        )

    post(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
