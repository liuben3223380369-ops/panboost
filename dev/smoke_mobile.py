"""mobile/main.py 的无 Kivy 冒烟测试：mock kivy 模块后跑完整流程。

覆盖：中文字体注册、三屏结构（下载/账号/历史）、账号 Cookie 持久化与
自动匹配、下载历史永久记录与开关、删除账号、主下载回归。
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

os.environ["PANBOOST_HOME"] = tempfile.mkdtemp(prefix="pbmobile_")
os.environ.setdefault("PANBOOST_NO_FSYNC", "1")

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

    def trigger(self):
        if callable(self._on_release):
            self._on_release(self)

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

        main = screen("main",
                      url_input=_Widget(), cookie_input=_Widget(),
                      threads_spinner=_Widget(text="16"),
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
        sm.current = "main"
        sm._screens = {"main": main, "accounts": accounts, "history": history}
        sm.get_screen = sm._screens.get
        return sm


lang_mod = types.ModuleType("kivy.lang")
lang_mod.Builder = _Builder
metrics_mod = types.ModuleType("kivy.metrics")
metrics_mod.dp = lambda x: x
metrics_mod.sp = lambda x: x
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
kivy.uix = uix_mod
kivy.core = core_mod
sys.modules.update({
    "kivy": kivy, "kivy.app": app_mod, "kivy.clock": clock_mod,
    "kivy.lang": lang_mod, "kivy.metrics": metrics_mod,
    "kivy.uix": uix_mod, "kivy.uix.button": btn_mod,
    "kivy.uix.label": lbl_mod, "kivy.core": core_mod,
    "kivy.core.text": text_mod, "kivy.uix.screenmanager": sm_mod,
})

import main as mobile_main  # noqa: E402
from test_server import TestServer  # noqa: E402
import panboost as pb  # noqa: E402

CHECKS = []


def check(name, ok, detail=""):
    CHECKS.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def main():
    # 用例0：中文字体注册（本地存在真字体文件）
    check("壳-中文字体已注册", mobile_main.register_font(),
          "fonts/cjk.ttf 存在且注册成功")

    # 用例0b：KV 引用的自定义类必须在 Python 有定义（v1.6.1 闪退根因，
    # mock 的 Builder 测不出，靠静态扫描防回归；真 Kivy 校验见 check_kv.py）
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
    check("壳-三屏类已定义且为Screen子类",
          all(issubclass(getattr(mobile_main, n, type(None)), _Screen)
              for n in ("MainScreen", "AccountsScreen", "HistoryScreen")))
    check("壳-崩溃日志钩子已安装", sys.excepthook is not sys.__excepthook__,
          "sys.excepthook 已替换为 crash logger")

    data = os.urandom(3 * 1024 * 1024)
    srv = TestServer()
    srv.set_data(data)

    tmp = tempfile.mkdtemp(prefix="pbmobile_dl_")
    mobile_main.external_files_dir = lambda: tmp
    app = mobile_main.PanBoostApp()
    app.build()

    # 用例1：账号保存 → 持久化 → 域名匹配
    app._scr("accounts").ids.domain_input.text = "127.0.0.1"
    app._scr("accounts").ids.cookie_input.text = "SID=auto123"
    app.save_account()
    store = pb.load_cookie_store()
    check("壳-账号Cookie已持久化", store.get("127.0.0.1") == "SID=auto123",
          str(store))
    app.refresh_accounts()
    n_acc = len(app._scr("accounts").ids.accounts_box.children)
    check("壳-账号列表已刷新", n_acc >= 1, f"条目数={n_acc}")

    # 用例2：下载自动匹配已存账号 Cookie（服务器校验 Cookie）
    srv2 = TestServer()
    srv2.set_data(data, require_cookie="SID=auto123")
    app._scr("main").ids.url_input.text = srv2.url + "/a.bin"
    app._scr("main").ids.cookie_input.text = ""  # 留空 → 自动匹配
    app.on_go()
    app.worker.join(timeout=90)
    files = list(Path(tmp).glob("a.bin"))
    check("壳-自动匹配Cookie下载完整",
          files and files[0].read_bytes() == data,
          f"auto匹配日志: {[l for l in app.logs if '自动匹配' in l][:1]}")

    # 用例3：历史永久记录
    h = mobile_main.load_history()
    check("壳-下载历史已写入", len(h["items"]) >= 1
          and h["items"][0]["name"] == "a.bin"
          and h["items"][0]["status"] == "完成",
          str(h["items"][:1]))
    app.refresh_history()
    n_hist = len(app._scr("history").ids.history_box.children)
    check("壳-历史列表已刷新", n_hist >= 1, f"条目数={n_hist}")

    # 用例4：历史开关关闭 → 不再记录
    app.on_rec_toggle(False)
    app._scr("main").ids.url_input.text = srv.url + "/b.bin"
    app.on_go()
    app.worker.join(timeout=90)
    h2 = mobile_main.load_history()
    check("壳-关闭记录后不再写入", len(h2["items"]) == len(h["items"])
          and h2["enabled"] is False,
          f"条目数不变={len(h2['items'])}")
    files = list(Path(tmp).glob("b.bin"))
    check("壳-关闭记录仍正常下载", files and files[0].read_bytes() == data)
    app.on_rec_toggle(True)

    # 用例5：删除账号
    app.del_account("127.0.0.1")
    check("壳-删除账号生效", "127.0.0.1" not in pb.load_cookie_store())

    # 用例6：失败任务也记录历史（URL 预填重跑）
    app._scr("main").ids.url_input.text = "http://127.0.0.1:9/f.bin"
    app.on_go()
    app.worker.join(timeout=60)
    h3 = mobile_main.load_history()
    check("壳-失败任务已记录", h3["items"][0]["status"] == "失败",
          str(h3["items"][0]))
    app.rerun("http://example.com/rerun.bin")
    check("壳-历史点击重跑预填URL",
          app._scr("main").ids.url_input.text == "http://example.com/rerun.bin"
          and app.root.current == "main")

    # 用例7：清空历史
    app.clear_history()
    check("壳-清空历史", mobile_main.load_history()["items"] == [])

    n_fail = sum(1 for _, ok in CHECKS if not ok)
    print(f"\n===== mobile 冒烟: {len(CHECKS) - n_fail}/{len(CHECKS)} 通过 =====")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
