[app]
title = PanBoost
package.name = panboost
package.domain = org.panboost

source.dir = .
source.include_exts = py

version = 1.6.0

requirements = python3,kivy,certifi,pyjnius

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
