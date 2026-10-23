package org.panboost.core.network

import org.json.JSONObject
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * UC 网盘仓库（v6.6.0——与 QuarkDriveRepository 同构，仅 API 实例/
 * 特征键不同；解析逻辑经 CookieKit 共享）。
 *
 * OpenList quark_uc 驱动实证：两家 API 响应形态完全一致
 * （code/message/data.list[]、data 数组包对象 download_url）。
 */
@Singleton
class UcDriveRepository @Inject constructor(
    private val api: UcApi,
    private val fidsBody: FidsBodyFactory,
    private val appLog: org.panboost.core.logging.AppLog,
) : DriveRepository {

    override suspend fun listFiles(pdirFid: String): List<DriveFile> {
        val body = try {
            api.listFiles(pdirFid = pdirFid).string()
        } catch (e: retrofit2.HttpException) {
            throw IllegalStateException(mapHttpError(e))
        }
        val root = JSONObject(body)
        checkCode(root)
        val list = root.optJSONObject("data")?.optJSONArray("list")
        if (list == null) {
            appLog.warn("drive", "[uc] list 响应无 data.list：${body.take(160)}")
            throw IllegalStateException(
                "UC 网盘列表为空响应（登录态可能已失效）——请到「账号」页删除 UC 后重新登录"
            )
        }
        return (0 until list.length()).mapNotNull { i ->
            val o = list.optJSONObject(i) ?: return@mapNotNull null
            DriveFile(
                fid = o.optString("fid"),
                name = o.optString("file_name"),
                size = o.optLong("size"),
                isDir = o.optBoolean("dir"),
                updatedAt = o.optString("updated_at"),
            )
        }.filter { it.fid.isNotEmpty() }
    }

    override suspend fun getDownloadUrl(fid: String): String {
        val body = try {
            api.getDownloadUrl(body = fidsBody.create(fid)).string()
        } catch (e: retrofit2.HttpException) {
            throw IllegalStateException(mapHttpError(e))
        }
        val root = JSONObject(body)
        checkCode(root)
        val url = CookieKit.extractDownloadUrl(root.opt("data"))
        if (!url.startsWith("http")) {
            appLog.error("drive", "[uc] 直链响应无 download_url：${body.take(300)}")
            throw IllegalStateException(
                "该文件未能取得直链（可能无下载权限或登录态受限）——详见日志"
            )
        }
        return url
    }

    override suspend fun getDownloadUrls(fid: String, count: Int): List<String> {
        val urls = linkedSetOf<String>()
        repeat(count.coerceIn(1, MULTI_URL_MAX)) {
            try {
                urls.add(getDownloadUrl(fid))
            } catch (_: Exception) {
            }
        }
        return urls.toList()
    }

    private fun mapHttpError(e: retrofit2.HttpException): String = when (e.code()) {
        401, 403 -> "UC 登录已过期——请到「账号」页重新登录 UC"
        429 -> "请求过于频繁被限流——请稍后再试"
        else -> "UC 网盘接口错误 HTTP ${e.code()}"
    }

    private fun checkCode(root: JSONObject) {
        val code = root.optInt("code", 0)
        val status = root.optInt("status", 0)
        if (code != 0 && status != 200) {
            throw IllegalStateException(
                "UC API code=$code: ${root.optString("message").take(80)}"
            )
        }
    }

    private companion object {
        const val MULTI_URL_MAX = 4
    }
}
