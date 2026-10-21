package org.panboost.core.network

import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Query

/**
 * 夸克分享 Web API（v4.2.0，规格来自 v3.2.8 引擎 resolve_quark
 * 实锤——与网页端一致的三步流）：
 * 1. POST /1/clouddrive/share/sharepage/token → data.stoken
 * 2. GET  /1/clouddrive/share/sharepage/detail → data.list[]
 * 3. GET  /1/clouddrive/share/sharepage/download → data.download_url
 *
 * 需登录 Cookie（拦截器自动携带）；Referer=pan.quark.cn。
 * 响应用 ResponseBody + org.json 手解析（与 QuarkApi 同策略）。
 */
interface QuarkShareApi {

    @POST("1/clouddrive/share/sharepage/token")
    suspend fun token(
        @Query("pr") pr: String = "ucpro",
        @Query("fr") fr: String = "pc",
        @Body body: okhttp3.RequestBody,
    ): ResponseBody

    @GET("1/clouddrive/share/sharepage/detail")
    suspend fun detail(
        @Query("pr") pr: String = "ucpro",
        @Query("fr") fr: String = "pc",
        @Query("pwd_id") pwdId: String,
        @Query("stoken") stoken: String,
        @Query("pdir_fid") pdirFid: String = "0",
        @Query("_page") page: Int = 1,
        @Query("_size") size: Int = 100,
    ): ResponseBody

    @GET("1/clouddrive/share/sharepage/download")
    suspend fun download(
        @Query("pr") pr: String = "ucpro",
        @Query("fr") fr: String = "pc",
        @Query("pwd_id") pwdId: String,
        @Query("stoken") stoken: String,
        @Query("fid") fid: String,
    ): ResponseBody

    companion object {
        /** 提取码参数：?code=xxx / &pwd=xxx / #xxxx（v3.2.8 _share_key） */
        const val SHARE_URL_PATTERN = "quark\\.cn/s/([A-Za-z0-9]+)"
    }
}
