[app]
title = PanBoost
package.name = panboost
package.domain = org.panboost

source.dir = .
source.include_exts = py,ttf

version = 1.8.1

requirements = python3,kivy,certifi,pyjnius

# 固定 p4a 到稳定 release（hostpython 3.11.5）；master 的 hostpython
# 3.14.2 会让纯依赖解析拉 cp314 android wheel → 平台不兼容报错
p4a.branch = v2024.01.21

orientation = portrait
fullscreen = 0

android.api = 33
android.minapi = 24
android.archs = arm64-v8a

# INTERNET 网络；WAKE_LOCK 锁屏保活；FOREGROUND_SERVICE+POST_NOTIFICATIONS
# 前台服务常驻通知（Android 12+ 后台冻结防护，下载不断流）
android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE,POST_NOTIFICATIONS
android.allow_backup = True

# 下载前台服务：保活心跳（下载线程在主进程，引擎实时落盘）
services = Download:service_down.py:foreground

# 日志输出到 logcat（adb logcat -s python）
android.logcat = True

[buildozer]
log_level = 2
warn_on_root = 1
