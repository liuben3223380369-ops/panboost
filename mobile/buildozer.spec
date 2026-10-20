[app]
title = PanBoost
package.name = panboost
package.domain = org.panboost

source.dir = .
source.include_exts = py,ttf

version = 3.2.1

requirements = python3,kivy,certifi,pyjnius

# v3.2.1 修复登录完成返回后 UI 纯黑卡住（三防线）：①LoginActivity
# onCreate 设 Translucent 主题（内容不透明视觉不变，但 PythonActivity
# 不进 onStop——SDL surface 不销毁）②finish 前同步 detachWebView
# （Chromium GPU 资源先于 EGL 重建释放）③main.py on_resume 强制
# ask_update 重绘兜底。
# v3.2.0 登录页独立 Activity 化（根治 Dialog 弹窗在部分真机
# "层不出现/WebView 区空白"）：
# - PanWebViewClient.java：WebViewClient 桥接（pyjnius 只能实现
#   接口不能继承抽象类）——导航守卫/渲染崩溃处理
# - LoginActivity.java：独立全屏登录/浏览页（Java 侧完整实现
#   UI + Cookie 采集校验 + 自动轮询），Python 侧只启动+收结果
# v1.8.2~v1.8.5 历史功能全部保留（导航守卫、onPageStarted 市场
# 页拦截、onRenderProcessGone 防杀 App、auth_keys 特征校验）
android.add_src = java_classes/PanWebViewClient.java, java_classes/LoginActivity.java

# v3.2.0：LoginActivity 注册进 manifest（p4a --add-activity 渲染
# <activity android:name> 到 <application> 内；无 intent-filter
# 无需 exported 声明，继承 application 主题，默认主进程与
# PythonActivity 共享 pyjnius 静态字段/回调）
android.add_activities = org.panboost.login.LoginActivity

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
