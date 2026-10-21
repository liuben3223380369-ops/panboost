package org.panboost.core.domain

/**
 * 分享链接解析出的可下载文件（v4.2.0：P0 分享链路回补）。
 *
 * 规格对齐 v3.2.8 引擎 resolve_quark 输出：直链 + 下载头
 * （夸克直链校验 Referer）。url 已含全部鉴权，enqueue 即下载。
 */
data class ShareFile(
    val name: String,
    val size: Long,
    val url: String,
)

/**
 * 分享链接解析仓库（v4.2.0）。
 *
 * 实现于 :core:network（夸克 sharepage 三接口）。需登录 Cookie
 * （__puus）——未登录时抛 IllegalStateException 提示先登录。
 */
interface ShareRepository {
    /**
     * 解析分享链接 → 可下载文件列表。
     *
     * @param shareUrl 分享链接（含或不含提取码参数）
     * @param passcode 提取码（链接内已含时传空）
     */
    suspend fun resolve(shareUrl: String, passcode: String): List<ShareFile>
}
