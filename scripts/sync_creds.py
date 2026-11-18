# -*- coding: utf-8 -*-
"""把 config.json 的分区凭据同步到「私有 gist」和「CI Secret FZJH_SERVERS」。

为什么要有这个脚本
------------------
这两处凭据是 APK / CI 取分区列表的唯一来源，历史上手工同步踩过两次坑：

1. **gist 写成裸数组**（v71 加 ios3 时）：`apk/lookup_core.py` 读的是
   `cfg.get("servers")`，裸数组时该值为 `None`，`refresh_remote_config()`
   静默 `return False`，设备上表现为「该分区未找到」，既不报错也不刷新缓存。
2. **Secret 写成裸数组**（v70/v71 加 ios2/ios3 时）：`.github/workflows/
   build-apk.yml` 的「注入分区凭据」步骤把 Secret 原样写成 `apk/config.json`，
   再 `json.load(...).get("servers", [])` —— 裸数组会抛
   `AttributeError: 'list' object has no attribute 'get'`，**APK 云端构建整条挂掉**
   （从加 ios1 起连续失败 6 次，下载页一直是旧包，直到人肉发现）。

所以这里把「写哪两个地方、写成什么格式」固化成一处，并强制校验。

用法
----
  python scripts/sync_creds.py --check              # 只校验 config.json，打印将要写入的内容摘要
  python scripts/sync_creds.py --apply              # 写 gist + 写 Secret
  python scripts/sync_creds.py --apply --gist-only   # 只写 gist
  python scripts/sync_creds.py --apply --secret-only # 只写 Secret

写完之后**必须**人力验证一次：
  1) 设备端删掉 `files/servers-remote.json` 再启动 App，看分区是否齐全；
  2) 在 Actions 页面手动跑一次 `build-apk.yml`，确认「注入分区凭据」步骤绿。

依赖：PyNaCl（`pip install pynacl`）。token 从 GH_TOKEN / GITHUB_TOKEN 环境变量
读，或从 `E:/workbuddy2/_agent_tmp/gh_token.txt` 读，**不打印**。
"""
import base64
import io
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("GH_REPO") or "fzpaihang/lanlandeku"
API = "https://api.github.com"
GIST_ID = "91b6a13fa2cc94584a6647ce57b260f9"
CONFIG = os.path.join(ROOT, "config.json")
TOKEN_FILE = os.path.join("E:" + os.sep, "workbuddy2", "_agent_tmp", "gh_token.txt")
# 每个分区必须具备的字段（缺一个 CI 或 APK 就会在运行期炸）
REQUIRED = ("key", "name", "channel", "uuid", "account")


def die(msg):
    raise SystemExit("[sync_creds] %s" % msg)


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t.strip()
    if os.path.exists(TOKEN_FILE):
        with io.open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    die("缺少 token：设置 GH_TOKEN 或放入 %s" % TOKEN_FILE)


TOK = token()


def call(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", "token " + TOK)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "fzjh-sync-creds")
    # 系统代理会把 api.github.com 拦掉，显式绕开
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=60) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:400]
        die("%s %s -> HTTP %s %s" % (method, path, e.code, body))


# ---------------------------------------------------------------- config.json

def load_config():
    """读 config.json 并校验结构。任何一处不对都直接 die，绝不带着坏数据去写。"""
    if not os.path.exists(CONFIG):
        die("找不到 %s（分区凭据只在这里，不进仓库）" % CONFIG)
    with io.open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        die("config.json 顶层必须是对象，实际是 %s" % type(cfg).__name__)
    servers = cfg.get("servers")
    if not isinstance(servers, list) or not servers:
        die("config.json 缺少 servers 数组（或为空）")
    seen = set()
    for i, s in enumerate(servers):
        if not isinstance(s, dict):
            die("servers[%d] 不是对象" % i)
        miss = [k for k in REQUIRED if not str(s.get(k) or "").strip()]
        if miss:
            die("servers[%d]（key=%s）缺字段：%s" % (i, s.get("key") or "?", "、".join(miss)))
        key = str(s["key"]).strip()
        if key in seen:
            die("servers 里 key 重复：%s" % key)
        seen.add(key)
    return cfg


def masked(s):
    """只露前 8 位，避免把凭据写进日志/终端历史。"""
    u = str(s.get("uuid") or "")
    return {
        "key": s["key"],
        "name": s.get("name"),
        "channel": s.get("channel"),
        "uuid": (u[:8] + "…" + u[-4:]) if len(u) > 14 else u,
        "account": "有" if s.get("account") else "**缺**",
        "domain": s.get("domain") or "(安卓默认)",
        "platform": s.get("platform") or "android",
    }


# ---------------------------------------------------------------------- gist

def gist_get():
    g = call("GET", "/gists/%s" % GIST_ID)
    raw = ((g.get("files") or {}).get("servers.json") or {}).get("content") or ""
    try:
        return json.loads(raw)
    except Exception:
        return None


def gist_put(cfg):
    """gist 必须是 {"servers": [...]} 字典 —— 裸数组会让 APK 静默读不到。"""
    body = {"files": {"servers.json": {
        "content": json.dumps(cfg, ensure_ascii=False, indent=2),
    }}}
    r = call("PATCH", "/gists/%s" % GIST_ID, body)
    return r.get("updated_at") or "?"


# -------------------------------------------------------------------- secret

def secret_put(cfg):
    """Secret 存**整份 config.json**：build-apk.yml 会原样写成 apk/config.json。"""
    try:
        from nacl import encoding, public
    except ImportError:
        die("缺少 PyNaCl：pip install pynacl")
    payload = json.dumps(cfg, ensure_ascii=False).encode("utf-8")
    pk = call("GET", "/repos/%s/actions/secrets/public-key" % REPO)
    pub = public.PublicKey(pk["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pub).encrypt(payload)
    body = {
        "encrypted_value": base64.b64encode(sealed).decode(),
        "key_id": pk["key_id"],
    }
    call("PUT", "/repos/%s/actions/secrets/FZJH_SERVERS" % REPO, body)
    return len(payload)


# ---------------------------------------------------------------------- main

def main(argv):
    cfg = load_config()
    servers = cfg["servers"]
    payload = json.dumps(cfg, ensure_ascii=False).encode("utf-8")

    print("config.json：%d 分区 / %d 字节" % (len(servers), len(payload)))
    for s in servers:
        m = masked(s)
        print("  %-10s %-6s channel=%-8s uuid=%s account=%s %s/%s"
              % (m["key"], m["name"], m["channel"], m["uuid"], m["account"],
                 m["platform"], m["domain"]))

    # 现状对比：gist 里已有的 key
    cur = gist_get()
    cur_keys = []
    if isinstance(cur, dict):
        cur_keys = [str(s.get("key")) for s in (cur.get("servers") or [])]
        print("\ngist 现状：%d 分区（%s）" % (len(cur_keys), ", ".join(cur_keys) or "空"))
    elif isinstance(cur, list):
        print("\ngist 现状：**裸数组 %d 项** —— 格式错误，APK 会读不到" % len(cur))
        cur_keys = [str(s.get("key")) for s in cur]
    else:
        print("\ngist 现状：读不到或不是合法 JSON")

    want = [str(s["key"]) for s in servers]
    if cur_keys != want:
        print("        差异：新增 %s / 删除 %s"
              % (sorted(set(want) - set(cur_keys)) or "无",
                 sorted(set(cur_keys) - set(want)) or "无"))

    if "--check" in argv:
        print("\n[check] 只校验、未写入。确认无误后用 --apply")
        return 0

    if "--apply" not in argv:
        print("\n[!] 需要 --check 或 --apply")
        return 1

    do_gist = "--secret-only" not in argv
    do_secret = "--gist-only" not in argv

    if do_gist:
        at = gist_put(cfg)
        back = gist_get()
        ok = isinstance(back, dict) and [str(s.get("key")) for s in (back.get("servers") or [])] == want
        print("gist 已写入（updated_at=%s），回读%s" % (at, "一致" if ok else "**不一致，检查语法**"))
        if not ok:
            die("gist 回读校验失败")

    if do_secret:
        n = secret_put(cfg)
        print("Secret FZJH_SERVERS 已写入（payload %d 字节 / %d 分区）" % (n, len(servers)))

    print("\n下一步（务必做，两次事故都是靠这里发现的）：")
    print("  1) adb shell run-as com.fzjh.fzjhlookup rm -f files/servers-remote.json")
    print("     再重启 App，确认分区下拉齐全")
    print("  2) Actions 手动跑一次 build-apk.yml，确认「注入分区凭据」步骤绿")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
