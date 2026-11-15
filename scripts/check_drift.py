# -*- coding: utf-8 -*-
"""对比本地工作区与远端 main，列出真正有差异的文件（只读，不提交）。

为什么需要它：本项目长期用 GitHub API 发布，本地 git 与远端长期分叉，
`git status` 显示的是「相对本地旧 HEAD」的差异，不是「相对线上」的差异。
这个脚本按 git blob 规则算本地文件 sha，与远端 main 的 tree 逐项比对，
输出「已修改 / 仅本地有 / 仅远端有」三类，判断发布范围时以此为准。

用法：
  python scripts/check_drift.py              # 摘要 + 前 40 条
  python scripts/check_drift.py --all        # 全部列出
  python scripts/check_drift.py --json       # 机器可读
  python scripts/check_drift.py --only apk   # 只看某个前缀

凭据：环境变量 GH_TOKEN，或 E:/workbuddy2/_agent_tmp/gh_token.txt。
退出码：0 正常（有无差异都是 0）；2 凭据/网络错误。
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("GH_REPO") or "fzpaihang/lanlandeku"
API = "https://api.github.com"
TOKEN_FILE = os.path.join("E:" + os.sep, "workbuddy2", "_agent_tmp", "gh_token.txt")


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t.strip()
    if os.path.exists(TOKEN_FILE):
        with io.open(TOKEN_FILE, encoding="utf-8") as f:
            return f.read().strip()
    raise SystemExit("缺少 token：设置 GH_TOKEN 或放入 %s" % TOKEN_FILE)


def call(path, tok):
    req = urllib.request.Request(API + path)
    req.add_header("Authorization", "token " + tok)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "fzjh-drift")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=60) as r:
        return json.loads(r.read().decode())


def remote_tree(tok):
    """远端 main 的 path -> (mode, sha)；子模块跳过。"""
    head = call("/repos/%s/git/ref/heads/main" % REPO, tok)["object"]["sha"]
    tree = call("/repos/%s/git/trees/%s?recursive=1" % (REPO, head), tok)
    out = {}
    for it in tree.get("tree", []):
        if it.get("type") != "blob":
            continue
        out[it["path"]] = (it.get("mode", "100644"), it["sha"])
    return head, out


def local_files():
    """tracked + untracked（遵守 .gitignore），相对仓库根、正斜杠。"""
    p = subprocess.run(["git", "ls-files", "-z", "-co", "--exclude-standard"],
                       cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise SystemExit("git ls-files 失败：%s" % p.stderr.decode("utf-8", "replace"))
    names = [x for x in p.stdout.decode("utf-8", "replace").split("\0") if x]
    return sorted(set(names))


def blob_sha(path, eol=None):
    """按 git blob 规则算 sha；eol 不为 None 时先统一换行。

    远端 blob 是 git 规范化后的内容（.gitattributes: * text=auto eol=lf），
    本地文件可能被 Windows 工具写成 CRLF，直接比会误报「整篇修改」。
    """
    with open(path, "rb") as f:
        data = f.read()
    if eol:
        data = data.replace(b"\r\n", b"\n")
        if eol == "crlf":
            data = data.replace(b"\n", b"\r\n")
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest(), len(data)


BINARY_EXT = (".png", ".jpg", ".jpeg", ".ico", ".zip", ".gz", ".ttf", ".otf", ".apk")


def eol_rule(rel):
    """文本文件在仓库里一律是 LF（`eol=crlf` 只影响检出），二进制不动。"""
    low = rel.lower()
    if low.endswith(BINARY_EXT):
        return None
    return "lf"


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    show_all = "--all" in args
    only = None
    if "--only" in args:
        i = args.index("--only")
        only = args[i + 1] if i + 1 < len(args) else None

    tok = token()
    try:
        head, remote = remote_tree(tok)
    except urllib.error.HTTPError as e:
        raise SystemExit("GitHub API HTTP %s：%s" % (e.code, e.reason))
    except urllib.error.URLError as e:
        raise SystemExit("网络错误：%s" % e)

    modified, added, missing, eol_only = [], [], [], []
    for rel in local_files():
        if only and not rel.replace("\\", "/").startswith(only.strip("/")):
            continue
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full):
            continue
        if os.path.basename(full) == ".gitkeep":
            continue
        rel = rel.replace("\\", "/")
        try:
            rule = eol_rule(rel)
            sha, size = blob_sha(full, rule)
            raw_sha, _ = blob_sha(full, None)
        except OSError:
            continue
        if rel not in remote:
            added.append((rel, size))
        elif remote[rel][1] == sha:
            pass                      # 与规范化后的 blob 一致，无需发布
        elif remote[rel][1] == raw_sha:
            eol_only.append((rel, size))   # 内容一致但仓库里存的是 CRLF，发布会重写
        else:
            modified.append((rel, size))
    for rel in remote:
        if only and not rel.startswith(only.strip("/")):
            continue
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            missing.append(rel)

    report = {
        "remoteHead": head,
        "modified": [{"path": p, "size": s} for p, s in modified],
        "added": [{"path": p, "size": s} for p, s in added],
        "missing": missing,
        "eolOnly": [{"path": p, "size": s} for p, s in eol_only],
    }
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print("远端 main HEAD：%s" % head[:12])
    print("本地与线上：已修改 %d / 仅本地有 %d / 仅远端有 %d / 仅换行差异 %d"
          % (len(modified), len(added), len(missing), len(eol_only)))
    limit = None if show_all else 40

    def dump(title, items):
        if not items:
            return
        print("\n== %s（%d）" % (title, len(items)))
        for it in items[:limit]:
            if isinstance(it, tuple):
                print("  %-46s %8.1f KB" % (it[0], it[1] / 1024.0))
            else:
                print("  " + it)
        if limit and len(items) > limit:
            print("  … 另 %d 条，用 --all 查看" % (len(items) - limit))

    dump("已修改", modified)
    dump("仅本地有", added)
    dump("仅远端有", missing)
    dump("仅换行差异（内容一致，无需发布）", eol_only)
    if not (modified or added or missing or eol_only):
        print("\n本地与线上完全一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
