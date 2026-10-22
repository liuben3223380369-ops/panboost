package org.panboost.core.domain

/**
 * 网盘清单（v4.3.0：v3.2.8 pans.py 原样迁移——18 家）。
 *
 * 数据驱动的静态目录：账号页宫格 / 通用登录屏 / 登录态判定
 * 全部从这里取数，新增网盘只改本文件。
 *
 * authKeys：登录成功特征 Cookie 键（全部命中才判"已登录"；
 * 空 = 该网盘登录态存 localStorage/token，Cookie 只能保存供
 * 下载尝试，账簿记"未验证"——v3.2.8 同语义）。
 */
data class PanInfo(
    val key: String,
    val name: String,
    val loginUrl: String,
    val homeUrl: String,
    val domains: List<String>,
    val authKeys: List<String>,
    val sharePatterns: List<String>,
)

object PanCatalog {

    val all: List<PanInfo> = listOf(
        PanInfo(
            "quark", "夸克网盘",
            "https://pan.quark.cn/", "https://pan.quark.cn/web/drive",
            listOf("quark.cn"),
            listOf("__uid", "__pus", "__puus"),
            listOf("pan.quark.cn/s/"),
        ),
        PanInfo(
            "uc", "UC网盘",
            "https://drive.uc.cn/", "https://drive.uc.cn/",
            listOf("uc.cn"),
            listOf("__pus", "__puus"),
            listOf("drive.uc.cn/s/"),
        ),
        PanInfo(
            "baidu", "百度网盘",
            "https://passport.baidu.com/v2/?login", "https://pan.baidu.com/disk/main",
            listOf("baidu.com"),
            listOf("BDUSS"),
            listOf("pan.baidu.com/s/"),
        ),
        PanInfo(
            "alipan", "阿里云盘",
            "https://www.alipan.com/drive/", "https://www.alipan.com/drive/",
            listOf("alipan.com", "aliyundrive.com"),
            emptyList(),
            listOf("alipan.com/s/", "aliyundrive.com/s/"),
        ),
        PanInfo(
            "weiyun", "腾讯微云",
            "https://www.weiyun.com/", "https://www.weiyun.com/disk",
            listOf("weiyun.com"),
            emptyList(),
            listOf("weiyun.com/disk/", "share.weiyun.com/"),
        ),
        PanInfo(
            "tianyi", "天翼云盘",
            "https://cloud.189.cn/web/", "https://cloud.189.cn/web/",
            listOf("189.cn"),
            listOf("COOKIE_LOGIN_USER"),
            listOf("cloud.189.cn/t/", "189.cn/t/"),
        ),
        PanInfo(
            "yidong", "移动云盘",
            "https://yun.139.com/", "https://yun.139.com/w/",
            listOf("139.com", "10086.cn"),
            emptyList(),
            listOf("caiyun.139.com/m/", "yun.139.com/"),
        ),
        PanInfo(
            "xunlei", "迅雷云盘",
            "https://pan.xunlei.com/", "https://pan.xunlei.com/",
            listOf("xunlei.com"),
            emptyList(),
            listOf("pan.xunlei.com/s/"),
        ),
        PanInfo(
            "pan123", "123云盘",
            "https://www.123pan.com/", "https://www.123pan.com/",
            listOf("123pan.com"),
            emptyList(),
            listOf("123pan.com/s/"),
        ),
        PanInfo(
            "lanzou", "蓝奏云",
            "https://www.lanzou.com/", "https://www.lanzou.com/u",
            listOf("lanzou.com", "lanzoux.com"),
            emptyList(),
            listOf(
                "lanzou.com/", "lanzoua.com/", "lanzoub.com/",
                "lanzouc.com/", "lanzoud.com/", "lanzoue.com/",
                "lanzouf.com/", "lanzoug.com/", "lanzouh.com/",
                "lanzoui.com/", "lanzouj.com/", "lanzouk.com/",
                "lanzoul.com/", "lanzoum.com/", "lanzoun.com/",
                "lanzouo.com/", "lanzoup.com/", "lanzouq.com/",
                "lanzour.com/", "lanzous.com/", "lanzout.com/",
                "lanzouu.com/", "lanzouv.com/", "lanzouw.com/",
                "lanzoux.com/", "lanzouy.com/", "lanzouz.com/",
                "lanzn.com/",
            ),
        ),
        PanInfo(
            "jianguo", "坚果云",
            "https://www.jianguoyun.com/", "https://www.jianguoyun.com/#home",
            listOf("jianguoyun.com"),
            emptyList(),
            listOf("jianguoyun.com/p/"),
        ),
        PanInfo(
            "gdrive", "Google Drive",
            "https://accounts.google.com/", "https://drive.google.com/drive/my-drive",
            listOf("google.com", "googleusercontent.com"),
            listOf("SAPISID"),
            listOf("drive.google.com/file/d/", "drive.google.com/uc?id="),
        ),
        PanInfo(
            "dropbox", "Dropbox",
            "https://www.dropbox.com/", "https://www.dropbox.com/home",
            listOf("dropbox.com", "dropboxusercontent.com"),
            listOf("lid"),
            listOf("dropbox.com/s/"),
        ),
        PanInfo(
            "onedrive", "OneDrive",
            "https://login.live.com/", "https://onedrive.live.com/",
            listOf("live.com", "1drv.com", "sharepoint.com"),
            listOf("ESTSAUTH"),
            listOf("1drv.ms/", "onedrive.live.com/"),
        ),
        PanInfo(
            "mega", "MEGA",
            "https://mega.nz/", "https://mega.nz/fm",
            listOf("mega.nz"),
            emptyList(),
            listOf("mega.nz/file/", "mega.nz/#!"),
        ),
        PanInfo(
            "pcloud", "pCloud",
            "https://www.pcloud.com/", "https://my.pcloud.com/",
            listOf("pcloud.com"),
            emptyList(),
            listOf("pcloud.com/"),
        ),
        PanInfo(
            "box", "Box",
            "https://www.box.com/", "https://app.box.com/folder/0",
            listOf("box.com", "boxcloud.com"),
            emptyList(),
            listOf("box.com/s/", "app.box.com/s/"),
        ),
        PanInfo(
            "yandex", "Yandex Disk",
            "https://disk.yandex.com/", "https://disk.yandex.com/",
            listOf("yandex.com", "yandex.ru"),
            emptyList(),
            listOf("disk.yandex.com/d/", "yadi.sk/d/"),
        ),
    )

    fun byKey(key: String): PanInfo? = all.firstOrNull { it.key == key }

    fun byShareUrl(url: String): PanInfo? =
        all.firstOrNull { pan -> pan.sharePatterns.any { url.contains(it) } }
}
