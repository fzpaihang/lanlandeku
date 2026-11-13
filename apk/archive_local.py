# -*- coding: utf-8 -*-
"""查询结果先落本地，再尝试写回仓库（uid → 昵称 累积）。

设计目标和取舍：
  * 本地记账是「必须成功」的那一步，写网络是「尽力而为」；
  * 只要 GitHub 可达就自动入库，不可达就攒着，下次启动/下次查询再补；
  * 回写失败绝不影响查询结果的展示。

凭据：gh.json（打包时从 GitHub Secret 注入，不进仓库）
      {"token": "gho_xxx", "repo": "owner/name"}
"""
import base64
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request

import lookup_core as L

DATA_DIR = getattr(L, "DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
PENDING = os.path.join(DATA_DIR, "pending_names.jsonl")
GH_PATH = "data/extra-names.json"
MAX_PENDING = 200
MAX_ITEMS = 5000
TIMEOUT = 12

_CTX = None
try:
    import ssl
    _CTX = ssl.create_default_context()
    _CTX.check_hostname = False
    _CTX.verify_mode = ssl.CERT_NONE
except Exception:
    pass

_lock = threading.Lock()
_syncing = False
_last_result = ""


# ---------------------------------------------------------------- 凭据

def _cred():
    """返回 (token, repo)；没配置就返回 ("", "")。

    热更后本模块在 live/ 里，凭据却在 app 私有目录，所以要复用 lookup_core 的查找逻辑。
    """
    paths = []
    try:
        paths.append(L._find("gh.json"))
    except Exception:
        pass
    for d in (getattr(L, "BASE", DATA_DIR), DATA_DIR):
        paths.append(os.path.join(d, "gh.json"))
    for p in paths:
        try:
            with io.open(p, encoding="utf-8") as f:
                j = json.load(f)
            tok = (j.get("token") or "").strip()
            repo = (j.get("repo") or "").strip()
            if tok and repo:
                return tok, repo
        except Exception:
            continue
    return "", ""


def configured():
    return bool(_cred()[0])


# ---------------------------------------------------------------- 本地记账

def _read_pending():
    out = []
    try:
        with io.open(PENDING, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return out


def _write_pending(items):
    # 原子替换：这里存的是「还没提交到仓库的昵称」，写一半被杀就永久丢记录
    tmp = PENDING + ".tmp"
    try:
        with io.open(tmp, "w", encoding="utf-8", newline="\n") as f:
            for it in items[-MAX_PENDING:]:
                f.write(json.dumps(it, ensure_ascii=False, separators=(",", ":")) + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(tmp, PENDING)
    except Exception:
        try:
            os.remove(tmp)
        except Exception:
            pass


def pending_count():
    return len(_read_pending())


def record(prof):
    """查询成功后记一条。同 uid 覆盖，保留最新昵称。"""
    uid = str((prof or {}).get("uid") or "").strip()
    name = str((prof or {}).get("name") or "").strip()
    if not uid or not name:
        return False
    item = {
        "u": int(uid) if uid.isdigit() else uid,
        "n": name,
        "s": prof.get("server") or "",
        "sn": prof.get("serverName") or "",
        "lv": prof.get("lv"),
        "ts": int(time.time()),
    }
    with _lock:
        items = _read_pending()
        items = [x for x in items if str(x.get("u")) != uid]
        items.append(item)
        _write_pending(items)
    return True


# ---------------------------------------------------------------- 同步

def _gh(method, url, payload, token):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "fzjh-apk")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def sync_once():
    """同步一次。返回 ok / off / empty / http4xx / 异常名。"""
    global _last_result
    token, repo = _cred()
    if not token or not repo:
        _last_result = "off"
        return "off"

    with _lock:
        items = _read_pending()
    if not items:
        _last_result = "empty"
        return "empty"

    url = "https://api.github.com/repos/%s/contents/%s" % (repo, GH_PATH)

    for attempt in range(2):
        try:
            sha = None
            db = {"items": []}
            try:
                cur = _gh("GET", url + "?ref=main", None, token)
                sha = cur.get("sha")
                db = json.loads(base64.b64decode(cur.get("content") or "").decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise

            server_items = db.get("items") or []
            by_uid = {}
            for x in server_items:
                by_uid[str(x.get("u"))] = x

            added = 0
            for rec in items:
                uid = str(rec.get("u"))
                name = rec.get("n") or ""
                hit = by_uid.get(uid)
                if hit:
                    if (hit.get("n") or "") == name:
                        continue
                    alias = [a for a in (hit.get("a") or []) if a]
                    if hit.get("n") and hit["n"] not in alias:
                        alias.append(hit["n"])
                    hit.update(rec)
                    hit["a"] = alias[-3:]
                else:
                    if len(server_items) >= MAX_ITEMS:
                        continue
                    server_items.append(rec)
                    added += 1
            if not added and all((by_uid.get(str(r.get("u"))) or {}).get("n") == r.get("n") for r in items):
                # 全部已在仓库里且昵称一致，只需清掉本地记录
                with _lock:
                    _write_pending([])
                _last_result = "ok"
                return "ok"

            db["items"] = server_items
            db["count"] = len(server_items)
            db["updatedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
            body = {
                "message": "APK 归档昵称 %d 条" % len(items),
                "content": base64.b64encode(
                    json.dumps(db, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                ).decode("ascii"),
                "branch": "main",
            }
            if sha:
                body["sha"] = sha
            _gh("PUT", url, body, token)

            with _lock:
                left = [x for x in _read_pending()
                        if str(x.get("u")) not in set(str(r.get("u")) for r in items)]
                _write_pending(left)
            _last_result = "ok"
            return "ok"
        except urllib.error.HTTPError as e:
            if e.code == 409 and attempt == 0:
                time.sleep(0.8)
                continue
            _last_result = "http%d" % e.code
            return _last_result
        except Exception as e:
            _last_result = type(e).__name__
            return _last_result
    _last_result = "conflict"
    return "conflict"


def sync_async(on_done=None):
    """后台同步，多个查询同时触发也只跑一个。"""
    global _syncing
    if _syncing:
        return
    _syncing = True

    def run():
        global _syncing
        try:
            r = sync_once()
        except Exception:
            r = "error"
        _syncing = False
        if on_done:
            try:
                on_done(r, pending_count())
            except Exception:
                pass

    threading.Thread(target=run, daemon=True).start()


def last_result():
    return _last_result
