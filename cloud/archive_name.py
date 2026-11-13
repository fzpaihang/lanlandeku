# -*- coding: utf-8 -*-
"""把 uid → 昵称 归档进 data/extra-names.json（GitHub Contents API）。

两处复用，保证只有一份实现：
    scripts/query_issue.py   Issue 查询成功后归档
    api/query.py             Vercel 函数查询成功后归档（当前暂不可达，保留）

环境变量：
    GH_TOKEN  需要 Contents: Read and write
    GH_REPO   owner/name，如 fzpaihang/lanlandeku

返回值（字符串，便于直接回显）：
    ok        新增或更新成功
    same      昵称没变，未产生提交
    off       没配置 token/repo
    skip      缺少 uid 或昵称
    full      已达条目上限
    http4xx   接口报错
    <异常名>  其它异常
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

GH_PATH = "data/extra-names.json"
GH_MAX_ITEMS = 5000      # 约 300 KB，前端一次加载还能接受
TIMEOUT = 8


def _gh(method, url, payload=None, token="", ctx=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "fzjh-archive")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def archive(prof, token=None, repo=None, ctx=None):
    token = token or os.environ.get("GH_TOKEN") or ""
    repo = repo or os.environ.get("GH_REPO") or ""
    if not token or not repo:
        return "off"

    uid = str(prof.get("uid") or "")
    name = (prof.get("name") or "").strip()
    if not uid or not name:
        return "skip"

    url = "https://api.github.com/repos/%s/contents/%s" % (repo, GH_PATH)
    rec = {
        "u": int(uid) if uid.isdigit() else uid,
        "n": name,
        "s": prof.get("server") or "",
        "sn": prof.get("serverName") or "",
        "lv": prof.get("lv"),
        "ts": int(time.time()),
    }

    for attempt in range(2):
        try:
            sha = None
            db = {"items": []}
            try:
                cur = _gh("GET", url + "?ref=main", token=token, ctx=ctx)
                sha = cur.get("sha")
                db = json.loads(base64.b64decode(cur.get("content") or "").decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise

            items = db.get("items") or []
            hit = next((x for x in items if str(x.get("u")) == uid), None)
            if hit:
                if (hit.get("n") or "") == name:
                    return "same"
                alias = [a for a in (hit.get("a") or []) if a]
                if hit.get("n") and hit["n"] not in alias:
                    alias.append(hit["n"])
                hit.update(rec)
                hit["a"] = alias[-3:]        # 改名后老昵称仍可搜到，只留最近 3 个
            else:
                if len(items) >= GH_MAX_ITEMS:
                    return "full"
                items.append(rec)

            db["items"] = items
            db["count"] = len(items)
            db["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
            body = {
                "message": "归档昵称：%s（%s）" % (name, uid),
                "content": base64.b64encode(
                    json.dumps(db, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).decode("ascii"),
                "branch": "main",
            }
            if sha:
                body["sha"] = sha
            _gh("PUT", url, body, token=token, ctx=ctx)
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt == 0:
                time.sleep(0.6)          # 并发提交撞车，重读一次再写
                continue
            return "http%d" % e.code
        except Exception as e:
            return type(e).__name__
    return "conflict"
