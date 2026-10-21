package org.panboost.core.network

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * POST /file/download 的请求体构造（fids JSON——单处定义，
 * 第 4 周）。
 */
class FidsBodyFactory {
    fun create(fid: String): RequestBody =
        """{"fids":["$fid"]}"""
            .toRequestBody("application/json".toMediaType())
}
