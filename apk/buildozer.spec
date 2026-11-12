[app]

# 应用名称与标识
title = 玩家查询
package.name = fzjhlookup
package.domain = com.fzjh

source.dir = .
source.include_exts = py,json,png,jpg,kv,atlas
source.exclude_patterns = __pycache__,*.pyc,.buildozer,bin,lookup_cache.json,player_lookup.py

version = 1.0

# 依赖：只用标准库 + Kivy（AES 已改为纯 Python 实现，无需 pycryptodome）
requirements = python3,kivy

orientation = portrait
fullscreen = 0

# 需要联网访问游戏接口
android.permissions = INTERNET, ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 24
android.ndk_api = 24
# 只编 64 位：现代安卓机都是 arm64，编两个架构会让构建时间翻倍
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True

# 应用外观
icon.filename = %(source.dir)s/icon.png
presplash.color = #F6F4EF

# 日志
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
