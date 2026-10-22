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
        @Query("uc_param_str") ucParamStr: String = "",
        @Query("pdir_fid") pdirFid: String,
        @Query("_page") page: Int = 1,
        @Query("_size") size: Int = 100,
        @Query("_fetch_total") fetchTotal: Int = 1,
        @Query("_fetch_sub_dirs") fetchSubDirs: Int = 0,
        @Query("_sort") sort: String = "file_type:asc,updated_at:desc",
        @Query("_fetch_full_path") fetchFullPath: Int = 0,
        @Query("fetch_all_file") fetchAll: Int = 1,
        @Query("fetch_risk_file_name") fetchRiskFileName: Int = 1,
    ): ResponseBody

    @POST("1/clouddrive/file/download")
    suspend fun getDownloadUrl(
        @Query("pr") pr: String = "ucpro",
        @Query("fr") fr: String = "pc",
        @Query("uc_param_str") ucParamStr: String = "",
        @retrofit2.http.Body body: okhttp3.RequestBody,
    ): ResponseBody

    companion object {
        const val BASE_URL = "https://drive-pc.quark.cn/"

        /**
         * 网页版客户端 UA（v5.3.0：对齐 quark-auto-save 实战版本——
         * 3072★项目长期验证的形态，旧 2.5.20 可能已过风控期）。
         */
        const val CLIENT_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) quark-cloud-drive/3.14.2 " +
                    "Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 " +
                    "Channel/pckk_other_ch"

        const val REFERER = "https://pan.quark.cn/"
        const val LOGIN_URL = "https://pan.quark.cn/"
        const val COOKIE_DOMAIN = "https://pan.quark.cn"

        /**
         * 登录成功特征键（v5.3.0 对齐 quark-auto-save 实战：__uid 为
         * 有效 Cookie 的标志键；__pus/__puus 为会话键）。
         */
        val AUTH_COOKIE_KEYS = listOf("__uid", "__pus", "__puus")
    }
}
