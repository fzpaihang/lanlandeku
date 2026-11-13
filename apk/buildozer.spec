[app]

# 应用名称与标识
title = 玩家查询
package.name = fzjhlookup
package.domain = com.fzjh

source.dir = .
# ttf：中文字体子集（fonts/NotoSansSC-Regular.ttf），由 scripts/build_font_subset.py 生成。
# 打包字体是为了不再依赖各厂商 ROM 的 /system/fonts 差异（详见 app_ui.py 字体段注释）。
source.include_exts = py,json,png,jpg,kv,atlas,ttf,otf
source.exclude_patterns = __pycache__,*.pyc,.buildozer,bin,lookup_cache.json,player_lookup.py

version = 1.0

# 依赖：只用标准库 + Kivy（AES 已改为纯 Python 实现，无需 pycryptodome）
requirements = python3,kivy

# 固定 p4a 版本：master 已升到 Python 3.14，Kivy 2.3 在其上编译失败（config.pxi 缺失）
# 2024.01.21 是 Python 3.11.5 + pyjnius 1.6.1，官方验证过的稳定组合
p4a.branch = v2024.01.21

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
