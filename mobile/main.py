#!/usr/bin/env python3
"""PanBoost Android 图形壳（Kivy）v1.9.0。

v1.9.0（真机反馈第六轮，登录层 UI 重构 + 网页版 URL 实锤修正）：
①"顶部三个色块没有文字"：登录层顶部 ✕/✓ 双按钮的文字设置在
  部分真机被静默吞掉（pyjnius 对 setText 多重载解析失败），用户
  只看到色块不知道是什么。weblogin 重构为标准登录页布局：深色
  标题栏（✕ + "网盘名 · 网页登录"）+ 黄色提示条 + WebView +
  底部通栏"已完成登录"大按钮（蓝底白字 17sp 高对比）；文字
  设置三级保险（str 直传 → java.lang.String 对象 → 失败记
  nav_log）。
②"夸克/阿里云盘打开是下载页"：登录 URL 落在产品宣传页——
  LinkSwift @match 清单实锤网页版真实路径：阿里
  www.alipan.com/drive/、天翼 cloud.189.cn/web/、移动云盘
  yun.139.com（旧门户跳 APP 引导）；移动 domains 补 139.com。
  夸克/UC 域名双源确认无误；桌面 UA 改独立设置 + 读回验证。
③首页卡片三行化：网盘名 + 状态行（已登录/Cookie已存·未验证/
  点击网页登录）+ 域名，操作引导一目了然。

v1.8.5（真机反馈第五轮，参考网盘解析项目根治登录误报）：
①"点卡片就记已登录"：record_login 此前只看 Cookie 非空——登录页
  游客 Cookie（BAIDUID 等）也非空，点 ✓ 必误记。参考 LinkSwift /
  netdisk-fast-download 的登录态判定思路（特征凭证命中或 API 业
  务码，绝不信"Cookie 非空"）：weblogin._finish 关层前校验
  auth_keys 全部命中（未命中 Toast 提示、登录层保持打开），
  record_login 防御性二次校验；特征键按调研补齐（夸克/UC 的
  __pus+__puus、天翼 COOKIE_LOGIN_USER、OneDrive ESTSAUTH、
  Dropbox lid）。auth_keys 为空的网盘（阿里/迅雷/123/移动等
  localStorage 型登录态）改记"Cookie 已存·未验证"，卡片与账号
  页如实显示，绝不冒充"已登录"。
②"三色区域依旧没字"：show() 后 setLayout 在真机仍被 floating
  主题强制 wrap 压回——改用非 floating 全屏主题构造 Dialog
  （Theme_Light_NoActionBar_Fullscreen）根治；WebView 先入容器
  后加载 + weight 布局；scheme/市场跳转被拦后回退重载登录页
  （2 次）仍被拦则显示说明页（替代空白屏）。

v1.8.4（真机反馈第四轮，双根因源码实锤）：v1.8.3 点击网盘卡片后
只弹"蓝灰黑三色小弹窗"、网页什么都没有，点击任何位置闪退——
① 三色弹窗：Dialog(activity) 用默认 floating 主题，AOSP
  PhoneWindow.generateLayout() 强制 setLayout(WRAP_CONTENT,
  WRAP_CONTENT)——窗口 wrap 后 WebView 高度塌陷成 0，只剩 160px
  按钮栏（灰✕+蓝✓）和深色窗口背景（黑）。修复：show() 后显式
  getWindow().setLayout(MATCH_PARENT, MATCH_PARENT) 全屏。
② 点击闪退：✕/✓ 按钮的 _ClickListener 内联创建未持 Python 强
  引用——pyjnius 官方文档明确 proxy 只存指针不持引用，CPython
  引用计数归零立即 GC，Java 侧点击已死 proxy 必 native crash。
  修复：所有回调对象强引用存 weblogin._STATE（click_cbs）。
③ 加固：WebView 渲染进程崩溃（onRenderProcessGone）不处理时
  系统默认杀整个 App——桥接类转发返回 true + 自动关层；
  登录回调（on_done/on_cancel）可能来自 Android UI 线程，Kivy
  控件操作统一经 Clock.schedule_once 调度回 Kivy 主线程。

v1.8.3（真机反馈第三轮，SDL 源码实锤）：v1.8.2 后百度已正常
（passport 登录页生效），但 ①其他网盘卡片仍跳"下载网盘APP"
界面；②"无法返回主页"自 v1.8.1 起始终未修复。抓 SDL 官方
SDLActivity.java（release-2.26.x）源码定位真正根因——
①手势返回无效：onBackPressed() 里 trap=SDL_ANDROID_TRAP_BACK_
  BUTTON 为真时直接 return（什么都不做）。Android 10+ 手势导航
  的返回手势不产生键盘事件、直接调 onBackPressed——trap=1 手势
  被吞（无反应），trap=0 退出整个 App；OnKeyListener 只收硬件
  键收不到手势——v1.8.1(vcode 27)/v1.8.2(OnKeyListener+trap)
  三条路对手势全部无效。修复：WebView 登录层改全屏 Dialog 承载
  ——手势/返回键自动 cancel Dialog（系统标准行为），OnCancel
  Listener 关层，唯一系统级可靠路径。
②其他网盘仍跳下载App：shouldOverrideUrlLoading 对服务端 302
  重定向无效（Android 官方文档），网盘 H5 壳"跳下载App"很多
  正是 302 落地。修复：onPageStarted 导航观测（一切导航必经
  点）——记录导航日志（登录结束落 nav-*.log 可取回诊断）+
  市场黑名单 URL（market:// 应用商店等）命中即 stopLoading。
③main.py 移除 SDL trap 环境变量：Dialog 方案不需要；trap=1 反
  而吞掉非登录屏的手势返回（无反应），移除后手势走 Android
  标准行为（退出 App），Kivy on_keyboard(27) 仍作三键兜底。

v1.8.2（联网研究根治版）：v1.8.1 的桌面 UA 修复无效，经源码级调研
定位真正根因——
①"跳到下载网盘APP界面"：WebView 未设置 WebViewClient，页面
  location.href / intent:// / market:// 导航全部逃逸到系统 intent
  分发（应用市场/网盘App 接管）；百度 H5 壳更有 100ms 延迟的强制
  跳转脚本（即使桌面 UA 也先落 H5 再跳）。修复：Java 桥接类
  PanWebViewClient（android.add_src 编入 APK，pyjnius 只能实现
  接口不能继承 WebViewClient 抽象类）+ 导航白名单（只放行
  http/https，intent:// 解析 browser_fallback_url）；百度入口改
  PC 版统一登录页 passport.baidu.com/v2/?login。
②返回键/手势无效：SDL_HINT_ANDROID_TRAP_BACK_BUTTON 默认 "0"，
  返回键根本不产生 SDL 事件（Kivy 收不到 27）；且 WebView 抢焦点
  后自己消费 KEYCODE_BACK。修复：SDL trap 环境变量（main.py 首段，
  必须早于任何 kivy import）+ WebView 层 View$OnKeyListener 拦截
  （网页后退→关闭登录层）+ Kivy Window.on_keyboard(27) 兜底。

v1.8.1：修复真机两大反馈——①网盘卡片点开的是"下载客户端"引导页
（WebView 缺桌面 UA，被网盘 302）；②登录层无法返回（Android 返回
键/手势无处理，无关闭入口）。修复：桌面 UA + 宽视口；顶部双按钮
（✕ 返回首页 / ✓ 完成登录）；返回键拦截（登录层→网页后退/关闭，
非首页屏→回首页，首页→系统默认退出）。

v1.7.2：WebView 登录层挂载失败可诊断——失败详情（含具体步骤名）
显示到账号页状态栏（用户实际所在屏）+ 落 crash-*.log；weblogin
挂载分步自检（关键/非关键步骤分级），UI 线程超时防幽灵层。

v1.7.1：修复真机"网盘卡片点击无反应"——WebView 层颜色参数 Java int
溢出 + UI 线程异常静默丢失（见 weblogin.py）；按钮回调统一异常兜底
（落 crash-*.log + 首页状态栏可见提示），登录层打开失败自动回落
账号页手动粘贴 Cookie。

v1.7.0：浅色 UI 全面重设计 + 首页网盘登录入口。

- 浅色主题：白卡片 / 主蓝 / 深字（弃用 Kivy 默认黑底）
- 首页网盘宫格：18 家国内外网盘（百度/夸克/阿里/微云/天翼/移动/迅雷/
  123/蓝奏/坚果/UC/Google Drive/Dropbox/OneDrive/MEGA/pCloud/Box/Yandex）
- 点击入口 → 原生 WebView 打开网盘官方登录页（验证码/扫码原生支持），
  登录后自动提取 Cookie 永久保存（下载对应网盘文件时自动携带）
- 下载保活：前台服务 + WakeLock（Android 12+ 锁屏/后台不断流）
- 四屏：首页（宫格）/ 下载（直链+Cookie+线程至1024）/ 账号 / 历史

v1.6.3：线程选项补全至 1024；v1.6.2：修复启动闪退（KV 自定义类必须
先在 Python 定义，Widget 元类才注册进 Factory）；v1.6.1：中文字体。
"""
import json
import os
import sys
import threading
import time
import urllib.parse
from pathlib import Path

# v1.8.3：移除 SDL_ANDROID_TRAP_BACK_BUTTON 设置（v1.8.2 曾设 "1"）。
# SDL 源码实锤（SDLActivity.release-2.26.x onBackPressed）：trap=1
# 时返回手势被直接吞掉（无反应）；trap=0（默认）走 Android 标准
# 行为。Android 10+ 手势导航不产生键盘事件，Kivy 层永远收不到，
# 登录层的返回改由全屏 Dialog 系统级处理（见 weblogin.py v1.8.3）；
# 非登录屏手势返回走系统默认（退出 App，符合 Android 惯例），
# 三键导航的 BACK 仍由 _on_key(keycode 27) 兜底处理。

# PANBOOST_HOME 必须在 import panboost 之前设置（CONFIG_DIR 是模块级求值）
IS_ANDROID = ("ANDROID_PRIVATE" in os.environ
              or "ANDROID_ARGUMENT" in os.environ)
if IS_ANDROID:
    _base = os.environ.get("ANDROID_PRIVATE", "/").rstrip("/") or "/"
    os.environ.setdefault("PANBOOST_HOME",
                          os.path.join(_base, "files", ".panboost"))

sys.path.insert(0, str(Path(__file__).parent))
import panboost as pb  # noqa: E402
import drive  # noqa: E402
import weblogin  # noqa: E402
import applog  # noqa: E402
from pans import PANS, PAN_BY_KEY  # noqa: E402
from theme import (BG, CARD, CARD_DOWN, PRIMARY, PRIMARY_DARK,  # noqa: E402
                   INK, SUB, GREEN)

HISTORY_FILE = pb.CONFIG_DIR / "history.json"
ACCOUNTS_FILE = pb.CONFIG_DIR / "accounts.json"

SHELL_VERSION = "3.2.7"
# v3.2.2：登录层架构回归主 Activity 内（LoginLayer addContentView
# 全屏叠加 + PanMainActivity 重写 onBackPressed）——真机实锤
# v3.2.0/v3.2.1 独立 LoginActivity 返回后 Kivy 主循环永不恢复
# （applog 停在“打开网页登录”，回调链日志全缺失 → 纯黑卡住），
# 主 Activity 从不退场后该路径结构性消除
# v3.2.3：LoginLayer 构建切 UI 线程（runOnUiThread）——v3.2.2
# 从 Kivy 的 SDL 线程直接构建视图+Handler，真机在
# new Handler(Looper.getMainLooper()) 处 NPE 崩溃（部分 ROM
# 从 SDL 线程取主 Looper 返回 null）；轮询/按钮恢复改
# View.postDelayed 彻底去掉自建 Handler
# v3.2.7：根治"探测通过但引擎写入仍被拒（Errno 13）"——差异
# 在打开模式：探测 open('wb') 豁免通过，引擎 os.open(O_RDWR)
# 被 FUSE 拒（公共目录拒发读写打开）。引擎降级（O_RDWR→
# O_WRONLY + flock/ftruncate fail-open，纯 pwrite 写功能完备）；
# 探测对齐引擎真实路径（O_WRONLY+pwrite 扩展写）；真实写入若
# 仍被拒则 _FORCE_PRIVATE 落闸自动改存应用目录重试（下载永不
# 失败）
# v3.2.6：①根治"公共 Download 写入被拒"——Android 11+ 上
# targetSdk 33 无任何运行时权限可直写公共 Download 媒体文件
# （.write_test 探测误判：非媒体文件允许直写），申请
# MANAGE_EXTERNAL_STORAGE + 首页一键授权卡片（跳系统设置，
# 授权后公共目录直写+多线程 seek 全速），App 私有目录永久
# 兜底下载永不失败；探测改 .probe.apk 真实反映可写性
# v3.2.5：①根治"下载结束即闪退"——p4a PythonService.onDestroy
# 的 Process.killProcess 杀同进程主 App（stop_keepalive→stopService
# 触发，30s 探测超时+开销≈38 秒后闪退），移除 AndroidService 保活
# 只留 PARTIAL_WAKE_LOCK；②UI MD3 现代化——底部导航图标+文字、
# 激活态品牌蓝胶囊指示器（NavigationBar 规范）、卡片大圆角
# dp(14)、主按钮 dp(48)
# v3.2.4：drive 层补 SSL 上下文（certifi CA + 回退，与引擎
# make_ssl_context 同模型）——Android 上无系统 CA 路径，
# 网盘列表 HTTPS 请求在连接层即炸（真机日志实锤）


def register_font():
    """把 Kivy 默认字体名 Roboto 重注册到自带中文字体（修乱码）。"""
    try:
        from kivy.core.text import LabelBase
        p = str(Path(__file__).parent / "fonts" / "cjk.ttf")
        if Path(p).exists():
            LabelBase.register("Roboto", p, p, p, p)
            return True
    except Exception:
        pass
    return False


register_font()  # 必须早于任何 Widget 创建

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.lang import Builder  # noqa: E402
from kivy.metrics import dp, sp  # noqa: E402
from kivy.properties import (BooleanProperty, ListProperty,  # noqa: E402
                             StringProperty)
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.screenmanager import Screen  # noqa: E402
from kivy.uix.spinner import SpinnerOption  # noqa: E402
try:  # v3.0.0 剪贴板识别（复制分享链接回 App 自动填入）
    from kivy.core.clipboard import Clipboard  # noqa: E402
except Exception:  # 冒烟/桌面无剪贴板后端
    Clipboard = None


class MainScreen(Screen):
    """首页：网盘宫格。KV 自定义类必须先在 Python 定义（v1.6.1 事故）。"""


class DownloadScreen(Screen):
    pass


class AccountsScreen(Screen):
    pass


class HistoryScreen(Screen):
    pass


class CardButton(Button):
    """白卡片按钮：圆角视觉全部在 KV 规则实现，Python 只声明属性
    （mock 环境下 import 零副作用）。"""
    bg = ListProperty(CARD)
    bg_down = ListProperty(CARD_DOWN)


class CompactOption(SpinnerOption):
    """紧凑下拉行（30dp）：9 个线程选项在小屏上不截断。

    注意：KV 属性值位置（如 option_cls:）是表达式求值上下文，类名
    必须经 app 属性传入（v1.6.3 CI 门禁抓到的问题）。"""
    pass


class NavTab(Button):
    """底部导航 Tab（v2.0.0）：active 态主色高亮，非 active 深色底。

    视觉在 KV 规则实现，Python 只声明属性（mock 零副作用）。
    """
    active = BooleanProperty(False)
    tab_bg = ListProperty(PRIMARY)


class FileRow(BoxLayout):
    """文件行（v3.0.1 自研 tap 手势，对标 YunX combinedClickable）。

    YunX 行用 Compose combinedClickable：Android 手势系统保证
    down→up 位移超 touchSlop(8dp) 即取消点击、事件让给列表滚动，
    滑动浏览永不误触。Kivy Button 的 on_release 只查抬手点是否
    仍在按钮内——ScrollView 滚动时行随内容一起移动，手指与行
    相对位置不变，collide 仍命中，拖动即误触发（真机"一碰就
    选中"根因）。自研同等语义：down 只记录起点、不消费事件
    （ScrollView 才能收到 move 起滚）；up 按屏幕绝对位移 ≤ 8dp
    且按压 ≤ 0.55s 且抬手点仍在行内才切勾选；滑动/长按不触发。
    """
    mark = StringProperty("[color=#94a3b8]☐[/color]")
    row_text = StringProperty("")
    sel_bg = ListProperty((0.886, 0.906, 0.933, 1))

    def __init__(self, idx=0, on_tap=None, **kw):
        self.idx = idx
        self._on_tap = on_tap
        super().__init__(**kw)

    def on_touch_down(self, touch):
        try:
            if (self.collide_point(*touch.pos)
                    and not touch.is_mouse_scrolling):
                touch.ud["pb_filerow"] = (id(self), touch.x, touch.y,
                                          time.time())
        except Exception:
            pass
        return False

    def on_touch_up(self, touch):
        try:
            hit = touch.ud.get("pb_filerow")
            if (hit is not None and hit[0] == id(self)
                    and self.collide_point(*touch.pos)
                    and abs(touch.x - hit[1]) <= dp(8)
                    and abs(touch.y - hit[2]) <= dp(8)
                    and time.time() - hit[3] <= 0.55
                    and self._on_tap):
                self._on_tap(self.idx)
        except Exception:
            pass
        return False


class FilesScreen(Screen):
    """文件列表屏（v3.0.0 分享勾选 + v3.1.0 网盘原生浏览双形态）。"""


class LogsScreen(Screen):
    """日志屏（v2.0.0）：统一日志实时查看（ERROR 红/WARN 橙着色）。"""
    pass


def external_files_dir():
    """应用外部私有目录（scoped storage 下免权限，用户可取文件）。"""
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        d = activity.getExternalFilesDir(None)
        if d is not None:
            return str(d.getAbsolutePath())
    except Exception:
        pass
    return str(Path(__file__).parent / "downloads")


_PUB_DL_OK = None


def _probe_public_download():
    """公共 Download 可写性探测（v3.2.7：对齐引擎真实写路径）。

    两轮真机实锤的教训：
    - v3.2.5：探测 open('wb') 通过，引擎 os.open(O_RDWR) 被拒
      （Errno 13）——FUSE 对公共目录拒发读写打开；
    - v3.2.6：探测改 .apk 后缀仍误判（差异不在后缀在打开模式）。
    v3.2.7 引擎已降级（O_RDWR→O_WRONLY + flock/ftruncate
    fail-open），探测必须模拟**降级后的最终路径**：
    os.open(O_WRONLY|O_CREAT) + pwrite 超 EOF 写（文件扩展
    语义）+ unlink——探测通过即引擎必能写。
    """
    from jnius import autoclass
    Env = autoclass("android.os.Environment")
    base = Env.getExternalStoragePublicDirectory(Env.DIRECTORY_DOWNLOADS)
    d = os.path.join(str(base.getAbsolutePath()), "PanBoost")
    os.makedirs(d, exist_ok=True)
    probe = os.path.join(d, ".probe.apk")
    fd = os.open(probe, os.O_WRONLY | os.O_CREAT, 0o644)
    try:
        os.pwrite(fd, b"ok", 1024)  # 超 EOF 写：文件扩展语义
    finally:
        os.close(fd)
    os.remove(probe)
    return d


_FORCE_PRIVATE = {"on": False}


def download_dir():
    """下载输出目录（v3.0.0：优先公共 Download/PanBoost）。

    公共目录文件管理器直接可见（用户诉求"下载的文件找不到"）。
    v3.2.7：①探测对齐引擎真实写路径（O_WRONLY+pwrite 扩展）；
    ②运行中真实写入若仍被拒（未知 FUSE 怪癖），_FORCE_PRIVATE
    落闸后本次运行全走 App 私有目录（必可写，下载永不失败），
    并自动重试该文件；重启 App 后重新探测（授权后有机会切回）。
    """
    global _PUB_DL_OK
    if _FORCE_PRIVATE["on"]:
        return external_files_dir()
    if _PUB_DL_OK is not None:
        return _PUB_DL_OK
    try:
        _PUB_DL_OK = _probe_public_download()
    except Exception:
        _PUB_DL_OK = external_files_dir()
    return _PUB_DL_OK


def reset_download_dir_probe():
    """权限变化后重置公共目录探测缓存（v3.2.6）。"""
    global _PUB_DL_OK
    _PUB_DL_OK = None


def all_files_granted():
    """"所有文件访问"权限（API 30+，v3.2.6）。

    授权后公共 Download 媒体文件可直接路径写（512 线程 seek
    全速）。非 Android / API 29- / 异常时 False。
    """
    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build$VERSION")
        if (Build.SDK_INT or 0) < 30:
            return False
        Env = autoclass("android.os.Environment")
        return bool(Env.isExternalStorageManager())
    except Exception:
        return False


def request_all_files():
    """跳系统"所有文件权限"设置页（API 30+）。返回是否已发起。"""
    try:
        from jnius import autoclass
        Build = autoclass("android.os.Build$VERSION")
        if (Build.SDK_INT or 0) < 30:
            return False
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        Intent = autoclass("android.content.Intent")
        i = Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION)
        i.setData(Uri.parse("package:"
                            + PythonActivity.mActivity.getPackageName()))
        PythonActivity.mActivity.startActivity(i)
        return True
    except Exception:
        return False


def _dump_crash(tag):
    """未捕获异常写 crash-*.log 到外部私有目录（可取回诊断）。

    文件名带微秒后缀：秒级精度下同秒多次异常会互相覆盖丢日志。"""
    try:
        import traceback
        d = external_files_dir()
        os.makedirs(d, exist_ok=True)
        p = os.path.join(
            d, "crash-%s-%06d.log" % (
                time.strftime("%Y%m%d-%H%M%S"),
                time.time_ns() % 1000000))
        with open(p, "w", encoding="utf-8") as f:
            f.write(tag + traceback.format_exc())
    except Exception:
        pass
    # v2.0.0：crash 同步进统一日志（日志屏实时可见）
    applog.error("crash", tag)


def _on_ui(fn):
    """Kivy 控件操作调度回 Kivy 主线程（v1.8.4 线程安全加固）。

    登录层回调（on_done/on_cancel）可能来自 Android UI 线程（按钮
    点击/Dialog 取消/渲染进程崩溃）或轮询线程——Kivy 控件属性操作
    非线程安全，跨线程直调有底层崩溃风险。Clock.schedule_once 是
    Kivy 官方的跨线程调度方式；不可用时同步直调（冒烟测试 mock）。
    """
    try:
        Clock.schedule_once(lambda _dt: fn())
    except Exception:
        fn()


def _on_ui_later(fn, delay=0.25):
    """登录层完成/取消回调的延迟调度（v2.0.1 防闪退强化）。

    v2.0.0 真机"完成登录后直接闪退"回归：on_done 在 Android UI
    线程（手动点【已完成登录】，_run_ui 同步执行 _ui_close 后）
    或轮询线程（特征命中）执行，其中新增的磁盘 IO 把回调线程拖
    在关闭链里；dismiss 后 Chromium 渲染流水线仍有迟到 IPC 在
    途，零延迟的 Clock 调度让 _after_login 的 UI 操作与关闭清理
    重叠——低端机上撞出 v1.9.1 同款 SIGSEGV 窗口。对策：回调线
    程零工作零 IO（全部挪入本调度）；延迟 0.25s 让 dismiss+解绑
    +退休完全落地。
    """
    try:
        Clock.schedule_once(lambda _dt: fn(), delay)
    except Exception:
        fn()


def _dump_nav_log(pan_key):
    """WebView 导航日志落盘 nav-*.log（v1.8.3 诊断"跳到下载App界面"）。

    onPageStarted 记录的一切导航（含 302 落地与市场拦截），登录
    结束（完成/放弃）时写到外部私有目录，用户反馈时可取回看
    "到底跳去了哪"。"""
    try:
        entries = weblogin.nav_log()
        if not entries:
            return
        d = external_files_dir()
        os.makedirs(d, exist_ok=True)
        p = os.path.join(
            d, "nav-%s-%s.log" % (pan_key,
                                  time.strftime("%Y%m%d-%H%M%S")))
        with open(p, "w", encoding="utf-8") as f:
            f.write("PanBoost v1.8.3 WebView 导航日志 [%s]\n" % pan_key)
            for kind, ts, u in entries:
                f.write("[%s] %-5s %s\n" % (ts, kind, u))
    except Exception:
        pass


def _install_crash_logger():
    """崩溃兜底：未捕获异常写 crash-*.log 到外部私有目录（可取回诊断）。"""
    def _hook(t, v, tb):
        _dump_crash("sys.excepthook: %s: %s\n" % (t.__name__, v))
        sys.__excepthook__(t, v, tb)

    sys.excepthook = _hook
    try:
        from kivy.base import ExceptionManager, ExceptionHandler

        class _CrashHandler(ExceptionHandler):
            def handle_exception(self, e):
                _dump_crash("kivy: %s: %s\n" % (type(e).__name__, e))
                return ExceptionManager.RAISE

        ExceptionManager.handler = _CrashHandler()
    except Exception:
        pass


_install_crash_logger()


# ---------------- 下载保活（前台服务 + WakeLock） ----------------

_KEEPALIVE = {"wl": None}


def start_keepalive():
    """下载开始：持 PARTIAL_WAKE_LOCK（v3.2.5 起唯一保活手段）。

    v3.2.4 及此前还起 p4a AndroidService 前台服务——真机实锤这是
    "下载结束即闪退"的雷源：p4a 的 PythonService.onDestroy() 里有
    Process.killProcess(Process.myPid())，而服务与主 App 同进程，
    下载 finally 调 stop_keepalive() → stopService → onDestroy →
    整个 App 被杀（30s 探测超时 + 开销 ≈ 用户实测的 38 秒闪退）。
    v3.2.5 移除服务路径，只留 WakeLock（纯 JNI 调用，无服务
    生命周期，不可能触发进程级 onDestroy）；锁屏下载保活由
    WakeLock 承担，任何一步失败静默降级（引擎实时落盘兜底）。"""
    if not IS_ANDROID:
        return False
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        PowerManager = autoclass("android.os.PowerManager")
        pm = PythonActivity.mActivity.getSystemService(Context.POWER_SERVICE)
        wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PanBoost:dl")
        wl.acquire()
        _KEEPALIVE["wl"] = wl
        return True
    except Exception:
        _KEEPALIVE["wl"] = None
        return False


def stop_keepalive():
    """下载结束：释放 WakeLock（必须释放防耗电；v3.2.5 起无服务
    路径——stopService 触发 p4a PythonService.onDestroy 的
    Process.killProcess 杀全进程，是 v3.2.4 真机闪退根因）。"""
    try:
        if _KEEPALIVE["wl"] is not None:
            _KEEPALIVE["wl"].release()
    except Exception:
        pass
    _KEEPALIVE["wl"] = None


# ---------------- 账簿（登录网盘永久记录） ----------------

def load_accounts():
    try:
        d = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return d
    except Exception:
        pass
    return {}


def save_accounts(acc):
    try:
        pb.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = str(ACCOUNTS_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(acc, f, ensure_ascii=False, indent=1)
        os.replace(tmp, ACCOUNTS_FILE)
    except Exception:
        pass


def record_login(pan_key, cookie, auto):
    """登录成功：写账簿 + 同步引擎 cookie store（下载自动匹配）。

    v1.8.5 防御性凭证校验（weblogin._finish 已校验，此处兜底防
    回退/异常路径）：有 auth_keys 的网盘特征未命中 → 返回 False
    不记账（游客 Cookie 绝不冒充登录态）；无 auth_keys 的网盘
    （localStorage 型登录态）记 "verified": False——Cookie 保存
    供下载尝试，但卡片/账号页显示"Cookie 已存·未验证"。
    """
    pan = PAN_BY_KEY.get(pan_key)
    if pan is None or not cookie:
        return False
    keys = [k.lower() for k in pan.get("auth_keys") or []]
    if keys and not all(f"{k}=" in cookie.lower() for k in keys):
        return False
    acc = load_accounts()
    acc[pan_key] = {"name": pan["name"], "ts": int(time.time()),
                    "auto": bool(auto), "len": len(cookie),
                    "verified": bool(keys)}
    save_accounts(acc)
    store = pb.load_cookie_store()
    for domain in pan["domains"]:
        store[domain] = cookie
    pb.save_cookie_store(store)
    return True


def remove_login(pan_key):
    """删除登录：账簿 + 引擎 cookie store 同步清理。"""
    pan = PAN_BY_KEY.get(pan_key)
    acc = load_accounts()
    if pan_key not in acc and pan is None:
        return False
    acc.pop(pan_key, None)
    save_accounts(acc)
    store = pb.load_cookie_store()
    for domain in (pan["domains"] if pan else []):
        store.pop(domain, None)
    pb.save_cookie_store(store)
    return True


def _safe_name(name, url):
    name = (name or "").replace("/", "_").replace("\\", "_") \
        .replace("\x00", "").strip()
    if not name:
        name = os.path.basename(urllib.parse.urlsplit(url).path) or ""
    return name or "download.bin"


# ---------------- 历史记录（永久保存） ----------------

def load_history():
    try:
        d = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict) and isinstance(d.get("items"), list):
            return d
    except Exception:
        pass
    return {"enabled": True, "items": []}


def save_history(h):
    try:
        pb.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = str(HISTORY_FILE) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(h, f, ensure_ascii=False, indent=1)
        os.replace(tmp, HISTORY_FILE)
    except Exception:
        pass


def add_history(entry):
    h = load_history()
    if not h.get("enabled", True):
        return
    h["items"].insert(0, entry)
    del h["items"][200:]
    save_history(h)


KV = """
<CardButton>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: self.bg_down if self.state == 'down' else self.bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(14)]
    color: 0.118, 0.161, 0.231, 1

<NavTab>:
    background_normal: ''
    background_down: ''
    background_color: 0, 0, 0, 0
    canvas.before:
        Color:
            rgba: 0.071, 0.09, 0.141, 1
        Rectangle:
            pos: self.pos
            size: self.size
        Color:
            rgba: 0.145, 0.388, 0.922, 0.22 if self.active else 0
        RoundedRectangle:
            pos: self.center_x - dp(26), self.y + dp(6)
            size: dp(52), dp(32)
            radius: [dp(16)]
    color: (0.376, 0.612, 0.965, 1) if self.active else (0.616, 0.663, 0.741, 1)
    font_size: sp(12)

<CompactOption>:
    height: dp(30)
    font_size: sp(12)
    background_normal: ''
    background_down: ''
    background_color: 0.145, 0.388, 0.922, 1 if self.state == 'down' else 0.96
    color: 1, 1, 1, 1

BoxLayout:
    orientation: 'vertical'
    ScreenManager:
        id: sm
        MainScreen:
        DownloadScreen:
        AccountsScreen:
        HistoryScreen:
        LogsScreen:
        FilesScreen:
    BoxLayout:
        id: navbar
        size_hint_y: None
        height: dp(64)
        padding: dp(6), dp(8)
        spacing: dp(6)
        canvas.before:
            Color:
                rgba: 0.071, 0.09, 0.141, 1
            Rectangle:
                pos: self.pos
                size: self.size
        NavTab:
            id: tab_home
            text: '⌂ 首页'
            on_release: app.go('home')
        NavTab:
            id: tab_download
            text: '↓ 下载'
            on_release: app.go('download')
        NavTab:
            id: tab_accounts
            text: '◉ 账号'
            on_release: app.go('accounts')
        NavTab:
            id: tab_history
            text: '≡ 历史'
            on_release: app.go('history')
        NavTab:
            id: tab_logs
            text: '日志'
            on_release: app.go('logs')

<MainScreen>:
    name: 'home'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(8)
        canvas.before:
            Color:
                rgba: 0.957, 0.965, 0.984, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(34)
            spacing: dp(8)
            Label:
                text: 'PanBoost'
                font_size: sp(24)
                bold: True
                color: 0.118, 0.161, 0.231, 1
                size_hint_x: 0.6
                halign: 'left'
                text_size: self.size
                valign: 'middle'
            Label:
                text: 'v' + app.shell_version
                font_size: sp(11)
                color: 0.396, 0.447, 0.533, 1
                size_hint_x: 0.4
                halign: 'right'
                text_size: self.size
                valign: 'middle'

        Label:
            text: '已登录点卡片直达我的网盘（复制链接去下载页加速）；未登录点卡片登录'
            font_size: sp(12)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: dp(18)

        ScrollView:
            GridLayout:
                id: pan_grid
                cols: 3
                size_hint_y: None
                height: self.minimum_height
                padding: dp(2), dp(2)
                spacing: dp(8)

        CardButton:
            text: '高级下载（URL 直链）'
            font_size: sp(15)
            bold: True
            bg: 0.145, 0.388, 0.922, 1
            bg_down: 0.118, 0.298, 0.761, 1
            size_hint_y: None
            height: dp(48)
            color: 1, 1, 1, 1
            on_release: app.go('download')

        CardButton:
            id: perm_hint
            text: '授予所有文件权限——下载保存到公共 Download'
            font_size: sp(12)
            bg: 0.988, 0.831, 0.251, 0.95
            bg_down: 0.906, 0.749, 0.204, 0.95
            size_hint_y: None
            height: dp(0)
            color: 0.235, 0.161, 0.039, 1
            on_release: app.on_perm_tap()

        Label:
            id: home_status
            text: ''
            font_size: sp(11)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: dp(16)
            halign: 'left'

<DownloadScreen>:
    name: 'download'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(6)
        canvas.before:
            Color:
                rgba: 0.957, 0.965, 0.984, 1
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            text: '下载'
            font_size: sp(20)
            bold: True
            color: 0.118, 0.161, 0.231, 1
            size_hint_y: None
            height: dp(30)
            halign: 'left'
            text_size: self.size

        TextInput:
            id: url_input
            hint_text: '下载 URL：直链，或蓝奏/123/夸克分享链接'
            multiline: False
            size_hint_y: None
            height: dp(40)

        TextInput:
            id: cookie_input
            hint_text: '本次 Cookie（可选，留空自动匹配已登录网盘）'
            multiline: False
            size_hint_y: None
            height: dp(40)

        BoxLayout:
            size_hint_y: None
            height: dp(40)
            spacing: dp(6)
            Label:
                text: '线程:'
                color: 0.118, 0.161, 0.231, 1
                size_hint_x: None
                width: dp(44)
            Spinner:
                id: threads_spinner
                text: 'auto'
                values: ['auto', '8', '16', '32', '64', '128', '256', '512', '1024']
                option_cls: app.compact_option
                size_hint_x: 0.35
            Switch:
                id: insecure_switch
                size_hint_x: None
                width: dp(44)
            Label:
                text: '跳过证书校验'
                font_size: sp(11)
                color: 0.396, 0.447, 0.533, 1
                halign: 'left'
                text_size: self.size

        CardButton:
            id: go_btn
            text: '开始下载'
            bold: True
            font_size: sp(15)
            bg: 0.145, 0.388, 0.922, 1
            bg_down: 0.118, 0.298, 0.761, 1
            color: 1, 1, 1, 1
            size_hint_y: None
            height: dp(46)
            on_release: app.on_go()

        ProgressBar:
            id: progress
            max: 1.0
            value: 0
            size_hint_y: None
            height: dp(14)

        Label:
            id: status_lbl
            text: '待命。目录: ' + app.dir_short
            font_size: sp(12)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: dp(34)
            halign: 'left'
            valign: 'middle'
            text_size: self.size

        ScrollView:
            Label:
                id: log_lbl
                text: ''
                font_size: sp(11)
                color: 0.396, 0.447, 0.533, 1
                size_hint_y: None
                height: max(self.texture_size[1], dp(24))
                text_size: (self.width - dp(6), None)
                halign: 'left'

<AccountsScreen>:
    name: 'accounts'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(6)
        canvas.before:
            Color:
                rgba: 0.957, 0.965, 0.984, 1
            Rectangle:
                pos: self.pos
                size: self.size

        Label:
            text: '我的账号'
            font_size: sp(20)
            bold: True
            color: 0.118, 0.161, 0.231, 1
            size_hint_y: None
            height: dp(30)
            halign: 'left'
            text_size: self.size

        Label:
            text: '已登录网盘永久记录在此。新登录请回首页点网盘卡片；也可手动粘贴任意站点 Cookie。点击条目删除。'
            font_size: sp(11)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: dp(42)
            text_size: self.size
            halign: 'left'

        TextInput:
            id: domain_input
            hint_text: '手动添加：域名，如 pan.baidu.com'
            multiline: False
            size_hint_y: None
            height: dp(38)

        TextInput:
            id: cookie_input
            hint_text: 'Cookie 值，如 BDUSS=xxx; STK=yyy'
            multiline: True
            size_hint_y: None
            height: dp(60)

        CardButton:
            text: '保存'
            bold: True
            font_size: sp(14)
            bg: 0.145, 0.388, 0.922, 1
            bg_down: 0.118, 0.298, 0.761, 1
            color: 1, 1, 1, 1
            size_hint_y: None
            height: dp(40)
            on_release: app.save_account()

        Label:
            id: accounts_status
            text: ''
            font_size: sp(11)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: max(self.texture_size[1], dp(18))
            text_size: (self.width - dp(4), None)
            halign: 'left'

        ScrollView:
            GridLayout:
                id: accounts_box
                cols: 1
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(4)

<HistoryScreen>:
    name: 'history'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(6)
        canvas.before:
            Color:
                rgba: 0.957, 0.965, 0.984, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(34)
            spacing: dp(8)
            Label:
                text: '下载历史（永久记录）'
                font_size: sp(17)
                bold: True
                color: 0.118, 0.161, 0.231, 1
                size_hint_x: 0.7
                halign: 'left'
                text_size: self.size
                valign: 'middle'
            Switch:
                id: rec_switch
                size_hint_x: None
                width: dp(44)
                on_active: app.on_rec_toggle(self.active)

        BoxLayout:
            size_hint_y: None
            height: dp(38)
            spacing: dp(8)
            CardButton:
                text: '清空历史'
                font_size: sp(13)
                on_release: app.clear_history()

        ScrollView:
            GridLayout:
                id: history_box
                cols: 1
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(4)

<LogsScreen>:
    name: 'logs'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(6)
        canvas.before:
            Color:
                rgba: 0.957, 0.965, 0.984, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(34)
            spacing: dp(8)
            Label:
                text: '运行日志'
                font_size: sp(20)
                bold: True
                color: 0.118, 0.161, 0.231, 1
                size_hint_x: 0.7
                halign: 'left'
                text_size: self.size
                valign: 'middle'
            CardButton:
                text: '刷新'
                font_size: sp(13)
                size_hint_x: 0.3
                on_release: app.refresh_logs()

        Label:
            id: logs_status
            text: ''
            font_size: sp(11)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: dp(30)
            text_size: self.size
            halign: 'left'

        ScrollView:
            Label:
                id: logs_lbl
                text: '（暂无日志）'
                markup: True
                font_size: sp(11)
                size_hint_y: None
                height: max(self.texture_size[1], dp(24))
                text_size: (self.width - dp(6), None)
                halign: 'left'

<FilesScreen>:
    name: 'files'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(6)
        canvas.before:
            Color:
                rgba: 0.957, 0.965, 0.984, 1
            Rectangle:
                pos: self.pos
                size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(34)
            spacing: dp(8)
            CardButton:
                text: '‹ 返回'
                font_size: sp(14)
                size_hint_x: None
                width: dp(76)
                on_release: app.files_back()
            Label:
                id: files_title
                text: '分享文件'
                font_size: sp(17)
                bold: True
                color: 0.118, 0.161, 0.231, 1
                halign: 'left'
                text_size: self.size
                valign: 'middle'

        Label:
            id: files_info
            text: ''
            font_size: sp(11)
            color: 0.396, 0.447, 0.533, 1
            size_hint_y: None
            height: dp(16)
            text_size: self.size
            halign: 'left'

        ScrollView:
            scroll_distance: dp(12)
            GridLayout:
                id: files_box
                cols: 1
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(4)

        BoxLayout:
            size_hint_y: None
            height: dp(42)
            spacing: dp(8)
            CardButton:
                id: files_sel_all
                text: '全选 / 全不选'
                font_size: sp(13)
                size_hint_x: 0.4
                on_release: app.toggle_all_files()
            CardButton:
                id: files_dl_btn
                text: '下载所选'
                font_size: sp(14)
                bold: True
                bg: 0.145, 0.388, 0.922, 1
                bg_down: 0.118, 0.298, 0.761, 1
                color: 1, 1, 1, 1
                size_hint_x: 0.6
                on_release: app.start_selected_downloads()

        BoxLayout:
            id: files_retry_box
            size_hint_y: None
            height: dp(0)
            opacity: 0
            spacing: dp(8)
            CardButton:
                id: files_retry_btn
                text: '🔄 重新加载'
                font_size: sp(13)
                bg: 0.145, 0.388, 0.922, 1
                bg_down: 0.118, 0.298, 0.761, 1
                color: 1, 1, 1, 1
                on_release: app.files_retry()

        Label:
            id: files_error_detail
            text: ''
            font_size: sp(10)
            color: 0.7, 0.2, 0.2, 1
            size_hint_y: None
            height: dp(0)
            text_size: self.size
            halign: 'left'
            valign: 'middle'


<FileRow>:
    orientation: 'horizontal'
    size_hint_y: None
    height: dp(52)
    padding: dp(10), dp(6)
    spacing: dp(4)
    canvas.before:
        Color:
            rgba: self.sel_bg
        Rectangle:
            pos: self.pos
            size: self.size
    Label:
        markup: True
        text: root.mark
        font_size: sp(17)
        size_hint_x: None
        width: dp(30)
    Label:
        markup: True
        font_size: sp(12)
        halign: 'left'
        valign: 'middle'
        text: root.row_text
        text_size: self.size
        color: 0.118, 0.161, 0.231, 1
"""


class PanBoostApp(App):
    title = "PanBoost"
    compact_option = CompactOption
    COLOR_BG = BG
    COLOR_CARD = CARD

    def build(self):
        self.shell_version = SHELL_VERSION
        self.dl = None
        self.worker = None
        self.logs = []
        self._log_serial = -1
        # v3.0.0 分享文件列表（YunX 式勾选下载）
        self._share_ctx = None
        self._drive_ctx = None
        self._drive_loading = False
        self._file_sel = []
        self._status = "待命"
        self._progress = 0.0
        self._btn_text = "开始下载"
        self.dir_short = external_files_dir()
        # v2.0.0 统一日志：app-*.log 按天轮转（保留 7 天）+ 全局
        # 异常钩子（主线程/子线程未捕获异常全部进日志，链式保留
        # crash-*.log 落盘）
        applog.init(self.dir_short)
        applog.install_hooks()
        applog.info("app", "PanBoost v%s 启动（Android=%s）"
                    % (SHELL_VERSION, IS_ANDROID))
        self.root = Builder.load_string(KV)
        # Android 返回键/手势（Kivy keycode 27）必须显式处理：
        # WebView 登录层打开时系统默认行为既不关层也不回退网页，
        # 用户会被困在登录层（v1.8.0 真机反馈）
        Window.bind(on_keyboard=self._on_key)
        # v3.0.0 剪贴板识别：复制分享链接回到 App 自动填入
        try:
            self.bind(on_resume=self._on_resume)
        except Exception:
            pass
        Clock.schedule_interval(self._tick, 0.5)
        self._build_pan_grid()
        self._load_settings()
        return self.root

    # ---------- 屏幕与设置 ----------

    def _guard(self, fn, *args):
        """按钮回调异常兜底：Kivy 只把回调异常写 logcat（用户无感知），
        这里落 crash-*.log 并显示到首页状态栏——绝不静默。"""
        def wrap(_btn):
            try:
                fn(*args)
            except Exception as e:
                _dump_crash("ui callback %s: " % getattr(fn, "__name__", fn))
                try:
                    self._home_status(f"操作失败: {type(e).__name__}: {e}")
                except Exception:
                    pass
        return wrap

    def go(self, name):
        """切屏（v2.0.0：底部导航 Tab 高亮同步 + 各屏惰性刷新）。"""
        try:
            self.root.ids.sm.current = name
        except Exception:
            pass
        for key in ("home", "download", "accounts", "history", "logs"):
            try:
                tab = getattr(self.root.ids, "tab_" + key, None)
                if tab is not None:
                    tab.active = (key == name)
            except Exception:
                pass
        if name == "accounts":
            self.refresh_accounts()
        elif name == "history":
            self.refresh_history()
        elif name == "logs":
            self.refresh_logs()
        elif name == "home":
            self.refresh_perm_hint()

    def _cur(self):
        """当前屏名（v2.0.0 root 为 BoxLayout，ScreenManager 在 ids.sm）。"""
        try:
            return self.root.ids.sm.current
        except Exception:
            return "home"

    def refresh_logs(self):
        """日志屏渲染：ring 最近 200 条，ERROR 红 / WARN 橙着色。"""
        try:
            lines = []
            for ts, lv, tag, msg in applog.ring_raw()[-200:]:
                one = "%s %s [%s] %s" % (ts, lv, tag, msg)
                if lv == "ERROR":
                    lines.append("[color=#dc2626]%s[/color]" % one)
                elif lv == "WARN":
                    lines.append("[color=#d97706]%s[/color]" % one)
                else:
                    lines.append(one)
            ids = self._scr("logs").ids
            ids.logs_lbl.text = "\n".join(lines) if lines else "（暂无日志）"
            n_files = len(applog.log_files())
            ids.logs_status.text = (
                "最近 %d 条 · 日志文件 %d 份（app-日期.log，保留 7 天，"
                "在应用外部目录可取回反馈）" % (len(lines), n_files))
        except Exception:
            _dump_crash("refresh_logs: ")

    def _on_key(self, window, key, *args):
        """三键导航 BACK 的 Kivy 兜底（v1.8.3：手势不经过此路径）：

        登录层打开 → request_back（网页后退/关闭）；非首页屏 → 切回
        首页；首页 → 返回 False 走系统默认。手势导航与登录层内的
        返回已由 Dialog 系统级处理（见 weblogin.py v1.8.3）。
        """
        if key != 27:
            return False
        try:
            if weblogin.is_open():
                weblogin.request_back()
                return True
            if self.root is not None and self._cur() != "home":
                self.go("home")
                return True
        except Exception:
            _dump_crash("on_back_key: ")
        return False

    def _scr(self, name):
        return self.root.ids.sm.get_screen(name)

    def _load_settings(self):
        h = load_history()
        try:
            self._scr("history").ids.rec_switch.active = bool(
                h.get("enabled", True))
        except Exception:
            pass

    def on_rec_toggle(self, active):
        h = load_history()
        h["enabled"] = bool(active)
        save_history(h)

    # ---------- 首页网盘宫格 ----------

    def _build_pan_grid(self):
        grid = self._scr("home").ids.pan_grid
        grid.clear_widgets()
        acc = load_accounts()
        for pan in PANS:
            rec = acc.get(pan["key"])
            if rec is not None and rec.get("verified", True):
                txt = (f"{pan['name']}\n"
                       "[b][color=#16a34a]已登录[/color][/b] "
                       "[color=#2563eb]进入我的网盘 ›[/color]\n"
                       f"[sub]{pan['domains'][0]}[/sub]")
            elif rec is not None:
                # v1.8.5：Cookie 已保存但无法验证登录态（localStorage
                # 型网盘）——如实显示，绝不冒充"已登录"
                txt = (f"{pan['name']}\n"
                       "[b][color=#b45309]Cookie已存·未验证[/color][/b]\n"
                       f"[sub]{pan['domains'][0]}[/sub]")
            else:
                # v1.9.0：第三行行动召唤，用户不用猜点卡片干什么
                txt = (f"{pan['name']}\n"
                       "[color=#2563eb]点击网页登录[/color]\n"
                       f"[sub]{pan['domains'][0]}[/sub]")
            btn = CardButton(
                text=txt, markup=True, font_size=sp(13),
                size_hint_y=None, height=dp(96),
                halign="center", valign="middle")
            btn.bind(on_release=self._guard(self.pan_login, pan["key"]))
            grid.add_widget(btn)

    def _home_status(self, msg):
        try:
            self._scr("home").ids.home_status.text = msg
        except Exception:
            pass

    def _open_browse(self, pan_key):
        """已登录网盘：WebView 直开网页版"我的文件"（浏览模式）。"""
        pan = PAN_BY_KEY.get(pan_key)

        def on_close():
            def _ui():
                applog.info("browse", "%s 浏览层关闭" % pan_key)
                self.go("download")
                self._home_status(
                    f"把在 {pan['name']} 复制的文件/分享链接粘贴到"
                    "本页，点开始下载即可加速")
            _on_ui_later(_ui)

        weblogin.open_browse(pan["home"], pan["name"], on_close=on_close)
        applog.info("browse", "打开 %s 我的网盘（%s）"
                    % (pan["name"], pan["home"]))
        self._home_status(
            f"已打开 {pan['name']} 我的网盘——浏览/长按复制文件或"
            "分享链接，完成后点底部按钮回到下载页")

    def pan_login(self, pan_key):
        """点击网盘卡片：已登录直入我的网盘；未登录 WebView 登录。"""
        pan = PAN_BY_KEY.get(pan_key)
        if pan is None:
            return
        if self.worker is not None and self.worker.is_alive():
            self._home_status("下载进行中，请等待完成后再登录")
            return
        # v2.1.0：已登录卡片直入网盘浏览模式——不再二次打开登录
        # 层（真机"已登录点卡片闪退"根因：poller 首轮特征 Cookie
        # 即命中 → 层 show 后 1-2s 被秒关，dismiss 与 Chromium 启
        # 动渲染竞争即 SIGSEGV；且已登录用户要的是"进我账号选
        # 东西下载"，不是再看一遍登录页）
        acc = load_accounts()
        rec = acc.get(pan_key)
        if rec is not None and rec.get("verified", True):
            # v3.1.0：夸克已登录走原生"我的网盘"（Web API + 原生
            # FileRow 列表）——WebView 网页版是 PC 页面，真机触摸
            # 拖拽被网页解释成选择/点按且无原生滚动（"手指放在
            # 文件区就自动选了"根因），原生列表的滑动/轻点即
            # YunX 式体验；其他网盘暂回退 WebView 浏览
            if (pan_key in drive.SUPPORTED
                    and pb.match_cookie_header(pan["home"])):
                try:
                    self._browse_drive(pan_key)
                    return
                except Exception as e:
                    # v3.2.0：原生列表失败不再回退 WebView 网页版
                    # （PC 页面真机触摸误选，用户明确反馈此坑），
                    # 提示重新登录后直接返回
                    _dump_crash("browse_drive[%s]: " % pan_key)
                    self._home_status(
                        f"网盘列表打开失败（{type(e).__name__}）——"
                        "会话可能过期，请到「账号」页删除后重新登录")
                    return
            if pan.get("home") and weblogin.available():
                try:
                    self._open_browse(pan_key)
                    return
                except Exception as e:
                    _dump_crash("open_browse[%s]: " % pan_key)
                    self._home_status(
                        f"打开网盘失败（{type(e).__name__}），"
                        "改开登录页")
        err_txt = None
        if weblogin.available():
            def on_done(cookie, auto):
                # v2.0.1：回调线程（Android UI 线程/轮询线程）零工作
                # 零 IO——磁盘日志全部挪入延迟调度；0.25s 让 _ui_close
                # 的解绑+dismiss+退休完全落地后再做 Kivy 操作
                _on_ui_later(
                    lambda: self._after_login(pan_key, cookie, auto))

            def on_cancel():
                def _ui():
                    applog.info("login", "%s 登录已取消（未保存）" % pan_key)
                    _dump_nav_log(pan_key)
                    self._home_status(
                        f"已返回（{pan['name']} 登录未保存）——"
                        "随时可再点卡片登录")
                _on_ui_later(_ui)

            try:
                weblogin.open_login(
                    pan["login"], pan["auth_keys"], on_done,
                    title=pan["name"], on_cancel=on_cancel,
                    cookie_urls=tuple(f"https://{d}/"
                                      for d in pan["domains"]))
                applog.info("login", "打开 %s 网页登录（%s）"
                            % (pan["name"], pan["login"]))
                self._home_status(
                    f"已打开 {pan['name']} 网页登录（桌面版）——"
                    "顶部 ✕ 或返回键回到本页"
                    + ("，检测到登录将自动保存" if pan["auth_keys"]
                       else "，登录后点底部【已完成登录】"))
                return
            except Exception as e:
                err_txt = f"{type(e).__name__}: {e}"
                _dump_crash("weblogin 打开失败[%s]: " % pan_key)
        # 回退：跳账号屏手动粘贴（预填域名）；WebView 失败详情必须
        # 显示到用户实际所在的账号页（v1.7.1 写首页状态栏用户看不到）
        acc = self._scr("accounts").ids
        acc.domain_input.text = pan["domains"][0]
        if err_txt:
            acc.accounts_status.text = (
                f"WebView 登录打开失败：{err_txt[:110]}\n"
                f"已切手动模式：浏览器登录 {pan['name']} 后复制 Cookie "
                "粘贴保存；详情见 crash-*.log")
        else:
            acc.accounts_status.text = (
                f"请在浏览器登录 {pan['name']}，复制 Cookie 粘贴到此处保存")
        self.go("accounts")

    def _after_login(self, pan_key, cookie, auto):
        # v2.0.1：整体 try 兜底——Clock 回调异常会杀 Kivy 主循环
        # （表象即闪退且无 crash-*.log）；IO 全部后置，先恢复
        # v1.9.2 纯 UI 时序：记账→刷卡片→状态栏，磁盘日志最后补
        try:
            pan = PAN_BY_KEY.get(pan_key)
            if record_login(pan_key, cookie, auto):
                self._build_pan_grid()
                when = "自动检测" if auto else "手动确认"
                if pan.get("auth_keys"):
                    self._home_status(
                        f"{pan['name']} 已登录（{when}，Cookie 已永久保存）")
                else:
                    self._home_status(
                        f"{pan['name']} 网页 Cookie 已保存（该网盘登录态不在"
                        " Cookie 中，无法自动验证；下载时将自动尝试携带）")
                applog.info("login", "%s 已登录并永久保存（auto=%s）"
                            % (pan_key, auto))
            else:
                applog.warn("login", "%s 凭证校验未通过（Cookie 未保存）"
                            % pan_key)
                self._home_status(
                    f"未检测到 {pan['name']} 的登录凭证——请先在页面完成"
                    "登录（已登录的浏览器内页面对象才能种下特征 Cookie）")
            _dump_nav_log(pan_key)
            applog.info("login", "%s 登录完成（auto=%s）"
                        % (pan_key, auto))
        except Exception as e:
            _dump_crash("_after_login[%s]: " % pan_key)
            try:
                self._home_status(
                    f"登录保存异常: {type(e).__name__}——Cookie 已在登录"
                    "层采集，可到账号页手动粘贴（详情见 crash-*.log）")
            except Exception:
                pass

    # ---------- 账号管理 ----------

    def save_account(self):
        ids = self._scr("accounts").ids
        domain = ids.domain_input.text.strip().lower().lstrip(".")
        cookie = ids.cookie_input.text.strip()
        st = ids.accounts_status
        if not domain or not cookie:
            st.text = "域名和 Cookie 都不能为空"
            return
        store = pb.load_cookie_store()
        store[domain] = cookie
        pb.save_cookie_store(store)
        ids.domain_input.text = ""
        ids.cookie_input.text = ""
        st.text = f"已保存 {domain}（下载时自动匹配携带）"
        applog.info("account", "手动保存账号 %s" % domain)
        self.refresh_accounts()

    def refresh_accounts(self):
        box = self._scr("accounts").ids.accounts_box
        box.clear_widgets()
        rows = []
        for k, v in load_accounts().items():
            pan = PAN_BY_KEY.get(k, {})
            name = (v.get("name") if isinstance(v, dict) else None) \
                or pan.get("name") or k
            ts = v.get("ts", 0) if isinstance(v, dict) else 0
            verified = v.get("verified", True) if isinstance(v, dict) else True
            state = "已登录网盘" if verified else "Cookie 已存·登录未验证"
            rows.append((name, state + " · "
                        + time.strftime("%Y-%m-%d", time.localtime(ts)), k))
        for domain, cookie in sorted(pb.load_cookie_store().items()):
            if any(domain in p["domains"] for p in PANS):
                continue  # 账簿已含
            rows.append((domain, f"手动添加 · {cookie[:28]}…", domain))
        if not rows:
            box.add_widget(Label(
                text="暂无账号。回首页点网盘卡片登录，或手动粘贴 Cookie。",
                font_size=sp(11), color=SUB,
                size_hint_y=None, height=dp(40)))
            return
        for title, sub, key in rows:
            btn = CardButton(
                text=f"{title}\n[sub]{sub}[/sub]", markup=True,
                font_size=sp(12), size_hint_y=None, height=dp(52),
                halign="left", valign="middle")
            btn.bind(on_release=self._guard(self.del_account, key))
            box.add_widget(btn)

    def del_account(self, key):
        applog.info("account", "删除账号 %s" % key)
        if key in PAN_BY_KEY:
            remove_login(key)
        else:
            store = pb.load_cookie_store()
            store.pop(key, None)
            pb.save_cookie_store(store)
        self._scr("accounts").ids.accounts_status.text = f"已删除 {key}"
        self.refresh_accounts()
        self._build_pan_grid()

    # ---------- 历史 ----------

    def refresh_history(self):
        box = self._scr("history").ids.history_box
        box.clear_widgets()
        items = load_history().get("items", [])
        if not items:
            box.add_widget(Label(text="暂无下载记录",
                                 font_size=sp(12), color=SUB,
                                 size_hint_y=None, height=dp(30)))
            return
        for it in items:
            ts = time.strftime("%m-%d %H:%M", time.localtime(it.get("ts", 0)))
            txt = (f"[{ts}] {it.get('status', '?')}  {it.get('name', '?')}  "
                   f"{pb.fmt_size(it.get('size', 0))}"
                   + (f"  {pb.fmt_size(it.get('speed', 0))}/s"
                      if it.get("speed") else ""))
            btn = CardButton(text=txt, font_size=sp(11), size_hint_y=None,
                             height=dp(36), halign="left")
            btn.bind(on_release=self._guard(self.rerun, it.get("url", "")))
            box.add_widget(btn)

    def rerun(self, url):
        if not url:
            return
        self._scr("download").ids.url_input.text = url
        self.go("download")
        self.log(f"已预填 URL，点击开始下载即可重跑（续传）：{url[:60]}")

    def clear_history(self):
        save_history({"enabled": load_history().get("enabled", True),
                      "items": []})
        self.refresh_history()

    # ---------- worker 线程侧 ----------

    def log(self, msg):
        stamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{stamp}] {msg}")
        if len(self.logs) > 200:
            del self.logs[:100]

    def on_go(self):
        if self.worker is not None and self.worker.is_alive():
            if self.dl is not None:
                self.dl.stop_event.set()
                self.log("已请求停止，进度将保存…")
            self._cancel = True
            return
        url = self._scr("download").ids.url_input.text.strip()
        if not url:
            self.log("请先输入下载 URL（直链或网盘分享链接）")
            return
        manual_cookie = self._scr("download").ids.cookie_input.text.strip()
        choice = self._scr("download").ids.threads_spinner.text
        insecure = bool(self._scr("download").ids.insecure_switch.active)
        auto_cookie = pb.match_cookie_header(url) if not manual_cookie else None
        if manual_cookie:
            self.log("使用手动填写的 Cookie")
        elif auto_cookie:
            self.log(f"自动匹配已登录网盘 Cookie（{auto_cookie[:40]}…）")
        else:
            self.log("未匹配到已存账号 Cookie，匿名下载")
        applog.info("download", "开始下载 %s（线程=%s）"
                    % (url[:96], choice))
        self._progress = 0.0
        self._status = "探测中…"
        self._cancel = False
        if start_keepalive():
            self.log("已开启前台保活（锁屏/后台下载不断流）")
        self.worker = threading.Thread(
            target=self._run_download,
            args=(url, manual_cookie or auto_cookie, choice, insecure),
            daemon=True)
        self.worker.start()

    def _probe_with_ua_fallback(self, url, headers, insecure):
        persona = pb.PersonaKit(enabled=True)
        try:
            return pb.probe_url(url, persona.apply(headers), insecure, 30), headers
        except pb.DownloadError as e:
            if "403" not in str(e) and "401" not in str(e):
                raise
            for ua in pb.UA_POOL:
                h2 = persona.apply({**headers, "User-Agent": ua})
                try:
                    return pb.probe_url(url, h2, insecure, 30), h2
                except pb.DownloadError:
                    continue
            raise

    def _run_download(self, url, cookie, choice, insecure,
                      share_name=None, share_headers=None, share_url=None):
        """下载入口（v3.2.7：公共目录被拒自动改存应用目录重试）。

        探测可能漏掉未知 FUSE 怪癖——真实写入被拒（PermissionError）
        时落 _FORCE_PRIVATE 闸 + 重置探测缓存 + 私有目录重试同一
        文件，用户无感、下载永不失败。
        """
        self._pub_denied = None
        self._run_download_once(url, cookie, choice, insecure,
                                share_name, share_headers, share_url)
        if getattr(self, "_pub_denied", None):
            self._pub_denied = None
            _FORCE_PRIVATE["on"] = True
            reset_download_dir_probe()
            self.log("公共目录被系统拒绝——已自动改存应用目录重试")
            applog.info("download", "公共目录写入被拒，切私有目录重试")
            self._run_download_once(url, cookie, choice, insecure,
                                    share_name, share_headers, share_url)

    def _run_download_once(self, url, cookie, choice, insecure,
                           share_name=None, share_headers=None,
                           share_url=None):
        # v1.8.0：分享链接先解析（蓝奏/123/夸克），多文件依次下载
        try:
            resolver = pb.find_resolver(url)
        except Exception:
            resolver = None
        if resolver:
            self._run_share(resolver, url, cookie, choice, insecure)
            return
        out_name = ""
        size = 0
        speed = 0.0
        status = "失败"
        try:
            headers = {"Cookie": cookie} if cookie else {}
            if share_headers:
                headers.update({k: v for k, v in share_headers.items() if v})
            probe, headers = self._probe_with_ua_fallback(
                url, headers, insecure)
            if probe.challenge_cookie:
                headers = pb.merge_cookie_header(
                    dict(headers), *probe.challenge_cookie)
                self.log("已自动通过浏览器验证挑战")
            out = Path(download_dir()) / _safe_name(
                share_name or probe.filename, url)
            out.parent.mkdir(parents=True, exist_ok=True)
            out_name = out.name
            size = probe.size or 0
            size_txt = pb.fmt_size(probe.size) if probe.size else "未知大小"
            self.log(f"文件: {out.name}  {size_txt}"
                     + ("" if probe.range_ok else "（服务器不支持Range，单线程流式）"))

            if not probe.range_ok:
                dl = pb.SingleThreadDownloader(
                    url, out, headers, insecure, 30, True,
                    persona=True)
                dl._final_url = probe.final_url
                dl._probe = probe
                self.dl = dl
                rc = dl.run()
            else:
                threads = 16
                if choice == "auto":
                    if (probe.size or 0) > 64 * 1024 * 1024:
                        threads = pb.auto_tune(
                            probe.final_url, headers, insecure,
                            probe.size, True)
                        self.log(f"auto 实测选定线程数: {threads}")
                else:
                    threads = int(choice)
                dl = pb.MultiThreadDownloader(
                    url, out, threads, headers, insecure, 30,
                    pb.RETRY_MAX, True,
                    host=pb.url_host(probe.final_url))
                dl._final_url = probe.final_url
                dl._initial_done = 0
                started = dl.prepare(probe=probe)
                if not started:
                    self.log("已是完整文件，无需下载")
                    self._status = f"完成: {out.name}"
                    self._progress = 1.0
                    return
                dl._initial_done = dl.done_bytes
                if dl.done_bytes > 0:
                    self.log(f"续传: 从 {pb.fmt_size(dl.done_bytes)} / "
                             f"{pb.fmt_size(dl.size)} 继续")
                self.dl = dl
                rc = dl.run()
            if rc == 0:
                self._progress = 1.0
                self._status = f"完成: {out.name}  {size_txt}"
                status = "完成"
                elapsed = max(time.time() - (self.dl.start_time
                                              if self.dl else time.time()), 1e-6)
                speed = (size or 0) / elapsed
                self.log("下载完成")
                applog.info("download", "完成 %s（%d 字节）"
                            % (out_name, size))
            elif rc == 130:
                self._status = "已停止（进度已保存，可续传）"
                status = "中断"
                applog.warn("download", "用户停止 %s（进度已保存）"
                            % out_name)
            else:
                err = self.dl.errors[0] if self.dl and self.dl.errors else "未知错误"
                self._status = "失败（进度已保存）"
                status = "失败"
                self.log(f"失败: {err}")
                applog.error("download", "下载失败 %s: %s"
                             % (url[:96], err))
        except PermissionError as e:
            # v3.2.7：写路径被系统拒（FUSE/权限怪癖）——不记失败
            # 历史，标记后由 _run_download 自愈重试（私有目录）
            self._pub_denied = str(e)
            self._status = "切换存储位置中…"
            self.log(f"写入被系统拒绝: {e}")
            applog.error("download", "写入被拒: %s（%s）"
                         % (e, url[:96]), exc=e)
        except Exception as e:
            self._status = "失败"
            status = "失败"
            if not out_name:
                out_name = _safe_name(share_name, url)  # 探测失败也记录，便于重跑
            self.log(f"{type(e).__name__}: {e}")
            applog.error("download", "%s: %s（%s）"
                         % (type(e).__name__, e, url[:96]), exc=e)
        finally:
            self.dl = None
            stop_keepalive()
            if out_name and not getattr(self, "_pub_denied", None):
                add_history({"ts": int(time.time()),
                             "url": share_url or url,
                             "name": out_name, "size": size,
                             "status": status, "speed": round(speed)})

    def _run_share(self, resolver, url, cookie, choice, insecure):
        """分享解析（v3.0.0 YunX 式）：解析出文件列表进勾选屏。

        不再解析完直接全量下载——用户先在文件列表屏勾选要下的
        文件（全选/单选切换），点「下载所选」才批量加速下载。
        """
        try:
            self.log(f"识别到分享链接（{resolver}），解析中…")
            headers = {"Cookie": cookie} if cookie else {}
            resolved = pb.RESOLVERS[resolver](url, headers)
        except pb.DownloadError as e:
            self._status = f"解析失败: {str(e)[:50]}"
            self.log(f"分享解析失败: {e}")
            applog.error("share", "分享解析失败 %s: %s"
                         % (url[:96], e), exc=e)
            add_history({"ts": int(time.time()), "url": url,
                         "name": _safe_name(None, url), "size": 0,
                         "status": "失败", "speed": 0})
            return
        if isinstance(resolved, str):
            resolved = [{"url": resolved, "name": None, "headers": None}]
        if isinstance(resolved, dict):
            resolved = [resolved]
        self._status = "解析完成，请勾选文件"
        _on_ui(lambda: self._show_share_files(
            resolved, url, cookie, choice, insecure))

    def _show_share_files(self, files, url, cookie, choice, insecure):
        """文件列表屏渲染（v3.0.0，主线程）。"""
        try:
            self._drive_ctx = None
            self._share_ctx = {"files": files, "url": url,
                               "cookie": cookie, "choice": choice,
                               "insecure": insecure}
            self._file_sel = [True] * len(files)
            self._render_files()
            self.go("files")
            self.log(f"解析出 {len(files)} 个文件——点行切换勾选，"
                     "选好点底部「下载所选」")
            applog.info("share", "分享解析 %s → %d 个文件（进勾选屏）"
                        % (url[:96], len(files)))
        except Exception as e:
            _dump_crash("_show_share_files: ")
            self._home_status(f"文件列表渲染失败: {type(e).__name__}")

    def _render_files(self):
        if self._drive_ctx is not None:
            self._render_drive()
            return
        ids = self._scr("files").ids
        box = ids.files_box
        box.clear_widgets()
        files = self._share_ctx["files"]
        total = sum(int(f.get("size") or 0) for f in files)
        ids.files_title.text = "分享文件（%d 个）" % len(files)
        ids.files_info.text = (
            "合计 %s · 轻点选择 · 上下滑动浏览" %
            (pb.fmt_size(total) if total else "大小未知"))
        for i, f in enumerate(files):
            box.add_widget(self._file_row(i, f))
        self._update_files_btn()

    def _file_row(self, i, f):
        """文件行（v3.1.0 双形态）：文件夹轻点进入；文件轻点勾选。"""
        name = f.get("name") or "文件"
        size = int(f.get("size") or 0)
        if f.get("dir"):
            return FileRow(
                idx=i, on_tap=self._guard(self._tap_row, i),
                mark="[color=#f59e0b]📁[/color]",
                row_text=("%s\n[sub]文件夹 · 轻点进入[/sub]" % name),
                sel_bg=(0.886, 0.906, 0.933, 1))
        sel = self._file_sel[i] if i < len(self._file_sel) else False
        return FileRow(
            idx=i, on_tap=self._guard(self._tap_row, i),
            mark=("[b][color=#16a34a]☑[/color][/b]" if sel
                  else "[color=#94a3b8]☐[/color]"),
            row_text=("%s\n[sub]%s[/sub]"
                      % (name,
                         pb.fmt_size(size) if size else "未知大小")),
            sel_bg=(0.831, 0.898, 0.949, 1) if sel
                  else (0.886, 0.906, 0.933, 1))

    def _toggle_file(self, i):
        """点行切换勾选（v3.0.0）。"""
        try:
            self._file_sel[i] = not self._file_sel[i]
            self._render_files()
        except Exception:
            pass

    def toggle_all_files(self):
        """全选/全不选切换（v3.0.0；v3.1.0 双形态）。"""
        try:
            if self._share_ctx is None and self._drive_ctx is None:
                return
            all_on = all(self._file_sel) if self._file_sel else False
            self._file_sel = [not all_on] * len(self._file_sel)
            self._render_files()
        except Exception:
            pass

    def _update_files_btn(self):
        n = sum(1 for s in self._file_sel if s)
        ids = self._scr("files").ids
        ids.files_dl_btn.text = "下载所选（%d）" % n
        if not self._file_sel:
            ids.files_info.text = (
                "（空目录）" if self._drive_ctx is not None
                else "（空分享）")

    def start_selected_downloads(self):
        """下载所选：批量加速下载勾选的文件（v3.1.0 双形态）。"""
        try:
            if self._share_ctx is None and self._drive_ctx is None:
                return
            if self.worker is not None and self.worker.is_alive():
                self._scr("files").ids.files_info.text = (
                    "下载进行中，请等完成后再来")
                return
            if self._drive_ctx is not None:
                ctx = self._drive_ctx
                sel = [f for f, s in zip(ctx.get("entries") or [],
                                         self._file_sel)
                       if s and not f.get("dir")]
                if not sel:
                    self._scr("files").ids.files_info.text = (
                        "未勾选任何文件（轻点文件行勾选）")
                    return
                self.go("download")
                self.log(f"开始下载所选 {len(sel)} 个文件"
                         "（可在下载页停止）")
                applog.info("download", "网盘批量下载 %d 个" % len(sel))
                self._progress = 0.0
                self._cancel = False
                if start_keepalive():
                    self.log("已开启唤醒锁（锁屏下载不断流）")
                self.worker = threading.Thread(
                    target=self._run_drive_batch,
                    args=(sel, ctx["pan_key"]), daemon=True)
                self.worker.start()
                return
            sel = [f for f, s in zip(self._share_ctx["files"],
                                     self._file_sel)
                   if s and not f.get("dir")]
            if not sel:
                self._scr("files").ids.files_info.text = "未勾选任何文件"
                return
            ctx = self._share_ctx
            self.go("download")
            self.log(f"开始下载所选 {len(sel)} 个文件"
                     "（可在下载页停止）")
            applog.info("download", "批量下载所选 %d 个（%s）"
                        % (len(sel), ctx["url"][:96]))
            self._progress = 0.0
            self._cancel = False
            if start_keepalive():
                self.log("已开启唤醒锁（锁屏下载不断流）")
            self.worker = threading.Thread(
                target=self._run_share_batch,
                args=(sel, ctx["url"], ctx["cookie"], ctx["choice"],
                      ctx["insecure"]), daemon=True)
            self.worker.start()
        except Exception as e:
            _dump_crash("start_selected_downloads: ")
            self._home_status(f"启动下载失败: {type(e).__name__}")

    def _run_share_batch(self, files, url, cookie, choice, insecure):
        """批量下载循环（worker 线程，v3.0.0 自 _run_share 拆出）。"""
        total = len(files)

        def _one(f):
            ck = (f.get("headers") or {}).get("Cookie") or cookie
            self._run_download(f["url"], ck, choice, insecure,
                               share_name=f.get("name"),
                               share_headers=f.get("headers"),
                               share_url=url)

        done = 0
        for i, f in enumerate(files, 1):
            if getattr(self, "_cancel", False):
                self.log(f"已停止（已完成 {done}/{total}）")
                break
            self.log(f"[{i}/{total}] {f.get('name') or '文件'}")
            self._status = f"[{i}/{total}] 下载中"
            _one(f)
            done = i
        self._status = f"批量完成 {done}/{total}"
        applog.info("download", "批量下载结束 %d/%d" % (done, total))

    def _browse_drive(self, pan_key):
        """已登录网盘：原生"我的网盘"文件列表（v3.1.0 夸克）。

        WebView 网页版在真机的触摸体验不可救（PC 页面把拖拽解释
        成选择/点按，无原生滚动——"手指放在文件区就自动选了"
        根因）——改调网页版前端同款公开 API 拉文件列表，Kivy
        原生 FileRow 渲染，滑动/轻点即 YunX 式体验。
        """
        self._share_ctx = None
        self._drive_ctx = {
            "pan_key": pan_key, "stack": [], "entries": [],
            "choice": self._scr("download").ids.threads_spinner.text,
            "insecure": bool(
                self._scr("download").ids.insecure_switch.active)}
        self._file_sel = []
        self._drive_loading = False
        ids = self._scr("files").ids
        ids.files_title.text = "我的网盘"
        ids.files_info.text = (
            "正在加载（%s 原生列表）…" % PAN_BY_KEY[pan_key]["name"])
        ids.files_box.clear_widgets()
        ids.files_dl_btn.text = "下载所选（0）"
        self.go("files")
        self._fetch_drive(pan_key, "0", "我的网盘", push=True)
        applog.info("drive", "原生网盘浏览打开 %s" % pan_key)

    def _fetch_drive(self, pan_key, fid, name, push):
        """拉取网盘目录（worker 线程，v3.1.0）。

        push=True 进子目录（目录栈 append）；False 为返回上级
        重拉。加载互斥（_drive_loading）防连点。
        """
        if self._drive_loading:
            return
        self._drive_loading = True
        self._scr("files").ids.files_info.text = "加载中…"

        def _ck():
            return pb.match_cookie_header(
                PAN_BY_KEY[pan_key]["home"]) or ""

        def _save_ck(ck):
            try:
                store = pb.load_cookie_store()
                for domain in PAN_BY_KEY[pan_key]["domains"]:
                    store[domain] = ck
                pb.save_cookie_store(store)
            except Exception:
                pass

        def work():
            entries = None
            err = None
            try:
                entries = drive.list_files(pan_key, _ck(), fid,
                                           on_cookie=_save_ck)
            except Exception as e:
                err = e
                applog.error("drive", "拉取文件列表失败", exc=e)

            def ui():
                self._drive_loading = False
                ids = self._scr("files").ids
                if entries is None:
                    ids.files_info.text = (
                        "加载失败（%s）" % type(err).__name__)
                    ids.files_error_detail.text = (
                        str(err)[:200] if err else "未知错误")
                    ids.files_retry_box.height = dp(42)
                    ids.files_retry_box.opacity = 1
                    ids.files_error_detail.height = dp(28)
                    return
                ids.files_retry_box.height = dp(0)
                ids.files_retry_box.opacity = 0
                ids.files_error_detail.height = dp(0)
                if push:
                    self._drive_ctx["stack"].append((fid, name))
                self._drive_ctx["entries"] = entries
                self._file_sel = [False] * len(entries)
                self._render_drive()
            _on_ui(ui)
        threading.Thread(target=work, daemon=True).start()

    def _render_drive(self):
        """网盘原生列表渲染（主线程，v3.1.0）。"""
        ids = self._scr("files").ids
        box = ids.files_box
        box.clear_widgets()
        ctx = self._drive_ctx or {}
        entries = ctx.get("entries") or []
        stack = ctx.get("stack") or []
        ids.files_title.text = (
            " › ".join(n for _f, n in stack) if stack else "我的网盘")
        nf = sum(1 for e in entries if not e.get("dir"))
        nd = len(entries) - nf
        total = sum(int(e.get("size") or 0)
                    for e in entries if not e.get("dir"))
        ids.files_info.text = (
            "%d 个文件 · %d 个文件夹 · 合计 %s · 轻点选择"
            % (nf, nd, pb.fmt_size(total) if total else "0"))
        for i, f in enumerate(entries):
            box.add_widget(self._file_row(i, f))
        self._update_files_btn()

    def _tap_row(self, i):
        """轻点行（v3.1.0）：文件夹进子目录；文件切换勾选。"""
        try:
            if self._drive_ctx is not None:
                entries = self._drive_ctx.get("entries") or []
                if i < len(entries) and entries[i].get("dir"):
                    self._fetch_drive(
                        self._drive_ctx["pan_key"],
                        entries[i]["fid"], entries[i]["name"],
                        push=True)
                    return
            self._toggle_file(i)
        except Exception:
            pass

    def files_retry(self):
        """加载失败重试（v3.1.1）：重拉当前目录。"""
        if self._drive_ctx is None:
            return
        ctx = self._drive_ctx
        stack = ctx.get("stack", [])
        if stack:
            fid, name = stack[-1]
        else:
            fid, name = "0", "我的网盘"
        self._fetch_drive(ctx["pan_key"], fid, name, push=False)

    def files_back(self):
        """文件屏返回（v3.1.0 双形态）。

        分享模式→下载屏；网盘模式→上级目录（重拉），根目录→
        账号屏。"""
        try:
            if self._drive_ctx is not None:
                stack = self._drive_ctx["stack"]
                if len(stack) > 1:
                    fid, name = stack[-2]
                    stack.pop()
                    self._fetch_drive(self._drive_ctx["pan_key"],
                                      fid, name, push=False)
                else:
                    self._drive_ctx = None
                    self.go("accounts")
                return
            self.go("download")
        except Exception:
            self.go("download")

    def _run_drive_batch(self, files, pan_key):
        """网盘勾选批量下载（worker 线程，v3.1.0）。

        逐文件取直链（带 Cookie + __puus 保活）→ 引擎加速下载。
        """
        total = len(files)
        hdrs = drive.download_headers(pan_key)
        choice = (self._drive_ctx or {}).get("choice", "auto")
        insecure = bool((self._drive_ctx or {}).get("insecure"))

        def _ck():
            return pb.match_cookie_header(
                PAN_BY_KEY[pan_key]["home"]) or ""

        done = 0
        for i, f in enumerate(files, 1):
            if getattr(self, "_cancel", False):
                self.log(f"已停止（已完成 {done}/{total}）")
                break
            self.log(f"[{i}/{total}] {f.get('name') or '文件'}")
            self._status = f"[{i}/{total}] 获取直链…"
            url = ""
            dl_name = ""
            try:
                r = drive.get_download_url(pan_key, _ck(), f["fid"])
                if r:
                    url, dl_name = r[0], (r[1] or f.get("name") or "")
            except Exception as e:
                self.log(f"获取直链失败: {e}")
                applog.error("drive", "直链失败 %s: %s"
                             % (f.get("fid"), e), exc=e)
            if url:
                self._status = f"[{i}/{total}] 下载中"
                self._run_download(url, _ck(), choice, insecure,
                                   share_name=f.get("name")
                                   or dl_name or None,
                                   share_headers=dict(hdrs)
                                   if hdrs else None)
            done = i
        self._status = f"批量完成 {done}/{total}"
        applog.info("download", "网盘批量下载结束 %d/%d"
                    % (done, total))

    def refresh_perm_hint(self):
        """首页"所有文件权限"卡片刷新（v3.2.6）。

        未授权（Android 11+ 公共 Download 媒体文件写被 scoped
        storage 拦截）→ 显示黄色卡片引导一键授权；已授权/非
        Android → 隐藏。授权后下载直存公共 Download（文件管理
        器直接可见 + 多线程 seek 全速）。
        """
        try:
            need = IS_ANDROID and not all_files_granted()
            hint = self._scr("home").ids.perm_hint
            hint.height = dp(44) if need else dp(0)
        except Exception:
            pass

    def on_perm_tap(self):
        """点击授权卡片：跳系统设置页（API 30+）。"""
        if not request_all_files():
            self._home_status(
                "此系统不支持该权限，文件将存应用目录（同样可下载）")
        else:
            self._home_status(
                "请在系统设置里打开「所有文件访问权限」后返回")

    def _on_resume(self, *args):
        """剪贴板识别（v3.0.0）+ 返回黑屏兜底（v3.2.1 防线③）。

        v3.2.1：从登录页（独立 Activity）返回后强制重绘一帧——
        部分 ROM 上 SDL surface 恢复事件（SIZE_CHANGED/RESTORED）
        丢失时 Kivy 不重绘即"纯黑卡住"；ask_update 标记 canvas 脏，
        下个 tick 强制重绘（Kivy 社区验证的标准黑屏修复）。"""
        try:
            Window.canvas.ask_update()
        except Exception:
            pass
        try:
            if (all_files_granted()
                    and not getattr(self, "_perm_nudged", False)):
                self._perm_nudged = True
                reset_download_dir_probe()
                self.refresh_perm_hint()
                self._home_status("已授权：下载将保存到公共 Download")
        except Exception:
            pass
        try:
            if Clipboard is None:
                return
            txt = (Clipboard.get() or "").strip()
            if not txt or len(txt) > 400:
                return
            if not pb.find_resolver(txt):
                return  # 只识别支持的分享链接，不打扰普通复制
            ids = self._scr("download").ids
            if ids.url_input.text.strip() == txt:
                return
            ids.url_input.text = txt
            self.log("已从剪贴板识别分享链接——点开始下载即可解析文件列表")
            self._home_status("检测到分享链接，已自动填入下载页")
            applog.info("clipboard", "剪贴板分享链接自动填入")
        except Exception:
            pass

    # ---------- 主线程侧（UI 刷新） ----------

    def _tick(self, _dt):
        dl_ids = self._scr("download").ids
        running = self.worker is not None and self.worker.is_alive()
        dl = self.dl
        if running and dl is not None and getattr(dl, "size", 0):
            pct = min(dl.done_bytes / dl.size, 1.0)
            self._progress = pct
            parts = [f"{pb.fmt_size(dl.done_bytes)} / {pb.fmt_size(dl.size)}"
                     f"  {pct * 100:.1f}%"]
            if getattr(dl, "speed", 0):
                parts.append(f"{pb.fmt_size(dl.speed)}/s")
            rate = getattr(dl, "rate", None)
            if rate is not None:
                cool = rate.cooldown_until - time.time()
                if cool > 0:
                    parts.append(f"冷却{cool:.0f}s")
                else:
                    parts.append(f"cap={rate.cap}")
            self._status = "  ".join(parts)
            self._btn_text = "停止"
        elif not running:
            self._btn_text = "开始下载"
        dl_ids.go_btn.text = self._btn_text
        dl_ids.progress.value = self._progress
        dl_ids.status_lbl.text = self._status
        if len(self.logs) != self._log_serial:
            self._log_serial = len(self.logs)
            dl_ids.log_lbl.text = "\n".join(self.logs[-14:])


if __name__ == "__main__":
    PanBoostApp().run()
