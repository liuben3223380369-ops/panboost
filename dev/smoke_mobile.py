"""mobile/main.py 的无 Kivy 冒烟测试：mock kivy 模块后跑完整流程。

覆盖 v1.7.0：中文字体注册、浅色主题、四屏结构（首页/下载/账号/历史）、
18 家网盘宫格、无 WebView 回退手动登录、WebView 登录回调账簿双写、
已登录徽标、空 Cookie 不覆盖、删除登录、前台服务保活 start/stop、
下载结束停保活、账号 Cookie 持久化与自动匹配、历史永久记录与开关、
失败记录、重跑预填、清空历史。
可复跑：python3 dev/smoke_mobile.py
"""
import os
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mobile"))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["PANBOOST_HOME"] = tempfile.mkdtemp(prefix="pbmobile_")
os.environ.setdefault("PANBOOST_NO_FSYNC", "1")
os.environ.setdefault("PANBOOST_CB_SCALE", "0.02")

# ---- mock kivy（必须在 import mobile.main 之前） ----
kivy = types.ModuleType("kivy")


class _App:
    pass


app_mod = types.ModuleType("kivy.app")
app_mod.App = _App


class _Clock:
    @staticmethod
    def schedule_interval(fn, interval):
        pass

    @staticmethod
    def schedule_once(fn, timeout=0):
        fn(0)


clock_mod = types.ModuleType("kivy.clock")
clock_mod.Clock = _Clock


class _Widget:
    def __init__(self, **kw):
        self.text = kw.get("text", "")
        self.active = kw.get("active", False)
        self.value = 0.0
        self.children = []
        self._on_release = kw.get("on_release")
        self._bound = {}

    def bind(self, *largs, **kwargs):
        for k, v in kwargs.items():
            self._bound[k] = v

    def trigger(self, name="on_release", *args):
        fn = self._bound.get(name) or self._on_release
        if callable(fn):
            fn(self, *args)

    def collide_point(self, *args):
        return True

    def clear_widgets(self):
        self.children = []

    def add_widget(self, w):
        self.children.append(w)


class _Btn(_Widget):
    pass


class _Builder:
    @staticmethod
    def load_string(kv):
        ns = types.SimpleNamespace

        def screen(name, **ids):
            s = types.SimpleNamespace()
            s.name = name
            s.ids = ns(**{k: (v if isinstance(v, _Widget) else _Widget(text=v))
                          for k, v in ids.items()})
            return s

        home = screen("home", pan_grid=_Widget(), home_status=_Widget())
        download = screen("download",
                          url_input=_Widget(), cookie_input=_Widget(),
                          threads_spinner=_Widget(text="auto"),
                          insecure_switch=_Widget(active=False),
                          go_btn=_Widget(text="开始下载"), progress=_Widget(),
                          status_lbl=_Widget(), log_lbl=_Widget())
        accounts = screen("accounts",
                          domain_input=_Widget(), cookie_input=_Widget(),
                          accounts_status=_Widget(),
                          accounts_box=_Widget())
        history = screen("history", rec_switch=_Widget(active=True),
                         history_box=_Widget())
        logs = screen("logs", logs_lbl=_Widget(text="（暂无日志）"),
                      logs_status=_Widget())
        files = screen("files", files_title=_Widget(text="分享文件"),
                       files_info=_Widget(),
                       files_box=_Widget(),
                       files_sel_all=_Widget(text="全选 / 全不选"),
                       files_dl_btn=_Widget(text="下载所选"))
        sm = types.SimpleNamespace()
        sm.current = "home"
        sm._screens = {"home": home, "download": download,
                       "accounts": accounts, "history": history,
                       "files": files,
                       "logs": logs}
        sm.get_screen = sm._screens.get
        # v2.0.0：root 为 BoxLayout（ScreenManager + 底部导航栏）
        root = types.SimpleNamespace()
        root.ids = types.SimpleNamespace(
            sm=sm,
            tab_home=_Widget(active=True), tab_download=_Widget(),
            tab_accounts=_Widget(), tab_history=_Widget(),
            tab_logs=_Widget())
        return root


lang_mod = types.ModuleType("kivy.lang")
lang_mod.Builder = _Builder
metrics_mod = types.ModuleType("kivy.metrics")
metrics_mod.dp = lambda x: x
metrics_mod.sp = lambda x: x
props_mod = types.ModuleType("kivy.properties")
props_mod.ListProperty = lambda *a, **k: list(a[0]) if a else []
props_mod.BooleanProperty = lambda *a, **k: bool(a[0]) if a else False
props_mod.StringProperty = lambda *a, **k: str(a[0]) if a else ""
uix_mod = types.ModuleType("kivy.uix")
bl_mod = types.ModuleType("kivy.uix.boxlayout")
bl_mod.BoxLayout = _Widget
btn_mod = types.ModuleType("kivy.uix.button")
btn_mod.Button = _Btn
lbl_mod = types.ModuleType("kivy.uix.label")
lbl_mod.Label = _Widget
sm_mod = types.ModuleType("kivy.uix.screenmanager")


class _Screen(_Widget):
    pass


sm_mod.Screen = _Screen
sm_mod.ScreenManager = _Widget
spin_mod = types.ModuleType("kivy.uix.spinner")
spin_mod.SpinnerOption = _Widget
spin_mod.Spinner = _Widget


class _LabelBase:
    @staticmethod
    def register(name, *paths):
        return None


text_mod = types.ModuleType("kivy.core.text")
text_mod.LabelBase = _LabelBase
window_mod = types.ModuleType("kivy.core.window")


class _Window:
    _bound = {}

    def bind(self, *largs, **kwargs):
        self._bound.update(kwargs)

    def unbind(self, *largs, **kwargs):
        for k in kwargs:
            self._bound.pop(k, None)


window_mod.Window = _Window()
core_mod = types.ModuleType("kivy.core")
core_mod.text = text_mod
core_mod.window = window_mod
kivy.app = app_mod
kivy.clock = clock_mod
kivy.lang = lang_mod
kivy.metrics = metrics_mod
kivy.properties = props_mod
kivy.uix = uix_mod
kivy.core = core_mod
clip_mod = types.ModuleType("kivy.core.clipboard")


class _Clipboard:
    _val = ""

    @staticmethod
    def get():
        return _Clipboard._val

    @staticmethod
    def copy(s):
        _Clipboard._val = str(s)


clip_mod.Clipboard = _Clipboard
sys.modules.update({
    "kivy.core.clipboard": clip_mod,
    "kivy": kivy, "kivy.app": app_mod, "kivy.clock": clock_mod,
    "kivy.lang": lang_mod, "kivy.metrics": metrics_mod,
    "kivy.properties": props_mod, "kivy.uix": uix_mod,
    "kivy.uix.boxlayout": bl_mod, "kivy.uix.button": btn_mod,
    "kivy.uix.label": lbl_mod,
    "kivy.core": core_mod, "kivy.core.text": text_mod,
    "kivy.core.window": window_mod,
    "kivy.uix.screenmanager": sm_mod, "kivy.uix.spinner": spin_mod,
})

# ---- mock android 前台服务（keepalive 用，import main 前注册） ----
SVC_CALLS = {"start": 0, "stop": 0}


class _MockService:
    def start(self, *a, **kw):
        SVC_CALLS["start"] += 1

    def stop(self):
        SVC_CALLS["stop"] += 1


android_mod = types.ModuleType("android")
android_mod.AndroidService = lambda title, desc: _MockService()
sys.modules["android"] = android_mod

import main as mobile_main  # noqa: E402
from test_server import TestServer  # noqa: E402
import panboost as pb  # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def main():
    # ---- 静态检查 ----
    check("壳-中文字体已注册", mobile_main.register_font(),
          "fonts/cjk.ttf 存在且注册成功")

    import re
    kv_names = set(re.findall(r"</?([A-Z][A-Za-z0-9_]*)>?:", mobile_main.KV))
    kv_std = {
        "ScreenManager", "Screen", "Widget", "BoxLayout", "GridLayout",
        "AnchorLayout", "StackLayout", "RelativeLayout", "FloatLayout",
        "ScatterLayout", "ScrollView", "Label", "Button", "TextInput",
        "Spinner", "Switch", "CheckBox", "ProgressBar", "Slider", "Image",
        "ToggleButton", "Accordion", "TabbedPanel", "Popup", "Carousel",
        "DropDown", "ActionBar", "Video", "Canvas",
    }
    custom = sorted(n for n in kv_names if n not in kv_std)
    py_src = Path(mobile_main.__file__).read_text(encoding="utf-8")
    defined = set(re.findall(r"^class\s+([A-Za-z0-9_]+)\b", py_src, re.M))
    missing = [n for n in custom if n not in defined]
    check("壳-KV自定义类均有Python定义", not missing and bool(custom),
          f"自定义类={custom} 缺失={missing}")
    check("壳-五屏类已定义且为Screen子类（含日志屏）",
          all(issubclass(getattr(mobile_main, n, type(None)), _Screen)
              for n in ("MainScreen", "DownloadScreen", "AccountsScreen",
                        "HistoryScreen", "LogsScreen")))
    vals = re.search(r"values: \[([^\]]+)\]", mobile_main.KV).group(1)
    check("壳-线程选项含512/1024", "'512'" in vals and "'1024'" in vals,
          vals)
    check("壳-下拉紧凑行高防小屏截断",
          "CompactOption" in mobile_main.KV
          and "option_cls: app.compact_option" in mobile_main.KV
          and hasattr(mobile_main, "CompactOption")
          and hasattr(mobile_main.PanBoostApp, "compact_option"))
    check("壳-浅色主题（弃用黑底）",
          mobile_main.BG[0] > 0.9 and mobile_main.BG[1] > 0.9
          and "rgba: 0.957, 0.965, 0.984, 1" in mobile_main.KV
          and "RoundedRectangle" in mobile_main.KV,
          f"BG={mobile_main.BG}")
    check("壳-崩溃日志钩子已安装", sys.excepthook is not sys.__excepthook__,
          "sys.excepthook 已替换为 crash logger")
    pans = mobile_main.PANS
    ok_pans = (len(pans) >= 18
               and all(p.get("key") and p.get("name")
                       and str(p.get("login", "")).startswith("http")
                       and isinstance(p.get("domains"), list) and p["domains"]
                       and isinstance(p.get("auth_keys"), list) for p in pans)
               and len({p["key"] for p in pans}) == len(pans))
    check("壳-网盘清单18家结构完整", ok_pans,
          f"{len(pans)}家: " + "、".join(p["name"] for p in pans[:5]) + "…")

    data = os.urandom(3 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data)

    tmp = tempfile.mkdtemp(prefix="pbmobile_dl_")
    mobile_main.external_files_dir = lambda: tmp
    app = mobile_main.PanBoostApp()
    app.build()

    # ---- v1.8.1 登录层桌面 UA + 返回键 ----
    import weblogin as _wl
    wsrc = Path(_wl.__file__).read_text(encoding="utf-8")
    check("壳-登录层桌面UA防跳下载App页",
          "Windows NT" in _wl.DESKTOP_UA
          and "setUserAgentString(DESKTOP_UA)" in wsrc
          and "setUseWideViewPort" in wsrc,
          _wl.DESKTOP_UA[:56] + "…")
    check("壳-登录层✕关闭与完成登录按钮（v1.9.0 标准布局）",
          '"✕"' in wsrc and "已完成登录，保存 Cookie" in wsrc
          and " · 网页登录" in wsrc
          and hasattr(_wl, "close_login")
          and hasattr(_wl, "request_back")
          and "canGoBack" in wsrc)
    check("壳-返回键keycode27已接入",
          hasattr(mobile_main.PanBoostApp, "_on_key")
          and "on_keyboard" in py_src and "key != 27" in py_src
          and "weblogin.request_back()" in py_src)
    check("壳-无登录层时返回接口安全",
          _wl.request_back() is False, "request_back 返回 False")
    _wl.close_login()  # 幂等：无登录层不抛错不回调
    check("壳-close_login幂等无异常", True)
    app.go("accounts")
    check("壳-非首页按返回键回首页",
          app._on_key(None, 27) is True
          and app.root.ids.sm.current == "home")
    check("壳-首页按返回键走系统默认退出",
          app._on_key(None, 27) is False)
    check("壳-非返回键不拦截",
          app._on_key(None, 13) is False)

    # ---- v1.8.2 导航守卫 + WebView 返回键（v1.8.3 起 SDL trap 移除）----
    check("壳-导航白名单_decide_url行为",
          _wl._decide_url("https://pan.baidu.com/") == (False, None)
          and _wl._decide_url("http://x/") == (False, None)
          and _wl._decide_url("market://details?id=x") == (True, None)
          and _wl._decide_url("tmast://appdetail") == (True, None)
          and _wl._decide_url("") == (True, None)
          and _wl._decide_url("weixin://x") == (True, None))
    check("壳-intent带fallback时转加载网页",
          _wl._decide_url(
              "intent://scan/#Intent;scheme=zxing;"
              "S.browser_fallback_url=https%3A%2F%2Fm.baidu.com%2F;end",
              parse_intent=lambda u: "https://m.baidu.com/")
          == (True, "https://m.baidu.com/")
          and _wl._decide_url("intent://x/#Intent;end",
                              parse_intent=lambda u: None) == (True, None))
    check("壳-WebViewClient导航守卫已接入",
          "setWebViewClient" in wsrc and "PanWebViewClient" in wsrc
          and "_UrlLoadingCallback" in wsrc
          and "browser_fallback_url" in wsrc,
          "Java桥接类+Python回调")
    check("壳-WebView层返回键监听已挂",
          "setOnKeyListener" in wsrc and "_BackKeyListener" in wsrc
          and "setFocusable" in wsrc)
    java_path = Path(mobile_main.__file__).parent / "java_classes" \
        / "PanWebViewClient.java"
    check("壳-Java桥接类存在且覆写双签名",
          java_path.exists()
          and "extends WebViewClient" in java_path.read_text(encoding="utf-8")
          and java_path.read_text(encoding="utf-8").count(
              "shouldOverrideUrlLoading") >= 2)
    check("壳-SDL返回键trap已移除（v1.8.3：吞手势返回）",
          'os.environ.setdefault("SDL_ANDROID_TRAP' not in py_src)
    check("壳-百度改用PC统一登录页",
          mobile_main.PAN_BY_KEY["baidu"]["login"]
          == "https://passport.baidu.com/v2/?login")
    check("壳-壳版本3.0.1",
          mobile_main.SHELL_VERSION == "3.0.1", mobile_main.SHELL_VERSION)

    # ---- v1.8.4 修复"三色弹窗无内容 + 点击闪退" ----
    check("壳-按钮回调持Python强引用（防GC闪退）",
          '"click_cbs"' in wsrc
          and "click_close, click_done" in wsrc
          and "tv_close.setOnClickListener(click_close)" in wsrc
          and "btn_done.setOnClickListener(click_done)" in wsrc,
          "pyjnius proxy 只存指针不持引用")
    check("壳-Dialog显式全屏（防WebView高度塌陷）",
          "setLayout(-1, -1)" in wsrc
          and "dialog.show()" in wsrc
          and wsrc.index("dialog.show()") < wsrc.index("setLayout(-1, -1)"),
          "show 后 setLayout 全屏")
    check("壳-渲染进程崩溃处理已接通（防杀）",
          "onRenderProcessGone" in java_path.read_text(encoding="utf-8")
          and "onRenderGone" in wsrc
          and "_on_render_gone" in wsrc,
          "onRenderProcessGone 返回 true + 自动关层")
    check("壳-登录回调调度回Kivy主线程",
          hasattr(mobile_main, "_on_ui")
          and "Clock.schedule_once" in py_src)
    mobile_main._on_ui(lambda: None)  # mock 下立即同步执行不炸
    check("壳-_on_ui冒烟可调用", True)

    # ---- v1.8.5 修复"误记已登录 + 三色区域依旧没字" ----
    check("壳-Dialog非floating全屏主题构造",
          "Theme_Light_NoActionBar_Fullscreen" in wsrc
          and "android.R$style" in wsrc,
          "floating 主题强制 wrap 是三色弹窗根因，主题构造根治")
    check("壳-WebView先入容器后加载且weight布局",
          wsrc.index('_step("加载登录页"')
          > wsrc.index('_step("WebView入容器"')
          and "LLParams(-1, 0, 1.0)" in wsrc,
          "未 attach 就 loadUrl 部分ROM不渲染；weight=1 稳占剩余高度")
    check("壳-登录凭证校验（防游客Cookie误记已登录）",
          'f"未检测到{title}的登录凭证' in wsrc
          and "def _toast" in wsrc
          and "Toast.makeText" in wsrc,
          "特征键未命中 Toast 提示且登录层保持打开")
    check("壳-凭证校验先于关层（未命中不关层不回调）",
          wsrc.index('f"未检测到{title}的登录凭证')
          < wsrc.index("done_once.set()", wsrc.index("def _finish")),
          "校验失败 return 早于 done_once.set()")
    check("壳-拦截回退防空白屏",
          "_fallback_after_block" in wsrc
          and "_BLOCKED_HTML" in wsrc,
          "scheme/市场跳转被拦后回退重载登录页，2次后显示说明页")
    check("壳-record_login防御性凭证校验+verified语义",
          '"verified": bool(keys)' in py_src
          and "Cookie已存·未验证" in py_src,
          "特征命中=已登录；localStorage 型网盘不冒充已登录")
    check("壳-特征键调研实锤（nfd白名单/天翼/微软）",
          mobile_main.PAN_BY_KEY["quark"]["auth_keys"] == ["__pus", "__puus"]
          and mobile_main.PAN_BY_KEY["uc"]["auth_keys"] == ["__pus", "__puus"]
          and "COOKIE_LOGIN_USER" in
          mobile_main.PAN_BY_KEY["tianyi"]["auth_keys"]
          and "ESTSAUTH" in mobile_main.PAN_BY_KEY["onedrive"]["auth_keys"],
          "夸克/UC=__pus+__puus；天翼=COOKIE_LOGIN_USER；OneDrive=ESTSAUTH")

    # ---- v1.9.0 修复"三色块无字 + 夸克/阿里下载页 + UC 打不开" ----
    check("壳-文字三级保险（真机按钮无字根因）",
          "def _set_text" in wsrc
          and 'autoclass("java.lang.String")' in wsrc,
          "setText 重载解析失败时走 Java String 对象通道")
    check("壳-文字颜色双保险",
          "def _set_text_color" in wsrc and "Color.rgb" in wsrc,
          "int 直传失败时 Color.rgb 同类型回传")

    class _V:
        def __init__(self, fail=False):
            self.txt = None
            self.fail = fail

        def setText(self, t):
            if self.fail:
                raise RuntimeError("no such method")
            self.txt = t
    v_ok = _V()
    check("壳-_set_text一级直传生效",
          _wl._set_text(v_ok, "测试") is True and v_ok.txt == "测试")
    check("壳-_set_text全失败返回False",
          _wl._set_text(_V(fail=True), "测试") is False,
          "非Android下二级通道不可用→False（真机二级通道生效）")
    check("壳-标准登录页布局（标题栏+提示条+底部大按钮）",
          "C_BAR_BG" in wsrc and " · 网页登录" in wsrc
          and "在下方页面登录账号" in wsrc
          and "已完成登录，保存 Cookie" in wsrc
          and "C_DONE_BG" in wsrc,
          "消灭'三个色块不知道是什么'")
    check("壳-桌面UA读回验证（下载页根因诊断）",
          "getUserAgentString" in wsrc
          and "setUserAgentString(DESKTOP_UA)" in wsrc,
          "UA 曾与整块配置一起被吞，现独立设置+验证记 nav_log")
    check("壳-登录URL实锤修正（LinkSwift @match）",
          mobile_main.PAN_BY_KEY["alipan"]["login"]
          == "https://www.alipan.com/drive/"
          and mobile_main.PAN_BY_KEY["tianyi"]["login"]
          == "https://cloud.189.cn/web/"
          and mobile_main.PAN_BY_KEY["yidong"]["login"]
          == "https://yun.139.com/"
          and "139.com" in mobile_main.PAN_BY_KEY["yidong"]["domains"],
          "阿里 /drive、天翼 /web、移动 yun.139.com")
    # ---- v1.9.2 根治"点保存没反应"（反馈通道+多域采集+埋点） ----
    check("壳-关键函数完整存在（v1.9.1误删current_cookies防回归）",
          hasattr(_wl, "current_cookies")
          and hasattr(_wl, "open_login")
          and hasattr(_wl, "close_login") and hasattr(_wl, "is_open")
          and hasattr(_wl, "nav_log"),
          "v1.9.1 曾误删 def current_cookies 致点保存必失败")
    msrc = Path(mobile_main.__file__).read_text(encoding="utf-8")
    check("壳-保存按钮反馈与多域采集结构（v1.9.2）",
          "def _nudge_button" in wsrc and "def _merge_cookies" in wsrc
          and "def _gather_cookies" in wsrc and "def _jstr" in wsrc
          and "C_ERR" in wsrc and "DONE_BTN_TEXT" in wsrc
          and '_STATE["btn_done"]' in wsrc
          and "cookie_urls=" in msrc,
          "按钮红色提示+Toast双保险+多域Cookie+点击/校验埋点")
    m1 = _wl._merge_cookies(None, "x=1; y=2")
    m2 = _wl._merge_cookies("x=1; y=2", "y=9; z=3")
    m3 = _wl._merge_cookies(None, None)
    check("壳-_merge_cookies合并去重与空安全",
          m1 == "x=1; y=2" and m2 == "x=1; y=9; z=3" and m3 is None,
          f"{m1!r} / {m2!r} / {m3!r}")
    check("壳-_jstr非Android回退原串",
          _wl._jstr("abc") == "abc",
          "Java String 通道不可用时静默回退")
    _oc = _wl.current_cookies
    try:
        _wl.current_cookies = lambda u: {
            "https://a.com/": "x=1",
            "https://b.com/": "y=2; x=9"}.get(u)
        c, e = _wl._gather_cookies(
            ("https://a.com/", "https://b.com/", "https://c.com/"))
        check("壳-_gather_cookies多域合并与空域容错",
              c == "x=9; y=2" and e is None, f"cookie={c!r} err={e!r}")
        _wl.current_cookies = lambda u: (_ for _ in ()).throw(
            RuntimeError("boom"))
        c2, e2 = _wl._gather_cookies(("https://a.com/",))
        check("壳-_gather_cookies全失败返回异常文本",
              c2 is None and "boom" in (e2 or ""), f"err={e2!r}")
    finally:
        _wl.current_cookies = _oc
    _saved2 = dict(_wl._STATE)
    try:
        _wl._STATE["btn_done"] = None
        _wl._nudge_button()
        _wl._STATE["btn_done"] = object()
        _wl._nudge_button()
        check("壳-_nudge_button非Android环境安全无异常", True,
              "按钮为 None 早退；_run_ui 不可用被吞不抛")
    finally:
        _wl._STATE.clear()
        _wl._STATE.update(_saved2)

    # ---- v1.9.1 根治"登录完成后直接闪退"（关闭时序三层防御） ----
    check("壳-退休列表机制（防GC后Java回调闪退）",
          "def _retire" in wsrc and '"retired": []' in wsrc
          and "del rl[:-6]" in wsrc,
          "回调对象延迟回收，封死 dismiss 后飞行回调窗口")
    check("壳-关闭前解绑回调源（闪退根因）",
          "setWebViewClient(None)" in wsrc
          and "setOnKeyListener(None)" in wsrc
          and "setOnCancelListener(None)" in wsrc,
          "dismiss 不终止 Chromium 流水线，必须先切断回调源")

    _saved = dict(_wl._STATE)
    try:
        _wl._STATE.update({
            "root": "R1", "webview": "W1", "dialog": "D1",
            "client_cb": "C1", "key_cb": "K1", "cancel_cb": "X1",
            "click_cbs": ("A1", "B1"), "retired": []})
        _wl._retire("root", "webview", "dialog", "client_cb", "key_cb",
                    "cancel_cb", "click_cbs")
        check("壳-_retire清空字段且一批对象全保留",
              _wl._STATE["root"] is None
              and _wl._STATE["click_cbs"] is None
              and len(_wl._STATE["retired"]) == 1
              and _wl._STATE["retired"][0].get("root") == "R1"
              and _wl._STATE["retired"][0].get("click_cbs")
              == ("A1", "B1"))
        for _i in range(8):
            _wl._STATE["root"] = f"R{_i}"
            _wl._retire("root")
        check("壳-退休列表上限裁剪（保留最近6批）",
              len(_wl._STATE["retired"]) == 6
              and _wl._STATE["retired"][-1] == {"root": "R7"},
              "防重复登录内存累积")
    finally:
        _wl._STATE.clear()
        _wl._STATE.update(_saved)


    # ---- v1.8.3 Dialog 承载 + onPageStarted 导航观测 ----
    check("壳-登录层全屏Dialog承载（手势返回系统级）",
          "android.app.Dialog" in wsrc
          and "setOnCancelListener" in wsrc
          and "setCancelable(True)" in wsrc
          and "_CancelListener" in wsrc
          and "DialogInterface$OnCancelListener" in wsrc
          and "dialog.dismiss()" in wsrc)
    check("壳-onPageStarted导航观测已接入",
          "onPageStarted" in wsrc and "onPageFinished" in wsrc
          and "stopLoading" in wsrc
          and "onPageStarted" in java_path.read_text(encoding="utf-8"),
          "302 落地守卫 + 导航日志")
    check("壳-市场URL黑名单命中正确",
          "market://details?id=x".startswith(_wl.MARKET_PREFIXES)
          and "https://play.google.com/store/apps?id=x".startswith(
              _wl.MARKET_PREFIXES)
          and "https://appgallery.huawei.com/x".startswith(
              _wl.MARKET_PREFIXES)
          and not "https://pan.baidu.com/".startswith(_wl.MARKET_PREFIXES))

    # ---- 首页宫格 ----
    grid = app._scr("home").ids.pan_grid
    check("壳-宫格卡片数等于网盘数", len(grid.children) == len(pans),
          f"{len(grid.children)} vs {len(pans)}")
    first_txt = grid.children[0].text  # add_widget 顺序：第一个是百度
    check("壳-未登录卡片显示域名", "baidu.com" in first_txt
          and "已登录" not in first_txt, first_txt.replace("\n", " "))

    # 无 WebView 环境 → 回退账号屏手动粘贴（预填域名）
    app.pan_login("baidu")
    check("壳-无WebView回退手动登录路径",
          app._scr("accounts").ids.domain_input.text == "baidu.com"
          and app.root.ids.sm.current == "accounts")

    # WebView 可用路径：mock open_login 直接回调（模拟自动检测到 Cookie）
    mobile_main.weblogin.available = lambda: True
    orig_open = mobile_main.weblogin.open_login
    mobile_main.weblogin.open_login = (
        lambda url, keys, on_done, title="", on_cancel=None,
        cookie_urls=(): on_done("BDUSS=fake123", True))
    app.pan_login("baidu")
    mobile_main.weblogin.open_login = orig_open
    acc = mobile_main.load_accounts()
    check("壳-登录记录账簿永久保存",
          acc.get("baidu", {}).get("name") == "百度网盘", str(list(acc)))
    check("壳-登录Cookie双写引擎store",
          pb.load_cookie_store().get("baidu.com") == "BDUSS=fake123",
          str({k: v[:12] for k, v in pb.load_cookie_store().items()}))
    baidu_txt = app._scr("home").ids.pan_grid.children[0].text
    check("壳-已登录徽标刷新", "已登录" in baidu_txt,
          baidu_txt.replace("\n", " "))
    check("壳-已登录卡片显示进入入口",
          "进入我的网盘" in baidu_txt, baidu_txt.replace("\n", " "))

    # ---- v2.1.0 已登录直入浏览模式 + 会话总闸 ----
    wsrc210 = Path(_wl.__file__).read_text(encoding="utf-8")
    check("壳-浏览模式与会话总闸（v2.1.0）",
          "def open_browse" in wsrc210
          and '"session": 0' in wsrc210
          and wsrc210.count("_only_now") >= 6
          and "time.sleep(3.0)" in wsrc210
          and "browse=True" in wsrc210,
          "已登录秒关层闪退根治：浏览模式+迟到回调作废+poller首轮延迟")
    check("壳-18家网盘全部有home页",
          all(p.get("home") for p in pans)
          and pans[0]["home"] == "https://pan.baidu.com/disk/main",
          "已登录卡片直入网页版文件页")
    orig_avail = mobile_main.weblogin.available
    orig_browse = mobile_main.weblogin.open_browse
    orig_open210 = mobile_main.weblogin.open_login
    browsed = []

    browse_cbs = []

    def _mock_browse(url, title="", on_close=None):
        browsed.append((url, title))
        browse_cbs.append(on_close)
        return True

    def _no_login(*a, **k):
        raise AssertionError("已登录不应再走登录层")

    mobile_main.weblogin.available = lambda: True
    mobile_main.weblogin.open_browse = _mock_browse
    mobile_main.weblogin.open_login = _no_login
    try:
        app.pan_login("baidu")
        ok210 = True
    except Exception:
        ok210 = False
    finally:
        mobile_main.weblogin.available = orig_avail
        mobile_main.weblogin.open_browse = orig_browse
        mobile_main.weblogin.open_login = orig_open210
    check("壳-已登录点卡片走浏览模式", ok210 and len(browsed) == 1
          and browsed[0][0] == "https://pan.baidu.com/disk/main"
          and browsed[0][1] == "百度网盘", str(browsed))
    check("壳-浏览打开提示（打开层时状态栏引导）",
          "已打开" in app._scr("home").ids.home_status.text)
    if browse_cbs and browse_cbs[0] is not None:
        browse_cbs[0]()  # 模拟用户关闭浏览层（✕/底部按钮）
    check("壳-浏览关闭自动切下载屏引导",
          app.root.ids.sm.current == "download"
          and "粘贴" in app._scr("home").ids.home_status.text)
    app.go("home")

    # 空 Cookie 不覆盖已有登录
    r = mobile_main.record_login("baidu", "", True)
    check("壳-空Cookie不覆盖登录", r is False
          and pb.load_cookie_store().get("baidu.com") == "BDUSS=fake123")

    # 删除登录：账簿 + store 双清
    app.del_account("baidu")
    check("壳-删除登录双清", "baidu" not in mobile_main.load_accounts()
          and "baidu.com" not in pb.load_cookie_store())

    # v1.8.5 凭证校验语义：特征命中=已登录；游客 Cookie 拒记账；
    # 无特征网盘（localStorage 型）记未验证
    mobile_main.record_login("quark", "__pus=a; __puus=b", True)
    qrec = mobile_main.load_accounts().get("quark", {})
    check("壳-夸克特征命中记已登录",
          qrec.get("verified") is True, str(qrec))
    r_q2 = mobile_main.record_login("quark", "BAIDUID=xyz", True)
    qrec2 = mobile_main.load_accounts().get("quark", {})
    check("壳-夸克游客Cookie拒记账",
          r_q2 is False and qrec2.get("len") == len("__pus=a; __puus=b"),
          "特征未命中拒绝新记账（既有有效登录保留不清除）")
    mobile_main.record_login("alipan", "cna=xyz", True)
    arec = mobile_main.load_accounts().get("alipan", {})
    check("壳-无特征网盘记未验证",
          arec.get("verified") is False and arec.get("len") == 7,
          str(arec))
    _acc = mobile_main.load_accounts()
    for _k in ("quark", "alipan"):
        _acc.pop(_k, None)
    mobile_main.save_accounts(_acc)
    _st = pb.load_cookie_store()
    for _d in ("quark.cn", "alipan.com"):
        _st.pop(_d, None)
    pb.save_cookie_store(_st)

    # v1.8.3 导航日志落盘：onPageStarted 记录 → 登录结束 nav-*.log
    _wl._STATE["nav_log"].clear()
    _wl._STATE["nav_log"].append(
        ("start", "08:00:00", "https://pan.quark.cn/"))
    _wl._STATE["nav_log"].append(
        ("block", "08:00:01", "市场URL已拦截: market://details?id=x"))
    mobile_main.weblogin.available = lambda: True
    orig_open = mobile_main.weblogin.open_login
    mobile_main.weblogin.open_login = (
        lambda url, keys, on_done, title="", on_cancel=None,
        cookie_urls=(): on_done("BDUSS=fake456", True))
    app.pan_login("baidu")
    mobile_main.weblogin.open_login = orig_open
    navs = sorted(Path(tmp).glob("nav-baidu-*.log"))
    nav_txt = navs[-1].read_text(encoding="utf-8") if navs else ""
    check("壳-导航日志落盘nav文件可取回诊断",
          bool(navs) and "market://details?id=x" in nav_txt
          and "pan.quark.cn" in nav_txt, f"{len(navs)} 份")
    check("壳-nav_log导出函数行为",
          hasattr(_wl, "nav_log") and len(_wl.nav_log()) == 2,
          f"{len(_wl.nav_log())} 条")

    # WebView 打开失败（真机 v1.7.0"卡片点击无反应"事故路径）→
    # 必须抛回调用方并回落账号屏手动路径，绝不静默；
    # v1.7.2 起：失败详情（含步骤名）显示到账号页状态栏 + 落 crash log
    mobile_main.weblogin.available = lambda: True

    def _boom(url, keys, on_done, title="", on_cancel=None,
              cookie_urls=()):
        raise mobile_main.weblogin.WebLoginError(
            "登录层挂载失败: WebLoginError: 步骤[挂载到窗口]失败: "
            "RuntimeException: addContentView")

    orig_open = mobile_main.weblogin.open_login
    mobile_main.weblogin.open_login = _boom
    n_crash0 = len(list(Path(tmp).glob("crash-*.log")))
    app.pan_login("quark")
    mobile_main.weblogin.open_login = orig_open
    acc_st = app._scr("accounts").ids.accounts_status.text
    check("壳-WebView失败回落账号屏手动路径",
          app._scr("accounts").ids.domain_input.text == "quark.cn"
          and app.root.ids.sm.current == "accounts")
    check("壳-WebView失败详情可见（账号页状态栏含步骤名）",
          "WebView 登录打开失败" in acc_st
          and "步骤[挂载到窗口]" in acc_st
          and "手动模式" in acc_st, acc_st[:80])
    check("壳-WebView失败已落crash日志",
          len(list(Path(tmp).glob("crash-*.log"))) == n_crash0 + 1
          and "weblogin 打开失败[quark]" in sorted(
              Path(tmp).glob("crash-*.log"))[-1].read_text(encoding="utf-8"))

    # 按钮回调异常兜底：guard 捕获 + crash log 落盘 + 首页可见提示
    n_before = len(list(Path(tmp).glob("crash-*.log")))
    app._guard(lambda: 1 / 0)(None)
    n_after = len(list(Path(tmp).glob("crash-*.log")))
    check("壳-回调异常guard兜底", n_after == n_before + 1
          and "操作失败" in app._scr("home").ids.home_status.text)

    # ---- 手动账号 + 自动匹配下载 + 前台保活 ----
    app._scr("accounts").ids.domain_input.text = "127.0.0.1"
    app._scr("accounts").ids.cookie_input.text = "SID=auto123"
    app.save_account()
    check("壳-手动账号Cookie已持久化",
          pb.load_cookie_store().get("127.0.0.1") == "SID=auto123")
    app.refresh_accounts()
    n_acc = len(app._scr("accounts").ids.accounts_box.children)
    check("壳-账号列表已刷新", n_acc >= 1, f"条目数={n_acc}")

    srv2 = TestServer()
    srv2.set_data(data, require_cookie="SID=auto123")
    mobile_main.IS_ANDROID = True  # 让 on_go 走前台保活分支
    app._scr("download").ids.url_input.text = srv2.url + "/a.bin"
    app._scr("download").ids.cookie_input.text = ""  # 留空 → 自动匹配
    app.on_go()
    app.worker.join(timeout=90)
    files = list(Path(tmp).glob("a.bin"))
    check("壳-自动匹配Cookie下载完整",
          files and files[0].read_bytes() == data,
          f"保活日志: {[l for l in app.logs if '保活' in l][:1]}")
    check("壳-前台服务start/stop各一次且下载结束已停",
          SVC_CALLS["start"] == 1 and SVC_CALLS["stop"] == 1
          and mobile_main._KEEPALIVE["svc"] is None,
          str(SVC_CALLS))
    mobile_main.IS_ANDROID = False

    # ---- 历史 ----
    h = mobile_main.load_history()
    check("壳-下载历史已写入", len(h["items"]) >= 1
          and h["items"][0]["name"] == "a.bin"
          and h["items"][0]["status"] == "完成", str(h["items"][:1]))
    app.refresh_history()
    n_hist = len(app._scr("history").ids.history_box.children)
    check("壳-历史列表已刷新", n_hist >= 1, f"条目数={n_hist}")

    app.on_rec_toggle(False)
    app._scr("download").ids.url_input.text = srv.url + "/b.bin"
    app.on_go()
    app.worker.join(timeout=90)
    h2 = mobile_main.load_history()
    check("壳-关闭记录后不再写入", len(h2["items"]) == len(h["items"])
          and h2["enabled"] is False,
          f"条目数不变={len(h2['items'])}")
    files = list(Path(tmp).glob("b.bin"))
    check("壳-关闭记录仍正常下载", files and files[0].read_bytes() == data)
    app.on_rec_toggle(True)

    # ---- v1.8.0 分享链接解析（123 多文件 mock 端到端） ----
    import json as _json
    d3a = os.urandom(200 * 1024)
    d3b = os.urandom(150 * 1024)
    srv3 = TestServer()
    srv3.add_path("/dl/a.bin", d3a)
    srv3.add_path("/dl/b.bin", d3b)
    srv3.add_json("/api/share/info",
                  {"code": 0, "data": {"ShareKey": "k1", "ShareKeyID": 9}})
    srv3.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"FileId": 1, "FileName": "sa.bin", "Size": len(d3a),
         "S3KeyTag": "t1", "IsDir": 0},
        {"FileId": 2, "FileName": "sb.bin", "Size": len(d3b),
         "S3KeyTag": "t2", "IsDir": 0}]}})
    srv3.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"DownloadUrl": f"{srv3.url}/dl/a.bin"}]}},
        when_query="S3KeyTag=t1")
    srv3.add_json("/api/share/get", {"code": 0, "data": {"InfoList": [
        {"DownloadUrl": f"{srv3.url}/dl/b.bin"}]}},
        when_query="S3KeyTag=t2")
    os.environ["PANBOOST_RESOLVER_HOSTS"] = _json.dumps(
        {"pan123": srv3.url})
    app._scr("download").ids.url_input.text = "https://www.123pan.com/s/k1"
    app._scr("download").ids.cookie_input.text = ""
    app.on_go()
    app.worker.join(timeout=120)
    # v3.0.0：解析后进文件列表屏（不再直接全量下载）
    check("壳-分享解析进文件列表屏",
          app.root.ids.sm.current == "files"
          and "2 个" in app._scr("files").ids.files_title.text,
          app._scr("files").ids.files_title.text)
    rows300 = app._scr("files").ids.files_box.children
    check("壳-文件列表行数与勾选态",
          len(rows300) == 2 and all(app._file_sel),
          "2 行默认全选")
    check("壳-下载所选按钮计数",
          "下载所选（2）" in app._scr("files").ids.files_dl_btn.text,
          app._scr("files").ids.files_dl_btn.text)
    # 取消第一个（sa.bin），只下载 sb.bin
    # v3.0.1 tap 手势：轻点（down→up 位移 < 8dp）切换勾选
    row0 = app._scr("files").ids.files_box.children[0]
    tap = types.SimpleNamespace(x=100.0, y=100.0, pos=(100.0, 100.0),
                                ud={}, profile=[],
                                is_mouse_scrolling=False)
    row0.on_touch_down(tap)
    tap.x, tap.y, tap.pos = 103.0, 102.0, (103.0, 102.0)
    row0.on_touch_up(tap)
    check("壳-轻点行切换勾选（tap 判定）",
          app._file_sel == [False, True]
          and "下载所选（1）" in app._scr("files").ids.files_dl_btn.text,
          str(app._file_sel))
    # 滑动（位移远超 8dp）不触发——滚动浏览与选择彻底分离
    row0b = app._scr("files").ids.files_box.children[0]
    swipe = types.SimpleNamespace(x=100.0, y=100.0, pos=(100.0, 100.0),
                                  ud={}, profile=[],
                                  is_mouse_scrolling=False)
    row0b.on_touch_down(swipe)
    swipe.x, swipe.y, swipe.pos = 180.0, 60.0, (180.0, 60.0)
    row0b.on_touch_up(swipe)
    check("壳-滑动不误触勾选（滚动与选择分离）",
          app._file_sel == [False, True], str(app._file_sel))
    # 长按（>0.55s）不触发
    row0c = app._scr("files").ids.files_box.children[0]
    hold = types.SimpleNamespace(x=100.0, y=100.0, pos=(100.0, 100.0),
                                 ud={}, profile=[],
                                 is_mouse_scrolling=False)
    row0c.on_touch_down(hold)
    time.sleep(0.6)
    row0c.on_touch_up(hold)
    check("壳-长按不误触勾选", app._file_sel == [False, True],
          str(app._file_sel))
    app.start_selected_downloads()
    app.worker.join(timeout=120)
    fa = list(Path(tmp).glob("sa.bin"))
    fb = list(Path(tmp).glob("sb.bin"))
    check("壳-只下载勾选的文件",
          (not fa) and fb and fb[0].read_bytes() == d3b,
          "sa 未下载、sb 完整")
    h4 = mobile_main.load_history()
    check("壳-分享历史记录分享链接便于重跑",
          h4["items"] and h4["items"][0]["url"].startswith(
              "https://www.123pan.com/s/"),
          str(h4["items"][:1]))
    # 全选场景：重跑全量下载（轻点第一行重新勾选）
    row0d = app._scr("files").ids.files_box.children[0]
    tap2 = types.SimpleNamespace(x=100.0, y=100.0, pos=(100.0, 100.0),
                                 ud={}, profile=[],
                                 is_mouse_scrolling=False)
    row0d.on_touch_down(tap2)
    row0d.on_touch_up(tap2)
    app.start_selected_downloads()
    app.worker.join(timeout=120)
    fa = list(Path(tmp).glob("sa.bin"))
    check("壳-全选批量下载完整",
          fa and fa[0].read_bytes() == d3a, "sa.bin 完整")
    del os.environ["PANBOOST_RESOLVER_HOSTS"]

    # ---- v3.0.0 剪贴板识别 + 公共目录回退 ----
    mobile_main.Clipboard = types.SimpleNamespace(
        get=lambda: "看看 https://www.123pan.com/s/k9 提取码 x1")
    app._scr("download").ids.url_input.text = ""
    app._on_resume()
    check("壳-剪贴板分享链接自动识别填入",
          app._scr("download").ids.url_input.text
          == "看看 https://www.123pan.com/s/k9 提取码 x1",
          app._scr("download").ids.url_input.text)
    mobile_main.Clipboard = types.SimpleNamespace(get=lambda: "普通文字")
    app._scr("download").ids.url_input.text = ""
    app._on_resume()
    check("壳-普通剪贴板内容不打扰",
          app._scr("download").ids.url_input.text == "", "非链接不填入")
    check("壳-下载目录回退私有目录（无 jnius）",
          mobile_main.download_dir() == mobile_main.external_files_dir(),
          "公共目录写测试失败时回退")

    app.del_account("127.0.0.1")
    check("壳-删除账号生效", "127.0.0.1" not in pb.load_cookie_store())

    # 失败任务也记录历史（URL 预填重跑）
    app._scr("download").ids.url_input.text = "http://127.0.0.1:9/f.bin"
    app.on_go()
    app.worker.join(timeout=60)
    h3 = mobile_main.load_history()
    check("壳-失败任务已记录", h3["items"][0]["status"] == "失败",
          str(h3["items"][0]))
    # ---- v2.0.0 统一日志 + 五屏 UI（底部导航 + 日志屏） ----
    import applog as _al
    check("壳-applog统一日志模块就绪",
          all(hasattr(_al, f) for f in (
              "init", "log", "info", "warn", "error", "tail",
              "ring_raw", "install_hooks", "cleanup", "log_files")),
          "app-日期.log 按天轮转保留 7 天 + 内存 ring + 异常钩子")
    check("壳-底部导航五Tab（v2.0.0）",
          all(("tab_%s" % k) in mobile_main.KV for k in (
              "home", "download", "accounts", "history", "logs"))
          and "NavTab" in mobile_main.KV
          and "class NavTab" in py_src,
          "首页/下载/账号/历史/日志")
    check("壳-日志屏已挂载（name=logs）",
          "LogsScreen" in mobile_main.KV and "name: 'logs'" in mobile_main.KV
          and "id: logs_lbl" in mobile_main.KV
          and "id: logs_status" in mobile_main.KV)
    check("壳-全局异常钩子已装（applog 链式）",
          sys.excepthook is not sys.__excepthook__)
    app.go("logs")
    check("壳-切日志屏Tab高亮同步",
          app.root.ids.tab_logs.active is True
          and app.root.ids.tab_home.active is False
          and app.root.ids.sm.current == "logs")
    check("壳-日志屏渲染ring内容",
          len(app._scr("logs").ids.logs_lbl.text) > 0
          and "份" in app._scr("logs").ids.logs_status.text,
          "refresh_logs 已渲染（ERROR红/WARN橙着色）")
    app.go("home")
    app_logs = sorted(Path(tmp).glob("app-*.log"))
    atxt = "\n".join(p.read_text(encoding="utf-8") for p in app_logs)
    check("壳-错误日志落盘（app-日期.log）",
          bool(app_logs) and "ERROR" in atxt and "download" in atxt,
          f"{len(app_logs)} 份（tmp 下）")
    check("壳-guard异常进统一日志",
          any(lv == "ERROR" and tag == "crash"
              for ts, lv, tag, msg in mobile_main.applog.ring_raw()),
          "UI 回调异常不静默")
    tmp2 = tempfile.mkdtemp(prefix="pbapplog_")
    _al.init(tmp2)
    _al.info("t", "info消息")
    _al.warn("t", "warn消息")
    try:
        1 / 0
    except ZeroDivisionError:
        _al.error("t", "捕获除零", exc=sys.exc_info()[1])
    afiles = list(Path(tmp2).glob("app-*.log"))
    ftxt = afiles[0].read_text(encoding="utf-8") if afiles else ""
    check("壳-applog文件写入与traceback",
          bool(afiles) and "info消息" in ftxt and "WARN" in ftxt
          and "ERROR" in ftxt and "ZeroDivisionError" in ftxt,
          afiles[0].name if afiles else "无文件")
    old = Path(tmp2) / "app-20200101.log"
    old.write_text("x", encoding="utf-8")
    os.utime(old, (0, 0))
    _al.cleanup()
    check("壳-applog轮转清理超期旧文件", not old.exists(), "保留 7 天")

    # ---- v2.0.1 登录完成闪退防御 ----
    check("壳-延迟调度器_on_ui_later就绪",
          hasattr(mobile_main, "_on_ui_later")
          and "Clock.schedule_once(lambda _dt: fn(), delay)" in py_src
          and '_dump_crash("_after_login' in py_src,
          "回调线程零工作 + 0.25s 落地缓冲 + try 兜底")
    mobile_main._on_ui_later(lambda: None)
    _orig_rl = mobile_main.record_login

    def _boom_login(*a, **k):
        raise RuntimeError("smoke201")

    mobile_main.record_login = _boom_login
    try:
        app._after_login("baidu", "BDUSS=xx", True)
        ok201 = True
    except Exception:
        ok201 = False
    finally:
        mobile_main.record_login = _orig_rl
    check("壳-_after_login异常兜底不穿透", ok201,
          "Clock 回调异常不杀主循环（表象即闪退）")
    _c201 = sorted(Path(tmp).glob("crash-*.log"))
    _c201_txt = "\n".join(
        p.read_text(encoding="utf-8") for p in _c201[-3:])
    check("壳-_after_login兜底落crash日志",
          "RuntimeError" in _c201_txt or "smoke201" in _c201_txt,
          f"{len(_c201)} 份 crash log")

    app.rerun("http://example.com/rerun.bin")
    check("壳-历史点击重跑预填URL",
          app._scr("download").ids.url_input.text
          == "http://example.com/rerun.bin"
          and app.root.ids.sm.current == "download")

    app.clear_history()
    check("壳-清空历史", mobile_main.load_history()["items"] == [])

    n_fail = sum(1 for _, ok in CHECKS if not ok)
    print(f"\n===== mobile 冒烟: {len(CHECKS) - n_fail}/{len(CHECKS)} 通过 =====")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
