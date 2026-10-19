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
core_mod = types.ModuleType("kivy.core")
core_mod.text = text_mod
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
        lambda url, keys, on_done, title="": on_done("BDUSS=fake123", True))
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

    # WebView 打开失败（真机 v1.7.0"卡片点击无反应"事故路径）→
    # 必须抛回调用方并回落账号屏手动路径，绝不静默；
    # v1.7.2 起：失败详情（含步骤名）显示到账号页状态栏 + 落 crash log
    mobile_main.weblogin.available = lambda: True

    def _boom(url, keys, on_done, title=""):
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
