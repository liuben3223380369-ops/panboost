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
) : DriveRepository {

    override suspend fun listFiles(pdirFid: String): List<DriveFile> {
        val body = api.listFiles(pdirFid = pdirFid).string()
        val root = JSONObject(body)
        checkCode(root)
        val list = root.optJSONObject("data")?.optJSONArray("list")
            ?: return emptyList()
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
        val body = api.getDownloadUrl(body = fidsBody.create(fid)).string()
        val root = JSONObject(body)
        checkCode(root)
        val data = root.opt("data")
        // YunX 实锤：data 为数组 [fid, name, download_url, size]
        val url = when (data) {
            is org.json.JSONArray -> data.optString(2)
            is JSONObject -> data.optString("download_url")
            else -> ""
        }
        require(url.startsWith("http")) { "直链解析失败：$body" }
        return url
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
