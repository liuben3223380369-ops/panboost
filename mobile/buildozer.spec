[app]
title = PanBoost
package.name = panboost
package.domain = org.panboost

source.dir = .
source.include_exts = py,ttf

version = 1.9.0

requirements = python3,kivy,certifi,pyjnius

# v1.8.2 导航守卫 + v1.8.3 onPageStarted 导航观测 + v1.8.4 渲染
# 进程崩溃处理（onRenderProcessGone，不处理时系统杀整个 App）；
# v1.8.5 登录凭证校验（auth_keys 特征命中才记账，防游客 Cookie
# 误报"已登录"）+ Dialog 非 floating 全屏主题（根治三色弹窗）：
# Java 桥接类（pyjnius 只能实现接口，不能继承 WebViewClient
# 抽象类）——shouldOverrideUrlLoading 拦截 intent://market:// 等
# 一切非 http/https 导航；onPageStarted 拦截 302 落地的应用市场页
# （前者对服务端 302 重定向无效，Android 官方文档明确）
android.add_src = java_classes/PanWebViewClient.java

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
