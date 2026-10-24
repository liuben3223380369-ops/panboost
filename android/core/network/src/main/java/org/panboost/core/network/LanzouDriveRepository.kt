package org.panboost.core.network

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 蓝奏云主页面仓库（v7.1.0——OpenList lanzou 驱动 Cookie 模式规格）。
 *
 * 规格（OpenList util.go 实证）：
 * - 列表：POST pc.woozooo.com/doupload.php?uid&vei 表单
 *   task=47（文件夹列表）/task=5（文件列表分页 pg）——响应
 *   {zt, info: {text: [...]}}——text 数组即条目
 * - uid/vei：GET pc.woozooo.com/mydisk.php?item=files&action=index
 *   页面正则提取（uid=xxx / html data["vei"]）——Cookie 会话有效
 *   时每次可重新提取（无需持久化）
 * - 直链：task=22 取 fileShare 信息 → 分享页解析（复用既有
 *   LanzouShareResolver 的 HTML 流）——本实现走 task=22 拿分享
 *   fid+pwd，再借 resolver 的 GetFilesByShareUrl 等价逻辑
 * - UA：标准桌面浏览器；Cookie 直连
 */
@Singleton
class LanzouDriveRepository @Inject constructor(
    private val appLog: org.panboost.core.logging.AppLog,
) : DriveRepository {

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    /** 会话缓存（uid/vei——Cookie 有效期内复用）。 */
    @Volatile
    private var cachedUid: String? = null

    @Volatile
    private var cachedVei: String? = null

    private fun cookie(): String = try {
        val cm = android.webkit.CookieManager.getInstance()
        listOf("https://pc.woozooo.com", "https://www.lanzou.com", "https://pan.lanzoui.com")
            .mapNotNull { cm.getCookie(it) }
            .joinToString("; ")
    } catch (_: Exception) {
        ""
    }

    private suspend fun session(): Pair<String, String> =
        withContext(Dispatchers.IO) {
            cachedUid?.let { u -> cachedVei?.let { v -> return@withContext u to v } }
            val c = cookie()
            if (c.isBlank()) {
                throw IllegalStateException("蓝奏云未登录——请到「账号」页登录蓝奏云")
            }
            val page = client.newCall(
                Request.Builder()
                    .url("https://pc.woozooo.com/mydisk.php?item=files&action=index")
                    .header("User-Agent", UA)
                    .header("Cookie", c)
                    .build()
            ).execute().use { resp ->
                if (!resp.isSuccessful) {
                    throw IllegalStateException("蓝奏云会话页 HTTP ${resp.code}——登录可能已过期")
                }
                resp.body?.string() ?: ""
            }
            val uid = Regex("uid=([^'\"&;]+)").find(page)?.groupValues?.get(1)
                ?: throw IllegalStateException("蓝奏云会话提取失败（uid 未找到——Cookie 可能过期）")
            val vei = Regex("\"?vei\"?\\s*[:=]\\s*['\"]?([A-Za-z0-9_-]+)")
                .find(page)?.groupValues?.get(1).orEmpty()
            cachedUid = uid
            cachedVei = vei
            appLog.info("drive", "[lanzou] 会话提取成功 uid=${uid.take(8)}…")
            uid to vei
        }

    private fun douploadBlocking(uid: String, vei: String, form: Map<String, String>): JSONArray {
        val c = cookie()
        val builder = FormBody.Builder()
        form.forEach { (k, v) -> builder.add(k, v) }
        val req = Request.Builder()
            .url("https://pc.woozooo.com/doupload.php?uid=$uid&vei=$vei")
            .header("User-Agent", UA)
            .header("Referer", "https://pc.woozooo.com/mydisk.php")
            .apply { if (c.isNotBlank()) header("Cookie", c) }
            .post(builder.build())
            .build()
        val body = client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw IllegalStateException("蓝奏云 API HTTP ${resp.code}")
            }
            resp.body?.string() ?: ""
        }
        val root = JSONObject(body)
        val zt = root.optInt("zt", -1)
        if (zt != 1) {
            throw IllegalStateException(
                "蓝奏云 API 失败（zt=$zt ${root.optString("info").take(50)}）——登录可能已过期"
            )
        }
        return root.optJSONObject("info")?.optJSONArray("text") ?: JSONArray()
    }

    override suspend fun listFiles(pdirFid: String): List<DriveFile> =
        withContext(Dispatchers.IO) {
            val (uid, vei) = session()
            val out = ArrayList<DriveFile>()
            // task=47：文件夹
            runCatching {
                douploadBlocking(uid, vei, mapOf("task" to "47", "folder_id" to pdirFid))
            }.getOrNull()?.let { arr ->
                for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { o ->
                        val name = o.optString("name")
                        if (name.isNotEmpty()) {
                            out.add(
                                DriveFile(
                                    fid = o.optString("fol_id", o.optLong("fol_id").toString()),
                                    name = name,
                                    size = 0L,
                                    isDir = true,
                                    updatedAt = "",
                                )
                            )
                        }
                    }
                }
            }
            // task=5：文件（分页）
            var pg = 1
            while (true) {
                val arr = runCatching {
                    douploadBlocking(
                        uid, vei,
                        mapOf("task" to "5", "folder_id" to pdirFid, "pg" to pg.toString()),
                    )
                }.getOrNull() ?: break
                if (arr.length() == 0) break
                for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { o ->
                        val name = o.optString("name")
                        if (name.isNotEmpty()) {
                            out.add(
                                DriveFile(
                                    fid = o.optString("id", o.optLong("id").toString()),
                                    name = name,
                                    size = parseSize(o.optString("size")),
                                    isDir = false,
                                    updatedAt = "",
                                )
                            )
                        }
                    }
                }
                pg++
            }
            out
        }

    override suspend fun getDownloadUrl(fid: String): String =
        withContext(Dispatchers.IO) {
            val (uid, vei) = session()
            // task=22：取文件分享信息（fid→share f_id + pwd）
            val share = douploadBlocking(uid, vei, mapOf("task" to "22", "file_id" to fid))
            val o = share.optJSONObject(0) ?: JSONObject()
            val shareFid = o.optString("f_id")
            val pwd = o.optString("pwd", "")
            if (shareFid.isEmpty()) {
                appLog.error("drive", "[lanzou] task=22 响应无分享信息")
                throw IllegalStateException("蓝奏云分享信息获取失败——详见日志")
            }
            // 分享页解析（与 LanzouShareResolver 同规格：iframe→sign→ajaxm）
            resolveShare(shareFid, pwd)
        }

    override suspend fun getDownloadUrls(fid: String, count: Int): List<String> =
        listOf(getDownloadUrl(fid))

    /** 分享页三步流（与 LanzouShareResolver 同规格——私有共享实现避免循环依赖）。 */
    private fun resolveShare(shareId: String, pwd: String): String {
        val c = cookie()
        val headers = mapOf(
            "User-Agent" to UA,
            "Referer" to "https://pan.lanzoui.com/",
        )
        val shareUrl = "https://pan.lanzoui.com/$shareId${if (pwd.isBlank()) "" else "?pwd=$pwd"}"
        val page = get(shareUrl, headers)
        val iframeMatch = Regex("<iframe[^>]+src=.([^\\s\"]*fn\\?[^\\s\"]*).")
            .find(page) ?: Regex("<iframe[^>]+src=.([^\\s\"]*fn[^\\s\"]*).").find(page)
        ?: throw IllegalStateException("蓝奏云分享页解析失败（下载入口未找到）")
        val iframeUrl = if (iframeMatch.groupValues[1].startsWith("http")) {
            iframeMatch.groupValues[1]
        } else {
            "https://pan.lanzoui.com" + iframeMatch.groupValues[1]
        }
        val dlPage = get(iframeUrl, headers)
        val sign = (Regex("'sign'\\s*:\\s*'([^']+)'").find(dlPage)?.groupValues?.get(1)
            ?: Regex("data-sign=.([A-Za-z0-9]+).").find(dlPage)?.groupValues?.get(1))
        val sign2 = sign ?: throw IllegalStateException("蓝奏云签名提取失败")
        val post = client.newCall(
            Request.Builder()
                .url("https://pan.lanzoui.com/ajaxm.php")
                .post(
                    FormBody.Builder()
                        .add("action", "downprocess")
                        .add("sign", sign2)
                        .add("kd", "1")
                        .add("ves", "1")
                        .build()
                )
                .header("User-Agent", UA)
                .header("Referer", iframeUrl)
                .header("X-Requested-With", "XMLHttpRequest")
                .apply { if (c.isNotBlank()) header("Cookie", c) }
                .build()
        ).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("蓝奏云接口 HTTP ${resp.code}")
            resp.body?.string() ?: ""
        }
        val data = JSONObject(post)
        if (data.optInt("zt") != 1) {
            throw IllegalStateException("蓝奏云直链失败：${data.optString("info").take(40)}")
        }
        var dom = data.optString("dom")
        if (dom.startsWith("//")) dom = "https:$dom"
        if (dom.isNotEmpty() && !dom.startsWith("http")) dom = "https://$dom"
        val path = data.optString("url")
        if (dom.isEmpty() || path.isEmpty()) throw IllegalStateException("蓝奏云直链为空")
        return "${dom.trimEnd('/')}/file/${path.trimStart('/')}"
    }

    private fun get(url: String, headers: Map<String, String>): String {
        val builder = Request.Builder().url(url)
        headers.forEach { (k, v) -> builder.header(k, v) }
        cookie().takeIf { it.isNotBlank() }?.let { builder.header("Cookie", it) }
        return client.newCall(builder.build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("蓝奏云页面 HTTP ${resp.code}")
            resp.body?.string() ?: throw IllegalStateException("蓝奏云页面空响应")
        }
    }

    private fun parseSize(s: String): Long {
        val m = Regex("([0-9.]+)\\s*([BKM]+)", RegexOption.IGNORE_CASE).find(s) ?: return 0L
        val n = m.groupValues[1].toDoubleOrNull() ?: return 0L
        return when (m.groupValues[2].uppercase()) {
            "B" -> n.toLong()
            "K", "KB" -> (n * 1024).toLong()
            "M", "MB" -> (n * 1024 * 1024).toLong()
            else -> 0L
        }
    }

    private companion object {
        const val UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
}
