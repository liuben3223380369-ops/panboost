#!/usr/bin/env python3
"""PanBoost Android 图形壳（Kivy）。

嵌入 panboost.py 单文件引擎：URL/Cookie 输入 → probe → 多线程下载（反风控
引擎全量生效）→ 主线程 Clock 轮询进度。下载目录为应用外部私有目录
（getExternalFilesDir，无需任何存储权限，USB/文件管理器可取）。

构建：mobile/buildozer.spec + GitHub Actions 云端打包（见
.github/workflows/android.yml），CI 会把仓库根的 panboost.py 复制到本目录。
"""
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

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.lang import Builder  # noqa: E402
from kivy.metrics import dp, sp  # noqa: E402


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


def _safe_name(name, url):
    name = (name or "").replace("/", "_").replace("\\", "_") \
        .replace("\x00", "").strip()
    if not name:
        name = os.path.basename(urllib.parse.urlsplit(url).path) or ""
    return name or "download.bin"


KV = """
BoxLayout:
    orientation: 'vertical'
    padding: dp(10)
    spacing: dp(6)

    Label:
        text: 'PanBoost v' + app.pb_version
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
        hint_text: 'Cookie（可选；网盘直链通常需要，形如 k1=v1; k2=v2）'
        multiline: True
        size_hint_y: None
        height: dp(64)

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
            values: ['auto', '8', '16', '32', '64', '128']
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

    ScrollView:
        Label:
            id: log_lbl
            text: ''
            font_size: sp(11)
            size_hint_y: None
            height: max(self.texture_size[1], dp(24))
            text_size: (self.width - dp(6), None)
            halign: 'left'
"""


class PanBoostApp(App):
    title = "PanBoost"

    def build(self):
        self.pb_version = pb.VERSION
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
        return self.root

    # ---------- worker 线程侧（只写普通属性，UI 更新全部交给 _tick） ----------

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
        url = self.root.ids.url_input.text.strip()
        if not url:
            self.log("请先输入下载直链 URL")
            return
        cookie = self.root.ids.cookie_input.text.strip()
        choice = self.root.ids.threads_spinner.text
        insecure = bool(self.root.ids.insecure_switch.active)
        self.logs.clear()
        self.log(f"开始: {url[:80]}")
        self._progress = 0.0
        self._status = "探测中…"
        self.worker = threading.Thread(
            target=self._run_download,
            args=(url, cookie, choice, insecure), daemon=True)
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
                self.log("下载完成")
            elif rc == 130:
                self._status = "已停止（进度已保存，可续传）"
            else:
                err = self.dl.errors[0] if self.dl and self.dl.errors else "未知错误"
                self._status = "失败（进度已保存）"
                self.log(f"失败: {err}")
        except Exception as e:
            self._status = "失败"
            self.log(f"{type(e).__name__}: {e}")
        finally:
            self.dl = None

    # ---------- 主线程侧（UI 刷新） ----------

    def _tick(self, _dt):
        ids = self.root.ids
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
        ids.go_btn.text = self._btn_text
        ids.progress.value = self._progress
        ids.status_lbl.text = self._status
        if len(self.logs) != self._log_serial:
            self._log_serial = len(self.logs)
            ids.log_lbl.text = "\n".join(self.logs[-14:])


if __name__ == "__main__":
    PanBoostApp().run()
