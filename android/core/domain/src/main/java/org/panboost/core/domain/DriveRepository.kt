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

    /**
     * 多直链解析（v6.3.0：aria2 multi-URI 同款）——夸克 download API
     * 每次调用返回不同 CDN 节点直链；解析 [count] 条去重。
     * 非夸克网盘默认返回单条（其 download API 无节点轮换语义）。
     */
    suspend fun getDownloadUrls(fid: String, count: Int): List<String>
}
