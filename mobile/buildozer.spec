[app]
title = PanBoost
package.name = panboost
package.domain = org.panboost

source.dir = .
source.include_exts = py,ttf

version = 3.2.6

requirements = python3,kivy,certifi,pyjnius

# v3.2.3 修复 v3.2.2 真机崩溃（日志实锤）：pyjnius 从 Kivy 的
# SDL 线程直接调 LoginLayer.start，视图构建 + addContentView +
# new Handler(Looper.getMainLooper()) 全跑 SDL 线程，部分 ROM 上
# getMainLooper() 从该线程返回 null → Handler 构造 NPE 崩溃。
# 修复：start 经 runOnUiThread 在 UI 线程构建（主 Looper 必然
# 存活）；轮询/按钮恢复改 View.postDelayed（UI 框架内部
# Handler），自建 Handler 彻底移除；closeLayer 同样 UI 线程化。
# v3.2.2 登录层回归主 Activity 内（真机实锤 v3.2.0/v3.2.1 独立
# LoginActivity 返回后 Kivy 主循环永不恢复→纯黑卡住）：
# - LoginLayer.java：登录/浏览全屏 View 层（addContentView 叠加
#   在 SDL surface 之上，非 Dialog 弹窗；Java 侧完整实现 UI +
#   Cookie 采集校验 + 自动轮询 + 导航守卫），主 Activity 从不
#   退场——SDL surface 与 Kivy 主循环全程存活
# - PanMainActivity.java：主入口（extends PythonActivity），仅
#   重写 onBackPressed 接管返回键/手势（LoginLayer.handleBack：
#   WebView 可后退先退网页，否则关层）——v1.8.3 当年 SDL trap
#   吞手势被迫用 Dialog 的问题由重写主 Activity 根治
# v1.8.2~v1.8.5 历史功能全部保留（导航守卫、onPageStarted 市场
# 页拦截、onRenderProcessGone 防杀 App、auth_keys 特征校验）
android.add_src = java_classes/PanWebViewClient.java, java_classes/LoginLayer.java, java_classes/PanMainActivity.java

# v3.2.2：主入口换成 PanMainActivity——manifest 的 android:name
# 由 p4a --android-entrypoint 渲染（经 p4a.extra_args 透传）；
# --activity-class-name 同步改 android recipe 的 pyjnius 配置
android.activity_class_name = org.panboost.PanMainActivity
p4a.extra_args = --android-entrypoint org.panboost.PanMainActivity

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
# v3.2.6：MANAGE_EXTERNAL_STORAGE——公共 Download 媒体文件直写
#（Android 11+ scoped storage 拦截 .apk 等媒体文件路径写；
# 用户在系统设置授权"所有文件访问"后 download_dir 自动切公共目录）
android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE,POST_NOTIFICATIONS,MANAGE_EXTERNAL_STORAGE
android.allow_backup = True

# 下载前台服务：保活心跳（下载线程在主进程，引擎实时落盘）
services = Download:service_down.py:foreground

# 日志输出到 logcat（adb logcat -s python）
android.logcat = True

[buildozer]
log_level = 2
warn_on_root = 1
