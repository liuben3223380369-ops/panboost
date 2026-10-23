package org.panboost.core.network

import org.json.JSONObject
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 夸克网盘仓库实现（第 4 周）。
 *
 * - listFiles：GET /file/sort → data.list[]（fid/file_name/size/
 *   dir），org.json 手解析（零转换器依赖）
 * - getDownloadUrl：POST /file/download → data 数组
 *   [fid, name, url, size]（YunX 实锤形态）
 * - API 错误码：code!=0 抛 IllegalStateException（消息带 code/
 *   message——真机诊断友好）
 */
@Singleton
class QuarkDriveRepository @Inject constructor(
    private val api: QuarkApi,
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
            // v5.2.0：夸克对失效 Cookie 会返回"假成功"（code:0 但无 data）
            // ——记入日志供诊断（日志屏可见）
            appLog.warn("drive", "list 响应无 data.list：${body.take(160)}")
            throw IllegalStateException(
                "网盘列表为空响应（登录态可能已失效）——请到「账号」页删除夸克后重新登录"
            )
        }
        if (list.length() == 0) {
            appLog.info("drive", "目录为空（正常空目录）")
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

    private companion object {
        const val MULTI_URL_MAX = 4
    }

    override suspend fun getDownloadUrl(fid: String): String {
        val body = try {
            api.getDownloadUrl(body = fidsBody.create(fid)).string()
        } catch (e: retrofit2.HttpException) {
            throw IllegalStateException(mapHttpError(e))
        }
        val root = JSONObject(body)
        checkCode(root)
        // v5.3.1：真机日志实锤 download 响应形态——data 为数组，
        // 元素是对象 {fid, file_name, pdir_fid, download_url?, ...}；
        // v3.2.8 时代的裸数组 [fid, name, url, size] 形态已过时。
        // 旧解析 data.optString(2) 取裸数组下标 → 永远为空（列表
        // 200 成功却报"解析失败"的唯一根因）。
        val url = org.panboost.core.network.CookieKit.extractDownloadUrl(root.opt("data"))
        if (!url.startsWith("http")) {
            // code:0 却无 download_url——两种可能：Cookie 失效假成功
            // 或该文件无下载权限；完整响应记日志供诊断
            appLog.error("drive", "直链响应无 download_url：${body.take(300)}")
            throw IllegalStateException(
                "该文件未能取得直链（可能无下载权限或登录态受限）——详见日志"
            )
        }
        return url
    }

    override suspend fun getDownloadUrls(fid: String, count: Int): List<String> {
        // 夸克 download API 每次调用返回不同 CDN 节点（dl-pc-zb-jN.
        // drive.quark.cn 的 N 轮换）——逐次解析去重收集
        val urls = linkedSetOf<String>()
        repeat(count.coerceIn(1, MULTI_URL_MAX)) {
            try {
                urls.add(getDownloadUrl(fid))
            } catch (_: Exception) {
            }
        }
        return urls.toList()
    }

    /** HTTP 层错误映射（v5.1.0：401 = Cookie 过期引导重登）。 */
    private fun mapHttpError(e: retrofit2.HttpException): String = when (e.code()) {
        401, 403 -> "登录已过期（夸克 Cookie 约 3 小时限）——请到「账号」页重新登录夸克"
        429 -> "请求过于频繁被限流——请稍后再试"
        else -> "网盘接口错误 HTTP ${e.code()}"
    }

    private fun checkCode(root: JSONObject) {
        val code = root.optInt("code", 0)
        val status = root.optInt("status", 0)
        if (code != 0 && status != 200) {
            throw IllegalStateException(
                "夸克 API code=$code: ${root.optString("message").take(80)}"
            )
        }
    }
}
