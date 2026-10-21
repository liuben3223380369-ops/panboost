package org.panboost.core.network

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.panboost.core.domain.ShareFile
import org.panboost.core.domain.ShareRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 夸克分享仓库实现（v4.2.0）。
 *
 * 三步流（v3.2.8 resolve_quark 规格）：
 * token（pwd_id+passcode→stoken）→ detail（文件列表）→
 * download（逐文件直链）。登录态由拦截器携带 Cookie；
 * code!=0 的"需登录"错误码（4100805/4101202）映射为
 * 友好提示。链接内提取码（?code=/&pwd=/#xxx）自动识别，
 * 手输提取码优先。
 */
@Singleton
class QuarkShareRepository @Inject constructor(
    private val api: QuarkShareApi,
) : ShareRepository {

    override suspend fun resolve(shareUrl: String, passcode: String): List<ShareFile> {
        val key = extractKey(shareUrl)
            ?: throw IllegalArgumentException("无法从链接提取分享码（需 quark.cn/s/xxxx 格式）")
        val code = passcode.ifBlank { extractPasscode(shareUrl) }

        // 1. token → stoken
        val tokenBody = """{"pwd_id":"$key","passcode":"$code"}"""
            .toRequestBody("application/json".toMediaType())
        val tokenResp = api.token(body = tokenBody).string()
        val tokenJson = JSONObject(tokenResp)
        checkShareCode(tokenJson, "分享令牌获取失败")
        val stoken = tokenJson.optJSONObject("data")?.optString("stoken").orEmpty()
        require(stoken.isNotEmpty()) { "接口未返回 stoken" }

        // 2. detail → 文件列表（只取文件，文件夹分享不展开——v3.2.8 同语义）
        val detailResp = api.detail(pwdId = key, stoken = stoken).string()
        val detailJson = JSONObject(detailResp)
        checkShareCode(detailJson, "文件列表获取失败")
        val list = detailJson.optJSONObject("data")?.optJSONArray("list")
            ?: return emptyList()
        val items = (0 until list.length()).mapNotNull { list.optJSONObject(it) }
            .filter { !it.optBoolean("dir") && it.optString("fid").isNotEmpty() }
        if (items.isEmpty()) {
            throw IllegalStateException("分享内没有可直接下载的文件（空分享或文件夹分享）")
        }

        // 3. download → 逐文件直链
        return items.map { item ->
            val fid = item.optString("fid")
            val dlResp = api.download(pwdId = key, stoken = stoken, fid = fid).string()
            val dlJson = JSONObject(dlResp)
            checkShareCode(dlJson, "未取得直链: ${item.optString("file_name")}")
            val url = dlJson.optJSONObject("data")?.optString("download_url").orEmpty()
            require(url.startsWith("http")) { "接口未返回 download_url" }
            ShareFile(
                name = item.optString("file_name").ifEmpty { "quark.bin" },
                size = item.optLong("size"),
                url = url,
            )
        }
    }

    /** 分享 key：quark.cn/s/([A-Za-z0-9]+)。 */
    private fun extractKey(url: String): String? {
        val m = Regex(QuarkShareApi.SHARE_URL_PATTERN).find(url)
        return m?.groupValues?.get(1)
    }

    /** 链接内提取码：?code= / &pwd= / #4~8 位。 */
    private fun extractPasscode(url: String): String {
        val m = Regex("[?&](?:code|pwd)=([A-Za-z0-9]+)").find(url)
            ?: Regex("#([A-Za-z0-9]{4,8})$").find(url)
        return m?.groupValues?.get(1).orEmpty()
    }

    private fun checkShareCode(root: JSONObject, what: String) {
        val code = root.optInt("code", 0)
        if (code == 0) return
        val msg = root.optString("message")
        if (code == 4100805 || code == 4101202 || msg.contains("登录")) {
            throw IllegalStateException(
                "夸克分享解析需登录 Cookie：请先在「网盘」页登录夸克账号"
            )
        }
        throw IllegalStateException("$what: ${msg.ifEmpty { "$code" }}")
    }
}
