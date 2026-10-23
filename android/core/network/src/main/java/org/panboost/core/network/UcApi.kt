package org.panboost.core.network

import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * UC 网盘 Web API（v6.6.0——OpenList quark_uc 驱动实锤：夸克/UC
 * 同源 clouddrive API，仅 baseUrl/UA/pr 三参数不同）。
 *
 * 规格（OpenList meta.go UC 实例）：
 * - api: https://pc-api.uc.cn/1/clouddrive
 * - UA: uc-cloud-drive/2.5.20 Chrome/100 Electron/18
 * - pr: UCBrowser（夸克是 ucpro）
 * - 接口路径/参数与夸克完全一致（file/sort、file/download）
 * - 登录 Cookie 同体系（__pus/__puus，authKeys 含 __uid）
 */
interface UcApi {

    @GET("1/clouddrive/file/sort")
    suspend fun listFiles(
        @Query("pr") pr: String = PR,
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
        @Query("pr") pr: String = PR,
        @Query("fr") fr: String = "pc",
        @Query("uc_param_str") ucParamStr: String = "",
        @Body body: okhttp3.RequestBody,
    ): ResponseBody

    companion object {
        const val BASE_URL = "https://pc-api.uc.cn/"
        const val PR = "UCBrowser"
        const val CLIENT_UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
                    "(KHTML, like Gecko) uc-cloud-drive/2.5.20 " +
                    "Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 " +
                    "Safari/537.36 Channel/pckk_other_ch"
        const val REFERER = "https://drive.uc.cn"
    }
}
