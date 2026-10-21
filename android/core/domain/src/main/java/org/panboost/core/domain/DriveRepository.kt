package org.panboost.core.domain

/**
 * 网盘仓库接口（第 4 周）。
 *
 * 实现于 :core:network（夸克 Web API + 登录 Cookie）。
 * 抛 IllegalStateException 等：调用方（ViewModel）映射为
 * 错误态展示。
 */
interface DriveRepository {
    suspend fun listFiles(pdirFid: String): List<DriveFile>
    suspend fun getDownloadUrl(fid: String): String
}
