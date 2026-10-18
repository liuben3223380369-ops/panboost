#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PanBoost —— 全网盘通用多线程加速下载器（零依赖，纯 Python 标准库）

原理：登录态直链 + HTTP Range 分段并发 + 断点续传。
所有网盘（百度/阿里/夸克/123/天翼/蓝奏/迅雷/OneDrive/Google Drive...）的下载
本质都是 HTTP(S) 直链 + 请求头凭据（Cookie/UA/Referer），
PanBoost 把这一层做成通用引擎，配合你自己的登录账号即可多线程满速下载。

v1.3 反风控引擎 Pro：
  三态熔断(closed/open/half-open 自动探测恢复)、403语义分类(直链过期≠封禁)、
  worker内UA轮换、跨会话域名风控记忆、拟人化请求层(浏览器头/建连抖动/块乱序/
  连接寿命)、--limit 全局限速、TLS 指纹缓解(Chrome风格cipher)、--explain 审计摘要。

用法：
  python panboost.py download <直链或分享链接> [选项]
  python panboost.py probe    <URL>              探测服务器能力(Range/大小/文件名)
  python panboost.py resolve  <分享链接>          解析出直链
  python panboost.py cookie   import <域名> <cookies.txt>   导入浏览器Cookie
  python panboost.py cookie   list               查看已导入的Cookie

代码分区导航：
  §1 常量与全局配置        §2 通用工具(格式化/pwrite/SSL/HTTP)
  §3 拟人化层(UA池/请求头/轮换)  §4 风控层(审计/域级记忆/熔断/限速/403分类)
  §5 探测层                §6 调优(auto线程数)
  §7 下载引擎(多线程/单线程)     §8 Cookie 与解析器
  §9 CLI
"""
import argparse
import fcntl
import hashlib
import http.client
import json
import os
import queue as _queue
import random
import re
import shutil
import signal
import socket
import ssl
import sys
import threading
import time
import urllib.parse
from pathlib import Path

# =====================================================================
# §1 常量与全局配置
# =====================================================================

VERSION = "1.6.0"
APP = "panboost"
CONFIG_DIR = Path(os.environ.get("PANBOOST_HOME") or Path.home() / ".panboost")
COOKIE_DB = CONFIG_DIR / "cookies.json"
RISK_DB = CONFIG_DIR / "antifraud.json"
AUDIT_LOG = CONFIG_DIR / "antifraud.log"
CTRL_SUFFIX = ".pbctrl"
PART_SUFFIX = ".pbpart"
LOCK_SUFFIX = ".pblock"

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "aria2/1.36.0",
    "curl/8.5.0",
]
DEFAULT_UA = UA_POOL[0]

CHUNK = 256 * 1024
MIN_PIECE = 512 * 1024
MAX_PIECE = 64 * 1024 * 1024
BLOCKS_PER_WORKER = 8
WRITE_BUF = 1024 * 1024     # worker 写盘聚合缓冲（aria2 --disk-cache 思路）
CONN_MIN_BYTES = 32 * 1024 * 1024  # 连接复用字节阈值（HTTPS 握手成本摊薄）
CONN_MAX_BLOCKS = 24       # 连接复用块数硬上限（保持拟人化换连接行为）
MAX_BLOCKS_PER_CONN = 6    # 拟人化：连接复用的最少块数（配合字节阈值）
MAX_UA_SWITCHES_PER_BLOCK = 2
MAX_REDIRECTS = 10
PROBE_TRANSIENT_RETRIES = 3   # 探测期瞬时限流(429/503)重试次数
DEFAULT_THREADS = 16
MAX_THREADS = 1024
RETRY_MAX = 8
CHALLENGE_SNIFF = 8192      # JS cookie 挑战页嗅探上限（字节）
CHALLENGE_MAX_SOLVE = 2     # 每下载会话最多自动应答次数（防挑战循环）
CHALLENGE_MAX_WAIT = 5.0    # 挑战页要求的最长礼貌等待（秒）
DEFAULT_STALL_TIMEOUT = 30.0  # 块级无进展看门狗（秒），0 关闭
GLOBAL_ERR_BUDGET = 16      # 连续网络错误达到该数触发全局退避（防请求风暴）
DISK_RESERVE = 16 * 1024 * 1024  # 磁盘空间预检预留

# Chrome 风格 cipher 序列（TLS1.2 及以下可配置部分），
# 用于缓解 JA3/JA4 客户端指纹（完整浏览器指纹需 curl_cffi，见 README）。
CHROME_CIPHERS = (
    "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256:"
    "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
    "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:"
    "ECDHE-RSA-AES128-SHA:ECDHE-RSA-AES256-SHA:AES128-GCM-SHA256:"
    "AES256-GCM-SHA384:AES128-SHA:AES256-SHA"
)

_pwrite_lock = threading.Lock()


class DownloadError(Exception):
    pass


class ThrottleError(Exception):
    """服务器限流/风控信号(429/503/403)，需要全局降速冷却"""


class LinkExpiredError(Exception):
    """直链已过期/签名失效——重试无意义，需用户重新获取直链"""


# =====================================================================
# §2 通用工具
# =====================================================================

def write_at(fd, data, offset):
    if hasattr(os, "pwrite"):
        view = memoryview(data)
        written = 0
        while written < len(view):
            written += os.pwrite(fd, view[written:], offset + written)
    else:
        with _pwrite_lock:
            os.lseek(fd, offset, os.SEEK_SET)
            view = memoryview(data)
            written = 0
            while written < len(view):
                written += os.write(fd, view[written:])


def fmt_size(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}B"
        n /= 1024


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def parse_size(text):
    """'10M'/'1.5G'/'512K'/'1048576' → 字节数"""
    if not text:
        return None
    m = re.fullmatch(r"\s*([0-9]*\.?[0-9]+)\s*([KkMmGg]?)(?:i?B?)?\s*", text)
    if not m:
        raise ValueError(f"无法解析的大小/速率: {text!r}")
    n = float(m.group(1))
    mult = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}[m.group(2).lower()]
    return int(n * mult)


def _ca_file():
    """CA 证书束定位：优先 certifi（Android 打包环境无系统 CA 路径，
    Termux/精简容器同样受益）；未安装则返回 None 走系统默认——
    桌面 Linux/macOS/Windows 行为完全不变。"""
    try:
        import certifi
        return certifi.where()
    except Exception:
        return None


def make_ssl_context(insecure=False):
    ctx = ssl.create_default_context(cafile=_ca_file())
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        ctx.set_ciphers(CHROME_CIPHERS)
    except (ssl.SSLError, ValueError):
        pass
    return ctx


def _tune_socket(conn, rcvbuf=256 * 1024):
    """socket 层性能调优（对齐 aria2/curl 的默认行为）。

    TCP_NODELAY：禁用 Nagle——Range 请求头是小包，Nagle 会引入
    最多 40ms 的合并等待，既拖慢请求也会污染延迟感知的 TTFB 测量。
    SO_RCVBUF：温和调大接收缓冲（高带宽×延迟链路的带宽延迟积），
    失败静默（不同平台支持不一）。
    """
    sock = getattr(conn, "sock", None)
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    try:
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF) < rcvbuf:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, rcvbuf)
    except OSError:
        pass


def open_connection(url, insecure=False, timeout=30, tune=True):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https"):
        raise DownloadError(f"不支持的协议: {u.scheme}")
    host = u.hostname
    if not host:
        raise DownloadError(f"无效URL: {url}")
    if u.scheme == "https":
        conn = http.client.HTTPSConnection(
            host, u.port or 443, timeout=timeout,
            context=make_ssl_context(insecure))
    else:
        conn = http.client.HTTPConnection(host, u.port or 80, timeout=timeout)
    if tune:
        try:
            conn.connect()
            _tune_socket(conn)
        except OSError:
            # 连接失败留给上层统一按网络错误处理（与惰性连接行为一致）
            try:
                conn.close()
            except Exception:
                pass
    path = u.path or "/"
    if u.query:
        path += "?" + u.query
    return conn, path


def http_request(url, method="GET", headers=None, body=None, insecure=False, timeout=30):
    conn, path = open_connection(url, insecure, timeout)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, dict(resp.getheaders()), data
    finally:
        conn.close()


def url_host(url):
    return urllib.parse.urlsplit(url).hostname or ""


def check_disk_space(dirpath, need):
    try:
        free = shutil.disk_usage(str(dirpath)).free
    except OSError:
        return True, 0
    return free >= need + DISK_RESERVE, free


def lock_file(fd, what):
    """输出文件互斥锁：防止两个进程同时写同一文件造成静默损坏。

    压测发现（ST5）：双进程下载不同数据源到同一输出文件时，
    两者可交错写完并各自报告"成功"，产物实为损坏混合体。
    flock 在进程退出/SIGKILL 时由内核自动释放，不影响续传。
    POSIX 平台生效；无 fcntl 的平台（Windows）跳过。
    """
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ValueError):
        raise DownloadError(
            f"{what} 正被另一个 PanBoost 进程下载（文件锁被占用）。"
            f"请等其完成后重试；若确认无其他进程，删除残留的"
            f"锁文件后重试") from None


# =====================================================================
# §3 拟人化层 —— 让流量模式更接近真实浏览器/下载器
# =====================================================================

class PersonaKit:
    """补全浏览器风格请求头（用户显式指定的头永远优先）。

    Accept-Encoding 固定 identity：Range 分段下载必须禁用透明压缩，
    否则 Content-Length 与解压后字节错位会写坏文件。
    """

    CHROME_UA_RE = re.compile(r"Chrome/|Chromium/|Edg/", re.I)
    BASE_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                  "image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "identity",
    }
    CHROME_SEC = {
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
    }

    def __init__(self, enabled=True):
        self.enabled = enabled

    def apply(self, headers):
        if not self.enabled:
            return dict(headers)
        ua = headers.get("User-Agent", DEFAULT_UA)
        out = dict(self.BASE_HEADERS)
        if self.CHROME_UA_RE.search(ua):
            out.update(self.CHROME_SEC)
        out.update(headers)
        return out


class UARotator:
    """进程级 UA 轮换器（线程安全游标，供 worker 在 403 时换 UA）"""

    def __init__(self, initial=None):
        initial = initial or DEFAULT_UA
        try:
            self._idx = UA_POOL.index(initial)
        except ValueError:
            self._idx = 0
        self._lock = threading.Lock()

    def current(self):
        with self._lock:
            return UA_POOL[self._idx]

    def next(self):
        with self._lock:
            self._idx = (self._idx + 1) % len(UA_POOL)
            return UA_POOL[self._idx]


def shuffled_blocks(nblocks, completed):
    """待下载块列表乱序入队：请求顺序不再 0,1,2... 单调递增，
    削弱'机器式顺序扫描'特征（对断点续传无影响：块索引即偏移）。"""
    blocks = [b for b in range(nblocks) if not completed[b]]
    random.shuffle(blocks)
    return blocks


# =====================================================================
# §4 风控层 —— 审计 / 域级记忆 / 三态熔断 / 限速 / 403分类
# =====================================================================

class AuditLog:
    """反风控审计：会话内事件内存聚合 + 追加式 JSONL 文件（--explain 查看摘要）"""

    def __init__(self):
        self.events = []
        self._lock = threading.Lock()

    def log(self, event, **kv):
        rec = {"t": round(time.time(), 3), "event": event}
        rec.update(kv)
        with self._lock:
            self.events.append(rec)
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def explain(self):
        with self._lock:
            evs = list(self.events)
        if not evs:
            print("[风控摘要] 本会话无风控事件，服务器全程友好")
            return
        stat = {}
        for e in evs:
            stat[e["event"]] = stat.get(e["event"], 0) + 1
        cool = sum(e.get("wait") or 0 for e in evs if e["event"] == "throttle")
        parts = [f"{k}×{v}" for k, v in sorted(stat.items())]
        print(f"[风控摘要] {' | '.join(parts)} | 限流冷却累计{cool:.0f}s"
              f" | 明细: {AUDIT_LOG}")

    def has(self, event):
        with self._lock:
            return any(e["event"] == event for e in self.events)


AUDIT = AuditLog()


class HostRiskStore:
    """跨会话域名风控记忆：进程退出后状态不丢失。

    v1.5 起记录三类信息：
    - until/events: 冷却状态（触发风控后的一段时间内低并发起步）
    - cap: AIMD 收敛学习到的该源并发上限——下次运行直接从该值起步，
      不必重新"挨打学习"；上限仍留 2 倍爬升空间，服务器变好可渐进恢复。
    下载成功后冷却清除、cap 更新为本次跑通值。
    """

    def __init__(self, path=RISK_DB):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(self.path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def cooldown_left(self, host):
        if not host:
            return 0.0
        rec = self._load().get(host)
        if not rec:
            return 0.0
        return max(0.0, rec.get("until", 0) - time.time())

    def learned_cap(self, host):
        """返回该域学习到的并发上限（无记录/无效返回 None）"""
        if not host:
            return None
        rec = self._load().get(host)
        if not rec:
            return None
        cap = rec.get("cap")
        try:
            cap = int(cap)
        except (TypeError, ValueError):
            return None
        return cap if cap >= 1 else None

    def note_cap(self, host, cap):
        """AIMD 收敛后写入学习值（限流时的当前并发上限）"""
        if not host or not cap or cap < 1:
            return
        with self._lock:
            data = self._load()
            rec = data.setdefault(host, {"until": 0, "events": 0})
            rec["cap"] = int(cap)
            rec["updated"] = time.time()
            self._save(data)
        AUDIT.log("cap_learned", host=host, cap=int(cap))

    def note_throttle(self, host, wait):
        if not host or not wait or wait <= 0:
            return
        with self._lock:
            data = self._load()
            rec = data.setdefault(host, {"until": 0, "events": 0})
            rec["until"] = max(rec.get("until", 0), time.time() + wait)
            rec["events"] = rec.get("events", 0) + 1
            rec["updated"] = time.time()
            self._save(data)
        AUDIT.log("host_cooldown_saved", host=host, wait=wait)

    def succeed(self, host, cap=None):
        """下载成功：清除冷却记忆（保留并更新并发学习值）。"""
        if not host:
            return
        with self._lock:
            data = self._load()
            rec = data.get(host)
            if rec:
                rec["until"] = 0
                rec["events"] = 0
                if cap and cap >= 1:
                    rec["cap"] = int(cap)
                rec["updated"] = time.time()
                self._save(data)
        AUDIT.log("host_cooldown_cleared", host=host)

    def clear(self, host):
        if not host:
            return
        with self._lock:
            data = self._load()
            if host in data:
                del data[host]
                self._save(data)
        AUDIT.log("host_cooldown_cleared", host=host)


def parse_retry_after(v):
    if not v:
        return None
    v = v.strip()
    if v.isdigit():
        return int(v)
    try:
        import datetime
        from email.utils import parsedate_to_datetime
        d = parsedate_to_datetime(v)
        if d.tzinfo is None:
            d = d.replace(tzinfo=datetime.timezone.utc)
        delta = (d - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
        return max(1, int(delta))
    except Exception:
        return None


LINK_EXPIRED_RE = re.compile(
    r"signature|\bsign\b|expired|expire|过期|失效|已删除|不存在|非法链接|"
    r"link.{0,12}(error|invalid|expired)|fetch.{0,8}error|请登录|"
    r"\blogin\b|\bauth\b|access.?denied.{0,20}url|鉴权",
    re.I)


def classify_forbidden(body_snippet, content_type):
    """区分 403 的两种语义：直链过期/签名失效（重试无意义）vs 风控封禁（可降速恢复）。

    返回 'expired' 或 None。仅当响应体是文本类且命中过期特征词时判定。
    """
    if not body_snippet:
        return None
    ct = (content_type or "").lower()
    if any(x in ct for x in ("image/", "video/", "audio/", "application/octet-stream")):
        return None
    try:
        text = body_snippet[:2048].decode("utf-8", "replace")
    except Exception:
        return None
    if LINK_EXPIRED_RE.search(text):
        return "expired"
    return None


def _cb_scale():
    """冷却时间缩放因子（默认1；测试用 PANBOOST_CB_SCALE=0.01 加速状态机演练）"""
    try:
        return max(0.001, float(os.environ.get("PANBOOST_CB_SCALE", "1") or 1))
    except ValueError:
        return 1.0


# ---- 19. JS Cookie 挑战自动应答（中科大镜像"Verifying"式验证页）----

CHALLENGE_COOKIE_RE = re.compile(
    rb'document\.cookie\s*=\s*"([^=;\s"]+)=([^;"\s]+)')
CHALLENGE_WAIT_RE = re.compile(
    rb'setTimeout\s*\(\s*(?:function\s*\(\s*\)\s*\{|[^,]+?),\s*(\d+)')
CHALLENGE_MARKERS = (b"verifying", b"verification", b"challenge",
                     b"location.reload", b"jschl", b"cf-chl")


def looks_like_cookie_challenge(status, ctype, body_head):
    """识别'验证浏览器'式 JS cookie 挑战页。

    实测样本：中科大镜像对大文件返回 200 + text/html + "Verifying your
    browser"页，页面脚本 document.cookie = "addr=<IP>" 后 setTimeout reload；
    带 cookie 重访即放行 206。判定要求多特征同时命中，避免误伤普通网页：
    状态 200/403/429 + text/html + document.cookie 赋值 + 验证标记词。
    """
    if status not in (200, 403, 429):
        return False
    if "html" not in (ctype or "").lower():
        return False
    if not body_head:
        return False
    if not CHALLENGE_COOKIE_RE.search(body_head):
        return False
    low = body_head.lower()
    return any(m in low for m in CHALLENGE_MARKERS)


def parse_challenge_cookie(body_head):
    """从挑战页脚本提取待设置的 cookie，返回 (name, value) 或 None。

    cookie 值就写在响应里（通常是客户端 IP），无需执行 JS。
    """
    m = CHALLENGE_COOKIE_RE.search(body_head)
    if not m:
        return None
    return (m.group(1).decode("ascii", "replace"),
            m.group(2).decode("ascii", "replace"))


def parse_challenge_wait_ms(body_head):
    """从挑战页 setTimeout 提取服务器要求的等待毫秒数（默认 2000）。"""
    m = CHALLENGE_WAIT_RE.search(body_head)
    return int(m.group(1)) if m else 2000


def merge_cookie_header(headers, name, value):
    """把挑战 cookie 合并进请求头（用户已有 Cookie 永远排在前，保住网盘鉴权态）。"""
    ck = f"{name}={value}"
    existing = headers.get("Cookie")
    headers["Cookie"] = f"{existing}; {ck}" if existing else ck
    return headers


# ---- 20. WAF 拦截页识别（区别于可自动应答的 JS cookie 挑战页）----

WAF_BLOCK_MARKERS = (
    "访问被拦截", "疑似攻击", "请求被拦截",            # 华为云 CloudWAF 等
    "cloudwaf", "waf拦截", "request rejected",
    "blocked by security", "access denied by security",
)


def looks_like_waf_block(status, ctype, body_head):
    """识别 WAF 拦截页（如华为云 CloudWAF 的 418/405 响应）。

    实测样本（2026-10 华为云镜像站）：高并发下载+连接集中中断后，
    后续请求返回 418 + text/html，页面含 <meta Server=CloudWAF>、
    "访问被拦截！/您的请求疑似攻击行为！/事件ID"——纯拦截页，
    没有 document.cookie 挑战可解，只能等待自动解除。
    作为礼貌客户端：明确告知用户等待，绝不尝试绕过。
    """
    if status not in (403, 405, 418, 429, 493, 509):
        return False
    is_html = "html" in (ctype or "").lower()
    if body_head:
        try:
            text = body_head[:4096].decode("utf-8", "replace").lower()
        except Exception:
            text = ""
        if any(m in text for m in WAF_BLOCK_MARKERS):
            return True
    # 418(I'm a teapot) 几乎只有 WAF/反爬在使用；html 响应即可判定
    return status == 418 and is_html


WAF_BLOCK_HINT = ("疑似被网站防火墙拦截(WAF, HTTP {status})。"
                  "通常因高并发/高频访问触发，一般几分钟至几小时自动解除。"
                  "建议稍等后以更低并发重试(如 -t 4 --limit 4M)；"
                  "已下载进度不受影响，解除后重新执行同一命令即可续传")


class RateController:
    """反风控自适应并发控制器（1024线程下依然安全的核心）。

    九要素（v1.3）：
    1. 平滑爬坡   并发上限从8开始每秒翻倍升至目标值，杜绝瞬时连接风暴
    2. 建连限速   令牌桶限制新连接建立速率（默认64/秒）+ 0~80ms 随机抖动
    3. AIMD降速   429/503/403 → 并发上限减半，自动收敛到服务器容忍值
    4. Retry-After合规  严格遵守服务器指定的冷却时间（403同样尊重）
    5. 指数冷却+抖动 无Retry-After时 30s→60s→120s 指数冷却，±10%抖动防惊群
    6. 三态熔断   CLOSED→OPEN(指数冷却30s~1800s)→HALF_OPEN(单请求探测)→…
                  探测成功自动恢复；连续4轮探测失败才最终放弃（借鉴
                  Polly/gobreaker 的 circuit breaker 模式，取代旧的永久死亡）
                  进入 OPEN 的两条路径：403连击超阈值；429/503持续且
                  NO_PROGRESS_OPEN 秒内零成功块（无进展熔断——正常 AIMD
                  收敛时始终有成功块穿插，不会误熔断）
    7. 健康慢恢复  限流事件后并发按+25%/秒缓慢回升，防止二次冲击
    8. 403语义分类 直链过期(签名失效)不占熔断名额，直接提示用户重新获取
    9. 建连抖动    令牌桶通过后随机停顿，削平令牌释放的周期性毛刺
    """

    RAMP_START = 8
    THROTTLE_403_LIMIT = 8      # 403 连击阈值：超过则进入 OPEN 熔断
    NO_PROGRESS_OPEN = 30.0     # 429/503 持续且该时长内零成功块 → OPEN 熔断
    PROBE_FAIL_GIVEUP = 4       # 半开探测连续失败轮数：达到则放弃
    MAX_OPEN_COOLDOWN = 1800.0
    LAT_ALPHA = 2.5             # 延迟感知：EWMA 超基准 α 倍视为服务器拥塞
    LAT_MIN_SAMPLES = 8         # 延迟感知：最少样本数（避免启动期误判）
    LAT_FLOOR = 0.05            # 延迟感知：基准 < 50ms 时噪声大，不判定

    CB_CLOSED = "closed"
    CB_OPEN = "open"
    CB_HALF = "half_open"

    def __init__(self, max_cap, conn_rate=64, quiet=False):
        self.max_cap = max(1, max_cap)
        self.conn_rate = max(1, conn_rate)
        self.quiet = quiet
        self.cap = min(self.RAMP_START, self.max_cap)
        self.active = 0
        self.cooldown_until = 0.0
        self.throttle_events = 0
        self.streak_403 = 0
        self.last_success_ts = time.time()  # 最近一次成功块时间(无进展熔断基准)
        self.give_up = False
        # 熔断状态机
        self.cb_state = self.CB_CLOSED
        self.cb_opens = 0         # 进入 OPEN 的累计次数（决定冷却时长）
        self.probe_fails = 0      # 半开探测连续失败轮数
        self._probe_permits = 0   # HALF 状态下可放行的探测者名额(0/1)
        self._cond = threading.Condition()
        self._pace_lock = threading.Lock()
        self._conn_times = []
        # 延迟感知（Vegas 式预防性降载）：TTFB 是服务器拥塞的先行指标
        self._lat_ewma = 0.0
        self._lat_min = float("inf")
        self._lat_samples = 0
        self._last_lat_adjust = 0.0

    # ---- 建连令牌桶 + 抖动 ----
    def _pace(self):
        while True:
            with self._pace_lock:
                now = time.time()
                while self._conn_times and now - self._conn_times[0] >= 1.0:
                    self._conn_times.pop(0)
                if len(self._conn_times) < self.conn_rate:
                    self._conn_times.append(now)
                    break
                wait = 1.0 - (now - self._conn_times[0]) + 0.02
            time.sleep(min(max(wait, 0.01), 1.0))
        time.sleep(random.uniform(0.0, 0.08))  # 拟人化建连抖动

    # ---- 并发名额获取：返回 True 表示本次为半开探测者 ----
    def acquire(self):
        self._pace()
        with self._cond:
            while True:
                if self.give_up:
                    raise ThrottleError("give_up")
                now = time.time()
                if self.cb_state == self.CB_OPEN:
                    if now >= self.cooldown_until:
                        self.cb_state = self.CB_HALF
                        self._probe_permits = 1
                        AUDIT.log("cb_half_open", opens=self.cb_opens)
                        continue
                    self._cond.wait(
                        timeout=min(self.cooldown_until - now, 5) + 0.05)
                    continue
                if self.cb_state == self.CB_HALF:
                    if self._probe_permits > 0:
                        self._probe_permits -= 1
                        self.active += 1
                        return True
                    self._cond.wait(timeout=1.0)
                    continue
                if self.active < self.cap:
                    self.active += 1
                    return False
                self._cond.wait(timeout=1.0)

    def release(self, probe_ok=None):
        with self._cond:
            self.active -= 1
            if probe_ok:
                # 半开探测成功 → 恢复 CLOSED，历史衰减
                self.cb_state = self.CB_CLOSED
                self.cb_opens = max(0, self.cb_opens - 1)
                self.probe_fails = 0
                self.streak_403 = 0
                self.throttle_events = max(0, self.throttle_events - 1)
                AUDIT.log("cb_recovered", cap=self.cap)
            self._cond.notify_all()

    def ramp_tick(self):
        with self._cond:
            now = time.time()
            if self.cooldown_until > now:
                return
            if self._latency_congested():
                # 延迟拥塞：温和降载（每秒 -10%）并暂停爬坡，
                # 避免继续加压直到服务器吐 429——防患于未然
                if self.cap > 1 and now - self._last_lat_adjust >= 1.0:
                    self._last_lat_adjust = now
                    self.cap = max(1, int(self.cap * 0.9))
                    AUDIT.log("latency_backoff", cap=self.cap,
                              ewma=round(self._lat_ewma, 3),
                              base=round(self._lat_min, 3))
                self._cond.notify_all()
                return
            if self.cap >= self.max_cap:
                return
            if self.throttle_events:
                self.cap = min(self.max_cap, int(self.cap * 1.25) + 1)
            else:
                self.cap = min(self.max_cap, self.cap * 2)
            self._cond.notify_all()

    def note_success(self):
        self.streak_403 = 0
        self.last_success_ts = time.time()

    def note_latency(self, seconds):
        """worker 上报一次首字节耗时（TTFB，复用连接=纯服务器排队+处理延迟）。

        延迟感知防封禁：429/403 是"已触发风控"的滞后信号；响应延迟
        抬升是服务器拥塞的先行指标。EWMA 相对会话基准抬升超过 α 倍
        即视为拥塞，ramp_tick 温和降载——把降速时机从"被拒之后"
        提前到"服务器吃力之时"，显著降低触发封禁的概率。
        """
        if seconds <= 0:
            return
        with self._cond:
            self._lat_samples += 1
            if self._lat_samples == 1:
                self._lat_ewma = seconds
            else:
                self._lat_ewma = self._lat_ewma * 0.7 + seconds * 0.3
            if self._lat_ewma < self._lat_min:
                self._lat_min = self._lat_ewma

    def _latency_congested(self):
        return (self._lat_samples >= self.LAT_MIN_SAMPLES
                and self._lat_min >= self.LAT_FLOOR
                and self._lat_ewma > self.LAT_ALPHA * self._lat_min)

    def clamp_cap(self, v):
        """域级学习值应用：当前上限与爬坡目标同时收敛到学习值附近。

        max_cap 保留 2 倍学习值的爬升空间——服务器状态变好时仍可渐进恢复。
        """
        with self._cond:
            v = max(1, min(int(v), self.max_cap))
            self.cap = min(self.cap, v)
            self.max_cap = max(1, min(self.max_cap, v * 2))
            self._cond.notify_all()

    def _open_cooldown(self):
        return min(30.0 * (2 ** max(0, self.cb_opens - 1)),
                   self.MAX_OPEN_COOLDOWN) * _cb_scale()

    def on_throttle(self, status, retry_after=None, probe=False):
        """记录一次限流/风控事件并降速。

        probe=True 表示本事件来自半开探测请求（探测失败 → 重新 OPEN）。
        返回 (旧cap, 新cap, 冷却秒数)。
        """
        with self._cond:
            self.throttle_events += 1
            old_cap = self.cap
            self.cap = max(1, self.cap // 2)
            now = time.time()
            if probe:
                # 半开探测失败：回到 OPEN，冷却翻倍
                self.cb_state = self.CB_OPEN
                self.cb_opens += 1
                self.probe_fails += 1
                if self.probe_fails >= self.PROBE_FAIL_GIVEUP:
                    self.give_up = True
                    self._cond.notify_all()
                    return old_cap, self.cap, None
                wait = self._open_cooldown()
            elif status == 403:
                self.streak_403 += 1
                if self.streak_403 > self.THROTTLE_403_LIMIT:
                    # 连击超阈值：进入 OPEN 熔断（不再永久死亡，半开自动探测恢复）
                    self.cb_state = self.CB_OPEN
                    self.cb_opens += 1
                    AUDIT.log("cb_open", streak=self.streak_403)
                    wait = self._open_cooldown()
                elif retry_after and retry_after > 0:
                    wait = min(float(retry_after), 300.0)
                else:
                    wait = 5.0 * _cb_scale()
            elif status in (429, 503):
                # 无进展熔断：持续限流且长时间零成功块，说明服务器已明确
                # 拒绝服务（而非并发撞墙——撞墙时始终有成功块穿插）。
                # 进入 OPEN 走半开探测→连续失败→放弃的有界退出路径，
                # 杜绝对永久 429 的无限重试挂死
                if now - self.last_success_ts >= self.NO_PROGRESS_OPEN \
                        * _cb_scale():
                    self.cb_state = self.CB_OPEN
                    self.cb_opens += 1
                    AUDIT.log("cb_open", reason="429_no_progress",
                              idle=round(now - self.last_success_ts, 1))
                    wait = self._open_cooldown()
                elif retry_after and retry_after > 0:
                    wait = min(float(retry_after), 1800.0)
                else:
                    wait = min(30.0 * (2 ** min(self.throttle_events, 5)),
                               900.0) * _cb_scale()
            else:
                wait = 5.0 * _cb_scale()
            self.cooldown_until = max(self.cooldown_until,
                                      now + wait * random.uniform(0.9, 1.1))
            self._cond.notify_all()
            return old_cap, self.cap, wait

    def state_desc(self):
        with self._cond:
            now = time.time()
            s = f"cap={self.cap}/{self.max_cap}"
            if self.cb_state == self.CB_OPEN:
                s += f" 熔断冷却{max(0, self.cooldown_until - now):.0f}s"
            elif self.cb_state == self.CB_HALF:
                s += " 半开探测中"
            elif self.cooldown_until > now:
                s += f" 冷却{self.cooldown_until - now:.0f}s"
            return s


class SpeedLimiter:
    """全局字节率整形（所有 worker 共享的令牌桶，--limit 启用）。

    用途：削平'瞬间打满带宽'的流量突刺特征，或与他人共享带宽时保持礼貌。
    """

    def __init__(self, bytes_per_sec):
        self.rate = max(1, int(bytes_per_sec))
        self.tokens = float(self.rate)
        self.ts = time.monotonic()
        self.lock = threading.Lock()

    def consume(self, n):
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.rate,
                                  self.tokens + (now - self.ts) * self.rate)
                self.ts = now
                if self.tokens >= n:
                    self.tokens -= n
                    return
                need = (n - self.tokens) / self.rate
            time.sleep(min(need, 1.0))


# =====================================================================
# §5 探测层
# =====================================================================

class Probe:
    def __init__(self):
        self.final_url = ""
        self.size = None
        self.range_ok = False
        self.etag = None
        self.last_modified = None
        self.filename = None
        self.headers = {}
        self.challenge_cookie = None


def filename_from_disposition(cd):
    if not cd:
        return None
    m = re.search(r"filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)", cd)
    if m:
        return urllib.parse.unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"([^"]+)"', cd)
    if m:
        return m.group(1)
    m = re.search(r"filename\s*=\s*([^;]+)", cd)
    if m:
        return urllib.parse.unquote(m.group(1).strip())
    return None


def filename_from_url(url):
    path = urllib.parse.urlsplit(url).path
    name = os.path.basename(urllib.parse.unquote(path))
    return re.sub(r'[\\/:*?"<>|]', "_", name) if name else None


def probe_url(url, headers, insecure=False, timeout=30):
    p = Probe()
    final = url
    resp = None
    redirects = 0
    chal_tries = 0
    transient = 0       # 瞬时限流(429/503)重试计数
    while True:
        conn, path = open_connection(final, insecure, timeout)
        try:
            conn.request("GET", path, headers={**headers, "Range": "bytes=0-0"})
            resp = conn.getresponse()
            if resp.status in (301, 302, 303, 307, 308):
                redirects += 1
                if redirects > MAX_REDIRECTS:
                    raise DownloadError("重定向次数过多")
                loc = resp.getheader("Location")
                resp.read()
                if not loc:
                    raise DownloadError("重定向缺少 Location")
                final = urllib.parse.urljoin(final, loc)
                continue
            ctype = resp.getheader("Content-Type") or ""
            body_head = b""
            if resp.status in (200, 403, 429) and "html" in ctype.lower():
                body_head = resp.read(CHALLENGE_SNIFF)
                if looks_like_cookie_challenge(resp.status, ctype, body_head):
                    ck = parse_challenge_cookie(body_head)
                    if chal_tries < 1 and ck:
                        chal_tries += 1
                        p.challenge_cookie = ck
                        wait = min(parse_challenge_wait_ms(body_head) / 1000.0
                                   + random.uniform(0.1, 0.4),
                                   CHALLENGE_MAX_WAIT)
                        time.sleep(wait)
                        headers = merge_cookie_header({**headers}, ck[0], ck[1])
                        AUDIT.log("challenge_solved", stage="probe",
                                  cookie=ck[0], wait=round(wait, 2))
                        continue
                    raise DownloadError(
                        "服务器要求浏览器验证(JS cookie挑战)，自动应答未成功——"
                        "请用浏览器打开链接通过验证后重试")
            if resp.status not in (200, 206, 416) and not body_head:
                body_head = resp.read(CHALLENGE_SNIFF)
            if resp.status not in (200, 206, 416) \
                    and looks_like_waf_block(resp.status, ctype, body_head):
                AUDIT.log("waf_block", stage="probe", status=resp.status)
                raise DownloadError(WAF_BLOCK_HINT.format(status=resp.status))
            if resp.status in (429, 503):
                # 瞬时限流重试（压测 ST1 发现）：探测期撞上服务器瞬时
                # 429/503 就放弃过于脆弱——带退避重试，遵守 Retry-After
                transient += 1
                if transient > PROBE_TRANSIENT_RETRIES:
                    raise DownloadError(
                        f"服务器持续限流({resp.status})，"
                        f"已重试{transient - 1}次——请稍后再试")
                ra = parse_retry_after(resp.getheader("Retry-After"))
                wait = min(float(ra), 60.0) if ra else \
                    min(2.0 ** transient, 10.0)
                wait *= random.uniform(0.9, 1.2)
                AUDIT.log("probe_transient", status=resp.status,
                          retry=transient, wait=round(wait, 1))
                time.sleep(wait)
                continue
            resp.read(1)
            break
        finally:
            conn.close()
    if resp is None:
        raise DownloadError("无法建立连接")
    p.final_url = final
    p.headers = {k.lower(): v for k, v in resp.getheaders()}
    p.etag = resp.getheader("ETag")
    p.last_modified = resp.getheader("Last-Modified")
    p.filename = filename_from_disposition(resp.getheader("Content-Disposition"))
    if resp.status == 206:
        p.range_ok = True
        cr = resp.getheader("Content-Range") or ""
        m = re.search(r"/(\d+)\s*$", cr)
        if m:
            p.size = int(m.group(1))
    elif resp.status == 200:
        cl = resp.getheader("Content-Length")
        if cl and cl.isdigit():
            p.size = int(cl)
    elif resp.status == 416:
        cr = resp.getheader("Content-Range") or ""
        m = re.search(r"\*/(\d+)\s*$", cr)
        if m and int(m.group(1)) == 0:
            p.size = 0
            p.range_ok = True
        else:
            raise DownloadError(f"服务器返回异常状态码 {resp.status}")
    elif resp.status in (401, 403):
        raise DownloadError(f"服务器拒绝访问({resp.status})：Cookie/登录态可能缺失或已过期")
    else:
        raise DownloadError(f"服务器返回异常状态码 {resp.status}")
    if not p.filename:
        p.filename = filename_from_url(final)
    return p


# =====================================================================
# §6 调优（--auto 自动选线程数）
# =====================================================================

def _speed_probe(url, headers, insecure, connections, seconds, size):
    """并发 connections 条连接各下载 seconds 秒，返回总吞吐 B/s"""
    results = [0] * connections

    def one(i):
        conn = None
        try:
            offset = min(i * 4 * 1024 * 1024, max(0, size - 1024 * 1024))
            end = min(offset + 32 * 1024 * 1024, size - 1)
            conn, path = open_connection(url, insecure, 15)
            conn.request("GET", path, headers={
                **headers, "Range": f"bytes={offset}-{end}"})
            resp = conn.getresponse()
            deadline = time.time() + seconds
            while time.time() < deadline:
                c = resp.read(64 * 1024)
                if not c:
                    break
                results[i] += len(c)
        except Exception:
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    ts = [threading.Thread(target=one, args=(i,), daemon=True)
          for i in range(connections)]
    t0 = time.time()
    for t in ts:
        t.start()
    for t in ts:
        t.join(seconds + 15)
    return sum(results) / max(time.time() - t0, 0.001)


def auto_tune(url, headers, insecure, size, quiet=False):
    """实测单连接与16并发吞吐，推荐线程数 = 并发吞吐 / 单连接吞吐"""
    if not quiet:
        print("[调优] 实测服务器限速特征：1 连接 / 16 连接 ...")
    v1 = _speed_probe(url, headers, insecure, 1, 2.0, size)
    v16 = _speed_probe(url, headers, insecure, 16, 2.5, size)
    if v1 <= 0 or v16 <= 0:
        n = DEFAULT_THREADS
    else:
        n = int(round(v16 / v1))
    n = max(1, min(n, 512))
    if not quiet:
        print(f"[调优] 单连接 {fmt_size(v1)}/s | 16并发 {fmt_size(v16)}/s "
              f"| 有效并发≈{max(1, round(v16 / max(v1, 1)))} → 采用 {n} 线程")
    return n


# =====================================================================
# §7 下载引擎
# =====================================================================

class _WriteBuffer:
    """worker 级顺序写盘缓冲：把连续的 256KB chunk 聚合成大 pwrite。

    cProfile 实测（32线程/500MB）：posix.pwrite 2048 次占写路径大头；
    聚合到 1MB 后系统调用次数 /4，页缓存更友好，_count_lock 争抢同频下降。

    崩溃一致性语义：flush() 先落盘、后由调用方更新 parts 记账——
    保证 ctrl v3 记录的块内偏移之前的数据必然已在盘上（SIGKILL 安全）。
    """

    __slots__ = ("fd", "parts", "base", "size")

    def __init__(self):
        self.fd = None
        self.parts = []      # list[bytes]，避免反复 bytes 拼接
        self.base = -1       # 缓冲区起始文件偏移
        self.size = 0

    def bind(self, fd):
        self.fd = fd

    def write(self, data, offset):
        """写入一段数据；offset 连续时聚合，跳变（防御路径）时先刷。

        注意：这里不做"缓冲满自动刷"——flush 必须由调用方经
        _flush_buf 触发以同步记账（_block_got/parts），否则裸落盘
        会让中途断点丢失记账，重试将整块重来。
        """
        if self.parts and offset != self.base + self.size:
            self.flush()
        if not self.parts:
            self.base = offset
        self.parts.append(data)
        self.size += len(data)

    def flush(self):
        """把缓冲一次性 pwrite 到盘上，返回本次落盘的 (起始偏移, 字节数)。"""
        if not self.parts or self.fd is None:
            self.parts.clear()
            self.size = 0
            return self.base, 0
        data = b"".join(self.parts)
        write_at(self.fd, data, self.base)
        off, n = self.base, len(data)
        self.parts.clear()
        self.size = 0
        return off, n

    def drop(self):
        """放弃未落盘缓冲（保留给调用方防御场景，正常路径不使用）。"""
        self.parts.clear()
        self.size = 0


class _WorkerCtx:
    """单个 worker 线程的私有状态：连接 / 当前UA / 连接寿命 / 探测标记 / 心跳 / 写缓冲"""

    def __init__(self, dl):
        self.dl = dl
        self.conn = None
        self.path = None
        self.ua = dl.headers.get("User-Agent", DEFAULT_UA)
        self.ua_tries = 0
        self.blocks_served = 0
        self.bytes_served = 0
        self.probe = False
        self.block_ok = False
        self.last_progress = 0.0   # 最近一次数据进展时刻（看门狗依据）
        self.stalled = False       # 被看门狗强制击杀标记
        self.buf = _WriteBuffer()

    def ensure_conn(self):
        if self.conn is None:
            self.conn, self.path = open_connection(
                self.dl._final_url, self.dl.insecure, self.dl.timeout)

    def recycle(self):
        if self.conn is not None:
            try:
                self.conn.close()
            except Exception:
                pass
        self.conn = None

    def maybe_recycle(self):
        # 字节感知连接寿命：小块场景（512KB×6=3MB）频繁重建连接，
        # HTTPS 握手+TCP慢启动开销大——服务满 32MB 才换（拟人化语义
        # 保留：浏览器单连接也就是下载几十 MB），24 块硬上限防极小块
        # 无限复用
        if (self.bytes_served >= CONN_MIN_BYTES
                and self.blocks_served >= MAX_BLOCKS_PER_CONN) \
                or self.blocks_served >= CONN_MAX_BLOCKS:
            self.recycle()


class MultiThreadDownloader:
    """动态分块 + 工作窃取式线程池 + keep-alive 连接复用。

    文件被切成远多于线程数的小块，放入共享队列；worker 线程持有一条
    持久连接反复取块下载。快连接自然多拿块、慢连接少拿块，彻底消除
    "一个慢分片拖住整个下载"的长尾问题。

    v1.3：块乱序入队 / 连接寿命限制 / UA 轮换 / 三态熔断 /
    拟人化请求头 / 全局限速 / 直链过期分类。
    """

    def __init__(self, url, output, threads=DEFAULT_THREADS, headers=None,
                 insecure=False, timeout=30, retry=RETRY_MAX, quiet=False,
                 min_piece=MIN_PIECE, conn_rate=64, limit=None,
                 persona=True, host=None, stall_timeout=DEFAULT_STALL_TIMEOUT):
        self.url = url
        self.output = Path(output)
        self.threads = threads
        self.headers = headers or {}
        self.insecure = insecure
        self.timeout = timeout
        self.retry = retry
        self.quiet = quiet
        self.min_piece = min_piece
        self.stall_timeout = max(0.0, stall_timeout)
        self.rate = RateController(threads, conn_rate, quiet)
        self.limiter = SpeedLimiter(limit) if limit else None
        self.persona = PersonaKit(enabled=persona)
        self.rotator = UARotator(self.headers.get("User-Agent"))
        self.risk = HostRiskStore()
        self.host = host or url_host(url)
        self.ctrl_path = Path(str(self.output) + CTRL_SUFFIX)
        self.stop_event = threading.Event()
        self.done_bytes = 0
        self.start_time = 0.0
        self.speed = 0.0
        self.size = 0
        self.fd = None
        self.block_size = 0
        self.nblocks = 0
        self.completed = bytearray()
        self.queue = None
        self.errors = []
        self.workers = 0
        self._ctrl_lock = threading.Lock()
        self._count_lock = threading.Lock()
        self._etag = None
        self._last_modified = None
        self.challenge_cookies = {}
        self._chal_solved = 0
        self._chal_lock = threading.Lock()
        self._block_got = {}       # 块内断点：bidx -> 已下载字节（块完成前有效）
        self._ctrl_dirty = True    # 进度脏标记（首次保存 + 变化时置位）
        self._net_errs = 0         # 全局连续网络错误计数（防请求风暴）
        self._ctxs = []            # 活跃 worker 注册表（看门狗扫描）
        self._ctx_lock = threading.Lock()

    def ctrl_data(self):
        with self._count_lock:
            parts = {str(k): v for k, v in self._block_got.items() if v > 0}
        return {
            "version": 3,
            "url": self.url,
            "size": self.size,
            "etag": self._etag,
            "last_modified": self._last_modified,
            "block_size": self.block_size,
            "done_hex": bytes(self.completed).hex(),
            "parts": parts,
        }

    def save_ctrl(self):
        with self._ctrl_lock:
            # 崩溃一致性：先 flush 数据页再写进度文件，
            # 保证 completed 标记不超前于盘上实际数据
            if self.fd is not None \
                    and not os.environ.get("PANBOOST_NO_FSYNC"):
                try:
                    os.fsync(self.fd)
                except OSError:
                    pass
            tmp = str(self.ctrl_path) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.ctrl_data(), f)
            os.replace(tmp, self.ctrl_path)

    def _blocks_match(self, data):
        if data.get("size") != self.size:
            return False
        if data.get("block_size") != self.block_size:
            return False
        if self._etag and data.get("etag") and self._etag != data["etag"]:
            return False
        if self._last_modified and data.get("last_modified") \
                and self._last_modified != data["last_modified"]:
            return False
        return True

    def _load_ctrl_v1(self, pieces):
        for s, e, d in pieces:
            if d < e - s + 1:
                continue
            b0 = s // self.block_size
            b1 = min(e // self.block_size, self.nblocks - 1)
            for b in range(b0, b1 + 1):
                bs = b * self.block_size
                be = min(bs + self.block_size, self.size) - 1
                if bs >= s and be <= e:
                    self.completed[b] = 1

    def load_ctrl(self):
        if not self.ctrl_path.exists():
            return
        try:
            data = json.loads(self.ctrl_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if data.get("version") in (2, 3):
            if not self._blocks_match(data):
                return
            try:
                raw = bytearray.fromhex(data.get("done_hex", ""))
            except ValueError:
                return
            if len(raw) == self.nblocks:
                self.completed = raw
            if data.get("version") == 3:
                for k, v in (data.get("parts") or {}).items():
                    try:
                        b, g = int(k), int(v)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= b < self.nblocks and not self.completed[b] \
                            and 0 < g < self._block_len(b):
                        self._block_got[b] = g
        elif data.get("version") == 1:
            if data.get("size") != self.size:
                return
            if self._etag and data.get("etag") and self._etag != data["etag"]:
                return
            self._load_ctrl_v1(data.get("pieces", []))

    def _block_len(self, b):
        return min((b + 1) * self.block_size, self.size) - b * self.block_size

    def prepare(self, probe=None):
        if probe is None:
            probe = probe_url(self.url, self.headers, self.insecure, self.timeout)
        p = probe
        if p.size is None:
            raise DownloadError("无法获取文件大小（无 Content-Length/Content-Range）")
        self.size = p.size
        self._etag = p.etag
        self._last_modified = p.last_modified
        if not p.range_ok:
            raise DownloadError("服务器不支持 Range 分段下载，请使用 --single 模式")
        if self.size == 0:
            self.nblocks = 0
            self.completed = bytearray()
            if not self.output.exists():
                self.output.parent.mkdir(parents=True, exist_ok=True)
                self.output.touch()
            return False
        target = (self.size + self.threads * BLOCKS_PER_WORKER - 1) \
            // (self.threads * BLOCKS_PER_WORKER)
        self.block_size = min(max(target, self.min_piece), MAX_PIECE)
        self.nblocks = (self.size + self.block_size - 1) // self.block_size
        self.completed = bytearray(self.nblocks)
        self.load_ctrl()
        self.queue = _queue.Queue()
        for b in shuffled_blocks(self.nblocks, self.completed):
            self.queue.put(b)
        with self._count_lock:
            self.done_bytes = sum(self._block_len(b) for b in range(self.nblocks)
                                  if self.completed[b])
            self.done_bytes += sum(self._block_got.values())
        if self.done_bytes >= self.size:
            return False
        self.output.parent.mkdir(parents=True, exist_ok=True)
        ok, free = check_disk_space(self.output.parent, self.size)
        if not ok:
            raise DownloadError(
                f"磁盘空间不足：需要 {fmt_size(self.size)}"
                f"（另有预留），可用 {fmt_size(free)}")
        self.fd = os.open(str(self.output), os.O_RDWR | os.O_CREAT, 0o644)
        lock_file(self.fd, str(self.output))
        if os.fstat(self.fd).st_size != self.size:
            os.ftruncate(self.fd, self.size)
        return True

    # ---- worker 主循环：取块 → _download_block（含重试/风控处理） ----
    def _worker(self):
        ctx = _WorkerCtx(self)
        ctx.buf.bind(self.fd)
        with self._ctx_lock:
            self._ctxs.append(ctx)
        try:
            while not self.stop_event.is_set():
                try:
                    bidx = self.queue.get_nowait()
                except _queue.Empty:
                    return
                self._download_block(bidx, ctx)
                if self.stop_event.is_set():
                    return
        finally:
            with self._ctx_lock:
                try:
                    self._ctxs.remove(ctx)
                except ValueError:
                    pass
            ctx.recycle()

    def _download_block(self, bidx, ctx):
        start = bidx * self.block_size
        end = min(start + self.block_size, self.size) - 1
        length = end - start + 1
        attempt = 0
        done = False
        while not done and not self.stop_event.is_set() \
                and attempt <= self.retry:
            try:
                ctx.probe = self.rate.acquire()
                ctx.block_ok = False
                try:
                    done = self._fetch_block(bidx, start, end, length, ctx)
                finally:
                    self.rate.release(
                        probe_ok=ctx.probe if ctx.block_ok else None)
            except LinkExpiredError as e:
                self.errors.append(f"块{bidx}: {e}")
                self.stop_event.set()
                break
            except ThrottleError as e:
                if self.rate.give_up:
                    self.errors.append(
                        f"块{bidx}: 多轮自动探测恢复均失败（{e}）。"
                        f"若直链已过期请重新获取；若为封禁请更换网络或稍后再试。"
                        f"进度已保存，重新执行同一命令即可续传")
                    self.stop_event.set()
                    break
                time.sleep(random.uniform(0.05, 0.3))
                continue
            except Exception as e:
                ctx.recycle()
                if self.stop_event.is_set() or str(e) == "stopped":
                    break
                attempt += 1
                # 全局网络错误预算：服务器半死时各 worker 独立重试会形成
                # 请求风暴；连续错误累计到阈值时全体退避（防打崩服务器
                # 也防自我放大），成功一块即清零
                with self._count_lock:
                    self._net_errs += 1
                    net_errs = self._net_errs
                if net_errs % GLOBAL_ERR_BUDGET == 0:
                    n = net_errs // GLOBAL_ERR_BUDGET
                    pause = min(1.0 * (2 ** (n - 1)), 10.0) \
                        * random.uniform(0.8, 1.2)
                    AUDIT.log("net_err_backoff", errs=net_errs,
                              pause=round(pause, 1))
                    time.sleep(pause)
                if attempt > self.retry:
                    self.errors.append(f"块{bidx}: {type(e).__name__}: {e}")
                    self.stop_event.set()
                    break
                time.sleep(min(0.5 * (2 ** (attempt - 1)), 15)
                           * random.uniform(0.7, 1.3))
        if done:
            self.completed[bidx] = 1
            with self._count_lock:
                self._block_got.pop(bidx, None)
                self._ctrl_dirty = True
        else:
            self.queue.put(bidx)

    def _fetch_block(self, bidx, start, end, length, ctx):
        """发起一次块请求并完整落盘（支持块内断点续传）。返回 True 表示成功。

        重试时从块内已下载偏移继续（Range: start+got0），
        大块场景不再整块重来——与看门狗配合：僵尸连接被杀后从断点续传。
        """
        ctx.ensure_conn()
        ctx.last_progress = time.time()
        with self._count_lock:
            got0 = self._block_got.get(bidx, 0)
        req = {**self.headers, "User-Agent": ctx.ua,
               "Range": f"bytes={start + got0}-{end}"}
        req = self.persona.apply(req)
        self._apply_challenge_cookie(req)
        t_ttfb = time.time()
        ctx.conn.request("GET", ctx.path, headers=req)
        resp = ctx.conn.getresponse()
        if resp.status == 206:
            # TTFB（复用连接时≈纯服务器处理+排队延迟）→ 延迟感知降载
            self.rate.note_latency(time.time() - t_ttfb)
        if resp.status in (429, 503, 403):
            self._handle_throttle(bidx, resp, ctx)
            return False
        if resp.status == 200 and "html" in \
                (resp.getheader("Content-Type") or "").lower():
            if self._solve_challenge(bidx, resp):
                return False
        if resp.status != 206:
            ctype = resp.getheader("Content-Type") or ""
            head = resp.read(2048) if "html" in ctype.lower() else b""
            if looks_like_waf_block(resp.status, ctype, head):
                AUDIT.log("waf_block", stage="worker", status=resp.status)
                raise DownloadError(
                    f"块{bidx} " + WAF_BLOCK_HINT.format(status=resp.status))
            raise DownloadError(f"块{bidx} 期望206，得到 {resp.status}")
        cr = (resp.getheader("Content-Range") or "").strip()
        m = re.match(r"bytes\s+(\d+)-(\d+)/(\d+|\*)", cr)
        if not m:
            raise DownloadError(f"块{bidx} 缺少Content-Range: {cr!r}")
        s0, e0, t0 = int(m.group(1)), int(m.group(2)), m.group(3)
        if s0 != start + got0 or e0 != end \
                or (t0 != "*" and int(t0) != self.size):
            raise DownloadError(
                f"块{bidx} Content-Range 错位: {cr} "
                f"(期望 bytes {start + got0}-{end}/{self.size})")
        off = start + got0
        got = got0
        try:
            while True:
                if self.stop_event.is_set():
                    raise DownloadError("stopped")
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                ctx.last_progress = time.time()
                if self.limiter is not None:
                    self.limiter.consume(len(chunk))
                    # 限速等待不算 stall：数据已到手，只是在礼貌排队
                    ctx.last_progress = time.time()
                # 写缓冲聚合：连续 chunk 攒到 ~1MB 再 pwrite（/4 系统调用），
                # parts 记账推迟到 flush——保证 ctrl 记录偏移之前的数据已落盘
                ctx.buf.write(chunk, off)
                off += len(chunk)
                got += len(chunk)
                if ctx.buf.size >= WRITE_BUF:
                    self._flush_buf(bidx, start, ctx)
                if got >= length:
                    break
        finally:
            # 所有出口统一结算：块完成 / 截断 / 网络异常 / 用户中断，
            # 已收字节一律落盘并记账——重试与续传才能从断点开始，
            # 而不是整块重来（空缓冲时 no-op）
            self._flush_buf(bidx, start, ctx)
        if got < length:
            raise DownloadError(f"块{bidx} 提前结束({got}/{length})")
        ctx.block_ok = True
        ctx.blocks_served += 1
        ctx.bytes_served += length
        ctx.maybe_recycle()
        with self._count_lock:
            self._net_errs = 0
        self.rate.note_success()
        return True

    def _flush_buf(self, bidx, start, ctx):
        """落盘 worker 缓冲并结算进度（块内断点 parts + 总进度 + ctrl 脏标记）。"""
        off, n = ctx.buf.flush()
        if n <= 0:
            return
        with self._count_lock:
            self.done_bytes += n
            self._block_got[bidx] = off + n - start
            self._ctrl_dirty = True

    def _apply_challenge_cookie(self, req):
        if not self.challenge_cookies:
            return
        ck = "; ".join(f"{k}={v}" for k, v in self.challenge_cookies.items())
        existing = req.get("Cookie")
        req["Cookie"] = f"{existing}; {ck}" if existing else ck

    def _solve_challenge(self, bidx, resp):
        """worker 收到 200+text/html（本应是 206+octet-stream）时的挑战应答。

        解析挑战页脚本里的 cookie 设置语句，存入会话级 cookie，
        按服务器要求的时长礼貌等待后由 worker 循环自动重试。
        返回 True 表示已应答可重试；False 表示不是挑战页（走错误路径）。
        """
        try:
            body_head = resp.read(CHALLENGE_SNIFF)
        except Exception:
            body_head = b""
        ctx = resp.getheader("Content-Type") or ""
        if not looks_like_cookie_challenge(resp.status, ctx, body_head):
            return False
        ck = parse_challenge_cookie(body_head)
        with self._chal_lock:
            solved = self._chal_solved
            if ck and solved < CHALLENGE_MAX_SOLVE:
                self._chal_solved = solved + 1
                self.challenge_cookies[ck[0]] = ck[1]
        if ck and solved < CHALLENGE_MAX_SOLVE:
            wait = min(parse_challenge_wait_ms(body_head) / 1000.0
                       + random.uniform(0.1, 0.4), CHALLENGE_MAX_WAIT)
            time.sleep(wait)
            AUDIT.log("challenge_solved", stage="worker", block=bidx,
                      cookie=ck[0], wait=round(wait, 2))
            return True
        raise DownloadError(
            f"块{bidx} 服务器要求浏览器验证(JS cookie挑战)，"
            f"自动应答已达上限({CHALLENGE_MAX_SOLVE}次)仍未通过——"
            f"请用浏览器打开链接通过验证后，重新执行本命令续传")

    def _handle_throttle(self, bidx, resp, ctx):
        """统一处理 429/503/403：读体 → 403分类 → UA轮换 → AIMD/熔断。

        结束时必然 raise（ThrottleError / LinkExpiredError）。
        """
        status = resp.status
        ra = parse_retry_after(resp.getheader("Retry-After"))
        body = b""
        try:
            body = resp.read(4096)
        except Exception:
            pass
        ctx.recycle()
        if status == 403:
            why = classify_forbidden(body, resp.getheader("Content-Type"))
            if why == "expired":
                AUDIT.log("link_expired", block=bidx, host=self.host)
                raise LinkExpiredError(
                    "403 直链已过期/签名失效（服务器返回过期特征）。"
                    "请到网盘重新获取直链后再续传，进度已保存")
        ua_switched = None
        if status == 403 and ctx.ua_tries < MAX_UA_SWITCHES_PER_BLOCK:
            ctx.ua_tries += 1
            ctx.ua = self.rotator.next()
            ua_switched = ctx.ua
            AUDIT.log("ua_switch", block=bidx, ua=ctx.ua)
        old_cap, new_cap, wait = self.rate.on_throttle(
            status, ra, probe=ctx.probe)
        self.risk.note_throttle(self.host, wait or 30)
        self.risk.note_cap(self.host, new_cap)
        AUDIT.log("throttle", status=status, cap=f"{old_cap}->{new_cap}",
                  wait=wait, probe=ctx.probe, ua_switch=ua_switched)
        raise ThrottleError(
            f"{status} 限流，并发{old_cap}→{new_cap}"
            f"{f'，冷却{wait:.0f}s' if wait else ''}"
            f"{f'(Retry-After={ra}s)' if ra else ''}"
            f"{f'，已切换UA' if ua_switched else ''}")

    def _watchdog(self, now):
        """块级无进展看门狗：僵尸连接（服务器/中间设备静默丢包，
        read 永久阻塞但 socket 未超时）强制 shutdown 击杀。

        被杀 worker 走异常重试路径，配合块内续传从断点继续。
        """
        with self._ctx_lock:
            ctxs = list(self._ctxs)
        for ctx in ctxs:
            lp = ctx.last_progress
            if not lp or now - lp <= self.stall_timeout:
                continue
            AUDIT.log("stall_killed", idle=round(now - lp, 1))
            ctx.stalled = True
            conn = ctx.conn
            if conn is not None:
                try:
                    if conn.sock is not None:
                        conn.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    conn.close()
                except Exception:
                    pass

    def _progress_loop(self):
        last_done = self.done_bytes
        last_ts = time.time()
        last_save = time.time()
        last_ramp = time.time()
        last_watch = time.time()
        ema = 0.0
        width = 30
        while not self.stop_event.is_set():
            time.sleep(0.25)
            now = time.time()
            with self._count_lock:
                cur = self.done_bytes
            inst = (cur - last_done) / max(now - last_ts, 1e-6)
            ema = inst if ema == 0 else ema * 0.7 + inst * 0.3
            last_done, last_ts = cur, now
            self.speed = ema
            if now - last_save >= 1.0:
                # 脏标记：仅在完成位/parts 变化时序列化（微小块场景
                # done_hex 全量 json 序列化每秒一次的开销被消除）
                with self._count_lock:
                    dirty = self._ctrl_dirty
                    self._ctrl_dirty = False
                if dirty:
                    self.save_ctrl()
                last_save = now
            if now - last_ramp >= 1.0:
                self.rate.ramp_tick()
                last_ramp = now
            if self.stall_timeout > 0 and now - last_watch >= 1.0:
                last_watch = now
                self._watchdog(now)
            if not self.quiet:
                if self.size:
                    pct = cur / self.size * 100
                    filled = int(width * cur // self.size)
                    bar = "█" * filled + "░" * (width - filled)
                    eta = (self.size - cur) / ema if ema > 1 else 0
                    line = (f"\r{bar} {pct:5.1f}% {fmt_size(cur)}/{fmt_size(self.size)} "
                            f"{fmt_size(ema)}/s ETA {fmt_time(eta)} "
                            f"[{self.rate.state_desc()}]")
                else:
                    line = f"\r已下载 {fmt_size(cur)} {fmt_size(ema)}/s"
                sys.stdout.write(line)
                sys.stdout.flush()

    def run(self):
        self.start_time = time.time()
        self.workers = min(self.threads, self.nblocks)
        workers = [threading.Thread(target=self._worker, daemon=True)
                   for _ in range(self.workers)]
        prog = threading.Thread(target=self._progress_loop, daemon=True)
        prog.start()
        for t in workers:
            t.start()
        for t in workers:
            t.join()
        self.stop_event.set()
        prog.join(timeout=2)
        if self.errors:
            self.save_ctrl()
            self.risk.note_throttle(self.host, 60)
            if not self.quiet:
                print(f"\n[错误] 下载失败: {self.errors[0]}")
                print(f"进度已保存，重新执行同一命令即可续传: {self.output}")
            return 1
        if not all(self.completed):
            self.save_ctrl()
            if not self.quiet:
                print(f"\n[中断] 进度已保存，重新执行同一命令即可续传: {self.output}")
            return 130
        self.save_ctrl()
        os.close(self.fd)
        self.fd = None
        self.risk.succeed(self.host, cap=self.rate.cap)
        try:
            self.ctrl_path.unlink()
        except OSError:
            pass
        if not self.quiet:
            elapsed = time.time() - self.start_time
            avg = (self.size - self._initial_done) / elapsed if elapsed > 0 else 0
            print(f"\n[完成] {self.output}  {fmt_size(self.size)}  "
                  f"用时{fmt_time(elapsed)}  平均{fmt_size(avg)}/s  "
                  f"{self.workers}线程/{self.nblocks}块")
        return 0

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


class SingleThreadDownloader:
    def __init__(self, url, output, headers=None, insecure=False, timeout=30,
                 quiet=False, limit=None, persona=True):
        self.url = url
        self.output = Path(output)
        self.part_path = Path(str(self.output) + PART_SUFFIX)
        self.headers = headers or {}
        self.insecure = insecure
        self.timeout = timeout
        self.quiet = quiet
        self.limiter = SpeedLimiter(limit) if limit else None
        self.persona = PersonaKit(enabled=persona)
        self.stop_event = threading.Event()
        self.speed = 0.0
        self._final_url = url
        self._challenge_cookie = None

    def _range_ok(self):
        p = getattr(self, "_probe", None)
        return bool(p and p.range_ok)

    def run(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        lock_path = Path(str(self.output) + LOCK_SUFFIX)
        lock_fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            lock_file(lock_fd, str(self.output))
            return self._run_locked()
        finally:
            os.close(lock_fd)
            try:
                lock_path.unlink()
            except OSError:
                pass

    def _run_locked(self):
        have = self.part_path.stat().st_size if self.part_path.exists() else 0
        chal_tries = 0
        while True:
            conn, path = open_connection(self._final_url, self.insecure,
                                         self.timeout)
            start_ts = time.time()
            try:
                req = self.persona.apply(dict(self.headers))
                if self._challenge_cookie:
                    ck = self._challenge_cookie
                    existing = req.get("Cookie")
                    req["Cookie"] = f"{existing}; {ck}" if existing else ck
                if have and self._range_ok():
                    # .pbpart 续传：从已写盘的字节继续（服务器支持 Range 时）
                    req["Range"] = f"bytes={have}-"
                conn.request("GET", path, headers=req)
                resp = conn.getresponse()
                ctype = resp.getheader("Content-Type") or ""
                if resp.status == 416 and "Range" in req:
                    # part 比源文件还大（源已变化）：作废重下
                    try:
                        resp.read()
                    except Exception:
                        pass
                    self.part_path.unlink(missing_ok=True)
                    have = 0
                    continue
                if resp.status == 200 and "html" in ctype.lower():
                    body_head = resp.read(CHALLENGE_SNIFF)
                    if looks_like_cookie_challenge(resp.status, ctype, body_head):
                        ckv = parse_challenge_cookie(body_head)
                        if ckv and chal_tries < CHALLENGE_MAX_SOLVE:
                            chal_tries += 1
                            wait = min(parse_challenge_wait_ms(body_head) / 1000.0
                                       + random.uniform(0.1, 0.4),
                                       CHALLENGE_MAX_WAIT)
                            time.sleep(wait)
                            self._challenge_cookie = f"{ckv[0]}={ckv[1]}"
                            AUDIT.log("challenge_solved", stage="single",
                                      cookie=ckv[0], wait=round(wait, 2))
                            continue
                        raise DownloadError(
                            "服务器要求浏览器验证(JS cookie挑战)，"
                            "自动应答未成功——请用浏览器打开链接通过验证后重试")
                if resp.status == 206:
                    mode, done0 = "ab", have
                elif resp.status == 200:
                    mode, done0 = "wb", 0
                else:
                    raise DownloadError(f"服务器返回 {resp.status}")
                return self._pump(conn, resp, start_ts, mode, done0)
            finally:
                conn.close()

    def _pump(self, conn, resp, start_ts, mode, done0):
        total = None
        cl = resp.getheader("Content-Length")
        if cl and cl.isdigit():
            total = done0 + int(cl)
        done = done0
        last_done, last_ts, ema = done0, start_ts, 0.0
        with open(self.part_path, mode) as f:
            while True:
                if self.stop_event.is_set():
                    if not self.quiet:
                        if self._range_ok():
                            print(f"\n[中断] 进度已保留({fmt_size(done)})，"
                                  f"重新执行同一命令将从断点续传")
                        else:
                            print("\n[中断] 服务器不支持断点续传，下次将重新下载")
                    return 130
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                if self.limiter is not None:
                    self.limiter.consume(len(chunk))
                f.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last_ts >= 0.5 and not self.quiet:
                    inst = (done - last_done) / (now - last_ts)
                    ema = inst if ema == 0 else ema * 0.7 + inst * 0.3
                    last_done, last_ts = done, now
                    if total:
                        pct = done / total * 100
                        filled = int(30 * done // total)
                        bar = "█" * filled + "░" * (30 - filled)
                        eta = (total - done) / ema if ema > 1 else 0
                        sys.stdout.write(f"\r{bar} {pct:5.1f}% {fmt_size(done)}/"
                                         f"{fmt_size(total)} {fmt_size(ema)}/s "
                                         f"ETA {fmt_time(eta)}   ")
                    else:
                        sys.stdout.write(f"\r已下载 {fmt_size(done)} {fmt_size(ema)}/s   ")
                    sys.stdout.flush()
        if total is not None and done != total:
            raise DownloadError(f"下载不完整({done}/{total})")
        p = getattr(self, "_probe", None)
        if p is not None and p.size is not None and done != p.size:
            raise DownloadError(f"下载大小与预期不符({done}/{p.size})")
        os.replace(self.part_path, self.output)
        elapsed = time.time() - start_ts
        if not self.quiet:
            print(f"\n[完成] {self.output}  {fmt_size(done)}  用时{fmt_time(elapsed)}")
        return 0

    def run_with_probe(self):
        p = probe_url(self.url, self.headers, self.insecure, self.timeout)
        self._final_url = p.final_url
        self._probe = p
        if p.challenge_cookie:
            self._challenge_cookie = f"{p.challenge_cookie[0]}={p.challenge_cookie[1]}"
        return self.run()


# =====================================================================
# §8 Cookie 与解析器
# =====================================================================

def load_cookie_store():
    if COOKIE_DB.exists():
        try:
            return json.loads(COOKIE_DB.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_cookie_store(store):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(COOKIE_DB) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
    os.replace(tmp, COOKIE_DB)


def parse_netscape_cookies(path):
    jars = {}
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                continue
            domain, _flag, _path, _secure, _expiry, name, value = parts
            domain = domain.lstrip(".")
            if not domain or not name:
                continue
            jars.setdefault(domain, {})[name] = value
    return {d: "; ".join(f"{k}={v}" for k, v in ck.items()) for d, ck in jars.items()}


def match_cookie_header(url):
    host = urllib.parse.urlsplit(url).hostname or ""
    store = load_cookie_store()
    hits = []
    for domain, cookie in store.items():
        if host == domain or host.endswith("." + domain):
            hits.append(cookie)
    return "; ".join(hits) if hits else None


def resolve_lanzou(url, headers=None):
    h = {"User-Agent": DEFAULT_UA, "Referer": url,
         "Accept-Language": "zh-CN,zh;q=0.9"}
    if headers:
        h.update({k: v for k, v in headers.items() if k in ("Cookie", "User-Agent")})
    if "://" not in url:
        url = "https://" + url
    m = re.match(r"(https?://[^/]+)", url)
    base = m.group(1)
    status, _, body = http_request(url, headers=h)
    if status != 200:
        raise DownloadError(f"分享页请求失败({status})")
    text = body.decode("utf-8", "replace")
    m = re.search(r'<iframe[^>]+src="([^"]*fn\?[^"]*)"', text) \
        or re.search(r'src="(/fn\?[^"]+)"', text)
    if not m:
        raise DownloadError("未在分享页找到下载入口（链接可能失效或需要提取密码）")
    iframe_url = urllib.parse.urljoin(base, m.group(1))
    status, _, body = http_request(iframe_url, headers=h)
    if status != 200:
        raise DownloadError(f"下载页请求失败({status})")
    text = body.decode("utf-8", "replace")
    m = (re.search(r"'sign'\s*:\s*'([^']+)'", text)
         or re.search(r'data-sign="([^"]+)"', text)
         or re.search(r"sign\s*[:=]\s*'([A-Za-z0-9:%\-]+)'", text))
    if not m:
        raise DownloadError("未提取到签名参数")
    sign = m.group(1)
    status, _, body = http_request(
        urllib.parse.urljoin(base, "/ajaxm.php"), method="POST",
        headers={**h,
                 "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "X-Requested-With": "XMLHttpRequest",
                 "Referer": iframe_url},
        body=urllib.parse.urlencode({"action": "downprocess", "sign": sign,
                                     "kd": "1", "ves": "1"}))
    if status != 200:
        raise DownloadError(f"接口请求失败({status})")
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        raise DownloadError("接口返回非JSON")
    if data.get("zt") != 1:
        raise DownloadError(f"接口返回异常: {data.get('info', data)}")
    dom = str(data.get("dom", ""))
    path_ = str(data.get("url", ""))
    if dom.startswith("//"):
        dom = "https:" + dom
    if dom and not dom.startswith("http"):
        dom = "https://" + dom
    if not dom or not path_:
        raise DownloadError("接口未返回直链")
    return f"{dom.rstrip('/')}/file/{path_.lstrip('/')}"


RESOLVERS = {
    "lanzou": resolve_lanzou,
}

RESOLVE_HINTS = [
    ("lanzou", re.compile(r"lanzou[a-z]*\.(?:com|cn)|lanzn\.com", re.I)),
]


def find_resolver(url):
    for name, pattern in RESOLVE_HINTS:
        if pattern.search(url):
            return name
    return None


# =====================================================================
# §9 CLI
# =====================================================================

def build_headers(args, url):
    headers = {"User-Agent": args.ua or DEFAULT_UA}
    if args.referer:
        headers["Referer"] = args.referer
    for h in args.header or []:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    cookie = args.cookie
    if not cookie and args.cookie_file:
        jars = parse_netscape_cookies(args.cookie_file)
        host = urllib.parse.urlsplit(url).hostname or ""
        parts = [c for d, c in jars.items() if host == d or host.endswith("." + d)]
        cookie = "; ".join(parts) or None
    if not cookie:
        cookie = match_cookie_header(url)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def decide_output(args, probe):
    bdir = getattr(args, "_batch_dir", None)
    if bdir is not None:
        # 批量模式：-o 作为输出目录，文件名取服务器/URL 名，重名自动编号
        name = (probe.filename or filename_from_url(args.url)
                or "download.bin")
        out = Path(bdir) / name
        stem, ext = out.stem, out.suffix
        n = 1
        while out.exists() or Path(str(out) + CTRL_SUFFIX).exists() \
                or Path(str(out) + PART_SUFFIX).exists():
            out = Path(bdir) / f"{stem}-{n}{ext}"
            n += 1
        return str(out)
    if args.output:
        return args.output
    if probe and probe.filename:
        return probe.filename
    return "download.bin"


_task_ref = {"obj": None}


def _sigint_handler(sig, frame):
    obj = _task_ref["obj"]
    if obj is not None and getattr(obj, "stop_event", None) is not None:
        obj.stop_event.set()
    else:
        raise KeyboardInterrupt


def file_digest(path, algo, block=8 * 1024 * 1024):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            b = f.read(block)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _run_once(args):
    """执行一次下载，返回 (returncode, output_path)"""
    url = args.url
    headers = build_headers(args, url)
    persona = PersonaKit(enabled=not getattr(args, "no_persona", False))
    resolver = find_resolver(url)
    if resolver and not args.no_resolve:
        try:
            direct = RESOLVERS[resolver](url, headers)
            if direct:
                print(f"[解析] {resolver} -> {direct}")
                url = direct
                headers = build_headers(args, url)
        except DownloadError as e:
            print(f"[解析失败] {e}，尝试按直链下载")
    probe = None
    try:
        probe = probe_url(url, persona.apply(headers), args.insecure, args.timeout)
    except DownloadError as e:
        if args.ua is None and ("403" in str(e) or "401" in str(e)):
            for ua in UA_POOL:
                if ua == headers.get("User-Agent"):
                    continue
                h2 = persona.apply({**headers, "User-Agent": ua})
                try:
                    probe = probe_url(url, h2, args.insecure, args.timeout)
                except DownloadError:
                    continue
                headers = h2
                AUDIT.log("ua_switch", stage="probe", ua=ua)
                print(f"[探测] 原UA被拒(403)，自动切换UA成功: {ua}")
                break
        if probe is None:
            print(f"[探测失败] {e}")
            return 1, None
    if probe.challenge_cookie:
        headers = merge_cookie_header(dict(headers), *probe.challenge_cookie)
        if not args.quiet:
            print(f"[验证] 已自动通过浏览器验证挑战"
                  f"(cookie {probe.challenge_cookie[0]})，继续下载")
    limit = parse_size(args.limit) if getattr(args, "limit", None) else None
    output = decide_output(args, probe)
    if args.single or not probe.range_ok:
        mode = "单线程流式(服务器不支持Range)" if not probe.range_ok else "单线程(指定)"
        if not args.quiet:
            print(f"[模式] {mode}  大小: {fmt_size(probe.size) if probe.size else '未知'}  "
                  f"文件名: {probe.filename or output}")
        dl = SingleThreadDownloader(url, output, headers, args.insecure,
                                    args.timeout, args.quiet, limit=limit,
                                    persona=not getattr(args, "no_persona", False))
        dl._final_url = probe.final_url
        dl._probe = probe
        _task_ref["obj"] = dl
        try:
            return dl.run(), output
        finally:
            _task_ref["obj"] = None
    threads = args.threads
    host = url_host(probe.final_url)
    risk = HostRiskStore()
    cooldown_left = risk.cooldown_left(host)
    if cooldown_left > 0:
        threads = min(threads, 8)
        if not args.quiet:
            print(f"[记忆] {host} 上次触发风控，冷却剩余{cooldown_left:.0f}s——"
                  f"本次以低并发 {threads} 线程起步，服务器友好后自动爬升")
            AUDIT.log("host_cooldown_loaded", host=host, left=round(cooldown_left))
    if args.auto and (probe.size or 0) > 64 * 1024 * 1024:
        threads = auto_tune(probe.final_url, headers, args.insecure,
                            probe.size, args.quiet)
    if not args.quiet:
        print(f"[模式] 多线程 x{threads}  大小: {fmt_size(probe.size)}  "
              f"文件名: {probe.filename or output}")
        if threads >= 64:
            print(f"[保护] 反风控引擎已启用（平滑爬坡8→{threads}、建连限速"
                  f"{args.conn_rate}/s+抖动、AIMD自动降速、Retry-After合规、"
                  f"三态熔断自动探测恢复、403语义分类、UA轮换、拟人化请求头）")
    dl = MultiThreadDownloader(url, output, threads, headers, args.insecure,
                               args.timeout, args.retry, args.quiet,
                               min_piece=args.min_piece,
                               conn_rate=args.conn_rate, limit=limit,
                               persona=not getattr(args, "no_persona", False),
                               host=host,
                               stall_timeout=getattr(args, "stall_timeout",
                                                     DEFAULT_STALL_TIMEOUT))
    dl._final_url = probe.final_url
    dl._initial_done = 0
    learned = risk.learned_cap(host)
    if learned and learned < threads:
        dl.rate.clamp_cap(learned)
        if not args.quiet:
            print(f"[记忆] {host} 上次学习到并发上限≈{learned}，"
                  f"本次从 {learned} 起步（稳定后逐次爬升，无需重新试错）")
        AUDIT.log("cap_applied", host=host, cap=learned)
    _task_ref["obj"] = dl
    try:
        started = dl.prepare(probe=probe)
        if not started:
            try:
                dl.ctrl_path.unlink()
            except OSError:
                pass
            print(f"[完成] {dl.output} 已是完整文件({fmt_size(dl.size)})")
            return 0, output
        dl._initial_done = dl.done_bytes
        if dl.done_bytes > 0 and not args.quiet:
            print(f"[续传] 从 {fmt_size(dl.done_bytes)} / {fmt_size(dl.size)} 继续")
        return dl.run(), output
    finally:
        _task_ref["obj"] = None
        dl.close()


def _run_batch(args):
    """批量下载队列（--input urls.txt）：逐文件下载 + 同域礼貌间隔 + 汇总。

    爬取下载能力（压测 ST9）：每行一个 URL（#注释/空行跳过），-o 语义
    变为输出目录；同域相邻文件间随机间隔 1~3s；单个失败不中断队列；
    全部成功返回 0，部分失败返回 2；Ctrl+C 中断队列并汇总已完成的。
    """
    try:
        lines = Path(args.input).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"[批量] 无法读取列表文件: {e}")
        return 1
    urls = [l.strip() for l in lines
            if l.strip() and not l.strip().startswith("#")]
    if not urls:
        print("[批量] 列表为空（每行一个 URL，#开头为注释）")
        return 1
    outdir = Path(args.output) if args.output else Path(".")
    try:
        outdir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[批量] 无法创建输出目录 {outdir}: {e}")
        return 1
    args._batch_dir = str(outdir)
    if not args.quiet:
        print(f"[批量] 共 {len(urls)} 个文件，输出目录: {outdir}")
    ok_list, fail_list, interrupted = [], [], False
    prev_host = None
    t0 = time.time()
    for i, u in enumerate(urls, 1):
        host = url_host(u)
        if i > 1 and host == prev_host:
            pause = random.uniform(1.0, 3.0)
            if not args.quiet:
                print(f"\n[批量] 同域({host})礼貌间隔 {pause:.1f}s ...")
            time.sleep(pause)
        if not args.quiet:
            print(f"\n[批量 {i}/{len(urls)}] {u}")
        prev_host = host
        args.url = u
        try:
            rc, _ = _run_once(args)
        except KeyboardInterrupt:
            interrupted = True
            break
        except Exception as e:
            print(f"[批量] 异常: {type(e).__name__}: {e}")
            rc = 1
        if rc == 0:
            ok_list.append(u)
        elif rc == 130:
            interrupted = True
            break
        else:
            fail_list.append(u)
    dt = time.time() - t0
    print(f"\n[批量汇总] 成功 {len(ok_list)}/{len(urls)}"
          f"  失败 {len(fail_list)}"
          f"{'  (用户中断)' if interrupted else ''}"
          f"  用时{fmt_time(dt)}")
    if fail_list:
        print("失败清单（修复后重跑同一命令，已完成文件自动跳过）:")
        for u in fail_list:
            print(f"  - {u}")
    return 0 if not fail_list and not interrupted else \
        (130 if interrupted and not ok_list else 2 if fail_list else 130)


def cmd_download(args):
    if getattr(args, "input", None):
        try:
            return _run_batch(args)
        finally:
            if getattr(args, "explain", False):
                AUDIT.explain()
    want = (args.sha256 or args.md5 or "").lower() or None
    try:
        if not want:
            rc, _ = _run_once(args)
            return rc
        algo = "sha256" if args.sha256 else "md5"
        for rnd in range(3):
            rc, output = _run_once(args)
            if rc != 0 or not output:
                return rc
            got = file_digest(output, algo)
            if got == want:
                if not args.quiet:
                    print(f"[校验] {algo} 校验通过 ✓ {output}")
                return 0
            if rnd == 2:
                print(f"[校验] {algo} 校验失败！期望 {want} 实际 {got}")
                print(f"        文件已保留: {output}（若官方哈希无误，多为下载源在高并发下")
                print(f"        返回了损坏数据，请稍后重试或降低线程数）")
                return 2
            if not args.quiet:
                print(f"[校验] {algo} 不匹配(第{rnd + 1}次)，删除损坏文件重新下载 ...")
            Path(output).unlink(missing_ok=True)
            Path(str(output) + CTRL_SUFFIX).unlink(missing_ok=True)
        return 2
    finally:
        if getattr(args, "explain", False):
            AUDIT.explain()


def cmd_probe(args):
    headers = build_headers(args, args.url)
    p = probe_url(args.url, headers, args.insecure, args.timeout)
    print(f"最终URL   : {p.final_url}")
    print(f"文件大小  : {fmt_size(p.size) if p.size else '未知'}")
    print(f"Range支持 : {'是' if p.range_ok else '否'}")
    print(f"文件名    : {p.filename or '(未提供)'}")
    print(f"ETag      : {p.etag or '-'}")
    print(f"Last-Mod  : {p.last_modified or '-'}")
    return 0


def cmd_cookie(args):
    if args.action == "import":
        jars = parse_netscape_cookies(args.file)
        if not jars:
            print("未从 cookies.txt 解析到任何 Cookie")
            return 1
        store = load_cookie_store()
        for domain, cookie in jars.items():
            if args.domain and domain != args.domain and not domain.endswith("." + args.domain):
                continue
            store[domain] = cookie
            print(f"[导入] {domain}: {cookie[:60]}{'...' if len(cookie) > 60 else ''}")
        save_cookie_store(store)
        print(f"已保存到 {COOKIE_DB}")
        return 0
    if args.action == "list":
        store = load_cookie_store()
        if not store:
            print(f"暂无Cookie（存储位置: {COOKIE_DB}）")
            return 0
        for domain, cookie in store.items():
            print(f"{domain}\t{cookie[:80]}{'...' if len(cookie) > 80 else ''}")
        return 0
    if args.action == "remove":
        store = load_cookie_store()
        removed = store.pop(args.domain, None)
        save_cookie_store(store)
        print(f"{'已删除' if removed else '未找到'}: {args.domain}")
        return 0
    return 1


def cmd_resolve(args):
    name = find_resolver(args.url)
    if not name:
        print("该链接无内置解析器。通用方法：在浏览器登录网盘后，用 F12 网络面板"
              "或油猴脚本获取直链，再交给 panboost download。")
        return 1
    try:
        direct = RESOLVERS[name](args.url)
        if direct:
            print(direct)
            return 0
        print("解析失败")
        return 1
    except DownloadError as e:
        print(f"解析失败: {e}")
        return 1


def add_common(p):
    p.add_argument("--ua", help="自定义 User-Agent")
    p.add_argument("--referer", help="自定义 Referer")
    p.add_argument("--cookie", help='Cookie 字符串，如 "BDUSS=xxx; STK=yyy"')
    p.add_argument("--cookie-file", help="Netscape cookies.txt 路径（浏览器扩展可导出）")
    p.add_argument("--header", action="append", help="额外请求头 X: Y（可多次）")
    p.add_argument("--insecure", action="store_true", help="跳过TLS证书校验")
    p.add_argument("--timeout", type=int, default=30, help="网络超时秒数")
    p.add_argument("--quiet", action="store_true", help="静默模式")


def build_parser():
    ap = argparse.ArgumentParser(
        prog="panboost",
        description="PanBoost 全网盘通用多线程加速下载器（零依赖）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法：")[1] if "用法：" in __doc__ else __doc__)
    ap.add_argument("--version", action="version", version=f"panboost {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="多线程下载（自动识别直链/分享链接）")
    d.add_argument("url", nargs="?",
                   help="下载直链或支持的分享链接（--input 批量模式下可省略）")
    d.add_argument("--input", help="批量下载：URL 列表文件（每行一个，"
                                   "#注释；此时 -o 为输出目录）")
    d.add_argument("-o", "--output", help="输出文件路径（--input 批量模式下为输出目录）")
    d.add_argument("-t", "--threads", type=int, default=DEFAULT_THREADS,
                   help=f"线程数（默认{DEFAULT_THREADS}，最高{MAX_THREADS}；"
                        f"超过有效并发=带宽/单连接限速后无收益，建议配合--auto）")
    d.add_argument("--auto", action="store_true",
                   help="下载前实测服务器限速特征，自动选择线程数（推荐）")
    d.add_argument("--conn-rate", type=int, default=64,
                   help="新连接建立速率上限/秒（默认64，反风控令牌桶，"
                        "避免瞬时连接风暴）")
    d.add_argument("--limit", help="全局限速（如 5M / 512K，字节率整形，"
                                   "削平瞬时打满带宽的突刺特征）")
    d.add_argument("--min-piece", type=int, default=MIN_PIECE,
                   help=f"块大小下限字节数（默认{MIN_PIECE}）")
    d.add_argument("--retry", type=int, default=RETRY_MAX, help="分片重试次数")
    d.add_argument("--stall-timeout", type=float, default=DEFAULT_STALL_TIMEOUT,
                   metavar="SEC",
                   help=f"块级无进展看门狗超时秒数（僵尸连接强制断开重连，"
                        f"从断点续传），默认{DEFAULT_STALL_TIMEOUT:.0f}，0关闭")
    d.add_argument("--single", action="store_true", help="强制单线程模式")
    d.add_argument("--no-resolve", action="store_true", help="跳过内置解析器，按直链下载")
    d.add_argument("--no-persona", action="store_true",
                   help="关闭拟人化请求层（浏览器风格头/块乱序/连接寿命）")
    d.add_argument("--explain", action="store_true",
                   help="结束时打印本会话反风控决策摘要（审计明细见 "
                        "~/.panboost/antifraud.log）")
    d.add_argument("--sha256", help="期望的SHA256值，下载后自动校验，不一致自动重下")
    d.add_argument("--md5", help="期望的MD5值，下载后自动校验，不一致自动重下")
    add_common(d)
    d.set_defaults(func=cmd_download)

    pr = sub.add_parser("probe", help="探测URL能力（Range/大小/文件名）")
    pr.add_argument("url")
    add_common(pr)
    pr.set_defaults(func=cmd_probe)

    ck = sub.add_parser("cookie", help="Cookie 管理")
    csub = ck.add_subparsers(dest="action", required=True)
    ci = csub.add_parser("import", help="导入 Netscape cookies.txt")
    ci.add_argument("domain", help="网盘域名，如 pan.baidu.com")
    ci.add_argument("file", help="cookies.txt 路径")
    cl = csub.add_parser("list", help="列出已导入Cookie")
    cr = csub.add_parser("remove", help="删除某域名Cookie")
    cr.add_argument("domain")
    ck.set_defaults(func=cmd_cookie)

    rs = sub.add_parser("resolve", help="解析分享链接为直链")
    rs.add_argument("url")
    add_common(rs)
    rs.set_defaults(func=cmd_resolve)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "func", None) is cmd_download \
            and not getattr(args, "input", None) and not args.url:
        print("错误：请提供下载 URL，或用 --input urls.txt 批量下载"
              "（python panboost.py download --help 查看用法）")
        return 1
    return args.func(args)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _sigint_handler)
    code = main()
    sys.exit(code)
