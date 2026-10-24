package org.panboost.core.network

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 百度网盘仓库（v7.2.0——OpenList baidu_youth 驱动规格：Cookie 直连）。
 *
 * 关键研究结论：OpenList 的 baidu_netdisk 走 OAuth（access_token 必须），
 * 但 baidu_youth 驱动实证了网页版 youth API 的 Cookie 直连路线：
 * - 列表：GET pan.baidu.com/youth/api/list?dir&page&num（app_id=250528
 *   web=1 clienttype=0）——标准 Cookie 会话
 * - 会话参数：GET /api/gettemplatevariable?fields=["bdstoken","uk","sk"]
 *   （Cookie 有效即返回）
 * - 直链：GET /youth/api/locatedownload?path&rand&sign&time——
 *   rand=SHA1(uk+sk+time+"0")、sign=MD5(md5_uk_fid_time)——纯本地签名
 * - 请求头：浏览器 UA + Referer pan.baidu.com/youth/pan/main + Cookie
 */
@Singleton
class BaiduDriveRepository @Inject constructor(
    private val appLog: org.panboost.core.logging.AppLog,
) : DriveRepository {

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    // 会话缓存
    @Volatile private var uk: Long = 0
    @Volatile private var bdstoken: String = ""
    @Volatile private var sk: String = ""

    private fun cookie(): String = try {
        val cm = android.webkit.CookieManager.getInstance()
        listOf("https://pan.baidu.com", "https://passport.baidu.com")
            .mapNotNull { cm.getCookie(it) }
            .joinToString("; ")
    } catch (_: Exception) {
        ""
    }

    private fun baseHeaders(): Request.Builder = Request.Builder()
        .header("Accept", "application/json, text/plain, */*")
        .header("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        .header("User-Agent", UA)
        .header("Origin", BASE)
        .header("Referer", "$BASE/youth/pan/main#/index?category=all")
        .header("X-Requested-With", "XMLHttpRequest")
        .apply { cookie().takeIf { it.isNotBlank() }?.let { header("Cookie", it) } }

    private suspend fun get(path: String, query: Map<String, String>): JSONObject =
        JSONObject(doGet(path, query))

    private suspend fun doGet(path: String, query: Map<String, String>): String =
        withContext(Dispatchers.IO) {
            val url = buildString {
                append(BASE).append(path)
                append("?app_id=$APP_ID&clienttype=0&web=1")
                query.forEach { (k, v) -> append("&$k=").append(android.net.Uri.encode(v)) }
            }
            client.newCall(baseHeaders().url(url).get().build()).execute().use { resp ->
                if (!resp.isSuccessful) {
                    throw IllegalStateException("百度 API HTTP ${resp.code}")
                }
                resp.body?.string() ?: ""
            }
        }

    /** 会话参数提取（bdstoken/uk/sk——Cookie 有效时返回）。 */
    private suspend fun ensureSession() {
        if (uk != 0L && sk.isNotEmpty()) return
        val body = doGet(
            "/api/gettemplatevariable",
            mapOf("fields" to "[\"bdstoken\",\"uk\",\"sk\"]"),
        )
        val root = JSONObject(body)
        // 双形态：records[0] 或 result
        val rec = root.optJSONArray("records")?.optJSONObject(0)
            ?: root.optJSONObject("result")
            ?: root.optJSONObject("data")
        uk = rec?.optLong("uk", 0L) ?: 0L
        bdstoken = rec?.optString("bdstoken").orEmpty()
        sk = rec?.optString("sk").orEmpty()
        if (uk == 0L || sk.isEmpty()) {
            appLog.warn("drive", "[baidu] 会话提取失败：${body.take(160)}")
            throw IllegalStateException("百度会话提取失败——登录可能已过期，请到「账号」页重新登录百度")
        }
        appLog.info("drive", "[baidu] 会话提取成功 uk=$uk")
    }

    override suspend fun listFiles(pdirFid: String): List<DriveFile> =
        withContext(Dispatchers.IO) {
            if (cookie().isBlank()) {
                throw IllegalStateException("百度网盘未登录——请到「账号」页登录百度")
            }
            // pdirFid 为路径（百度 list 用 dir 路径参数——Home 面包屑传 fid，
            // 百度场景传路径字符串）
            val out = ArrayList<DriveFile>()
            var page = 1
            while (true) {
                val root = get(
                    "/youth/api/list",
                    mapOf(
                        "dir" to pdirFid,
                        "page" to page.toString(),
                        "num" to "1000",
                        "order" to "name",
                        "desc" to "0",
                    ),
                )
                val errno = root.optInt("errno", -1)
                if (errno != 0) {
                    throw IllegalStateException("百度列表失败 errno=$errno——登录可能过期")
                }
                val list = root.optJSONArray("list") ?: break
                if (list.length() == 0) break
                for (i in 0 until list.length()) {
                    list.optJSONObject(i)?.let { o ->
                        out.add(
                            DriveFile(
                                fid = o.optLong("fs_id").toString(),
                                name = o.optString("server_filename"),
                                size = o.optLong("size"),
                                isDir = o.optInt("isdir") == 1,
                                updatedAt = "",
                            )
                        )
                    }
                }
                if (list.length() < 1000) break
                page++
            }
            out
        }

    override suspend fun getDownloadUrl(fid: String): String =
        withContext(Dispatchers.IO) {
            ensureSession()
            // 先按 fid 查文件元数据（path/md5）——用 filemetas
            val root = get(
                "/api/filemetas",
                mapOf("target" to "[\"$fid\"]", "dlink" to "1", "web" to "5"),
            )
            val info = root.optJSONArray("info")?.optJSONObject(0)
            val path = info?.optString("path").orEmpty()
            val md5 = info?.optString("md5").orEmpty()
            if (path.isEmpty() || md5.isEmpty()) {
                appLog.error("drive", "[baidu] filemetas 响应：${root.toString().take(200)}")
                throw IllegalStateException("百度文件元数据获取失败——详见日志")
            }
            // locatedownload 签名（youth 规格：本地 SHA1/MD5）
            val now = System.currentTimeMillis().toString()
            val rand = sha1Hex("$uk$sk${now}0")
            val sign = md5Hex("${md5}_${uk}_${fid}_$now")
            val dl = get(
                "/youth/api/locatedownload",
                mapOf(
                    "devuid" to "0",
                    "dp-logid" to now,
                    "path" to path,
                    "rand" to rand,
                    "sign" to sign,
                    "time" to now,
                ),
            )
            var url = dl.optString("url")
            if (url.isEmpty()) {
                appLog.error("drive", "[baidu] locatedownload 响应：${dl.toString().take(200)}")
                throw IllegalStateException("百度直链获取失败（errno=${dl.optInt("errno")}）——详见日志")
            }
            if (!url.contains("response-cache-control=")) {
                url += if (url.contains("?")) "&" else "?"
                url += "response-cache-control=private"
            }
            url
        }

    override suspend fun getDownloadUrls(fid: String, count: Int): List<String> =
        listOf(getDownloadUrl(fid))

    private fun sha1Hex(s: String): String =
        MessageDigest.getInstance("SHA-1").digest(s.toByteArray())
            .joinToString("") { "%02x".format(it) }

    private fun md5Hex(s: String): String =
        MessageDigest.getInstance("MD5").digest(s.toByteArray())
            .joinToString("") { "%02x".format(it) }

    private companion object {
        const val BASE = "https://pan.baidu.com"
        const val APP_ID = "250528"
        const val UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
}
