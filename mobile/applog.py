"""PanBoost 统一应用日志（v2.0.0）。

三大诊断日志体系（全部在应用外部私有目录，用户可直接取回反馈）：
- crash-*.log      未捕获异常完整 traceback（main._dump_crash）
- nav-*.log        WebView 登录层导航流水（main._dump_nav_log）
- app-YYYYMMDD.log 本模块——全部关键操作与错误的流水账，按天轮转
                   保留 7 天，UI「日志」屏实时可见（applog.ring）

设计约束：
- 纯标准库、无 Kivy/pyjnius 依赖——冒烟测试与真机行为完全一致
- 线程安全（Lock）：下载 worker、轮询线程、UI 线程并发写安全
- 文件写失败静默降级（只进内存 ring）——日志系统绝不能弄崩 App
- install_hooks 链式调用已装钩子：crash-*.log 落盘等既有行为保留
"""
import os
import sys
import threading
import time
import traceback
from pathlib import Path

_LOCK = threading.Lock()
_DIR = None          # None = 未初始化（仅内存 ring，不落盘）
_RING = []           # (ts, level, tag, msg) 最近条目
_RING_MAX = 500
_KEEP_DAYS = 7
_HOOKED = False


def init(base_dir, keep_days=7):
    """初始化日志目录（App.build 调用；失败自动降级为仅内存模式）。"""
    global _DIR, _KEEP_DAYS
    _KEEP_DAYS = max(1, int(keep_days))
    try:
        d = Path(base_dir)
        d.mkdir(parents=True, exist_ok=True)
        _DIR = d
    except Exception:
        _DIR = None
    cleanup()


def _write(level, tag, msg):
    """追加一行到当天日志文件（app-YYYYMMDD.log，跨天自动换文件）。

    持有 _LOCK 时调用；任何失败静默。
    """
    if _DIR is None:
        return
    try:
        p = _DIR / ("app-%s.log" % time.strftime("%Y%m%d"))
        line = "%s %s [%s] %s\n" % (
            time.strftime("%Y-%m-%d %H:%M:%S"), level, tag,
            str(msg).replace("\r", ""))
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def log(level, tag, msg=""):
    """记录一条日志：内存 ring（UI 可见）+ 当天文件（可取回）。"""
    level = str(level).upper()
    if level not in ("INFO", "WARN", "ERROR"):
        level = "INFO"
    ts = time.strftime("%H:%M:%S")
    with _LOCK:
        _RING.append((ts, level, str(tag), str(msg)))
        del _RING[:-_RING_MAX]
        _write(level, tag, msg)


def info(tag, msg=""):
    log("INFO", tag, msg)


def warn(tag, msg=""):
    log("WARN", tag, msg)


def error(tag, msg="", exc=None):
    """ERROR 级：自动附完整 traceback（exc 或当前活跃异常）。"""
    tb = ""
    try:
        if exc is not None:
            tb = "".join(traceback.format_exception(
                type(exc), exc, getattr(exc, "__traceback__", None)))
        elif sys.exc_info()[0] is not None:
            tb = traceback.format_exc()
    except Exception:
        tb = ""
    body = str(msg) + (("\n" + tb) if tb else "")
    log("ERROR", tag, body)


def ring_raw():
    """内存 ring 快照：[(ts, level, tag, msg), ...]（UI 着色渲染用）。"""
    with _LOCK:
        return list(_RING)


def tail(n=200):
    """最近 n 条纯文本行（诊断导出用）。"""
    with _LOCK:
        items = _RING[-int(max(1, n)):]
    return ["%s %s [%s] %s" % (ts, lv, tag, msg) for ts, lv, tag, msg in items]


def cleanup():
    """删除超过保留期的旧日志（init 时调用；失败静默）。"""
    if _DIR is None:
        return
    try:
        cutoff = time.time() - _KEEP_DAYS * 86400
        for p in _DIR.glob("app-*.log"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def log_files(base_dir=None):
    """列出日志目录下全部 app-*.log（日志屏提示用）。"""
    d = Path(base_dir) if base_dir is not None else _DIR
    if d is None:
        return []
    try:
        return sorted(p.name for p in d.glob("app-*.log"))
    except Exception:
        return []


def install_hooks():
    """全局未捕获异常兜底：主线程 + 子线程异常全部进 app 日志。

    链式调用已装钩子（crash-*.log 等既有落盘不丢）；重复调用幂等。
    """
    global _HOOKED
    if _HOOKED:
        return
    _HOOKED = True

    prev = sys.excepthook

    def _hook(t, v, tb):
        try:
            error("crash", "未捕获异常 %s: %s" % (
                getattr(t, "__name__", t), v), exc=v)
        except Exception:
            pass
        try:
            prev(t, v, tb)
        except Exception:
            sys.__excepthook__(t, v, tb)

    sys.excepthook = _hook

    prev_th = getattr(threading, "excepthook", None)
    if prev_th is not None:
        def _thook(args):
            try:
                error("crash", "线程 %s 未捕获异常 %s: %s" % (
                    getattr(getattr(args, "thread", None), "name", "?"),
                    getattr(args.exc_type, "__name__", args.exc_type),
                    args.exc_value), exc=args.exc_value)
            except Exception:
                pass
            try:
                prev_th(args)
            except Exception:
                pass

        threading.excepthook = _thook
