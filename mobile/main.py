#!/usr/bin/env python3
"""PanBoost Android 图形壳（Kivy）v1.7.1。

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

# PANBOOST_HOME 必须在 import panboost 之前设置（CONFIG_DIR 是模块级求值）
IS_ANDROID = ("ANDROID_PRIVATE" in os.environ
              or "ANDROID_ARGUMENT" in os.environ)
if IS_ANDROID:
    _base = os.environ.get("ANDROID_PRIVATE", "/").rstrip("/") or "/"
    os.environ.setdefault("PANBOOST_HOME",
                          os.path.join(_base, "files", ".panboost"))

sys.path.insert(0, str(Path(__file__).parent))
import panboost as pb  # noqa: E402
import weblogin  # noqa: E402

HISTORY_FILE = pb.CONFIG_DIR / "history.json"
ACCOUNTS_FILE = pb.CONFIG_DIR / "accounts.json"

SHELL_VERSION = "1.7.1"

# ---------------- 浅色主题色板 ----------------
BG = (0.957, 0.965, 0.984, 1)          # 页面底 #F4F6FB
CARD = (1.0, 1.0, 1.0, 1.0)            # 卡片白
CARD_DOWN = (0.906, 0.925, 0.969, 1)   # 卡片按压
PRIMARY = (0.145, 0.388, 0.922, 1)     # 主蓝 #2563EB
PRIMARY_DARK = (0.118, 0.298, 0.761, 1)
INK = (0.118, 0.161, 0.231, 1)         # 主文字 #1E293B
SUB = (0.396, 0.447, 0.533, 1)         # 次文字 #64748B
GREEN = (0.086, 0.639, 0.290, 1)       # 已登录 #16A34A


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
from kivy.lang import Builder  # noqa: E402
from kivy.metrics import dp, sp  # noqa: E402
from kivy.properties import ListProperty  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.screenmanager import Screen  # noqa: E402
from kivy.uix.spinner import SpinnerOption  # noqa: E402


# ---------------- 网盘清单（首页宫格） ----------------
# auth_keys: 登录成功特征 Cookie 键，命中自动完成；空 = 依赖用户点
#            "完成登录"按钮返回
# domains:   Cookie 生效域（写入引擎 cookie store，下载时后缀匹配）
PANS = [
    {"key": "baidu", "name": "百度网盘", "login": "https://pan.baidu.com/",
     "domains": ["baidu.com"], "auth_keys": ["BDUSS"]},
    {"key": "quark", "name": "夸克网盘", "login": "https://pan.quark.cn/",
     "domains": ["quark.cn"], "auth_keys": ["__puus"]},
    {"key": "alipan", "name": "阿里云盘", "login": "https://www.alipan.com/",
     "domains": ["alipan.com", "aliyundrive.com"], "auth_keys": []},
    {"key": "weiyun", "name": "腾讯微云", "login": "https://www.weiyun.com/",
     "domains": ["weiyun.com"], "auth_keys": []},
    {"key": "tianyi", "name": "天翼云盘", "login": "https://cloud.189.cn/",
     "domains": ["189.cn"], "auth_keys": []},
    {"key": "yidong", "name": "移动云盘",
     "login": "https://caiyun.feixin.10086.cn/",
     "domains": ["10086.cn"], "auth_keys": []},
    {"key": "xunlei", "name": "迅雷云盘", "login": "https://pan.xunlei.com/",
     "domains": ["xunlei.com"], "auth_keys": []},
    {"key": "pan123", "name": "123云盘", "login": "https://www.123pan.com/",
     "domains": ["123pan.com"], "auth_keys": []},
    {"key": "lanzou", "name": "蓝奏云", "login": "https://www.lanzou.com/",
     "domains": ["lanzou.com", "lanzoux.com"], "auth_keys": []},
    {"key": "jianguo", "name": "坚果云", "login": "https://www.jianguoyun.com/",
     "domains": ["jianguoyun.com"], "auth_keys": []},
    {"key": "uc", "name": "UC网盘", "login": "https://drive.uc.cn/",
     "domains": ["uc.cn"], "auth_keys": []},
    {"key": "gdrive", "name": "Google Drive",
     "login": "https://accounts.google.com/",
     "domains": ["google.com", "googleusercontent.com"],
     "auth_keys": ["SAPISID"]},
    {"key": "dropbox", "name": "Dropbox", "login": "https://www.dropbox.com/",
     "domains": ["dropbox.com", "dropboxusercontent.com"],
     "auth_keys": []},
    {"key": "onedrive", "name": "OneDrive",
     "login": "https://login.live.com/",
     "domains": ["live.com", "1drv.com", "sharepoint.com"],
     "auth_keys": []},
    {"key": "mega", "name": "MEGA", "login": "https://mega.nz/",
     "domains": ["mega.nz"], "auth_keys": []},
    {"key": "pcloud", "name": "pCloud", "login": "https://www.pcloud.com/",
     "domains": ["pcloud.com"], "auth_keys": []},
    {"key": "box", "name": "Box", "login": "https://www.box.com/",
     "domains": ["box.com", "boxcloud.com"], "auth_keys": []},
    {"key": "yandex", "name": "Yandex Disk", "login": "https://disk.yandex.com/",
     "domains": ["yandex.com", "yandex.ru"], "auth_keys": []},
]
PAN_BY_KEY = {p["key"]: p for p in PANS}


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


def _dump_crash(tag):
    """未捕获异常写 crash-*.log 到外部私有目录（可取回诊断）。"""
    try:
        import traceback
        d = external_files_dir()
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "crash-%s.log" % time.strftime("%Y%m%d-%H%M%S"))
        with open(p, "w", encoding="utf-8") as f:
            f.write(tag + traceback.format_exc())
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
                _dump("kivy: %s: %s\n" % (type(e).__name__, e))
                return ExceptionManager.RAISE

        ExceptionManager.handler = _CrashHandler()
    except Exception:
        pass


_install_crash_logger()


# ---------------- 下载保活（前台服务 + WakeLock） ----------------

_KEEPALIVE = {"svc": None, "wl": None}


def start_keepalive():
    """下载开始：起前台服务 + 持 PARTIAL_WAKE_LOCK。

    Android 12+ 对后台应用冻结，前台服务是唯一可靠保活手段；
    任何一步失败静默降级（下载仍靠引擎实时落盘保证）。"""
    if not IS_ANDROID:
        return False
    ok = False
    try:
        from android import AndroidService
        _KEEPALIVE["svc"] = AndroidService(
            "PanBoost 下载中", "多线程下载进行中，进度实时保存")
        _KEEPALIVE["svc"].start("")
        ok = True
    except Exception:
        _KEEPALIVE["svc"] = None
    try:
        from jnius import autoclass
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Context = autoclass("android.content.Context")
        PowerManager = autoclass("android.os.PowerManager")
        pm = PythonActivity.mActivity.getSystemService(Context.POWER_SERVICE)
        wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PanBoost:dl")
        wl.acquire()
        _KEEPALIVE["wl"] = wl
        ok = True
    except Exception:
        _KEEPALIVE["wl"] = None
    return ok


def stop_keepalive():
    """下载结束：停服务、释放 WakeLock（必须释放防耗电）。"""
    try:
        if _KEEPALIVE["svc"] is not None:
            _KEEPALIVE["svc"].stop()
    except Exception:
        pass
    _KEEPALIVE["svc"] = None
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
    """登录成功：写账簿 + 同步引擎 cookie store（下载自动匹配）。"""
    pan = PAN_BY_KEY.get(pan_key)
    if pan is None or not cookie:
        return False
    acc = load_accounts()
    acc[pan_key] = {"name": pan["name"], "ts": int(time.time()),
                    "auto": bool(auto), "len": len(cookie)}
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
            radius: [dp(9)]
    color: 0.118, 0.161, 0.231, 1

<CompactOption>:
    height: dp(30)
    font_size: sp(12)
    background_normal: ''
    background_down: ''
    background_color: 0.145, 0.388, 0.922, 1 if self.state == 'down' else 0.96
    color: 1, 1, 1, 1

ScreenManager:
    MainScreen:
    DownloadScreen:
    AccountsScreen:
    HistoryScreen:

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

        Label:
            text: 'PanBoost'
            font_size: sp(24)
            bold: True
            color: 0.118, 0.161, 0.231, 1
            size_hint_y: None
            height: dp(30)

        Label:
            text: '点击网盘卡片登录（Cookie 永久保存，下载自动携带）'
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
            height: dp(46)
            color: 1, 1, 1, 1
            on_release: app.go('download')

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

        BoxLayout:
            size_hint_y: None
            height: dp(34)
            spacing: dp(8)
            CardButton:
                text: '首页'
                font_size: sp(13)
                size_hint_x: 0.3
                on_release: app.go('home')
            Label:
                text: '下载'
                font_size: sp(17)
                bold: True
                color: 0.118, 0.161, 0.231, 1

        TextInput:
            id: url_input
            hint_text: '下载直链 URL（http/https）'
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

        BoxLayout:
            size_hint_y: None
            height: dp(38)
            spacing: dp(8)
            CardButton:
                text: '我的账号'
                font_size: sp(13)
                on_release: app.go('accounts')
            CardButton:
                text: '下载历史'
                font_size: sp(13)
                on_release: app.go('history')

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

        BoxLayout:
            size_hint_y: None
            height: dp(34)
            spacing: dp(8)
            CardButton:
                text: '首页'
                font_size: sp(13)
                size_hint_x: 0.3
                on_release: app.go('home')
            Label:
                text: '我的账号'
                font_size: sp(17)
                bold: True
                color: 0.118, 0.161, 0.231, 1

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
            height: dp(18)

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
            CardButton:
                text: '首页'
                font_size: sp(13)
                size_hint_x: 0.3
                on_release: app.go('home')
            Label:
                text: '下载历史（永久记录）'
                font_size: sp(16)
                bold: True
                color: 0.118, 0.161, 0.231, 1
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
            CardButton:
                text: '返回'
                font_size: sp(13)
                on_release: app.go('home')

        ScrollView:
            GridLayout:
                id: history_box
                cols: 1
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(4)
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
        self._status = "待命"
        self._progress = 0.0
        self._btn_text = "开始下载"
        self.dir_short = external_files_dir()
        self.root = Builder.load_string(KV)
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
        self.root.current = name
        if name == "accounts":
            self.refresh_accounts()
        elif name == "history":
            self.refresh_history()

    def _scr(self, name):
        return self.root.get_screen(name)

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
            logged = pan["key"] in acc
            if logged:
                txt = f"{pan['name']}\n[b][color=#16a34a]已登录[/color][/b]"
            else:
                txt = f"{pan['name']}\n[sub]{pan['domains'][0]}[/sub]"
            btn = CardButton(
                text=txt, markup=True, font_size=sp(13),
                size_hint_y=None, height=dp(84),
                halign="center", valign="middle")
            btn.bind(on_release=self._guard(self.pan_login, pan["key"]))
            grid.add_widget(btn)

    def _home_status(self, msg):
        try:
            self._scr("home").ids.home_status.text = msg
        except Exception:
            pass

    def pan_login(self, pan_key):
        """点击网盘卡片：WebView 登录（Android）或手动粘贴回退。"""
        pan = PAN_BY_KEY.get(pan_key)
        if pan is None:
            return
        if self.worker is not None and self.worker.is_alive():
            self._home_status("下载进行中，请等待完成后再登录")
            return
        if weblogin.available():
            def on_done(cookie, auto):
                self._after_login(pan_key, cookie, auto)
            try:
                weblogin.open_login(pan["login"], pan["auth_keys"],
                                    on_done, title=pan["name"])
                self._home_status(
                    f"已打开 {pan['name']} 登录页——完成登录后自动返回"
                    + ("（检测到登录将自动保存）" if pan["auth_keys"]
                       else "（登录后请点顶部按钮返回）"))
                return
            except Exception as e:
                self._home_status(f"登录窗口打开失败（{e}），请手动添加 Cookie")
        # 回退：跳账号屏手动粘贴（预填域名）
        acc = self._scr("accounts").ids
        acc.domain_input.text = pan["domains"][0]
        acc.accounts_status.text = (
            f"请在浏览器登录 {pan['name']}，复制 Cookie 粘贴到此处保存")
        self.go("accounts")

    def _after_login(self, pan_key, cookie, auto):
        pan = PAN_BY_KEY.get(pan_key)
        if record_login(pan_key, cookie, auto):
            self._build_pan_grid()
            when = "自动检测" if auto else "手动确认"
            self._home_status(
                f"{pan['name']} 已登录（{when}，Cookie 已永久保存）")
        else:
            self._home_status(
                f"未捕获到 {pan['name']} 的 Cookie——请确认已完成登录后重试")

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
            rows.append((name, "已登录网盘 · "
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
            return
        url = self._scr("download").ids.url_input.text.strip()
        if not url:
            self.log("请先输入下载直链 URL")
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
        self._progress = 0.0
        self._status = "探测中…"
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

    def _run_download(self, url, cookie, choice, insecure):
        out_name = ""
        size = 0
        speed = 0.0
        status = "失败"
        try:
            headers = {"Cookie": cookie} if cookie else {}
            probe, headers = self._probe_with_ua_fallback(
                url, headers, insecure)
            if probe.challenge_cookie:
                headers = pb.merge_cookie_header(
                    dict(headers), *probe.challenge_cookie)
                self.log("已自动通过浏览器验证挑战")
            out = Path(external_files_dir()) / _safe_name(probe.filename, url)
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
            elif rc == 130:
                self._status = "已停止（进度已保存，可续传）"
                status = "中断"
            else:
                err = self.dl.errors[0] if self.dl and self.dl.errors else "未知错误"
                self._status = "失败（进度已保存）"
                status = "失败"
                self.log(f"失败: {err}")
        except Exception as e:
            self._status = "失败"
            status = "失败"
            if not out_name:
                out_name = _safe_name(None, url)  # 探测失败也记录，便于重跑
            self.log(f"{type(e).__name__}: {e}")
        finally:
            self.dl = None
            stop_keepalive()
            if out_name:
                add_history({"ts": int(time.time()), "url": url,
                             "name": out_name, "size": size,
                             "status": status, "speed": round(speed)})

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
