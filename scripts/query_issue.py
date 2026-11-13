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
# 原实现每次重试都重新握手。这里改成复用会话（省一次握手），
# 但**超时必须给足**：游戏服务器对机房 IP 响应很慢，单次请求常要 10–20 秒。
ATTEMPT_TIMEOUT = 25.0    # 单次尝试（握手+查询）硬超时
ATTEMPT_MAX = 3
DEADLINE = 75.0           # 查询阶段总预算
EMPTY_RETRY = 2           # errcode=0 但 data 为空时，先当作「可能被限流」再试几次

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
    """只查指定分区。

    重要：账号被限流时游戏接口**不一定**回 20616，也可能回 errcode=0 + data 为空。
    所以「空数据」不能立刻判定成「这个区没有这个人」，必须先多试一次，
    否则会把限流误报成「分区选错了」。
    """
    t0 = time.time()
    empties = 0
    for attempt in range(ATTEMPT_MAX):
        data, ec = L.try_one(srv, uid, hotver)
        if data:
            return L._finish(uid, srv, data, cache, hotver, note)
        if ec == 0:
            empties += 1
            cache["_empty"] = empties
            if empties >= EMPTY_RETRY:
                cache["_last_ec"] = 0
                return None                   # 连续两次明确回「没有这个角色」
            time.sleep(1.0)
            continue
        cache["_last_ec"] = ec
        if ec not in (20616, -1):
            break
        cache["_limited"] = ec
        if attempt < ATTEMPT_MAX - 1 and time.time() - t0 < DEADLINE:
            time.sleep(1.2 * (attempt + 1))
    return None


L.try_one = _fast_try_one
L._lookup_single = _fast_single


def fmt(v, suffix=""):
    if v is None or v == "":
        return "—"
    return "%s%s" % (v, suffix)


def build_markdown(prof, elapsed, arch="off"):
    # 完整档案（HTML 注释，页面上看不见），查询页直接拿它渲染，不用去评论区
    payload = dict(prof)
    payload["ms"] = int((elapsed or 0) * 1000)
    lines = [
        "<!--FZJHJSON %s-->" % json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
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


def board_snapshot(server, uid):
    """本地榜单快照：接口拿不到数据时，用它验证「分区到底对不对」。

    返回 (行, 榜单更新时间)；没命中返回 (None, 更新时间或 None)。
    """
    p = os.path.join(ROOT, "data", "servers", server, "gaoshoubang.json")
    try:
        with open(p, encoding="utf-8") as f:
            b = json.load(f)
    except Exception:
        return None, None
    at = b.get("updatedAt")
    for r in b.get("rows") or []:
        if str(r.get("userid")) == str(uid):
            return r, at
    return None, at


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
    cache = {}
    if not err:
        try:
            cfg = {"servers": servers, "hotver": int(os.environ.get("FZJH_HOTVER") or 18464)}
            prof = L.lookup(uid, server=server, cfg=cfg, cache=cache)
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)

    elapsed = time.time() - t0
    srv_name = (by_key.get(server) or {}).get("name") or server

    if prof:
        arch = archive(prof)
        print("归档结果：%s" % arch)
        body = build_markdown(prof, elapsed, arch)
    elif err:
        body = "## 查询失败\n\n```\n%s\n```\n\n---\nGitHub Actions 执行异常，稍后重试或检查 Secrets。" % err
    else:
        board, board_at = board_snapshot(server, uid)
        ec = cache.get("_limited") or cache.get("_last_ec")
        if cache.get("_limited"):
            head = "## 接口繁忙（errcode `%s`）" % ec
            why = "游戏接口正在限流，这次没能拿到实时数据。"
        elif cache.get("_empty"):
            head = "## 接口返回空数据"
            why = "游戏接口回了 `errcode=0` 但内容是空的——这是账号被限流时的另一种表现，不代表查无此人。"
        else:
            head = "## 没查到"
            why = "游戏接口没有返回这个角色的数据。"

        if board:
            # 榜单里有这个人 → 分区和 UID 都是对的，问题在接口
            row = [
                head,
                "",
                "**分区和 UID 都是对的**：`%s` 确实在「%s」的榜单上（第 %s 名）。" % (
                    board.get("name") or uid, srv_name, board.get("rank") or "—"),
                "",
                why,
                "",
                "**等 1–2 分钟再提交一次**。如果连续几次都是这个结果，说明这个查询账号的接口配额接近上限了"
                "（每天 12:00、18:00 的榜单抓取会消耗大量配额，机房 IP 也更容易被限）。"
                "想立刻拿到实时数据，用 APK 查——它走你自己的网络，不受机房 IP 限流影响。",
                "",
                "下面是榜单快照（%s），仅供参考：" % (board_at or "时间未知"),
                "",
                "| 项目 | 值 |",
                "|---|---|",
                "| 昵称 | **%s** |" % (board.get("name") or "—"),
                "| 分区 | %s（`%s`） |" % (srv_name, server),
                "| UID | `%s` |" % uid,
                "| 等级 | %s |" % fmt(board.get("lv")),
                "| 门派 | %s |" % fmt(board.get("menpai")),
                "| 经验 | %s |" % L.fmt_big(board.get("exp")),
                "| 武学造诣 | %s |" % fmt(board.get("kongfu")),
                "| 福缘 | %s |" % fmt(board.get("fuyuan")),
                "| 排名 | %s |" % ("第 %s 名" % board["rank"] if board.get("rank") else "—"),
                "| 传承 | %s |" % fmt(board.get("inheritCount"), " 世"),
                "",
                "---",
                "GitHub Actions 实时查询",
            ]
            # 给查询页一个可渲染的摘要（不带 skills，前端会自动走摘要网格）
            snap = {
                "uid": uid,
                "n": board.get("name"),
                "s": server,
                "sn": srv_name,
                "lv": board.get("lv"),
                "m": board.get("menpai"),
                "exp": board.get("exp"),
                "k": board.get("kongfu"),
                "fy": board.get("fuyuan"),
                "r": board.get("rank"),
                "ic": board.get("inheritCount"),
                "at": board_at,
                "stale": True,
                "ms": int(elapsed * 1000),
            }
            body = "<!--FZJHJSON %s-->\n%s" % (
                json.dumps(snap, ensure_ascii=False, separators=(",", ":")),
                "\n".join(row),
            )
        else:
            body = (
                "%s\n\n"
                "UID `%s` 在「%s」没有查到。可能是：\n\n"
                "- **分区选错了**——换个区再试（自动匹配已停用，必须选对区）\n"
                "- UID 写错（应为游戏个人信息页里的 5–12 位角色 ID）\n"
                "- 角色不在任何已收录的榜单里，且接口正忙\n\n"
                "---\nGitHub Actions 实时查询"
                % (head, uid, srv_name)
            )

    post(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
