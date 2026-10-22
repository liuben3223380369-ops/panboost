package org.panboost.core.network

import org.json.JSONObject
import org.panboost.core.domain.ShareFile
import org.panboost.core.domain.ShareRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 123 云盘分享仓库（v5.0.0：v3.2.8 resolve_pan123 原生迁移）。
 *
 * 公开分享**免登录**（与夸克不同）。两步流：
 * 1. GET /api/share/info?shareKey&pwd → ShareKey/ShareKeyID
 * 2. GET /api/share/get?ShareKey&ShareKeyId&Limit=100 → InfoList[]
 *    （S3KeyTag/FileId/FileName/Size/IsDir）
 * 3. 逐文件 GET /api/share/get?...&S3KeyTag&FileId → InfoList[0].DownloadUrl
 * 直链带 Referer 下载（pcapi 头由 Worker 统一加）。
 */
@Singleton
class Pan123ShareRepository @Inject constructor(
    private val api: Pan123ShareApi,
) : ShareRepository {

    override suspend fun resolve(shareUrl: String, passcode: String): List<ShareFile> {
        val key = Regex("123pan\\.com/s/([A-Za-z0-9]+)").find(shareUrl)
            ?.groupValues?.get(1)
            ?: throw IllegalArgumentException("无法从链接提取 123 云盘分享码")
        val pwd = passcode.ifBlank {
            Regex("[?&](?:code|pwd)=([A-Za-z0-9]+)").find(shareUrl)
                ?.groupValues?.get(1).orEmpty()
        }

        // 1. info → ShareKey/ShareKeyID
        val infoJson = JSONObject(api.info(shareKey = key, pwd = pwd).string())
        checkCode(infoJson, "分享信息获取失败")
        val data = infoJson.optJSONObject("data")
            ?: throw IllegalStateException("分享信息响应异常")
        val sk = data.optString("ShareKey").ifEmpty { key }
        val skid = data.optString("ShareKeyID", data.optString("ShareKeyId"))

        // 2. get → 文件列表
        val listJson = JSONObject(api.list(shareKey = sk, shareKeyId = skid).string())
        checkCode(listJson, "文件列表获取失败")
        val items = listJson.optJSONObject("data")?.optJSONArray("InfoList")
            ?: throw IllegalStateException("分享内没有可直接下载的文件")
        val files = (0 until items.length())
            .mapNotNull { items.optJSONObject(it) }
            .filter { it.optInt("IsDir") == 0 }
        if (files.isEmpty()) {
            throw IllegalStateException("分享内没有可直接下载的文件（空分享或文件夹分享）")
        }

        // 3. 逐文件直链
        return files.map { item ->
            val dlJson = JSONObject(
                api.direct(
                    shareKey = sk,
                    shareKeyId = skid,
                    s3KeyTag = item.optString("S3KeyTag"),
                    fileId = item.optString("FileId"),
                ).string()
            )
            checkCode(dlJson, "未取得直链: ${item.optString("FileName")}")
            val url = dlJson.optJSONObject("data")
                ?.optJSONArray("InfoList")?.optJSONObject(0)
                ?.optString("DownloadUrl").orEmpty()
            require(url.startsWith("http")) {
                "接口未返回 DownloadUrl: ${item.optString("FileName")}"
            }
            ShareFile(
                name = item.optString("FileName").ifEmpty { "123pan.bin" },
                size = item.optLong("Size"),
                url = url,
            )
        }
    }

    private fun checkCode(root: JSONObject, what: String) {
        val code = root.optInt("code", 0)
        if (code != 0) {
            throw IllegalStateException("$what: ${root.optString("message").ifEmpty { "$code" }}")
        }
    }
}

/** 123 云盘 API（Retrofit；Referer 走通用拦截器不够——由 @Header 显式带）。 */
interface Pan123ShareApi {

    @retrofit2.http.GET("api/share/info")
    suspend fun info(
        @retrofit2.http.Query("shareKey") shareKey: String,
        @retrofit2.http.Query("pwd") pwd: String,
        @retrofit2.http.Header("Referer") referer: String = "https://www.123pan.com/",
    ): okhttp3.ResponseBody

    @retrofit2.http.GET("api/share/get")
    suspend fun list(
        @retrofit2.http.Query("ShareKey") shareKey: String,
        @retrofit2.http.Query("ShareKeyId") shareKeyId: String,
        @retrofit2.http.Query("Limit") limit: Int = 100,
        @retrofit2.http.Query("Offset") offset: Int = 0,
        @retrofit2.http.Header("Referer") referer: String = "https://www.123pan.com/",
    ): okhttp3.ResponseBody

    @retrofit2.http.GET("api/share/get")
    suspend fun direct(
        @retrofit2.http.Query("ShareKey") shareKey: String,
        @retrofit2.http.Query("ShareKeyId") shareKeyId: String,
        @retrofit2.http.Query("S3KeyTag") s3KeyTag: String,
        @retrofit2.http.Query("FileId") fileId: String,
        @retrofit2.http.Header("Referer") referer: String = "https://www.123pan.com/",
    ): okhttp3.ResponseBody

    companion object {
        const val BASE_URL = "https://www.123pan.com/"
    }
}
