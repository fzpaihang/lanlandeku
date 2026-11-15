# -*- coding: utf-8 -*-
"""统一发布：用 GitHub API 把指定文件推到 main（base_tree 增量，不动工作区）。

为什么需要它：本地 git 与远端长期分叉，直接 push 会被拒；而以前每次发布都要
在 _agent_tmp 里临时拼一份 blob→tree→commit→PATCH 的脚本，容易漏文件、漏
base_tree、把 code.zip 和 version.json 拆开发。这个脚本把这些规则固化下来。

用法：
  python scripts/publish.py --check "说明" apk/app_ui.py apk/update/code.zip apk/update/version.json
  python scripts/publish.py "热更 v57：xxx" apk/app_ui.py apk/update/code.zip apk/update/version.json
  python scripts/publish.py "清理" --delete api/index.py

规则：
  - `--check` 只比对远端、打印将要发生的改动，不写任何东西；
  - 自动跳过与远端完全一致的文件；全部一致时不造空 commit；
  - `apk/update/code.zip` 与 `version.json` 必须成对出现，只给一个直接报错；
  - 拒绝发布敏感文件（config.json / gh.json / .keys / dist / api/build / data/logs）；
  - 始终带 base_tree，避免覆盖 CI 刚提交的 data/。
"""
import base64
import hashlib
import io
import json
import os
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
TOKEN_FILE = os.path.join("E:" + os.sep, "workbuddy2", "_agent_tmp", "gh_token.txt")

REFUSE = (
    "config.json", "apk/config.json", "apk/gh.json", "worker/.dev.vars",
    ".keys/", "dist/", "api/build/", "data/logs/", "apk/lookup_cache.json",
)


def die(msg):
    raise SystemExit("[publish] %s" % msg)


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
    req.add_header("User-Agent", "fzjh-publish")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with op.open(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        die("HTTP %s %s %s → %s" % (e.code, method, path, body))


BINARY_EXT = (".png", ".jpg", ".jpeg", ".ico", ".zip", ".gz", ".ttf", ".otf", ".apk")


def eol_rule(rel):
    """与 .gitattributes 对齐：.bat/.cmd 用 CRLF，二进制不动，其余 LF。

    API 发布不走 git 的换行规范化，所以这里手动做一遍，避免 CRLF 文件
    在 GitHub 上显示成「整篇 1277 行都改了」。
    """
    low = rel.lower()
    if low.endswith(BINARY_EXT):
        return None
    if low.endswith((".bat", ".cmd")):
        return "crlf"
    return "lf"


def blob_sha(path, eol=None):
    data = open(path, "rb").read()
    if eol:
        data = data.replace(b"\r\n", b"\n")
        if eol == "crlf":
            data = data.replace(b"\n", b"\r\n")
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest(), data


def remote_state():
    head = call("GET", "/repos/%s/git/ref/heads/main" % REPO)["object"]["sha"]
    tree = call("GET", "/repos/%s/git/trees/%s?recursive=1" % (REPO, head))
    return head, {it["path"]: it["sha"] for it in tree.get("tree", []) if it.get("type") == "blob"}


def norm(path):
    """统一成正斜杠的相对路径；只去掉开头的 ./，不能用 lstrip('./')。

    lstrip 会把 '.gitignore' 的前导点也吃掉（踩过）。
    """
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


def check_sensitive(paths):
    for p in paths:
        rel = norm(p)
        for bad in REFUSE:
            if rel == bad or (bad.endswith("/") and rel.startswith(bad)):
                die("拒绝发布敏感/忽略文件：%s（%s）" % (rel, bad))


def main():
    args = sys.argv[1:]
    check_only = "--check" in args
    args = [a for a in args if a != "--check"]

    deletes = []
    while "--delete" in args:
        i = args.index("--delete")
        if i + 1 >= len(args):
            die("--delete 后面要跟路径")
        deletes.append(norm(args[i + 1]))
        del args[i:i + 2]

    if len(args) < 1:
        die('用法：publish.py "说明" 文件... [--check] [--delete 路径]')
    message, files = args[0], [norm(a) for a in args[1:]]
    if not files and not deletes:
        die("没有指定任何文件")

    check_sensitive(files)
    for f in files:
        if not os.path.isfile(os.path.join(ROOT, f)):
            die("文件不存在：%s" % f)

    if ("apk/update/code.zip" in files) != ("apk/update/version.json" in files):
        die("code.zip 与 version.json 必须同时发布（只推一个会导致 md5 不匹配、客户端静默回退）")

    head, remote = remote_state()
    changes = []   # (kind, path, sha, data)
    for f in files:
        rule = eol_rule(f)
        sha, data = blob_sha(os.path.join(ROOT, f), rule)
        raw_sha, _ = blob_sha(os.path.join(ROOT, f), None)
        if f not in remote:
            changes.append(("A", f, sha, data))
        elif remote[f] not in (sha, raw_sha):
            changes.append(("M", f, sha, data))
    for d in deletes:
        if d not in remote:
            die("远端没有这个文件，无法删除：%s" % d)
        changes.append(("D", d, None, None))

    print("远端 main：%s" % head[:12])
    if not changes:
        print("所有文件与远端一致，无需提交。")
        return 0
    for kind, path, _sha, data in changes:
        extra = "" if data is None else "  %8.1f KB" % (len(data) / 1024.0)
        print("  %s  %s%s" % (kind, path, extra))
    print("共 %d 个变更" % len(changes))

    if check_only:
        print("\n--check：未提交。")
        return 0

    entries = []
    for kind, path, sha, data in changes:
        if kind == "D":
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            continue
        if kind == "A" or remote.get(path) != sha:
            blob = call("POST", "/repos/%s/git/blobs" % REPO,
                        {"content": base64.b64encode(data).decode(), "encoding": "base64"})
            sha = blob["sha"]
        entries.append({"path": path, "mode": "100644", "type": "blob", "sha": sha})

    base_commit = call("GET", "/repos/%s/git/commits/%s" % (REPO, head))
    tree = call("POST", "/repos/%s/git/trees" % REPO,
                {"base_tree": base_commit["tree"]["sha"], "tree": entries})
    commit = call("POST", "/repos/%s/git/commits" % REPO,
                  {"message": message, "tree": tree["sha"], "parents": [head]})
    call("PATCH", "/repos/%s/git/refs/heads/main" % REPO,
         {"sha": commit["sha"], "force": False})

    now = call("GET", "/repos/%s/git/ref/heads/main" % REPO)["object"]["sha"]
    if now != commit["sha"]:
        die("推送后远端 HEAD=%s 与预期 %s 不一致" % (now[:12], commit["sha"][:12]))
    print("\n已提交 %s" % commit["sha"][:12])
    print("https://github.com/%s/commit/%s" % (REPO, commit["sha"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
