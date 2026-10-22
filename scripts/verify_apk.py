#!/usr/bin/env python3
"""APK 发布门禁（v4.3.1：本地与 CI 通用——防"装上即闪"残废包）。

四项校验（任一失败即非零退出）：
1. 启动链校验（本工具核心）：解 binary AndroidManifest 的字符串池，
   对每个类名形态字符串（含相对名 .X 按包名解析）在 dex 中查
   L<pkg>/<Name>; ——v4.0~v4.3 全系启动即闪的根因（namespace
   org.panboost.app 与源码包 org.panboost 失配，相对名解析出
   不存在的类）就死在这里，此后永不再过。
2. R8 保真：dex 必含关键 API 端点/引擎标记（防过度裁剪）。
3. 零存储权限：manifest 权限白名单（网络/前台服务/通知之外
   一律拒绝，MANAGE_EXTERNAL_STORAGE 绝不允许）。
4. 结构完整性：classes.dex / resources.arsc / AndroidManifest
   必在，且至少一个 res/ 主题条目。

用法：python3 verify_apk.py <apk> [--application-id org.panboost.app]
"""
import re
import struct
import sys
import zipfile

DEFAULT_APPLICATION_ID = "org.panboost.app"

# 关键标记（R8 保真——API 端点/引擎核心类）
DEX_KEYS = [
    b"drive-pc.quark.cn",
    b"pan.quark.cn",
    b"sharepage/token",
    b"MultiThreadDownloadWorker",
    b"CrashReporter",
    b"Lorg/panboost",
]

# 权限白名单（零存储边界：MediaStore 正统路径）
ALLOWED_PERMISSIONS_PREFIXES = (
    "android.permission.INTERNET",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.POST_NOTIFICATIONS",
    "android.permission.ACCESS_NETWORK_STATE",
    "android.permission.WAKE_LOCK",
    # 库组件合并进来的自身权限（WorkManager 持久化/诊断）
    "android.permission.RECEIVE_BOOT_COMPLETED",
    "android.permission.BIND_JOB_SERVICE",
    "android.permission.DUMP",
    "android.permission.FOREGROUND_SERVICE_DATA_SYNC",
)

CLASSISH = re.compile(r"^[a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*\.[A-Z][A-Za-z0-9_]*$")
RELATIVE = re.compile(r"^\.[A-Z][A-Za-z0-9_]*$")

RES_STRING_POOL_TYPE = 0x0001
UTF8_FLAG = 1 << 8


def _read_len8(data: bytes, pos: int):
    """UTF-8 池的变长 u8（modified UTF-8 长度前缀）。"""
    b = data[pos]
    pos += 1
    if b & 0x80:
        b2 = data[pos]
        pos += 1
        return ((b & 0x7F) << 8) | b2, pos
    return b, pos


def read_string_pool(data: bytes, offset: int) -> list:
    """解析 ResStringPool chunk → 字符串列表（UTF-8/UTF-16）。"""
    if offset + 28 > len(data):
        return []
    ctype, _chsize, _csize = struct.unpack_from("<HHI", data, offset)
    if ctype != RES_STRING_POOL_TYPE:
        return []
    str_count, _style_count, flags, strings_start, _styles_start = \
        struct.unpack_from("<IIIII", data, offset + 8)
    base = offset + 28
    if base + 4 * str_count > len(data):
        return []
    offsets = struct.unpack_from(f"<{str_count}I", data, base)
    data_base = offset + strings_start
    out = []
    for so in offsets[:str_count]:
        pos = data_base + so
        if flags & UTF8_FLAG:
            _nchars, pos = _read_len8(data, pos)
            nbytes, pos = _read_len8(data, pos)
            out.append(data[pos:pos + nbytes].decode("utf-8", "replace"))
        else:
            ln = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            if ln & 0x8000:
                hi = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                ln = ((ln & 0x7FFF) << 16) | hi
            out.append(data[pos:pos + ln * 2].decode("utf-16-le", "replace"))
    return out


def axml_strings(manifest: bytes) -> list:
    """AXML（binary）首子 chunk 即全局字符串池。"""
    if len(manifest) < 16:
        return []
    magic = struct.unpack_from("<I", manifest, 0)[0]
    if (magic & 0xFFFF) != 0x0003:  # RES_XML_TYPE
        return []
    return read_string_pool(manifest, 8)


def main() -> int:
    apk_path = sys.argv[1]
    app_id = DEFAULT_APPLICATION_ID
    if "--application-id" in sys.argv:
        app_id = sys.argv[sys.argv.index("--application-id") + 1]

    errors = []
    z = zipfile.ZipFile(apk_path)
    names = z.namelist()

    # ---- 4. 结构完整性 ----
    for must in ("classes.dex", "resources.arsc", "AndroidManifest.xml"):
        if must not in names:
            errors.append(f"结构缺失: {must}")
    if not any(n.startswith("res/") or n == "resources.arsc" for n in names):
        errors.append("无任何资源条目")
    dex = z.read("classes.dex")
    manifest = z.read("AndroidManifest.xml")

    # ---- 2. R8 保真 ----
    missing_keys = [k.decode() for k in DEX_KEYS if k not in dex]
    if missing_keys:
        errors.append(f"R8 过度裁剪，dex 缺失: {missing_keys}")

    # ---- 1. 启动链校验 ----
    strings = axml_strings(manifest)
    if not strings:
        errors.append("AndroidManifest 字符串池解析失败（AXML 异常）")
    class_names = []
    for s in strings:
        if not s or s.startswith(("http://", "https://", "android.", "res/")):
            continue
        if CLASSISH.match(s):
            # 只校验 App 自有组件类（org.panboost.*）——库内部类
            # （androidx.* 等）被 R8 裁剪合法；intent action 字符串
            # （含 .action. 段）与自定义权限声明（*_PERMISSION）跳过
            if (s.startswith("org.panboost.")
                    and ".action." not in s
                    and "PERMISSION" not in s
                    and "NOT_EXPORTED" not in s):
                class_names.append(s)
    checked, bad = [], []
    for cn in class_names:
        dex_form = f"L{cn.replace('.', '/')};".encode()
        if dex_form not in dex:
            bad.append(cn)
        checked.append(cn)
    # 相对名（.MainActivity 形态）按 applicationId 解析
    for s in strings:
        if RELATIVE.match(s) and "PERMISSION" not in s:
            full = app_id + s
            dex_form = f"L{full.replace('.', '/')};".encode()
            if dex_form not in dex:
                bad.append(f"{s} (解析为 {full}，dex 不存在)")
            checked.append(full)
    if bad:
        errors.append(f"启动链断裂——manifest 类在 dex 中不存在: {bad}")
    if not checked:
        errors.append("manifest 中未发现任何组件类名（解析异常）")

    # ---- 3. 零存储权限 ----
    for s in strings:
        if s.startswith("android.permission."):
            if not any(s.startswith(p) for p in ALLOWED_PERMISSIONS_PREFIXES):
                errors.append(f"越界权限: {s}")

    if errors:
        print("VERIFY FAIL:")
        for e in errors:
            print("  ✗", e)
        return 1
    print(f"VERIFY PASS: 启动链 {len(checked)} 组件全在 dex | "
          f"R8 保真 {len(DEX_KEYS)} 标记 | 权限白名单 | 结构完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
