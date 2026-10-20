#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PanBoost 本地测试服务器：支持 Range / 限速 / 重定向 / Cookie 校验 / 并发统计"""
import http.server
import io
import random
import re
import socket
import struct
import threading
import time


class TestHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PanBoostTest/1.0"

    def setup(self):
        super().setup()
        self.conn_id = self.server.next_conn_id()

    def log_message(self, *a):
        pass

    @property
    def cfg(self):
        return self.server.cfg

    def _route_data(self):
        """按路径取数据（双进程竞争测试：不同路径返回不同内容）"""
        alt = self.cfg.get("alt_path")
        if alt and self.path == alt:
            return self.cfg["alt_data"]
        return self.cfg["data"]

    def _reject(self, status, msg, retry_after=None):
        body = msg.encode() if isinstance(msg, str) else msg
        self.send_response(status)
        if retry_after is not None:
            self.send_header("Retry-After", str(retry_after))
        self.send_header(
            "Content-Type",
            self.cfg.get("reject_ctype", "text/plain; charset=utf-8"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _check_cookie(self):
        need = self.cfg.get("require_cookie")
        if need and need not in self.headers.get("Cookie", ""):
            self._reject(403, "403 need cookie")
            return False
        return True

    def _seq_reject(self):
        """按请求序号注入 403/429（reject_skip 跳过前 N 个请求，模拟探测期正常、下载期封禁）"""
        self.server.req_seq += 1
        seq = self.server.req_seq
        skip = self.cfg.get("reject_skip", 0)
        cnt = self.cfg.get("reject_count", 0)
        if cnt and skip < seq <= skip + cnt:
            self._reject(self.cfg.get("reject_status", 403),
                         self.cfg.get("reject_body", "forbidden"),
                         self.cfg.get("reject_retry_after", 1))
            return True
        return False

    def _ua_reject(self):
        forbid = self.cfg.get("forbid_uas")
        if forbid and self.headers.get("User-Agent") in forbid:
            self._reject(403, self.cfg.get("reject_body", "ua forbidden"),
                         self.cfg.get("reject_retry_after", 1))
            return True
        return False

    def _observe(self):
        """捕获请求特征（拟人化/乱序/连接寿命测试用）"""
        self.server.header_log.append(dict(self.headers))
        rng = self.headers.get("Range") or ""
        m = re.match(r"bytes=(\d+)-", rng)
        self.server.range_log.append(int(m.group(1)) if m else -1)

    def _challenge(self):
        """模拟中科大镜像式 JS cookie 挑战：无 cookie 返回 Verifying 页。

        challenge 配置: {"cookie": "addr=1.2.3.4", "wait_ms": 100}
        challenge_forever: True 时带 cookie 也永远挑战（测防循环保护）
        """
        chal = self.cfg.get("challenge")
        if not chal:
            return False
        want = chal.get("cookie", "addr=1.2.3.4")
        name = want.split("=", 1)[0]
        got = self.headers.get("Cookie", "")
        if name in got and not self.cfg.get("challenge_forever"):
            return False
        wait = chal.get("wait_ms", 100)
        ip = want.split("=", 1)[1]
        body = (
            "<!DOCTYPE html><html><head><title>Verifying - Test Mirrors</title></head>"
            "<body><h1>Verifying your browser</h1>"
            "<p>Additional verification is required for this file you requested.</p>"
            f"<p>Your IP address is {ip}</p>"
            "<script>\n"
            f'document.cookie = "{want}; max-age=300";\n'
            "setTimeout(function() {\n"
            "    location.reload();\n"
            f"}}, {wait});\n"
            "</script></body></html>").encode()
        self.server.challenge_count += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=UTF-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return True

    def _stall(self):
        """模拟僵尸连接：指定连接号范围收到请求后长期不回任何字节。

        stall_conns: 挂住的连接条数；stall_start: 起始连接号（跳过探测连接）
        stall_secs: 挂住秒数（客户端看门狗会在其间强制断开）
        """
        n = self.cfg.get("stall_conns", 0)
        start = self.cfg.get("stall_start", 1)
        if n and start <= self.conn_id <= start + n - 1:
            self.server.stall_count += 1
            time.sleep(self.cfg.get("stall_secs", 20))
            return True
        return False

    def _rst(self):
        """模拟暴力连接重置：发完响应头+前几个字节后以 RST 关闭连接。

        rst_conns: 前 N 条数据连接被重置；rst_at: 重置前发送的字节数。
        与 truncate 不同：无 FIN 正常挥手，客户端 read 直接 ConnectionReset。
        """
        n = self.cfg.get("rst_conns", 0)
        if n and self.server.rst_count < n:
            self.server.rst_count += 1
            at = self.cfg.get("rst_at", 8 * 1024)
            data = self.cfg["data"]
            rng = self.headers.get("Range")
            start = 0
            if rng:
                m = re.match(r"bytes=(\d+)-", rng)
                if m:
                    start = int(m.group(1))
            payload = data[start:start + at]
            self.send_response(206)
            self.send_header("Content-Range",
                             f"bytes {start}-{len(data)-1}/{len(data)}")
            self.send_header("Content-Length", str(len(data) - start))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()
            # SO_LINGER {on, 0} → close() 立即发 RST，丢弃未读数据
            self.connection.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            self.close_connection = True
            return True
        return False

    def _chaos(self):
        """混沌模式：按可复现随机序列注入混合故障（429/503/RST/截断/慢速）。

        fail_prob: 单请求故障概率；fail_seed: 随机种子（可复现）。
        返回 True 表示已注入故障（响应已发完，终止正常处理）。
        """
        prob = self.cfg.get("fail_prob", 0.0)
        if not prob:
            return False
        roll = self.server.fail_rng.random()
        if roll >= prob:
            return False
        kind = self.server.fail_rng.random()
        if kind < 0.4:                      # 40% 概率 429/503 限流
            self.server.throttle_count += 1
            status = 429 if kind < 0.2 else 503
            self.send_response(status)
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if kind < 0.7:                      # 30% 概率 RST 重置
            return self._rst()
        # 30% 概率响应头后直接断开（截断为 0 字节，无 RST）
        self.server.truncate_hits += 1
        self.send_response(206)
        self.send_header("Content-Range",
                         f"bytes 0-{len(self.cfg['data'])-1}/"
                         f"{len(self.cfg['data'])}")
        self.send_header("Content-Length", str(len(self.cfg["data"])))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        return True

    def do_HEAD(self):
        if not self._check_cookie():
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.cfg["data"])))
        self.send_header("Accept-Ranges",
                         "bytes" if self.cfg.get("support_range", True) else "none")
        for k, v in self.cfg.get("extra_headers", {}).items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        if self.cfg.get("redirect_to"):
            self.send_response(302)
            self.send_header("Location", self.cfg["redirect_to"])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self._challenge():
            return
        if not self._check_cookie():
            return
        if self._seq_reject() or self._ua_reject():
            return
        self._observe()
        if self._stall():
            return
        if self._rst() or self._chaos():
            return
        limit = self.cfg.get("conn_limit")
        after = self.cfg.get("throttle_after")
        throttled = (limit is not None and self.server.concurrent >= limit) or \
            (after is not None and self.server.success_count >= after)
        if throttled:
            self.server.throttle_count += 1
            self.send_response(self.cfg.get("throttle_status", 429))
            self.send_header("Retry-After", str(self.cfg.get("retry_after", 2)))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.server.success_count += 1
        data = self._route_data()
        rng = self.headers.get("Range")
        self.server.concurrent += 1
        self.server.max_concurrent = max(self.server.max_concurrent,
                                         self.server.concurrent)
        self.server.conn_log.append(time.time())
        try:
            if rng and self.cfg.get("support_range", True):
                # 负载感知 TTFB：并发越高响应头越慢（模拟真实服务器
                # 拥塞排队——客户端延迟感知降载的测试锚点）
                ttfb = self.cfg.get("ttfb_factor", 0.0)
                if ttfb:
                    time.sleep(0.05 * (1 + self.server.concurrent * ttfb))
                m = re.match(r"bytes=(\d+)-(\d*)", rng)
                if not m:
                    self.send_response(416)
                    self.send_header("Content-Range",
                                     f"bytes */{len(data)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else len(data) - 1
                end = min(end, len(data) - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header("Content-Range",
                                     f"bytes */{len(data)}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                payload = data[start:end + 1]
                # 模拟 CDN 截断响应：声称完整 Content-Length 但只发前 N 字节断连
                tc = self.cfg.get("truncate_count", 0)
                if tc and self.server.truncate_hits < tc:
                    self.server.truncate_hits += 1
                    cut = self.cfg.get("truncate_at", 0)
                    self.send_response(206)
                    self.send_header("Content-Range",
                                     f"bytes {start}-{end}/{len(data)}")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(payload[:cut])
                    self.close_connection = True
                    return
                self.send_response(206)
                self.send_header("Content-Range",
                                 f"bytes {start}-{end}/{len(data)}")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(len(payload)))
                for k, v in self.cfg.get("extra_headers", {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self._stream(payload)
            else:
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                if self.cfg.get("support_range", True):
                    self.send_header("Accept-Ranges", "bytes")
                for k, v in self.cfg.get("extra_headers", {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self._stream(data)
        finally:
            self.server.concurrent -= 1

    def _stream(self, payload):
        buf = io.BytesIO(payload)
        csize = self.cfg.get("chunk_size", 64 * 1024)
        slow = self.cfg.get("slow_conns", 0)
        if slow and self.conn_id <= slow:
            delay = self.cfg.get("slow_delay", 0.0)
        else:
            delay = self.cfg.get("delay_per_chunk", 0.0)
        load_factor = self.cfg.get("load_factor", 0.0)
        while True:
            chunk = buf.read(csize)
            if not chunk:
                break
            # 负载感知延迟：并发越高响应越慢（模拟真实服务器拥塞排队）
            d = delay * (1 + self.server.concurrent * load_factor) \
                if load_factor else delay
            self.wfile.write(chunk)
            self.server.total_sent += len(chunk)
            if d:
                time.sleep(d)


class TestServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr=("127.0.0.1", 0)):
        self.concurrent = 0
        self.max_concurrent = 0
        self.total_sent = 0
        self.conn_seq = 0
        self.throttle_count = 0
        self.success_count = 0
        self.conn_log = []
        self.req_seq = 0
        self.header_log = []
        self.range_log = []
        self.challenge_count = 0
        self.stall_count = 0
        self.truncate_hits = 0
        self.rst_count = 0
        self.fail_rng = random.Random(42)
        self.cfg = {"data": b"", "support_range": True}
        super().__init__(addr, TestHandler)
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def next_conn_id(self):
        self.conn_seq += 1
        return self.conn_seq

    def handle_error(self, request, client_address):
        pass

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"

    def set_data(self, data, **kw):
        self.cfg = {
            "data": data,
            "support_range": kw.get("support_range", True),
            "delay_per_chunk": kw.get("delay_per_chunk", 0.0),
            "chunk_size": kw.get("chunk_size", 64 * 1024),
            "require_cookie": kw.get("require_cookie"),
            "redirect_to": kw.get("redirect_to"),
            "extra_headers": kw.get("extra_headers", {}),
            "slow_conns": kw.get("slow_conns", 0),
            "slow_delay": kw.get("slow_delay", 0.0),
            "conn_limit": kw.get("conn_limit"),
            "throttle_after": kw.get("throttle_after"),
            "retry_after": kw.get("retry_after", 2),
            "throttle_status": kw.get("throttle_status", 429),
            "reject_skip": kw.get("reject_skip", 0),
            "reject_count": kw.get("reject_count", 0),
            "reject_status": kw.get("reject_status", 403),
            "reject_body": kw.get("reject_body", "forbidden"),
            "reject_ctype": kw.get("reject_ctype"),
            "reject_retry_after": kw.get("reject_retry_after", 1),
            "forbid_uas": kw.get("forbid_uas"),
            "challenge": kw.get("challenge"),
            "challenge_forever": kw.get("challenge_forever", False),
            "stall_conns": kw.get("stall_conns", 0),
            "stall_start": kw.get("stall_start", 1),
            "stall_secs": kw.get("stall_secs", 20),
            "truncate_count": kw.get("truncate_count", 0),
            "truncate_at": kw.get("truncate_at", 0),
            "rst_conns": kw.get("rst_conns", 0),
            "rst_at": kw.get("rst_at", 8 * 1024),
            "fail_prob": kw.get("fail_prob", 0.0),
            "alt_path": kw.get("alt_path"),
            "alt_data": kw.get("alt_data", b""),
            "load_factor": kw.get("load_factor", 0.0),
            "ttfb_factor": kw.get("ttfb_factor", 0.0),
        }
        self.fail_rng = random.Random(kw.get("fail_seed", 42))
        self.concurrent = 0
        self.max_concurrent = 0
        self.total_sent = 0
        self.conn_seq = 0
        self.throttle_count = 0
        self.success_count = 0
        self.conn_log = []
        self.req_seq = 0
        self.header_log = []
        self.range_log = []
        self.challenge_count = 0
        self.stall_count = 0
        self.truncate_hits = 0
        self.rst_count = 0

    def new_conn_rate_peak(self):
        """任意1秒滑窗内新增连接数的峰值"""
        log = sorted(self.conn_log)
        peak = 0
        for i, t in enumerate(log):
            j = i
            while j < len(log) and log[j] - t < 1.0:
                j += 1
            peak = max(peak, j - i)
        return peak
