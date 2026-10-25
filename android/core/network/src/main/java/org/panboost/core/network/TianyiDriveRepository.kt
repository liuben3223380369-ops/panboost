package org.panboost.core.network

import okhttp3.ResponseBody
import org.json.JSONObject
import org.panboost.core.domain.DriveFile
import org.panboost.core.domain.DriveRepository
import retrofit2.http.GET
import retrofit2.http.Query
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 天翼云盘仓库（v7.0.0——OpenList 189 驱动规格：Cookie 直连）。
 *
 * 规格（OpenList util.go 实证）：
 * - List: GET cloud.189.cn/api/open/file/listFiles.action
 *   参数 pageSize/pageNum/mediaType/folderId/iconOption/orderBy/descending
 *   响应 FileListAO：FolderList[]（id/name/lastOpTime）+ FileList[]
 *   （id/name/size/lastOpTime）——分页至 count==0
 * - Link: GET cloud.189.cn/api/portal/getFileInfo.action?fileId
 *   → FileDownloadUrl → 跟 302 两跳取最终直链
 * - 会话：Cookie（SessionKey 由 Cookie 维系）；Referer cloud.189.cn/
 */
@Singleton
class TianyiDriveRepository @Inject constructor(
    private val api: TianyiApi,
    private val appLog: org.panboost.core.logging.AppLog,
) : DriveRepository {

    override suspend fun listFiles(pdirFid: String): List<DriveFile> {
        // v7.4.1：天翼根目录 folderId=-1（Home 传 "0" 表根目录）
        val folderId = if (pdirFid == "0") "-1" else pdirFid
        val out = ArrayList<DriveFile>()
        var pageNum = 1
        while (true) {
            val body = try {
                api.listFiles(folderId = folderId, pageNum = pageNum).string()
            } catch (e: retrofit2.HttpException) {
                throw IllegalStateException(mapHttpError(e))
            }
            val root = JSONObject(body)
            if (root.optString("res_code")?.isNotEmpty() == true &&
                root.optString("res_code") != "0"
            ) {
                appLog.warn("drive", "[tianyi] list 响应异常：${body.take(160)}")
                throw IllegalStateException(
                    "天翼云盘列表失败（${root.optString("res_message").take(60)}）——登录态可能过期，请到「账号」页重新登录"
                )
            }
            val ao = root.optJSONObject("fileListAO") ?: break
            val count = ao.optInt("count", 0)
            if (count == 0) break
            ao.optJSONArray("folderList")?.let { arr ->
                for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { o ->
                        out.add(
                            DriveFile(
                                fid = o.optLong("id").toString(),
                                name = o.optString("name"),
                                size = 0L,
                                isDir = true,
                                updatedAt = o.optString("lastOpTime"),
                            )
                        )
                    }
                }
            }
            ao.optJSONArray("fileList")?.let { arr ->
                for (i in 0 until arr.length()) {
                    arr.optJSONObject(i)?.let { o ->
                        out.add(
                            DriveFile(
                                fid = o.optLong("id").toString(),
                                name = o.optString("name"),
                                size = o.optLong("size"),
                                isDir = false,
                                updatedAt = o.optString("lastOpTime"),
                            )
                        )
                    }
                }
            }
            if (out.size >= count) break
            pageNum++
        }
        return out
    }

    override suspend fun getDownloadUrl(fid: String): String {
        // OpenList 规格：getFileInfo → FileDownloadUrl → 302 两跳追直链
        val body = try {
            api.getFileInfo(fileId = fid).string()
        } catch (e: retrofit2.HttpException) {
            throw IllegalStateException(mapHttpError(e))
        }
        val root = JSONObject(body)
        // OpenList 实证形态：res_data 为 "//..." 协议相对直链
        //（302 追链由 Worker 探测层统一处理）
        val rd = root.opt("res_data")
        val firstUrl = when {
            rd is String && rd.startsWith("//") -> "https:$rd"
            rd is String && rd.startsWith("http") -> rd
            rd is JSONObject -> {
                val u = rd.optString("fileDownloadUrl")
                when {
                    u.startsWith("//") -> "https:$u"
                    u.startsWith("http") -> u
                    else -> ""
                }
            }
            else -> ""
        }
        if (!firstUrl.startsWith("http")) {
            appLog.error("drive", "[tianyi] getFileInfo 响应：${body.take(200)}")
            throw IllegalStateException("天翼直链解析失败——详见日志")
        }
        return firstUrl
    }

    override suspend fun getDownloadUrls(fid: String, count: Int): List<String> =
        listOf(getDownloadUrl(fid))

    private fun mapHttpError(e: retrofit2.HttpException): String = when (e.code()) {
        401, 403 -> "天翼登录已过期——请到「账号」页重新登录天翼"
        429 -> "请求过于频繁被限流——请稍后再试"
        else -> "天翼接口错误 HTTP ${e.code()}"
    }
}

/** 天翼 Web API（Retrofit——Cookie/Referer 由拦截器供给）。 */
interface TianyiApi {

    @GET("api/open/file/listFiles.action")
    suspend fun listFiles(
        @Query("pageSize") pageSize: Int = 60,
        @Query("pageNum") pageNum: Int,
        @Query("mediaType") mediaType: Int = 0,
        @Query("folderId") folderId: String,
        @Query("iconOption") iconOption: Int = 5,
        @Query("orderBy") orderBy: String = "lastOpTime",
        @Query("descending") descending: Boolean = true,
    ): ResponseBody

    @GET("api/portal/getFileInfo.action")
    suspend fun getFileInfo(
        @Query("fileId") fileId: String,
    ): ResponseBody

    companion object {
        const val BASE_URL = "https://cloud.189.cn/"
        const val REFERER = "https://cloud.189.cn/"
    }
}
