package org.panboost.core.network

import okhttp3.ResponseBody
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * 夸克 Web API（第 4 周）。
 *
 * 网页版前端（pan.quark.cn 网页版）自己调用的公开接口 +
 * 用户自己的登录 Cookie——礼貌客户端模式，不逆向任何协议
 * 加密（与 Kivy 版同一安全边界）。规格来自 YunX 实锤：
 * - 列表 GET /1/clouddrive/file/sort，data.list[]：fid/
 *   file_name/size/dir
 * - 直链 POST /1/clouddrive/file/download，data 数组
 *   [fid, file_name, download_url, size]
 * 响应用 ResponseBody 返回（org.json 手解析——零转换器依赖，
 * 夸克响应字段少且稳定）。
 */
interface QuarkApi {

    @GET("1/clouddrive/file/sort")
    suspend fun listFiles(
        @Query("pr") pr: String = "ucpro",
        @Query("fr") fr: String = "pc",
        @Query("pdir_fid") pdirFid: String,
        @Query("_page") page: Int = 1,
        @Query("_size") size: Int = 100,
        @Query("_sort") sort: String = "file_type:asc,updated_at:desc",
        @Query("fetch_all_file") fetchAll: Int = 1,
        @Query("fetch_total") fetchTotal: Int = 1,
    ): ResponseBody

    @POST("1/clouddrive/file/download")
    suspend fun getDownloadUrl(
        @Query("pr") pr: String = "ucpro",
        @Query("fr") fr: String = "pc",
        @retrofit2.http.Body body: okhttp3.RequestBody,
    ): ResponseBody

    companion object {
        const val BASE_URL = "https://drive-pc.quark.cn/"

        /** 网页版客户端 UA（YunX 实锤规格）。 */
        const val CLIENT_UA =
            "quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 " +
                    "Electron/18.3.5.12-a038f7b798 Safari/537.36 " +
                    "Channel/pckk_other_ch"

        const val REFERER = "https://pan.quark.cn/"
        const val LOGIN_URL = "https://pan.quark.cn/"
        const val COOKIE_DOMAIN = "https://pan.quark.cn"

        /** 登录成功特征键（命中即认为已登录）。 */
        const val AUTH_COOKIE_KEYS = listOf("__pus", "__puus")
    }
}
