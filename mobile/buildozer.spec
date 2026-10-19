[app]
title = PanBoost
package.name = panboost
package.domain = org.panboost

source.dir = .
source.include_exts = py,ttf

version = 1.6.3

requirements = python3,kivy,certifi,pyjnius

# 固定 p4a 到稳定 release（hostpython 3.11.5）；master 的 hostpython
# 3.14.2 会让纯依赖解析拉 cp314 android wheel → 平台不兼容报错
p4a.branch = v2024.01.21

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 24
android.archs = arm64-v8a

android.permissions = INTERNET
android.allow_backup = True

# 日志输出到 logcat（adb logcat -s python）
android.logcat = True

[buildozer]
log_level = 2
warn_on_root = 1
