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
        sm = types.SimpleNamespace()
        sm.current = "home"
        sm._screens = {"home": home, "download": download,
                       "accounts": accounts, "history": history}
        sm.get_screen = sm._screens.get
        return sm


lang_mod = types.ModuleType("kivy.lang")
lang_mod.Builder = _Builder
metrics_mod = types.ModuleType("kivy.metrics")
metrics_mod.dp = lambda x: x
metrics_mod.sp = lambda x: x
props_mod = types.ModuleType("kivy.properties")
props_mod.ListProperty = lambda *a, **k: list(a[0]) if a else []
uix_mod = types.ModuleType("kivy.uix")
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
sys.modules.update({
    "kivy": kivy, "kivy.app": app_mod, "kivy.clock": clock_mod,
    "kivy.lang": lang_mod, "kivy.metrics": metrics_mod,
    "kivy.properties": props_mod, "kivy.uix": uix_mod,
    "kivy.uix.button": btn_mod, "kivy.uix.label": lbl_mod,
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
    check("壳-四屏类已定义且为Screen子类",
          all(issubclass(getattr(mobile_main, n, type(None)), _Screen)
              for n in ("MainScreen", "DownloadScreen", "AccountsScreen",
                        "HistoryScreen")))
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
          app._on_key(None, 27) is True and app.root.current == "home")
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
    check("壳-壳版本1.9.0",
          mobile_main.SHELL_VERSION == "1.9.0", mobile_main.SHELL_VERSION)

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
          and app.root.current == "accounts")

    # WebView 可用路径：mock open_login 直接回调（模拟自动检测到 Cookie）
    mobile_main.weblogin.available = lambda: True
    orig_open = mobile_main.weblogin.open_login
    mobile_main.weblogin.open_login = (
        lambda url, keys, on_done, title="", on_cancel=None:
        on_done("BDUSS=fake123", True))
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
        lambda url, keys, on_done, title="", on_cancel=None:
        on_done("BDUSS=fake456", True))
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

    def _boom(url, keys, on_done, title="", on_cancel=None):
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
          and app.root.current == "accounts")
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
        {"FileId": 1, "FileName": "a.bin", "Size": len(d3a),
         "S3KeyTag": "t1", "IsDir": 0},
        {"FileId": 2, "FileName": "b.bin", "Size": len(d3b),
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
    fa = list(Path(tmp).glob("a.bin"))
    fb = list(Path(tmp).glob("b.bin"))
    check("壳-123分享链接多文件下载完整",
          fa and fb and fa[0].read_bytes() == d3a
          and fb[0].read_bytes() == d3b)
    h4 = mobile_main.load_history()
    check("壳-分享历史记录分享链接便于重跑",
          h4["items"] and h4["items"][0]["url"].startswith(
              "https://www.123pan.com/s/"),
          str(h4["items"][:1]))
    del os.environ["PANBOOST_RESOLVER_HOSTS"]

    app.del_account("127.0.0.1")
    check("壳-删除账号生效", "127.0.0.1" not in pb.load_cookie_store())

    # 失败任务也记录历史（URL 预填重跑）
    app._scr("download").ids.url_input.text = "http://127.0.0.1:9/f.bin"
    app.on_go()
    app.worker.join(timeout=60)
    h3 = mobile_main.load_history()
    check("壳-失败任务已记录", h3["items"][0]["status"] == "失败",
          str(h3["items"][0]))
    app.rerun("http://example.com/rerun.bin")
    check("壳-历史点击重跑预填URL",
          app._scr("download").ids.url_input.text
          == "http://example.com/rerun.bin"
          and app.root.current == "download")

    app.clear_history()
    check("壳-清空历史", mobile_main.load_history()["items"] == [])

    n_fail = sum(1 for _, ok in CHECKS if not ok)
    print(f"\n===== mobile 冒烟: {len(CHECKS) - n_fail}/{len(CHECKS)} 通过 =====")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
