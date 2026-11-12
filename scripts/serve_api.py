# -*- coding: utf-8 -*-
"""本地联调服务器：静态站 + /api/query（直连云函数 handler，不用部署也能验）

用法:
  python scripts/build_api_zip.py --stage-only    # 先准备 api/build/staging
  python scripts/serve_api.py 8788
  # 浏览器打开 http://127.0.0.1:8788/lookup.html?uid=21079729670

它会用 config.json 里的五区凭据设置 FZJH_SERVERS / FZJH_HOTVER，
再用 api/build/staging 里那份代码跑 api/index.py 的 main_handler。
"""
import http.server
import io
import json
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, "api", "build", "staging")
CONFIG = os.path.join(ROOT, "config.json")


def load_env():
    if not os.path.isdir(STAGE):
        raise SystemExit("缺少 %s，先跑：python scripts/build_api_zip.py --stage-only" % STAGE)
    if not os.path.exists(CONFIG):
        raise SystemExit("缺少 config.json（本地凭据），没法联调")
    with io.open(CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    os.environ["FZJH_SERVERS"] = json.dumps(cfg["servers"], ensure_ascii=False)
    os.environ["FZJH_HOTVER"] = str(cfg["hotver"])
    if not os.environ.get("FZJH_ORIGIN"):
        os.environ["FZJH_ORIGIN"] = "http://127.0.0.1"


load_env()
sys.path.insert(0, STAGE)
os.chdir(STAGE)
import index as API  # noqa: E402


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def _send(self, status, headers, body):
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _event(self, query):
        return {
            "httpMethod": self.command,
            "queryString": query,
            "headers": {"Origin": "http://127.0.0.1:%d" % self.server.server_port},
        }

    def do_OPTIONS(self):
        p = urllib.parse.urlparse(self.path)
        r = API.main_handler(self._event(dict(urllib.parse.parse_qsl(p.query))), None)
        self._send(r["statusCode"], r["headers"], b"")

    def do_GET(self):
        p = urllib.parse.urlparse(self.path)
        if p.path.rstrip("/") in ("/api/query", "/api"):
            q = dict(urllib.parse.parse_qsl(p.query))
            r = API.main_handler(self._event(q), None)
            self._send(r["statusCode"], r["headers"], r["body"].encode("utf-8"))
            return
        return super().do_GET()

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve_api] " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8788
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler) as s:
        print("静态站 + /api/query 已就绪：http://127.0.0.1:%d/lookup.html" % port, flush=True)
        s.serve_forever()


if __name__ == "__main__":
    main()
