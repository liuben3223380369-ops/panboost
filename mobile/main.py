#!/usr/bin/env python3
"""PanBoost Android 图形壳（Kivy）v1.6.3。

三屏界面：
  下载 —— URL/线程/进度/日志（引擎反风控全量生效）
  账号 —— 网盘 Cookie 按域名持久化，下载时自动匹配携带
  历史 —— 下载记录永久保存（可开关/清空/点击重跑）

字体：fonts/cjk.ttf（Noto Sans SC 子集，21985 字符）重注册为 Kivy
默认字体 Roboto——修复默认字体无 CJK 字形导致的中文方块乱码。

v1.6.3：线程选项补全至 1024（引擎 MAX_THREADS=1024；建议仅对大文件
且服务器允许时使用超高并发，引擎会平滑爬坡并自动 AIMD 降速），
下拉列表改紧凑行高适配小屏。

v1.6.2：修复 v1.6.1 启动闪退——KV 引用的 MainScreen/AccountsScreen/
HistoryScreen 此前未在 Python 定义，Kivy Builder 实例化时抛
FactoryException 导致打开即崩。自定义屏必须先在 Python 定义（Widget
元类会自动注册进 Kivy Factory）。另增崩溃日志兜底：任何未捕获异常
写入下载目录 crash-*.log，可用文件管理器取回诊断。
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

HISTORY_FILE = pb.CONFIG_DIR / "history.json"


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
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.screenmanager import Screen  # noqa: E402

SHELL_VERSION = "1.6.3"


class MainScreen(Screen):
    """KV 规则引用的自定义屏必须在 Python 定义，否则
    Builder 抛 FactoryException、App 启动即闪退（v1.6.1 事故根因）。"""


class AccountsScreen(Screen):
    pass


class HistoryScreen(Screen):
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


def _install_crash_logger():
    """崩溃兜底：未捕获异常写 crash-*.log 到外部私有目录（可取回诊断）。"""
    def _dump(tag):
        try:
            import traceback
            d = external_files_dir()
            os.makedirs(d, exist_ok=True)
            p = os.path.join(
                d, "crash-%s.log" % time.strftime("%Y%m%d-%H%M%S"))
            with open(p, "w", encoding="utf-8") as f:
                f.write(tag + traceback.format_exc())
        except Exception:
            pass

    def _hook(t, v, tb):
        _dump("sys.excepthook: %s: %s\n" % (t.__name__, v))
        sys.__excepthook__(t, v, tb)

    sys.excepthook = _hook
    try:
        from kivy.base import ExceptionHandler, ExceptionManager

        class _CrashHandler(ExceptionHandler):
            def handle_exception(self, e):
                _dump("kivy: %s: %s\n" % (type(e).__name__, e))
                return ExceptionManager.RAISE

        ExceptionManager.handler = _CrashHandler()
    except Exception:
        pass


_install_crash_logger()


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
<CompactOption@SpinnerOption>:
    height: dp(30)
    font_size: sp(12)

ScreenManager:
    MainScreen:
    AccountsScreen:
    HistoryScreen:

<MainScreen>:
    name: 'main'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(6)

        Label:
            text: 'PanBoost v' + app.shell_version
            font_size: sp(19)
            bold: True
            size_hint_y: None
            height: dp(26)

        TextInput:
            id: url_input
            hint_text: '下载直链 URL（http/https）'
            multiline: False
            size_hint_y: None
            height: dp(40)

        TextInput:
            id: cookie_input
            hint_text: '本次 Cookie（可选，留空自动匹配已存账号）'
            multiline: False
            size_hint_y: None
            height: dp(40)

        BoxLayout:
            size_hint_y: None
            height: dp(40)
            spacing: dp(6)
            Label:
                text: '线程:'
                size_hint_x: None
                width: dp(44)
                halign: 'right'
            Spinner:
                id: threads_spinner
                text: 'auto'
                values: ['auto', '8', '16', '32', '64', '128', '256', '512', '1024']
                option_cls: CompactOption
                size_hint_x: 0.35
            Switch:
                id: insecure_switch
                size_hint_x: None
                width: dp(44)
            Label:
                text: '跳过证书校验'
                font_size: sp(11)
                halign: 'left'
                text_size: self.size

        Button:
            id: go_btn
            text: '开始下载'
            bold: True
            size_hint_y: None
            height: dp(46)
            on_release: app.on_go()

        ProgressBar:
            id: progress
            max: 1.0
            value: 0
            size_hint_y: None
            height: dp(16)

        Label:
            id: status_lbl
            text: '待命。目录: ' + app.dir_short
            font_size: sp(12)
            size_hint_y: None
            height: dp(34)
            halign: 'left'
            valign: 'middle'
            text_size: self.size

        BoxLayout:
            size_hint_y: None
            height: dp(38)
            spacing: dp(6)
            Button:
                text: '账号管理'
                on_release: app.go('accounts')
            Button:
                text: '下载历史'
                on_release: app.go('history')

        ScrollView:
            Label:
                id: log_lbl
                text: ''
                font_size: sp(11)
                size_hint_y: None
                height: max(self.texture_size[1], dp(24))
                text_size: (self.width - dp(6), None)
                halign: 'left'

<AccountsScreen>:
    name: 'accounts'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(6)

        Label:
            text: '网盘账号（Cookie 持久化）'
            font_size: sp(17)
            bold: True
            size_hint_y: None
            height: dp(24)

        Label:
            text: '先在浏览器登录网盘，F12 开发者工具复制请求里的 Cookie 粘贴到这里（按域名保存）。下载该域名文件时自动携带，永久保存。点击列表条目可删除。'
            font_size: sp(11)
            size_hint_y: None
            height: dp(58)
            text_size: self.size
            halign: 'left'

        TextInput:
            id: domain_input
            hint_text: '网盘域名，如 pan.baidu.com'
            multiline: False
            size_hint_y: None
            height: dp(40)

        TextInput:
            id: cookie_input
            hint_text: 'Cookie 值，如 BDUSS=xxx; STK=yyy'
            multiline: True
            size_hint_y: None
            height: dp(64)

        Button:
            text: '保存账号'
            bold: True
            size_hint_y: None
            height: dp(42)
            on_release: app.save_account()

        Label:
            id: accounts_status
            text: ''
            font_size: sp(11)
            size_hint_y: None
            height: dp(20)

        ScrollView:
            BoxLayout:
                id: accounts_box
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(4)

        Button:
            text: '返回'
            size_hint_y: None
            height: dp(40)
            on_release: app.go('main')

<HistoryScreen>:
    name: 'history'
    BoxLayout:
        orientation: 'vertical'
        padding: dp(10)
        spacing: dp(6)

        BoxLayout:
            size_hint_y: None
            height: dp(30)
            Label:
                text: '下载历史（永久记录）'
                font_size: sp(16)
                bold: True
            Switch:
                id: rec_switch
                size_hint_x: None
                width: dp(44)
                on_active: app.on_rec_toggle(self.active)

        BoxLayout:
            size_hint_y: None
            height: dp(36)
            spacing: dp(6)
            Button:
                text: '清空历史'
                on_release: app.clear_history()
            Button:
                text: '返回'
                on_release: app.go('main')

        ScrollView:
            BoxLayout:
                id: history_box
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: dp(4)
"""


class PanBoostApp(App):
    title = "PanBoost"

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
        self._load_settings()
        return self.root

    # ---------- 屏幕与设置 ----------

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

    # ---------- 账号（Cookie 持久化） ----------

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

    def del_account(self, domain):
        store = pb.load_cookie_store()
        store.pop(domain, None)
        pb.save_cookie_store(store)
        self._scr("accounts").ids.accounts_status.text = f"已删除 {domain}"
        self.refresh_accounts()

    def refresh_accounts(self):
        box = self._scr("accounts").ids.accounts_box
        box.clear_widgets()
        store = pb.load_cookie_store()
        if not store:
            box.add_widget(Label(
                text="暂无账号。保存第一个网盘 Cookie 后，下载对应域名文件时将自动携带。",
                font_size=sp(11), size_hint_y=None, height=dp(40)))
            return
        for domain, cookie in sorted(store.items()):
            show = f"{domain}    {cookie[:36]}{'…' if len(cookie) > 36 else ''}"
            btn = Button(text=show, font_size=sp(11), size_hint_y=None,
                         height=dp(34),
                         on_release=lambda _b, d=domain: self.del_account(d))
            box.add_widget(btn)

    # ---------- 历史 ----------

    def refresh_history(self):
        box = self._scr("history").ids.history_box
        box.clear_widgets()
        items = load_history().get("items", [])
        if not items:
            box.add_widget(Label(text="暂无下载记录",
                                 font_size=sp(12), size_hint_y=None,
                                 height=dp(30)))
            return
        for it in items:
            ts = time.strftime("%m-%d %H:%M", time.localtime(it.get("ts", 0)))
            txt = (f"[{ts}] {it.get('status', '?')}  {it.get('name', '?')}  "
                   f"{pb.fmt_size(it.get('size', 0))}"
                   + (f"  {pb.fmt_size(it.get('speed', 0))}/s"
                      if it.get("speed") else ""))
            btn = Button(text=txt, font_size=sp(11), size_hint_y=None,
                         height=dp(34), halign="left",
                         on_release=lambda _b, u=it.get("url", ""):
                         self.rerun(u))
            box.add_widget(btn)

    def rerun(self, url):
        if not url:
            return
        self._scr("main").ids.url_input.text = url
        self.go("main")
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
        url = self._scr("main").ids.url_input.text.strip()
        if not url:
            self.log("请先输入下载直链 URL")
            return
        manual_cookie = self._scr("main").ids.cookie_input.text.strip()
        choice = self._scr("main").ids.threads_spinner.text
        insecure = bool(self._scr("main").ids.insecure_switch.active)
        auto_cookie = pb.match_cookie_header(url) if not manual_cookie else None
        if manual_cookie:
            self.log("使用手动填写的 Cookie")
        elif auto_cookie:
            self.log(f"自动匹配已存账号 Cookie（{auto_cookie[:40]}…）")
        else:
            self.log("未匹配到已存账号 Cookie，匿名下载")
        self._progress = 0.0
        self._status = "探测中…"
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
            if out_name:
                add_history({"ts": int(time.time()), "url": url,
                             "name": out_name, "size": size,
                             "status": status, "speed": round(speed)})

    # ---------- 主线程侧（UI 刷新） ----------

    def _tick(self, _dt):
        main = self._scr("main").ids
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
        main.go_btn.text = self._btn_text
        main.progress.value = self._progress
        main.status_lbl.text = self._status
        if len(self.logs) != self._log_serial:
            self._log_serial = len(self.logs)
            main.log_lbl.text = "\n".join(self.logs[-14:])


if __name__ == "__main__":
    PanBoostApp().run()
