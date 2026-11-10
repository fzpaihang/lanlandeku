# -*- coding: utf-8 -*-
"""本地预览服务器（仅用于开发预览，正式站是静态托管，不需要它）

用法: python scripts/serve.py [端口]
Windows 上 Python 的 http.server 会调 socket.getfqdn()，遇到非 UTF-8 主机名会崩，
这里把它替换掉。
"""
import http.server
import os
import socketserver
import sys

socket_getfqdn = __import__("socket").getfqdn
__import__("socket").getfqdn = lambda *a, **k: "localhost"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8791


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, fmt, *args):
        pass


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    print("serving %s at http://127.0.0.1:%d/" % (ROOT, PORT))
    httpd.serve_forever()
