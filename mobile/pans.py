"""PanBoost 网盘清单（首页宫格数据，纯数据模块）。

auth_keys: 登录成功特征 Cookie 键，全部命中才判定"已登录"并记账；
           空 = 该网盘登录态不存于 Cookie（localStorage/token 型），
           只能保存网页 Cookie 供下载尝试，无法自动验证登录
domains:   Cookie 生效域（写入引擎 cookie store，下载时后缀匹配）
share:     分享链接域名特征（引擎 resolve_share 识别用）

v1.9.0 登录 URL 实锤修正（LinkSwift v1.1.4 @match 清单 +
AList 驱动文档双源调研，2026-10-20）：
- 阿里云盘：www.alipan.com/ 首页是产品宣传页（含"下载客户端"
  引导），网页版真实路径 www.alipan.com/drive/
- 天翼云盘：cloud.189.cn/ 根路径会跳 APP 引导，网页版在
  cloud.189.cn/web/
- 移动云盘：旧门户 caiyun.feixin.10086.cn 会跳 APP 引导，
  网页版主域 yun.139.com；Cookie 域补 139.com（旧域只有
  10086.cn，新域 Cookie 匹配不到）
- 夸克 pan.quark.cn / UC drive.uc.cn：LinkSwift @match 与
  AList 官方入口双源确认域名无误（真机"下载页/打不开"表象
  根因是桌面 UA 与整块配置一起被吞，见 weblogin v1.9.0）

特征键调研来源（2026-10-20，v1.8.5）：
- 夸克/UC：netdisk-fast-download（qaiu）CookieUtils.UC_QUARK_COOKIE_KEYS
  实战白名单 __pus/__kp/__kps/__ktd/__uid/__puus；__puus 为会话签名
  （服务器 1 小时过期），__pus 为持久会话标识（刷新 __puus 的前提）
  ——两者同时命中才是完整登录态，只查 __puus 会在过期后误判失败
- 天翼云盘：COOKIE_LOGIN_USER（天翼网页登录后种下的用户会话，
  开源社区签到/挂机项目通用判定键）
- OneDrive：ESTSAUTH（login.live.com 微软账号会话 Cookie）
- Dropbox：lid（Dropbox 登录设备标识 Cookie）
- 百度/Google：v1.7.0 起实机验证有效（BDUSS/SAPISID）
- 阿里云盘/迅雷/123/移动/微云/蓝奏/坚果云/MEGA 等：网页登录态存
  localStorage 或 JWT token（LinkSwift 源码调研：123 用 authorization
  JWT、迅雷走 captcha token、阿里走 refreshToken），Cookie 无法承载
  登录态——auth_keys 留空，登录层照常可用但账簿记"未验证"
"""

PANS = [
    {"key": "baidu", "name": "百度网盘",
     # PC 版统一登录页：pan.baidu.com 的 H5 壳内嵌 100ms 延迟强制
     # 跳转脚本（location.href 跳"下载客户端"），即使桌面 UA 也会
     # 先落 H5 再跳（v1.8.2 调研实测）；passport 登录态与网盘同域
     "login": "https://passport.baidu.com/v2/?login", "home": "https://pan.baidu.com/disk/main",
     "domains": ["baidu.com"], "auth_keys": ["BDUSS"],
     "share": ["pan.baidu.com/s/"]},
    {"key": "quark", "name": "夸克网盘", "login": "https://pan.quark.cn/", "home": "https://pan.quark.cn/web/drive",
     "domains": ["quark.cn"], "auth_keys": ["__pus", "__puus"],
     "share": ["pan.quark.cn/s/"]},
    # v1.9.0：首页 / 是产品宣传页（含下载客户端引导），网页版
    # 真实路径 /drive/（LinkSwift @match www.alipan.com/drive*）
    {"key": "alipan", "name": "阿里云盘",
     "login": "https://www.alipan.com/drive/", "home": "https://www.alipan.com/drive/",
     "domains": ["alipan.com", "aliyundrive.com"], "auth_keys": [],
     "share": ["alipan.com/s/", "aliyundrive.com/s/"]},
    {"key": "weiyun", "name": "腾讯微云", "login": "https://www.weiyun.com/", "home": "https://www.weiyun.com/disk",
     "domains": ["weiyun.com"], "auth_keys": [],
     "share": ["weiyun.com/disk/", "share.weiyun.com/"]},
    # v1.9.0：cloud.189.cn/ 根路径会跳 APP 引导，网页版在
    # cloud.189.cn/web/（LinkSwift @match cloud.189.cn/web/*）
    {"key": "tianyi", "name": "天翼云盘",
     "login": "https://cloud.189.cn/web/", "home": "https://cloud.189.cn/web/",
     "domains": ["189.cn"], "auth_keys": ["COOKIE_LOGIN_USER"],
     "share": ["cloud.189.cn/t/", "189.cn/t/"]},
    # v1.9.0：旧门户 caiyun.feixin.10086.cn 会跳 APP 引导，网页版
    # 主域 yun.139.com（LinkSwift @match yun.139.com/*）；Cookie
    # 域补 139.com（下载携带时后缀匹配需要）
    {"key": "yidong", "name": "移动云盘",
     "login": "https://yun.139.com/", "home": "https://yun.139.com/w/",
     "domains": ["139.com", "10086.cn"], "auth_keys": [],
     "share": ["caiyun.139.com/m/", "yun.139.com/"]},
    {"key": "xunlei", "name": "迅雷云盘", "login": "https://pan.xunlei.com/", "home": "https://pan.xunlei.com/",
     "domains": ["xunlei.com"], "auth_keys": [],
     "share": ["pan.xunlei.com/s/"]},
    {"key": "pan123", "name": "123云盘", "login": "https://www.123pan.com/", "home": "https://www.123pan.com/",
     "domains": ["123pan.com"], "auth_keys": [],
     "share": ["123pan.com/s/"]},
    {"key": "lanzou", "name": "蓝奏云", "login": "https://www.lanzou.com/", "home": "https://www.lanzou.com/u",
     "domains": ["lanzou.com", "lanzoux.com"], "auth_keys": [],
     "share": ["lanzou.com/", "lanzoux.com/", "lanzoui.com/",
               "lanzoub.com/", "lanzoue.com/", "lanzoup.com/",
               "lanzouw.com/", "lanzoux.com/", "lanzn.com/"]},
    {"key": "jianguo", "name": "坚果云", "login": "https://www.jianguoyun.com/", "home": "https://www.jianguoyun.com/#home",
     "domains": ["jianguoyun.com"], "auth_keys": [],
     "share": ["jianguoyun.com/p/"]},
    {"key": "uc", "name": "UC网盘", "login": "https://drive.uc.cn/", "home": "https://drive.uc.cn/",
     "domains": ["uc.cn"], "auth_keys": ["__pus", "__puus"],
     "share": ["drive.uc.cn/s/"]},
    {"key": "gdrive", "name": "Google Drive",
     "login": "https://accounts.google.com/", "home": "https://drive.google.com/drive/my-drive",
     "domains": ["google.com", "googleusercontent.com"],
     "auth_keys": ["SAPISID"],
     "share": ["drive.google.com/file/d/", "drive.google.com/uc?id="]},
    {"key": "dropbox", "name": "Dropbox", "login": "https://www.dropbox.com/", "home": "https://www.dropbox.com/home",
     "domains": ["dropbox.com", "dropboxusercontent.com"],
     "auth_keys": ["lid"],
     "share": ["dropbox.com/s/"]},
    {"key": "onedrive", "name": "OneDrive",
     "login": "https://login.live.com/", "home": "https://onedrive.live.com/",
     "domains": ["live.com", "1drv.com", "sharepoint.com"],
     "auth_keys": ["ESTSAUTH"],
     "share": ["1drv.ms/", "onedrive.live.com/"]},
    {"key": "mega", "name": "MEGA", "login": "https://mega.nz/", "home": "https://mega.nz/fm",
     "domains": ["mega.nz"], "auth_keys": [],
     "share": ["mega.nz/file/", "mega.nz/#!"]},
    {"key": "pcloud", "name": "pCloud", "login": "https://www.pcloud.com/", "home": "https://my.pcloud.com/",
     "domains": ["pcloud.com"], "auth_keys": [],
     "share": ["pcloud.com/"]},
    {"key": "box", "name": "Box", "login": "https://www.box.com/", "home": "https://app.box.com/folder/0",
     "domains": ["box.com", "boxcloud.com"],
     "auth_keys": [],
     "share": ["box.com/s/", "app.box.com/s/"]},
    {"key": "yandex", "name": "Yandex Disk", "login": "https://disk.yandex.com/", "home": "https://disk.yandex.com/",
     "domains": ["yandex.com", "yandex.ru"], "auth_keys": [],
     "share": ["disk.yandex.com/d/", "yadi.sk/d/"]},
]

PAN_BY_KEY = {p["key"]: p for p in PANS}
