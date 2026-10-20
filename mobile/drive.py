#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网盘账号文件浏览 API 层（v3.1.0）。

v2.1.0 的"已登录直入我的网盘"用 WebView 加载夸克 PC 版网页——
PC 页面在手机上触摸拖拽被网页解释成选择/点按且无原生滚动（真机
反馈"手指放在文件区就自动选了，根本没有滑动功能"的根因）。
本层改调网盘网页版前端自己使用的公开 Web API + 用户登录 Cookie
（WebView 登录时保存），把账号内文件列表交给 Kivy 原生 FileRow
渲染——原生滚动与 tap 手势（v3.0.1）即 YunX 式体验。

礼貌客户端边界：仅调用网盘网页版前端使用的公开 HTTP API（带
用户自己的登录 Cookie），不逆向任何协议加密；登录仍走官方页面
WebView。首版支持夸克网盘；其他网盘 list_files 返回 None，调用
方回退 WebView 浏览模式（后续版本逐家接入）。

夸克 API 规格（与 YunX QuarkApi.kt/QuarkConstants.kt 同源，均抓
自网页版前端）：
- 列表 GET drive-pc.quark.cn/1/clouddrive/file/sort
  ?pr=ucpro&fr=pc&pdir_fid={fid}&_page&_size&_sort=...
  响应 data.list[]: fid/file_name/size/dir(boolean)/updated_at
- 直链 POST .../file/download?pr=ucpro&fr=pc  body {"fids":[fid]}
  响应 data[0]: fid/file_name/download_url/size
- 必须 UA=夸克 PC 客户端 + Origin/Referer=pan.quark.cn
- __puus/__pus 约 3 小时过期（直链签名校验关键字段）——每次
  响应的 Set-Cookie 要合并回 Cookie 串保持新鲜
"""
import json
import os
import urllib.parse
import urllib.request

QUARK_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 "
            "Electron/18.3.5.12-a038f7b798 Safari/537.36 "
            "Channel/pckk_other_ch")
QUARK_BASE = "https://drive-pc.quark.cn/1/clouddrive"
QUARK_HEADERS = {
    "User-Agent": QUARK_UA,
    "Origin": "https://pan.quark.cn",
    "Referer": "https://pan.quark.cn/",
}
SUPPORTED = ("quark",)


def _base(pan_key):
    """API 基址：PANBOOST_DRIVE_HOSTS 环境注入（冒烟测试 mock）。"""
    try:
        hosts = json.loads(os.environ.get("PANBOOST_DRIVE_HOSTS")
                           or "{}")
    except Exception:
        hosts = {}
    if pan_key in hosts:
        return hosts[pan_key] + "/1/clouddrive"
    if pan_key == "quark":
        return QUARK_BASE
    return None


def _set_kv(cookie, k, v):
    items = [it for it in cookie.split("; ") if it
             and not it.startswith(k + "=")]
    items.append(k + "=" + v)
    return "; ".join(items)


def _merge_set_cookie(cookie, resp):
    """响应 Set-Cookie 合并回 Cookie 串（__puus/__pus 新鲜化，
    YunX QuarkCookieUtils 同思路——直链签名校验关键字段）。"""
    try:
        for kv in resp.headers.get_all("Set-Cookie") or []:
            part = kv.split(";", 1)[0]
            if "=" in part:
                k, v = part.split("=", 1)
                cookie = _set_kv(cookie, k.strip(), v.strip())
    except Exception:
        pass
    return cookie


def _get_json(pan_key, cookie, url, on_cookie):
    with urllib.request.urlopen(
            urllib.request.Request(
                url, headers=dict(QUARK_HEADERS, Cookie=cookie or "")),
            timeout=20) as r:
        new_ck = _merge_set_cookie(cookie or "", r)
        data = json.loads(r.read().decode("utf-8", "replace"))
    if new_ck != (cookie or "") and on_cookie:
        try:
            on_cookie(new_ck)
        except Exception:
            pass
    return data


def list_files(pan_key, cookie, dir_fid="0", page=1, size=100,
               on_cookie=None):
    """拉取账号内文件列表（网页版前端同款公开 API + 登录 Cookie）。

    返回 entries：[{fid, name, size, dir, updated_at}]；
    pan_key 不支持时返回 None（调用方回退 WebView 浏览）。
    on_cookie(new_cookie)：Set-Cookie 合并后的新鲜 Cookie 回调
    （持久化保活 __puus）。
    """
    base = _base(pan_key)
    if base is None:
        return None
    if pan_key == "quark":
        q = {"pr": "ucpro", "fr": "pc", "uc_param_str": "",
             "pdir_fid": dir_fid, "_page": str(page),
             "_size": str(size), "_fetch_total": "1",
             "_fetch_sub_dirs": "0",
             "_sort": "file_type:asc,updated_at:desc",
             "fetch_all_file": "1", "fetch_risk_file_name": "1"}
        data = _get_json(pan_key, cookie,
                         base + "/file/sort?"
                         + urllib.parse.urlencode(q), on_cookie)
        if data.get("code") != 0 and data.get("status") != 200:
            raise RuntimeError(
                "code=%s %s" % (data.get("code"),
                                str(data.get("message", ""))[:80]))
        lst = (data.get("data") or {}).get("list") or []
        return [{"fid": f.get("fid", ""),
                 "name": f.get("file_name") or f.get("fname")
                 or "未命名",
                 "size": int(f.get("size") or 0),
                 "dir": bool(f.get("dir")),
                 "updated_at": str(f.get("updated_at") or "")}
                for f in lst]
    return None


def get_download_url(pan_key, cookie, fid, on_cookie=None):
    """取单文件下载直链。返回 (url, name, size) 或 None（不支持）。

    夸克响应 data 为数组（YunX 实锤），兼容 str/dict 形态。
    """
    base = _base(pan_key)
    if base is None:
        return None
    if pan_key == "quark":
        url = (base + "/file/download"
               "?pr=ucpro&fr=pc&sys=win32&ve=3.23.2")
        body = json.dumps({"fids": [fid]}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=dict(
            QUARK_HEADERS, Cookie=cookie or "",
            **{"Content-Type": "application/json"}))
        with urllib.request.urlopen(req, timeout=20) as r:
            new_ck = _merge_set_cookie(cookie or "", r)
            data = json.loads(r.read().decode("utf-8", "replace"))
        if new_ck != (cookie or "") and on_cookie:
            try:
                on_cookie(new_ck)
            except Exception:
                pass
        if data.get("code") != 0 and data.get("status") != 200:
            raise RuntimeError(
                "code=%s %s" % (data.get("code"),
                                str(data.get("message", ""))[:80]))
        lst = data.get("data")
        if isinstance(lst, str):
            lst = [{"download_url": lst}]
        if isinstance(lst, dict):
            lst = [lst]
        if not lst:
            return None
        item = lst[0] or {}
        return (item.get("download_url") or "",
                item.get("file_name") or item.get("filename") or "",
                int(item.get("size") or 0))
    return None


def download_headers(pan_key):
    """直链下载所需 headers（夸克直链校验 Referer）。"""
    if pan_key == "quark":
        return {"Referer": "https://pan.quark.cn/"}
    return {}
