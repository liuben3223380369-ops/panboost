package org.panboost.core.network

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import org.panboost.core.domain.ShareFile
import org.panboost.core.domain.ShareRepository
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 蓝奏云分享解析（v5.0.0：v3.2.8 resolve_lanzou 原生迁移）。
 *
 * HTML 页面流（无 JSON API 前段，Retrofit 不适用——纯 OkHttp）：
 * 1. GET 分享页 → 正则取 iframe src（fn? 下载入口）
 * 2. GET 下载页 → 正则取 sign 签名
 * 3. POST /ajaxm.php（downprocess）→ dom + url → 拼直链
 * 免登录；多域名（lanzou[a-z]*.com 等）由 URL 本身决定。
 * 单文件分享（蓝奏页面结构）——返回单元素列表。
 */
@Singleton
class LanzouShareResolver @Inject constructor() : ShareRepository {

    private val client = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    override suspend fun resolve(shareUrl: String, passcode: String): List<ShareFile> =
        withContext(Dispatchers.IO) {
            var url = shareUrl.trim()
            if (!url.contains("://")) url = "https://$url"
            val base = Regex("(https?://[^/]+)").find(url)?.groupValues?.get(1)
                ?: throw IllegalArgumentException("链接格式异常")
            val headers = mapOf(
                "User-Agent" to UA,
                "Referer" to url,
                "Accept-Language" to "zh-CN,zh;q=0.9",
            )

            // 1. 分享页 → iframe 下载入口
            val page = get("$url${if (passcode.isBlank()) "" else "?pwd=$passcode"}", headers)
            val iframeMatch = Regex("""<iframe[^>]+src="([^"]*fn\?[^"]*)"""").find(page)
                ?: Regex("""src="(/fn\?[^"]+)"""").find(page)
                ?: throw IllegalStateException("未在分享页找到下载入口（链接可能失效或需要提取密码）")
            val iframeUrl = if (iframeMatch.groupValues[1].startsWith("http")) {
                iframeMatch.groupValues[1]
            } else {
                base + iframeMatch.groupValues[1]
            }

            // 2. 下载页 → sign
            val dlPage = get(iframeUrl, headers)
            val sign = Regex("""'sign'\s*:\s*'([^']+)'""").find(dlPage)?.groupValues?.get(1)
                ?: Regex("""data-sign="([^"]+)"""").find(dlPage)?.groupValues?.get(1]
                ?: Regex("""sign\s*[:=]\s*'([A-Za-z0-9:%\-]+)'""").find(dlPage)?.groupValues?.get(1]
                ?: throw IllegalStateException("未提取到签名参数")

            // 3. POST /ajaxm.php → dom + url
            val post = client.newCall(
                Request.Builder()
                    .url("$base/ajaxm.php")
                    .post(
                        FormBody.Builder()
                            .add("action", "downprocess")
                            .add("sign", sign)
                            .add("kd", "1")
                            .add("ves", "1")
                            .build()
                    )
                    .header("User-Agent", UA)
                    .header("Referer", iframeUrl)
                    .header("X-Requested-With", "XMLHttpRequest")
                    .build()
            ).execute().use { resp ->
                if (!resp.isSuccessful) throw IllegalStateException("接口请求失败(${resp.code})")
                resp.body?.string() ?: throw IllegalStateException("接口响应空")
            }
            val data = JSONObject(post)
            if (data.optInt("zt") != 1) {
                throw IllegalStateException("接口返回异常: ${data.optString("info")}")
            }
            var dom = data.optString("dom")
            if (dom.startsWith("//")) dom = "https:$dom"
            if (dom.isNotEmpty() && !dom.startsWith("http")) dom = "https://$dom"
            val path = data.optString("url")
            if (dom.isEmpty() || path.isEmpty()) {
                throw IllegalStateException("接口未返回直链")
            }
            val direct = "${dom.trimEnd('/')}/file/${path.trimStart('/')}"

            // 文件名从分享页 <title> 提取（蓝奏页面惯例）
            val name = Regex("""<title>(.*?)</title>""").find(page)
                ?.groupValues?.get(1)?.substringBeforeLast(" - ")?.trim()
                ?.ifEmpty { null } ?: "lanzou.bin"

            listOf(ShareFile(name = name, size = 0L, url = direct))
        }

    private fun get(url: String, headers: Map<String, String>): String {
        val builder = Request.Builder().url(url)
        headers.forEach { (k, v) -> builder.header(k, v) }
        return client.newCall(builder.build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IllegalStateException("页面请求失败(${resp.code})")
            resp.body?.string() ?: throw IllegalStateException("页面响应空")
        }
    }

    private companion object {
        const val UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
}
